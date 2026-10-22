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

"""Fields of Research code lists and the allocation tree aggregation.

Served by ``/v1/for-codes*/`` and ``/v1/for-tree*/``. The tree groups the
compute and budget quotas of active allocations by FoR code, split by the
allocation's FoR percentages. Results are cached for a day, as the old
API did with ``cache_page``.
"""

import threading

import cachetools

from rcallocation import choices
from rcallocation.extensions import db
from rcallocation import forcodes
from rcallocation import models
from rcallocation import utils


CACHE_TTL = 86400

_lock = threading.Lock()
_cache = cachetools.TTLCache(maxsize=16, ttl=CACHE_TTL)


def reset():
    with _lock:
        _cache.clear()


def cached(key, compute):
    with _lock:
        if key in _cache:
            return _cache[key]
    value = compute()
    with _lock:
        _cache[key] = value
    return value


def for_codes_2008():
    return forcodes.FOR_CODES_2008


def for_codes_2020():
    return forcodes.FOR_CODES_2020


def for_codes_all():
    return forcodes.FOR_CODES_ALL


def for_tree(for_code_map):
    return restructure_allocations_tree(for_code_map)


def _resource_id(codename):
    resource = models.Resource.by_codename(codename)
    return resource.id if resource else None


def partition_active_allocations(for_code_map):
    allocation_summaries = list()
    Allocation = models.AllocationRequest
    active_allocations = (
        db.session.query(Allocation)
        .filter(
            Allocation.status.in_([choices.APPROVED, choices.UPDATE_PENDING]),
            Allocation.parent_request_id.is_(None),
        )
        .all()
    )
    instances_id = _resource_id('compute.instances')
    cores_id = _resource_id('compute.cores')

    codes = for_code_map.keys()
    for active_allocation in active_allocations:
        for code in (
            active_allocation.field_of_research_1,
            active_allocation.field_of_research_2,
            active_allocation.field_of_research_3,
        ):
            if code in codes:
                allocation_summaries.append(
                    summary(active_allocation, code, instances_id, cores_id)
                )
    return allocation_summaries


def organise_allocations_tree(for_code_map):
    allocations = partition_active_allocations(for_code_map)
    allocations_tree = dict()

    for allocation in allocations:
        allocation_code_2 = allocation['for_2']
        if allocation_code_2 not in allocations_tree:
            allocations_tree[allocation_code_2] = dict()
        branch_major = allocations_tree[allocation_code_2]
        allocation_code_4 = allocation['for_4']
        if allocation_code_4 not in branch_major:
            branch_major[allocation_code_4] = dict()
        branch_minor = branch_major[allocation_code_4]
        allocation_code_6 = allocation['for_6']
        if allocation_code_6 not in branch_minor:
            branch_minor[allocation_code_6] = list()
        twig = dict()
        twig['id'] = allocation['id']
        twig['projectDescription'] = allocation['project_description']
        twig['institution'] = allocation['institution']
        twig['instanceQuota'] = allocation['instance_quota']
        twig['coreQuota'] = allocation['core_quota']
        twig['budgetQuota'] = allocation['budget_quota']
        twig['national'] = allocation['national']
        branch_minor[allocation_code_6].append(twig)
    return allocations_tree


def create_allocation_tree_branch_node(name):
    return {'name': name, 'children': []}


def create_allocation_tree_leaf_node(allocation_summary):
    allocation_items = {
        'id': allocation_summary['id'],
        'name': allocation_summary['projectDescription'],
        'institution': allocation_summary['institution'],
        'instanceQuota': allocation_summary['instanceQuota'],
        'coreQuota': allocation_summary['coreQuota'],
        'budgetQuota': allocation_summary['budgetQuota'],
        'national': allocation_summary['national'],
    }
    return allocation_items


def restructure_allocations_tree(for_code_map):
    allocations_tree = organise_allocations_tree(for_code_map)
    restructured_tree = create_allocation_tree_branch_node('allocations')
    traverse_allocations_tree(allocations_tree, restructured_tree, 0)
    return restructured_tree


def traverse_allocations_tree(allocations_tree, node_parent, recursion_depth):
    MAX_RECURSION_DEPTH = 2
    for node_name in allocations_tree.keys():
        node_children = create_allocation_tree_branch_node(node_name)
        node_parent['children'].append(node_children)
        allocations_subtree = allocations_tree[node_name]
        if recursion_depth < MAX_RECURSION_DEPTH:
            traverse_allocations_tree(
                allocations_subtree, node_children, recursion_depth + 1
            )
        else:
            for allocation_summary in allocations_subtree:
                allocation_items = create_allocation_tree_leaf_node(
                    allocation_summary
                )
                node_children['children'].append(allocation_items)


def apply_for_code_to_summary(allocation_summary, code):
    allocation_summary['for_2'] = code[:2]
    allocation_summary['for_4'] = code[:4]
    allocation_summary['for_6'] = code[:6]


def apply_partitioned_quotas(
    allocation, allocation_summary, percentage, instances_id, cores_id
):
    fraction = float(percentage) / 100.0
    instance_quota = 0
    core_quota = 0

    for group in allocation.quota_groups:
        if group.zone_id != 'nectar' or group.service_type_id not in (
            'compute',
            'rating',
        ):
            continue
        for quota in group.quotas:
            if quota.resource_id == instances_id:
                instance_quota = quota.quota
            elif quota.resource_id == cores_id:
                core_quota = quota.quota
    allocation_summary['instance_quota'] = instance_quota * fraction
    allocation_summary['core_quota'] = core_quota * fraction
    budget_quota = allocation.su_budget or 0
    allocation_summary['budget_quota'] = budget_quota * fraction


def summary(allocation, code, instances_id, cores_id):
    allocation_summary = dict()
    allocation_summary['id'] = allocation.id
    allocation_summary['institution'] = utils.institution_from_email(
        allocation.contact_email
    )
    allocation_summary['project_description'] = allocation.project_description
    allocation_summary['national'] = allocation.national
    apply_for_code_to_summary(allocation_summary, code)
    if code == allocation.field_of_research_1:
        percentage = allocation.for_percentage_1
    elif code == allocation.field_of_research_2:
        percentage = allocation.for_percentage_2
    else:
        percentage = allocation.for_percentage_3
    apply_partitioned_quotas(
        allocation, allocation_summary, percentage, instances_id, cores_id
    )
    return allocation_summary
