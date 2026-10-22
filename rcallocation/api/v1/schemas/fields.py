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

"""Fields that serialise references as names or ids and resolve them back.

Error messages are those of the old DRF fields in nectar-dashboard's
``rcallocation/api/fields.py``.
"""

import marshmallow as ma
import sqlalchemy as sa

from rcallocation import choices
from rcallocation.extensions import db
from rcallocation import models


class LookupField(ma.fields.Field):
    """Serialise a model instance as a key and resolve the key on load."""

    def represent(self, obj):
        raise NotImplementedError

    def lookup(self, value):
        raise NotImplementedError

    def _serialize(self, value, attr, obj, **kwargs):
        if value is None:
            return None
        return self.represent(value)

    def _deserialize(self, value, attr, data, **kwargs):
        return self.lookup(value)


class ManyLookupField(ma.fields.Field):
    """A list of lookups with DRF's flat error list."""

    #: Marks the field as multi-valued for form parsing
    is_multiple = True

    def __init__(self, child, **kwargs):
        self.child = child
        super().__init__(**kwargs)

    def _serialize(self, value, attr, obj, **kwargs):
        if value is None:
            return []
        return [self.child.represent(item) for item in value]

    def _deserialize(self, value, attr, data, **kwargs):
        if isinstance(value, (str, bytes)) or not hasattr(value, "__iter__"):
            raise ma.ValidationError(
                f'Expected a list of items but got type "{type(value).__name__}".'
            )
        return [self.child.lookup(item) for item in value]


def _valid_site(name):
    if not name:
        return None
    site = db.session.query(models.Site).filter_by(name=name).first()
    if site is None:
        raise ma.ValidationError(f"Site '{name}' does not exist")
    return site


class AllocationHomeField(ma.fields.Field):
    """Compatibility field writing ``national`` and ``associated_site``.

    Dumps the derived ``allocation_home`` and loads a mapping of the
    columns to set, applied by the manager.
    """

    def _serialize(self, value, attr, obj, **kwargs):
        return value

    def _deserialize(self, value, attr, data, **kwargs):
        if value == choices.ALLOC_HOME_UNASSIGNED:
            return {'national': False, 'associated_site': None}
        if value == choices.ALLOC_HOME_NATIONAL:
            # Leave the existing 'associated_site' value alone.
            # We don't know what it *should* be.
            return {'national': True}
        site = _valid_site(value)
        if site is None:
            raise ma.ValidationError(
                "'allocation_home' must be a real site name"
            )
        return {'national': False, 'associated_site': site}


class AssociatedSiteField(LookupField):
    def represent(self, obj):
        return obj.name

    def lookup(self, value):
        return _valid_site(value)


class BundleField(LookupField):
    def represent(self, obj):
        return obj.name

    def lookup(self, value):
        bundle = db.session.query(models.Bundle).filter_by(name=value).first()
        if bundle is None:
            raise ma.ValidationError(f"Bundle '{value}' does not exist")
        return bundle


class ZoneField(LookupField):
    def represent(self, obj):
        return obj.name

    def lookup(self, value):
        zone = db.session.get(models.Zone, str(value))
        if zone is None:
            raise ma.ValidationError(f"Zone '{value}' does not exist")
        return zone


class UsageTypeField(LookupField):
    # We must allow creation, etc of an allocation request with
    # no usage types via the API.  Alternatives are impractical.

    def represent(self, obj):
        return obj.name

    def lookup(self, value):
        usage_type = (
            db.session.query(models.UsageType).filter_by(name=value).first()
        )
        if usage_type is None:
            raise ma.ValidationError(f"'{value}' is not a known UsageType")
        if not usage_type.enabled:
            raise ma.ValidationError(f"UsageType '{value}' is disabled")
        return usage_type


class OrganisationField(LookupField):
    """Serialize as a ROR id (if available) or the native id.
    Deserialization also allows an organisation's short or full name ...
    provided that the name supplied is unambiguous.
    """

    def represent(self, obj):
        return obj.ror_id or obj.id

    def lookup(self, value):
        Organisation = models.Organisation
        text = str(value)
        if isinstance(value, int) or text.isdigit():
            organisation = db.session.get(Organisation, int(text))
        else:
            organisation = (
                db.session.query(Organisation).filter_by(ror_id=text).first()
            )
            if organisation is None:
                matches = (
                    db.session.query(Organisation)
                    .filter(
                        sa.or_(
                            sa.func.lower(Organisation.full_name)
                            == text.lower(),
                            sa.func.lower(Organisation.short_name)
                            == text.lower(),
                        )
                    )
                    .limit(2)
                    .all()
                )
                if len(matches) > 1:
                    raise ma.ValidationError(
                        f"'{value}' is an ambiguous Organisation name"
                    )
                organisation = matches[0] if matches else None
        if organisation is None:
            raise ma.ValidationError(
                f"'{value}' doesn't match a known Organisation"
            )
        if not organisation.enabled:
            raise ma.ValidationError(f"Organisation '{value}' is disabled")
        return organisation


class PrimaryOrganisationField(OrganisationField):
    def lookup(self, value):
        organisation = super().lookup(value)
        if organisation.full_name == choices.ORG_ALL_FULL_NAME:
            raise ma.ValidationError(
                "'All Organisations' may not be used here"
            )
        return organisation


class NCRISFacilityField(LookupField):
    def represent(self, obj):
        return obj.short_name

    def lookup(self, value):
        Facility = models.NCRISFacility
        text = str(value).lower()
        facility = (
            db.session.query(Facility)
            .filter(
                sa.or_(
                    sa.func.lower(Facility.short_name) == text,
                    sa.func.lower(Facility.name) == text,
                )
            )
            .first()
        )
        if facility is None:
            raise ma.ValidationError(
                f"'{value}' is not a known NCRIS Facility"
            )
        return facility


class ARDCSupportField(LookupField):
    def represent(self, obj):
        return obj.short_name

    def lookup(self, value):
        Support = models.ARDCSupport
        text = str(value).lower()
        support = (
            db.session.query(Support)
            .filter(
                sa.or_(
                    sa.func.lower(Support.short_name) == text,
                    sa.func.lower(Support.name) == text,
                )
            )
            .first()
        )
        if support is None:
            raise ma.ValidationError(
                f"'{value}' is not a known ARDC project or program"
            )
        return support


class PrimaryKeyField(ma.fields.Field):
    """An integer primary key that must exist (DRF PrimaryKeyRelatedField).

    Dumps the related object's id and loads the object.
    """

    def __init__(self, model, **kwargs):
        self.model = model
        super().__init__(**kwargs)

    def _serialize(self, value, attr, obj, **kwargs):
        if value is None:
            return None
        if isinstance(value, int):
            return value
        return value.id

    def _deserialize(self, value, attr, data, **kwargs):
        try:
            ident = int(value)
        except (TypeError, ValueError):
            raise ma.ValidationError(
                f"Incorrect type. Expected pk value, received "
                f"{type(value).__name__}."
            )
        obj = db.session.get(self.model, ident)
        if obj is None:
            raise ma.ValidationError(
                f'Invalid pk "{value}" - object does not exist.'
            )
        return obj


class ManyPrimaryKeyField(ma.fields.Field):
    is_multiple = True

    def __init__(self, model, **kwargs):
        self.child = PrimaryKeyField(model)
        super().__init__(**kwargs)

    def _serialize(self, value, attr, obj, **kwargs):
        if value is None:
            return []
        return [self.child._serialize(item, attr, obj) for item in value]

    def _deserialize(self, value, attr, data, **kwargs):
        if isinstance(value, (str, bytes)) or not hasattr(value, "__iter__"):
            raise ma.ValidationError(
                f'Expected a list of items but got type "{type(value).__name__}".'
            )
        return [self.child._deserialize(item, attr, data) for item in value]
