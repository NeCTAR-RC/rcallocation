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

"""Helpers creating model instances for tests.

These replace the factory_boy factories of the dashboard's test suite.
``create_allocation`` reproduces ``AllocationFactory.create`` including
its quota rows so the ported tests keep their expectations.
"""

import random
import string

from rcallocation import choices
from rcallocation.extensions import db
from rcallocation import forcodes
from rcallocation import models


ALL_SITES = ['uom', 'qcif', 'monash', 'ardc']


def fuzzy_text(length=12):
    return ''.join(random.choices(string.ascii_letters, k=length))


def fuzzy_int(low=1, high=100000):
    return random.randint(low, high)


def fuzzy_for_code():
    return random.choice(list(forcodes.for_codes()))


def get(model, **kwargs):
    return db.session.query(model).filter_by(**kwargs).one()


def first(model, **kwargs):
    return db.session.query(model).filter_by(**kwargs).first()


def active_usage_types():
    return (
        db.session.query(models.UsageType)
        .filter_by(enabled=True)
        .order_by(models.UsageType.id)
        .all()
    )


def _add(obj):
    db.session.add(obj)
    db.session.commit()
    return obj


def create_zone(name, display_name=None, enabled=True):
    zone = first(models.Zone, name=name)
    if zone is None:
        zone = _add(
            models.Zone(
                name=name, display_name=display_name or name, enabled=enabled
            )
        )
    return zone


def create_service_type(catalog_name, zones=(), **kwargs):
    st = first(models.ServiceType, catalog_name=catalog_name)
    if st is None:
        kwargs.setdefault("name", fuzzy_text())
        kwargs.setdefault("description", fuzzy_text())
        st = models.ServiceType(catalog_name=catalog_name, **kwargs)
        db.session.add(st)
    for zone in zones:
        if zone not in st.zones:
            st.zones.append(zone)
    db.session.commit()
    return st


def create_resource(quota_name, service_type, **kwargs):
    resource = first(
        models.Resource,
        quota_name=quota_name,
        service_type_id=service_type.catalog_name,
    )
    if resource is None:
        kwargs.setdefault("name", fuzzy_text())
        kwargs.setdefault("unit", fuzzy_text())
        resource = _add(
            models.Resource(
                quota_name=quota_name, service_type=service_type, **kwargs
            )
        )
    return resource


def create_bundle(name, zone, su_per_year, **kwargs):
    kwargs.setdefault("description", fuzzy_text())
    kwargs.setdefault("order", fuzzy_int())
    return _add(
        models.Bundle(name=name, zone=zone, su_per_year=su_per_year, **kwargs)
    )


def create_bundle_quota(bundle, resource, quota=None):
    return _add(
        models.BundleQuota(
            bundle=bundle,
            resource=resource,
            quota=fuzzy_int() if quota is None else quota,
        )
    )


def create_site(name, display_name=None, enabled=True):
    site = first(models.Site, name=name)
    if site is None:
        site = _add(
            models.Site(
                name=name, display_name=display_name or name, enabled=enabled
            )
        )
    return site


def create_approver(username, display_name, sites=()):
    approver = _add(
        models.Approver(username=username, display_name=display_name)
    )
    for site in sites:
        approver.sites.append(site)
    db.session.commit()
    return approver


def create_organisation(**kwargs):
    kwargs.setdefault("short_name", fuzzy_text(8))
    kwargs.setdefault("full_name", fuzzy_text())
    kwargs.setdefault("enabled", True)
    kwargs.setdefault("ror_id", "")
    kwargs.setdefault("proposed_by", "")
    kwargs.setdefault("country", "AU")
    return _add(models.Organisation(**kwargs))


def create_usage_type(name, enabled=True):
    usage_type = first(models.UsageType, name=name)
    if usage_type is None:
        usage_type = _add(models.UsageType(name=name, enabled=enabled))
    return usage_type


def create_ncris_facility(name, short_name):
    return _add(models.NCRISFacility(name=name, short_name=short_name))


def create_ardc_support(name, short_name, **kwargs):
    return _add(models.ARDCSupport(name=name, short_name=short_name, **kwargs))


def create_quota_group(allocation, service_type, zone):
    group = models.QuotaGroup(
        allocation_id=allocation.id,
        zone_id=zone.name,
        service_type_id=service_type.catalog_name,
    )
    db.session.add(group)
    db.session.commit()
    db.session.expire(allocation, ["quota_groups"])
    return group


def create_quota(group, resource, quota=0, requested_quota=None):
    quota_row = models.Quota(
        group_id=group.id,
        resource_id=resource.id,
        quota=quota,
        requested_quota=(
            fuzzy_int() if requested_quota is None else requested_quota
        ),
    )
    db.session.add(quota_row)
    db.session.commit()
    db.session.expire(group, ["quotas"])
    return quota_row


def create_investigator(allocation, primary_organisation=None, **kwargs):
    kwargs.setdefault("title", "Prof.")
    kwargs.setdefault("given_name", "MeRC")
    kwargs.setdefault("surname", "Monash")
    kwargs.setdefault("email", "merc.monash@monash.edu")
    kwargs.setdefault("additional_researchers", "None")
    ci = models.ChiefInvestigator(
        allocation_id=allocation.id,
        primary_organisation=primary_organisation,
        **kwargs,
    )
    db.session.add(ci)
    db.session.commit()
    db.session.expire(allocation, ["investigators"])
    return ci


def create_grant(allocation, **kwargs):
    kwargs.setdefault(
        "grant_type", random.choice([c for c, _ in choices.GRANT_TYPES])
    )
    kwargs.setdefault(
        "grant_subtype",
        random.choice([c for c, _ in choices.GRANT_SUBTYPES]),
    )
    kwargs.setdefault("funding_body_scheme", "ARC funding scheme")
    kwargs.setdefault("grant_id", "arc-grant-0001")
    kwargs.setdefault("first_year_funded", 2015)
    kwargs.setdefault("last_year_funded", 2017)
    kwargs.setdefault("total_funding", 20000)
    grant = models.Grant(allocation_id=allocation.id, **kwargs)
    db.session.add(grant)
    db.session.commit()
    db.session.expire(allocation, ["grants"])
    return grant


def create_publication(allocation, **kwargs):
    kwargs.setdefault("publication", "publication testing")
    kwargs.setdefault("output_type", choices.NON_PEER_REVIEWED_PAPER)
    pub = models.Publication(allocation_id=allocation.id, **kwargs)
    db.session.add(pub)
    db.session.commit()
    db.session.expire(allocation, ["publications"])
    return pub


def create_allocation(
    create_quotas=True,
    only_requestable=True,
    quota_value=0,
    modified_time=None,
    submit_date=None,
    usage_types=None,
    ncris_facilities=(),
    ardc_support=(),
    supported_organisations=('Monash',),
    **kwargs,
):
    """Create an allocation request with the factory's defaults.

    Relationship keywords take names: ``usage_types`` (None means every
    enabled usage type), ``supported_organisations`` (short names),
    ``ncris_facilities`` and ``ardc_support`` (short names). With
    ``create_quotas`` the standard quota rows are created at
    ``quota_value`` with a random requested quota.
    """
    kwargs.setdefault("created_by", fuzzy_text())
    kwargs.setdefault("contact_email", "test@example.com")
    kwargs.setdefault("use_case", fuzzy_text())
    kwargs.setdefault("usage_patterns", fuzzy_text())
    kwargs.setdefault("geographic_requirements", fuzzy_text())
    kwargs.setdefault("project_description", fuzzy_text())
    kwargs.setdefault("field_of_research_1", fuzzy_for_code())
    kwargs.setdefault("field_of_research_2", fuzzy_for_code())
    kwargs.setdefault("field_of_research_3", fuzzy_for_code())
    kwargs.setdefault("for_percentage_1", 50)
    kwargs.setdefault("for_percentage_2", 40)
    kwargs.setdefault("for_percentage_3", 10)
    if "associated_site" not in kwargs and "associated_site_id" not in kwargs:
        kwargs["associated_site"] = get(
            models.Site, name=random.choice(ALL_SITES)
        )
    if isinstance(kwargs.get("bundle"), str):
        kwargs["bundle"] = get(models.Bundle, name=kwargs["bundle"])

    allocation = models.AllocationRequest(**kwargs)
    if modified_time is not None:
        allocation.modified_time = modified_time
    if submit_date is not None:
        allocation.submit_date = submit_date
    db.session.add(allocation)
    db.session.flush()

    if usage_types is None:
        allocation.usage_types = active_usage_types()
    else:
        allocation.usage_types = [
            get(models.UsageType, name=name) for name in usage_types
        ]
    allocation.supported_organisations = [
        get(models.Organisation, short_name=name)
        for name in supported_organisations
    ]
    allocation.ncris_facilities = [
        get(models.NCRISFacility, short_name=name) for name in ncris_facilities
    ]
    allocation.ardc_support = [
        get(models.ARDCSupport, short_name=name) for name in ardc_support
    ]
    db.session.commit()

    if create_quotas:
        monash = get(models.Zone, name='monash')
        melbourne = get(models.Zone, name='melbourne')
        nectar = get(models.Zone, name='nectar')

        volume_st = get(models.ServiceType, catalog_name='volume')
        object_st = get(models.ServiceType, catalog_name='object')
        compute_st = get(models.ServiceType, catalog_name='compute')
        network_st = get(models.ServiceType, catalog_name='network')
        rating_st = get(models.ServiceType, catalog_name='rating')

        def resource(service_type, quota_name):
            return get(
                models.Resource,
                quota_name=quota_name,
                service_type_id=service_type.catalog_name,
            )

        group_volume_monash = create_quota_group(allocation, volume_st, monash)
        group_volume_melbourne = create_quota_group(
            allocation, volume_st, melbourne
        )
        group_object = create_quota_group(allocation, object_st, nectar)
        group_compute = create_quota_group(allocation, compute_st, nectar)
        group_rating = create_quota_group(allocation, rating_st, nectar)
        group_network = create_quota_group(allocation, network_st, nectar)
        create_quota(group_object, resource(object_st, 'object'), quota_value)
        create_quota(
            group_volume_monash, resource(volume_st, 'gigabytes'), quota_value
        )
        create_quota(
            group_volume_melbourne,
            resource(volume_st, 'gigabytes'),
            quota_value,
        )
        create_quota(group_compute, resource(compute_st, 'cores'), quota_value)
        create_quota(
            group_compute, resource(compute_st, 'instances'), quota_value
        )
        if not only_requestable:
            create_quota(
                group_compute, resource(compute_st, 'ram'), quota_value
            )
        create_quota(group_rating, resource(rating_st, 'budget'), quota_value)
        create_quota(
            group_network, resource(network_st, 'router'), quota_value
        )
        create_quota(
            group_network, resource(network_st, 'network'), quota_value
        )
        create_quota(
            group_network, resource(network_st, 'loadbalancer'), quota_value
        )
        create_quota(
            group_network, resource(network_st, 'floatingip'), quota_value
        )

    db.session.expire(allocation)
    return allocation


def refresh(obj):
    """Reload an object from the database."""
    db.session.expire(obj)
    return db.session.get(type(obj), obj.id)


def history_count(allocation):
    return (
        db.session.query(models.AllocationRequest)
        .filter_by(parent_request_id=allocation.id)
        .count()
    )
