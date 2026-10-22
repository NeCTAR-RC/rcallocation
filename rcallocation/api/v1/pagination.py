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

"""A port of Django REST Framework's LimitOffsetPagination.

The response envelope is ``{"count", "next", "previous", "results"}`` with
absolute ``next`` and ``previous`` links, which python-nectarallocationclient
follows. Query parameter handling (invalid or zero ``limit`` falls back to
the default, invalid ``offset`` to zero, parameters sorted in the links)
matches DRF so links are byte-for-byte what the old API produced.
"""

from urllib import parse

import flask
from oslo_config import cfg


CONF = cfg.CONF

LIMIT_PARAM = "limit"
OFFSET_PARAM = "offset"


def _positive_int(value, strict=False, cutoff=None):
    ret = int(value)
    if ret < 0 or (ret == 0 and strict):
        raise ValueError()
    if cutoff:
        return min(ret, cutoff)
    return ret


def get_limit(args, default_limit, max_limit):
    try:
        return _positive_int(args[LIMIT_PARAM], strict=True, cutoff=max_limit)
    except (KeyError, ValueError):
        return default_limit


def get_offset(args):
    try:
        return _positive_int(args[OFFSET_PARAM])
    except (KeyError, ValueError):
        return 0


def replace_query_param(url, key, val):
    (scheme, netloc, path, query, fragment) = parse.urlsplit(url)
    query_dict = parse.parse_qs(query, keep_blank_values=True)
    query_dict[key] = [val]
    query = parse.urlencode(sorted(query_dict.items()), doseq=True)
    return parse.urlunsplit((scheme, netloc, path, query, fragment))


def remove_query_param(url, key):
    (scheme, netloc, path, query, fragment) = parse.urlsplit(url)
    query_dict = parse.parse_qs(query, keep_blank_values=True)
    query_dict.pop(key, None)
    query = parse.urlencode(sorted(query_dict.items()), doseq=True)
    return parse.urlunsplit((scheme, netloc, path, query, fragment))


def next_link(url, limit, offset, count):
    if offset + limit >= count:
        return None
    url = replace_query_param(url, LIMIT_PARAM, limit)
    return replace_query_param(url, OFFSET_PARAM, offset + limit)


def previous_link(url, limit, offset):
    if offset <= 0:
        return None
    url = replace_query_param(url, LIMIT_PARAM, limit)
    if offset - limit <= 0:
        return remove_query_param(url, OFFSET_PARAM)
    return replace_query_param(url, OFFSET_PARAM, offset - limit)


def paginate(query, dump, args=None, url=None):
    """Paginate a SQLAlchemy query into the DRF envelope.

    :param query: an ordered SQLAlchemy query (or anything with ``count()``,
        ``offset()``, ``limit()`` and ``all()``)
    :param dump: callable turning the list of items into serialised data
    :param args: request args (defaults to the current request)
    :param url: the request URL to build links from
    """
    if args is None:
        args = flask.request.args
    if url is None:
        url = flask.request.url
    limit = get_limit(args, CONF.api.page_size, CONF.api.max_page_size)
    offset = get_offset(args)
    count = query.order_by(None).count()
    if count == 0 or offset > count:
        items = []
    else:
        items = query.offset(offset).limit(limit).all()
    return {
        "count": count,
        "next": next_link(url, limit, offset, count),
        "previous": previous_link(url, limit, offset),
        "results": dump(items),
    }
