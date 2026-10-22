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

"""Chief investigators, publications and grants of allocation requests.

Readable by their owner (the allocation contact) and read admins, and
writable while the allocation is pending.
"""

from rcallocation.api.v1 import base
from rcallocation.api.v1 import filtering
from rcallocation.api.v1.schemas import related as schemas
from rcallocation import choices
from rcallocation.common import exceptions
from rcallocation.common import policies
from rcallocation.extensions import db
from rcallocation import manager
from rcallocation import models


Allocation = models.AllocationRequest


class RelatedResource(base.Resource):
    model = None

    def visible_query(self):
        query = db.session.query(self.model)
        if self.authorize("list:all", do_raise=False):
            return query
        return query.filter(
            self.model.allocation.has(
                Allocation.contact_email == self.context.user_name
            )
        )

    def get_visible(self, ident):
        return self.get_or_404(self.model, ident, query=self.visible_query())

    def require_modifiable(self, obj):
        self.require_object("update", obj)
        allocation = obj.allocation
        if allocation.is_history() or (
            allocation.status not in choices.PENDING_STATUSES
        ):
            raise exceptions.PermissionDenied(
                "Permission denied or allocation in wrong state."
            )

    def _list(self):
        self.require("list")
        query = self.filter(self.visible_query()).order_by(self.model.id)
        return self.paginate(query)

    def _create(self):
        self.require("create")
        data = self.body(self.schema)
        obj = manager.Manager(self.context).create_related(
            self.model, data, is_write_admin=self.is_write_admin
        )
        return self.dump(obj), 201

    def _get(self, ident):
        self.require("get")
        return self.dump(self.get_visible(ident))

    def _update(self, ident, partial):
        self.require_authenticated()
        obj = self.get_visible(ident)
        self.require_modifiable(obj)
        data = self.body(type(self.schema)(partial=partial))
        obj = manager.Manager(self.context).update_related(
            obj, data, is_write_admin=self.is_write_admin
        )
        return self.dump(obj)

    def _delete(self, ident):
        self.require_authenticated()
        obj = self.get_visible(ident)
        self.require_modifiable(obj)
        manager.Manager(self.context).delete_related(obj)
        return "", 204


class RelatedList(RelatedResource):
    def get(self):
        return self._list()

    def post(self):
        return self._create()


class RelatedItem(RelatedResource):
    def get(self, ident):
        return self._get(ident)

    def put(self, ident):
        return self._update(ident, partial=False)

    def patch(self, ident):
        return self._update(ident, partial=True)

    def delete(self, ident):
        return self._delete(ident)


# -- chief investigators ------------------------------------------------------

investigators_blp = base.v1_blueprint(
    "chiefinvestigators",
    __name__,
    "chiefinvestigators",
    description="Chief investigators of allocation requests",
)


class InvestigatorFilterSet(filtering.FilterSet):
    filters = {
        "allocation": filtering.F(models.ChiefInvestigator.allocation_id),
    }


class InvestigatorBase(RelatedResource):
    POLICY_PREFIX = policies.CHIEF_INVESTIGATOR_PREFIX
    model = models.ChiefInvestigator
    schema = schemas.ChiefInvestigatorSchema()
    filterset = InvestigatorFilterSet


@investigators_blp.route("/")
class InvestigatorList(InvestigatorBase, RelatedList):
    pass


@investigators_blp.route("/<int:ident>/")
class InvestigatorItem(InvestigatorBase, RelatedItem):
    pass


# -- publications ---------------------------------------------------------------

publications_blp = base.v1_blueprint(
    "publications",
    __name__,
    "publications",
    description="Research outputs of allocation requests",
)


class PublicationFilterSet(filtering.FilterSet):
    filters = {
        "allocation": filtering.F(models.Publication.allocation_id),
    }


class PublicationBase(RelatedResource):
    POLICY_PREFIX = policies.PUBLICATION_PREFIX
    model = models.Publication
    schema = schemas.PublicationSchema()
    filterset = PublicationFilterSet


@publications_blp.route("/")
class PublicationList(PublicationBase, RelatedList):
    pass


@publications_blp.route("/<int:ident>/")
class PublicationItem(PublicationBase, RelatedItem):
    pass


# -- grants -----------------------------------------------------------------------

grants_blp = base.v1_blueprint(
    "grants", __name__, "grants", description="Grants of allocation requests"
)


class GrantFilterSet(filtering.FilterSet):
    filters = {
        "allocation": filtering.F(models.Grant.allocation_id),
    }


class GrantBase(RelatedResource):
    POLICY_PREFIX = policies.GRANT_PREFIX
    model = models.Grant
    schema = schemas.GrantSchema()
    filterset = GrantFilterSet


@grants_blp.route("/")
class GrantList(GrantBase, RelatedList):
    pass


@grants_blp.route("/<int:ident>/")
class GrantItem(GrantBase, RelatedItem):
    pass


BLUEPRINTS = [investigators_blp, publications_blp, grants_blp]
