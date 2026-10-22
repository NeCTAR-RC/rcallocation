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

"""Projects a caller is considered a member of.

Ownership of an allocation is extended from the token's own project to
every project where the caller holds the tenantmanager role, so the
dashboard's "my allocations" view can list them with one call. Role
assignments are read through the service account and cached briefly.
"""

import threading

import cachetools
from keystoneclient.v3 import client as ks_client
from oslo_config import cfg
from oslo_log import log as logging

from rcallocation.common import keystone


CONF = cfg.CONF
LOG = logging.getLogger(__name__)

_lock = threading.Lock()
_cache = None
_role_id = None


def _get_cache():
    global _cache
    if _cache is None:
        _cache = cachetools.TTLCache(
            maxsize=10000, ttl=CONF.allocations.role_assignment_cache_seconds
        )
    return _cache


def reset():
    global _cache, _role_id
    _cache = None
    _role_id = None


def _keystone():
    session = keystone.KeystoneSession().get_session()
    return ks_client.Client(session=session)


def _tenant_manager_role_id(client):
    global _role_id
    if _role_id is None:
        roles = client.roles.list(name=CONF.allocations.tenant_manager_role)
        if not roles:
            LOG.warning(
                "Role %s not found in keystone",
                CONF.allocations.tenant_manager_role,
            )
            return None
        _role_id = roles[0].id
    return _role_id


def managed_project_ids(user_id):
    """Return the ids of projects where ``user_id`` holds tenantmanager."""
    if not user_id or CONF.auth_strategy != "keystone":
        return set()
    cache = _get_cache()
    with _lock:
        if user_id in cache:
            return cache[user_id]
    try:
        client = _keystone()
        role_id = _tenant_manager_role_id(client)
        if role_id is None:
            result = set()
        else:
            assignments = client.role_assignments.list(
                user=user_id, role=role_id
            )
            result = {
                a.scope["project"]["id"]
                for a in assignments
                if "project" in getattr(a, "scope", {})
            }
    except Exception:
        LOG.exception(
            "Could not look up tenantmanager projects for %s", user_id
        )
        return set()
    with _lock:
        cache[user_id] = result
    return result


def caller_project_ids(context):
    ids = set()
    if context.project_id:
        ids.add(context.project_id)
    ids |= managed_project_ids(context.user_id)
    return ids
