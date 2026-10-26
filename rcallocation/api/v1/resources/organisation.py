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

"""Organisation endpoints, including proposals and vetting."""

import sqlalchemy as sa

from rcallocation.api.v1 import base
from rcallocation.api.v1 import filtering
from rcallocation.api.v1.schemas import organisation as schemas
from rcallocation import choices
from rcallocation.common import exceptions
from rcallocation.common import policies
from rcallocation.extensions import db
from rcallocation import manager
from rcallocation import models


Organisation = models.Organisation

blp = base.v1_blueprint(
    "organisations",
    __name__,
    "organisations",
    description="Research organisations (ROR backed and proposed)",
)


def _filter_search(query, lookup, value):
    pattern = filtering.like_pattern(value)
    escape = filtering.LIKE_ESCAPE
    return query.filter(
        sa.or_(
            Organisation.full_name.ilike(pattern, escape=escape),
            Organisation.short_name.ilike(pattern, escape=escape),
        )
    )


def _filter_exclude_all(query, lookup, value):
    if filtering.parse_bool(value):
        return query.filter(
            Organisation.full_name != choices.ORG_ALL_FULL_NAME
        )
    return query


def _filter_vetted(query, lookup, value):
    vetted = filtering.parse_bool(value)
    if vetted is None:
        return query
    condition = sa.or_(
        Organisation.ror_id != "", Organisation.vetted_by_id.is_not(None)
    )
    return query.filter(condition if vetted else sa.not_(condition))


class OrganisationFilterSet(filtering.FilterSet):
    filters = {
        "ror_id": filtering.F(Organisation.ror_id, ["exact", "iexact"]),
        "short_name": filtering.F(
            Organisation.short_name, ["exact", "iexact"]
        ),
        "full_name": filtering.F(
            Organisation.full_name, ["exact", "iexact", "icontains"]
        ),
        "country": filtering.F(
            Organisation.country, ["exact", "iexact", "in"]
        ),
        "url": filtering.F(Organisation.url, ["exact", "iexact"]),
        "enabled": filtering.F(Organisation.enabled),
        "proposed_by": filtering.F(Organisation.proposed_by),
    }
    methods = {
        "search": _filter_search,
        "exclude_all": _filter_exclude_all,
        "vetted": _filter_vetted,
    }


class OrganisationResource(base.Resource):
    POLICY_PREFIX = policies.ORGANISATION_PREFIX
    schema = schemas.OrganisationSchema()
    admin_schema = schemas.AdminOrganisationSchema()
    filterset = OrganisationFilterSet

    def get_schema(self):
        # Write admins (admins and approvers) see the vetting fields.
        if self.is_write_admin:
            return self.admin_schema
        return self.schema

    def query(self):
        return db.session.query(Organisation).order_by(
            Organisation.full_name, Organisation.id
        )

    def manager(self):
        return manager.Manager(self.context)


@blp.route("/")
class OrganisationList(OrganisationResource):
    def get(self):
        self.require("list")
        return self.paginate(self.filter(self.query()))

    def post(self):
        if self.is_write_admin:
            self.require("create")
            data = self.body(schemas.AdminOrganisationWriteSchema())
            organisation = self.manager().create_organisation(data)
        else:
            self.require("propose")
            data = self.body(schemas.ProposedOrganisationSchema())
            organisation = self.manager().propose_organisation(data)
        return self.dump(organisation), 201


@blp.route("/<int:ident>/")
class OrganisationItem(OrganisationResource):
    def get(self, ident):
        self.require("get")
        return self.dump(self.get_or_404(Organisation, ident))

    def _update(self, ident, partial):
        self.require("update")
        organisation = self.get_or_404(Organisation, ident)
        data = self.body(schemas.AdminOrganisationWriteSchema(partial=partial))
        organisation = self.manager().update_organisation(organisation, data)
        return self.dump(organisation)

    def put(self, ident):
        return self._update(ident, partial=False)

    def patch(self, ident):
        return self._update(ident, partial=True)

    def delete(self, ident):
        self.require("update")
        raise exceptions.MethodNotAllowed("DELETE")


class OrganisationVet(OrganisationResource):
    ENABLE = True

    def post(self, ident):
        self.require("vet")
        organisation = self.get_or_404(Organisation, ident)
        organisation = self.manager().vet_organisation(
            organisation, enable=self.ENABLE
        )
        return self.admin_schema.dump(organisation)


@blp.route("/<int:ident>/approve/")
class OrganisationApprove(OrganisationVet):
    ENABLE = True


@blp.route("/<int:ident>/decline/")
class OrganisationDecline(OrganisationVet):
    ENABLE = False
