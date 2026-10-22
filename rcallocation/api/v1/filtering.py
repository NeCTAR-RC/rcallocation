#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""A small emulation of django-filter's query parameter lookups.

Consumers filter with ``?field=value`` and ``?field__lookup=value`` and
expect unknown parameters to be ignored, empty values to be skipped and
booleans to accept ``true``/``True``/``false``/``False``. Each resource
declares an allowlist of filterable columns and the lookups permitted on
each; anything else is silently dropped, as django-filter did.
"""

import datetime
import decimal

import sqlalchemy as sa

from rcallocation.common import exceptions


LOOKUPS = {
    "exact",
    "iexact",
    "in",
    "isnull",
    "contains",
    "icontains",
    "startswith",
    "istartswith",
    "endswith",
    "iendswith",
    "regex",
    "lt",
    "lte",
    "gt",
    "gte",
    "year",
    "date",
}

_BOOLEANS = {
    "true": True,
    "false": False,
    "1": True,
    "0": False,
}


def parse_bool(value):
    """Return True/False for a boolean query value, or None if unparsable."""
    if isinstance(value, bool):
        return value
    return _BOOLEANS.get(str(value).strip().lower())


def _like_escape(value):
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _coerce_value(column, value, lookup):
    """Coerce a query string value to the column's Python type."""
    if lookup == "year":
        python_type = int
        message = "Enter a whole number."
    elif lookup == "date":
        python_type = datetime.date
        message = "Enter a valid date."
    else:
        try:
            python_type = column.type.python_type
        except NotImplementedError:
            return value
        message = "Enter a valid value."
    try:
        if python_type is bool:
            parsed = parse_bool(value)
            if parsed is None:
                raise ValueError(value)
            return parsed
        if python_type is int:
            return int(value)
        if python_type is float:
            return float(value)
        if python_type is decimal.Decimal:
            return decimal.Decimal(value)
        if python_type is datetime.datetime:
            if isinstance(value, datetime.datetime):
                return value
            parsed = datetime.datetime.fromisoformat(value)
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone(datetime.timezone.utc).replace(
                    tzinfo=None
                )
            return parsed
        if python_type is datetime.date:
            if isinstance(value, datetime.date):
                return value
            return datetime.date.fromisoformat(value)
    except (TypeError, ValueError, decimal.InvalidOperation):
        raise exceptions.ValidationError({"__param__": [message]})
    return value


def _condition(column, lookup, value):
    if lookup == "exact":
        return column == value
    if lookup == "iexact":
        return sa.func.lower(column) == str(value).lower()
    if lookup == "in":
        return column.in_(value)
    if lookup == "isnull":
        return column.is_(None) if value else column.is_not(None)
    if lookup == "contains":
        return column.like(f"%{_like_escape(value)}%", escape="\\")
    if lookup == "icontains":
        return column.ilike(f"%{_like_escape(value)}%", escape="\\")
    if lookup == "startswith":
        return column.like(f"{_like_escape(value)}%", escape="\\")
    if lookup == "istartswith":
        return column.ilike(f"{_like_escape(value)}%", escape="\\")
    if lookup == "endswith":
        return column.like(f"%{_like_escape(value)}", escape="\\")
    if lookup == "iendswith":
        return column.ilike(f"%{_like_escape(value)}", escape="\\")
    if lookup == "regex":
        return column.regexp_match(value)
    if lookup == "lt":
        return column < value
    if lookup == "lte":
        return column <= value
    if lookup == "gt":
        return column > value
    if lookup == "gte":
        return column >= value
    if lookup == "year":
        return sa.extract("year", column) == value
    if lookup == "date":
        return sa.func.date(column) == value
    raise ValueError(lookup)


class F:
    """A filterable column.

    :param column: the SQLAlchemy column (or hybrid) to filter on
    :param lookups: the lookups accepted for this parameter
    :param joins: relationship attributes to join before filtering, for
        columns that live on a related table
    :param coerce: optional callable applied to each raw value before the
        type coercion (e.g. to map a name onto an id)
    """

    def __init__(self, column, lookups=("exact",), joins=(), coerce=None):
        self.column = column
        self.lookups = set(lookups)
        self.joins = tuple(joins)
        self.coerce = coerce

    def apply(self, query, lookup, values, joined):
        for join in self.joins:
            key = str(join)
            if key not in joined:
                query = query.join(join)
                joined.add(key)
        if lookup == "in":
            raw = []
            for value in values:
                raw.extend(v for v in str(value).split(",") if v != "")
            if not raw:
                return query
            if self.coerce:
                raw = [self.coerce(v) for v in raw]
            value = [_coerce_value(self.column, v, lookup) for v in raw]
        else:
            value = values[-1]
            if value == "" or value is None:
                return query
            if lookup == "isnull":
                value = parse_bool(value)
                if value is None:
                    return query
            else:
                if self.coerce:
                    value = self.coerce(value)
                try:
                    python_type = self.column.type.python_type
                except NotImplementedError:
                    python_type = None
                if python_type is bool and lookup == "exact":
                    value = parse_bool(value)
                    if value is None:
                        return query
                else:
                    value = _coerce_value(self.column, value, lookup)
        return query.filter(_condition(self.column, lookup, value))


class FilterSet:
    """Declarative set of filters for a list endpoint.

    Subclasses set ``filters`` (parameter base name to :class:`F`) and
    optionally ``methods`` (parameter base name to a callable
    ``fn(query, lookup, value)`` for filters that need custom logic).
    """

    filters = {}
    methods = {}

    @classmethod
    def split(cls, param):
        base, sep, lookup = param.rpartition("__")
        if (
            sep
            and lookup in LOOKUPS
            and (base in cls.filters or base in cls.methods)
        ):
            return base, lookup
        return param, "exact"

    @classmethod
    def apply(cls, query, args):
        joined = set()
        for param in args.keys():
            base, lookup = cls.split(param)
            values = args.getlist(param)
            if base in cls.methods:
                value = values[-1]
                if value == "" or value is None:
                    continue
                query = cls.methods[base](query, lookup, value)
                continue
            spec = cls.filters.get(base)
            if spec is None or lookup not in spec.lookups:
                continue
            try:
                query = spec.apply(query, lookup, values, joined)
            except exceptions.ValidationError as exc:
                messages = exc.messages.get("__param__", ["Invalid value."])
                raise exceptions.ValidationError({param: messages})
        return query
