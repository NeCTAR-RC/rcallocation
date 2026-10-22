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

import flask
from flask import views
import flask_smorest
from oslo_log import log as logging
from oslo_policy import policy as oslo_policy

from rcallocation.api.v1 import pagination
from rcallocation.api.v1 import parsing
from rcallocation.common import context
from rcallocation.common import exceptions
from rcallocation.common import keystone
from rcallocation.common import policies
from rcallocation.extensions import db
from rcallocation import policy


LOG = logging.getLogger(__name__)

ANONYMOUS = "anonymous"
ADMIN = "admin"
USER = "user"


PARSER = parsing.Parser()


class Blueprint(flask_smorest.Blueprint):
    ARGUMENTS_PARSER = PARSER


def v1_blueprint(name, import_name, path, **kwargs):
    return Blueprint(name, import_name, url_prefix=f"/v1/{path}", **kwargs)


class Resource(views.MethodView):
    """Base class for API views.

    Provides the request context, policy enforcement, DRF-compatible
    pagination and filtering, and serializer selection by caller kind.
    """

    #: ``rcallocation:<resource>:%s``; ``authorize("list")`` fills the
    #: action in.
    POLICY_PREFIX = "rcallocation:%s"

    #: Dump schemas by caller kind. ``schema`` is used when the others
    #: are not set.
    schema = None
    admin_schema = None
    public_schema = None

    #: FilterSet classes; ``public_filterset`` applies to anonymous callers
    #: when set.
    filterset = None
    public_filterset = None

    @property
    def context(self):
        ctx = flask.request.environ.get(keystone.REQUEST_CONTEXT_ENV)
        if ctx is None:
            ctx = context.anonymous()
        return ctx

    # -- policy -----------------------------------------------------------

    def rule_name(self, action):
        if "%s" in self.POLICY_PREFIX:
            return self.POLICY_PREFIX % action
        return action

    def authorize(self, action, target=None, do_raise=True):
        """Enforce ``rcallocation:<resource>:<action>`` for the caller.

        Returns True/False when ``do_raise`` is false, otherwise raises
        ``PolicyNotAuthorized``.
        """
        rule = self.rule_name(action)
        target = target or {}
        try:
            return policy.get_enforcer().authorize(
                rule, target, self.context, do_raise=do_raise
            )
        except oslo_policy.InvalidScope as exc:
            if do_raise:
                raise oslo_policy.PolicyNotAuthorized(
                    rule, target, self.context.to_policy_values()
                ) from exc
            return False

    def require(self, action, target=None):
        """Enforce a rule, answering 403 when it fails."""
        try:
            self.authorize(action, target)
        except oslo_policy.PolicyNotAuthorized:
            raise exceptions.PermissionDenied()

    def authorize_rule(self, name):
        """Check a base rule (``admin``, ``read_admin`` ...) by name."""
        return policy.get_enforcer().authorize(
            name, {}, self.context, do_raise=False
        )

    def require_authenticated(self):
        """Answer 403 for anonymous callers (as the old API did)."""
        if self.context.is_anonymous:
            raise exceptions.PermissionDenied()

    def body(self, schema):
        """Parse the request body (JSON or form) with ``schema``."""
        return PARSER.parse(schema, location="json")

    @property
    def is_write_admin(self):
        return self._cached(
            "is_write_admin",
            lambda: self.authorize_rule(policies.WRITE_ADMIN),
        )

    @property
    def is_admin(self):
        return self._cached(
            "is_admin", lambda: self.authorize_rule(policies.ADMIN)
        )

    @property
    def is_read_admin(self):
        return self._cached(
            "is_read_admin", lambda: self.authorize_rule(policies.READ_ADMIN)
        )

    @property
    def is_approver(self):
        return self._cached(
            "is_approver", lambda: self.authorize_rule(policies.APPROVER)
        )

    @property
    def caller_kind(self):
        def compute():
            if self.context.is_anonymous:
                return ANONYMOUS
            if self.is_read_admin:
                return ADMIN
            return USER

        return self._cached("caller_kind", compute)

    def _cached(self, key, compute):
        # Flask builds a new view instance per request, so caching on the
        # instance scopes the value to this request.
        cache = self.__dict__.setdefault("_request_cache", {})
        if key not in cache:
            cache[key] = compute()
        return cache[key]

    # -- serialisation ---------------------------------------------------

    def get_schema(self):
        kind = self.caller_kind
        if kind == ADMIN and self.admin_schema is not None:
            return self.admin_schema
        if kind == ANONYMOUS and self.public_schema is not None:
            return self.public_schema
        return self.schema

    def dump(self, obj, schema=None, many=False):
        schema = schema or self.get_schema()
        return schema.dump(obj, many=many)

    # -- querying ----------------------------------------------------------

    def get_filterset(self):
        if self.caller_kind == ANONYMOUS and self.public_filterset:
            return self.public_filterset
        return self.filterset

    def filter(self, query, filterset=None):
        filterset = filterset or self.get_filterset()
        if filterset is None:
            return query
        return filterset.apply(query, flask.request.args)

    def paginate(self, query, schema=None):
        schema = schema or self.get_schema()
        return pagination.paginate(
            query, lambda items: schema.dump(items, many=True)
        )

    def get_or_404(self, model, ident, query=None):
        if query is not None:
            obj = query.filter(
                getattr(model, model.__mapper__.primary_key[0].name) == ident
            ).first()
        else:
            obj = db.session.get(model, ident)
        if obj is None:
            raise exceptions.NotFound()
        return obj

    # -- ownership ---------------------------------------------------------

    def caller_project_ids(self):
        """Projects the caller is considered a member of.

        The token's own project plus any project where the caller holds
        the tenantmanager role (looked up through keystone and cached).
        """

        def compute():
            from rcallocation.common import projects

            return projects.caller_project_ids(self.context)

        return self._cached("project_ids", compute)

    def is_owner(self, allocation):
        if self.context.is_anonymous or allocation is None:
            return False
        if allocation.contact_email and (
            allocation.contact_email == self.context.user_name
        ):
            return True
        return bool(
            allocation.project_id
            and allocation.project_id in self.caller_project_ids()
        )

    def policy_target(self, obj):
        """Build the policy target dict for an object.

        Walks ``obj.allocation`` or ``obj.group.allocation`` so quotas and
        related records resolve to their allocation, as the old DRF
        permission classes did.
        """
        allocation = allocation_of(obj)
        if allocation is None:
            return {}
        return {
            "contact_email": allocation.contact_email,
            "project_id": allocation.project_id,
            "status": allocation.status,
            "is_owner": self.is_owner(allocation),
        }

    def require_object(self, action, obj):
        self.require(action, self.policy_target(obj))


def allocation_of(obj):
    if obj is None:
        return None
    if hasattr(obj, "contact_email"):
        return obj
    if hasattr(obj, "allocation"):
        return obj.allocation
    if hasattr(obj, "group"):
        return obj.group.allocation
    return None


def not_allowed(method):
    """Shared body for routes that exist only to answer 405."""
    raise exceptions.MethodNotAllowed(method)
