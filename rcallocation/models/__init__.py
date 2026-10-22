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

"""SQLAlchemy models. Importing this package registers every table."""

from rcallocation.models.allocation import AllocationRequest
from rcallocation.models.allocation import ChiefInvestigator
from rcallocation.models.allocation import Grant
from rcallocation.models.allocation import Publication
from rcallocation.models.allocation import Quota
from rcallocation.models.allocation import QuotaGroup
from rcallocation.models.base import allocation_ardc_support
from rcallocation.models.base import allocation_ncris_facility
from rcallocation.models.base import allocation_organisation
from rcallocation.models.base import allocation_usage_type
from rcallocation.models.base import approver_site
from rcallocation.models.base import organisation_precedes
from rcallocation.models.base import service_type_zone
from rcallocation.models.base import utcnow
from rcallocation.models.organisation import Organisation
from rcallocation.models.reference import Approver
from rcallocation.models.reference import ARDCSupport
from rcallocation.models.reference import Bundle
from rcallocation.models.reference import BundleQuota
from rcallocation.models.reference import NCRISFacility
from rcallocation.models.reference import Resource
from rcallocation.models.reference import ServiceType
from rcallocation.models.reference import Site
from rcallocation.models.reference import UsageType
from rcallocation.models.reference import Zone

__all__ = [
    "AllocationRequest",
    "ChiefInvestigator",
    "Grant",
    "Publication",
    "Quota",
    "QuotaGroup",
    "Organisation",
    "Approver",
    "ARDCSupport",
    "Bundle",
    "BundleQuota",
    "NCRISFacility",
    "Resource",
    "ServiceType",
    "Site",
    "UsageType",
    "Zone",
    "allocation_ardc_support",
    "allocation_ncris_facility",
    "allocation_organisation",
    "allocation_usage_type",
    "approver_site",
    "organisation_precedes",
    "service_type_zone",
    "utcnow",
]
