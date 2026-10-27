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

import datetime

import sqlalchemy as sa

from rcallocation import choices
from rcallocation.extensions import db
from rcallocation import models


# These correspond to expiration states for expiring allocations
DANGER = 'Danger'  # getting close to auto-decline
ARCHIVED = 'Archived'
STOPPED = 'Stopped'
EXPIRED = 'Expired'
NONE = 'None'  # not expiring
UNKNOWN = 'Unknown'  # can't figure out when the expiry clock stopped.

# These represent the waiting time for non-expiring allocations
OVERDUE = 'Overdue'
WARNING = 'Warning'
ATTENTION = 'Attention'
NEW = 'New'


def get_clockstop_amendment(allocation):
    """Gets the amendment request that we infer would have stopped the
    expiry clock for this allocation's current expiration.  This does
    not take account of ticket holds or the special Christmas break logic.
    There is also a scenario where an amendment is declined but the user
    then submits a further amendment.  In that scenario, it is unclear
    what the notional "clock stop" time should be.

    These edge-cases could be avoided by querying Keystone (indirectly)
    to find out the project's real expiry status.
    """
    return get_clockstop_amendments([allocation]).get(allocation.id)


def get_clockstop_amendments(allocations):
    """Batch form of get_clockstop_amendment, in a single query.

    Returns a dict of allocation id to its clock-stop amendment; ids
    with no clock-stop amendment are absent.
    """
    ids = [allocation.id for allocation in allocations]
    if not ids:
        return {}
    Allocation = models.AllocationRequest
    # The time of the last approval of each allocation
    approvals = (
        db.session.query(
            Allocation.parent_request_id.label("allocation_id"),
            sa.func.max(Allocation.modified_time).label("approved_time"),
        )
        .filter(
            Allocation.status == choices.APPROVED,
            Allocation.parent_request_id.in_(ids),
        )
        .group_by(Allocation.parent_request_id)
        .subquery()
    )
    # The amendments after the last approval, earliest first
    rows = (
        db.session.query(Allocation, approvals.c.allocation_id)
        .join(
            approvals,
            sa.and_(
                sa.or_(
                    Allocation.parent_request_id == approvals.c.allocation_id,
                    Allocation.id == approvals.c.allocation_id,
                ),
                Allocation.modified_time > approvals.c.approved_time,
            ),
        )
        .filter(Allocation.status == choices.UPDATE_PENDING)
        .order_by(Allocation.modified_time, Allocation.id)
    )
    result = {}
    for amendment, allocation_id in rows:
        result.setdefault(allocation_id, amendment)
    return result


def _is_expiring(allocation, today):
    return bool(allocation.end_date and allocation.end_date < today)


def get_urgency_infos(allocations):
    """get_urgency_info for many allocations, keyed by allocation id,
    with the clock-stop lookups batched into one query.
    """
    today = datetime.date.today()
    clockstops = get_clockstop_amendments(
        [a for a in allocations if _is_expiring(a, today)]
    )
    return {a.id: get_urgency_info(a, clockstops) for a in allocations}


def get_urgency_info(allocation, clockstops=None):
    """Derive the urgency info for the urgency field from the modification
    date for the current allocation request and the project's inferred
    expiration state ... if the allocation past its end date.  This does not
    take account of ticket holds.  (That would require a Keystone "project
    show" and the Approver doesn't have permission to do that.)

    ``clockstops`` is an optional result of get_clockstop_amendments
    covering this allocation, to avoid querying for it here.
    """
    today = datetime.date.today()
    mod_date = allocation.modified_time.date()
    if _is_expiring(allocation, today):
        # Allocations that are expiring.  The urgency corresponds to
        # the expiry state at the point that we infer that the expiry
        # clock was stopped.
        if clockstops is None:
            clockstop = get_clockstop_amendment(allocation)
        else:
            clockstop = clockstops.get(allocation.id)
        if clockstop:
            expiry_clock = clockstop.modified_time.date()
            if expiry_clock + datetime.timedelta(days=30 * 5) < today:
                # At risk of automatic decline, restarting expiry
                expiry = DANGER
            elif expiry_clock > allocation.end_date + datetime.timedelta(
                days=28
            ):
                expiry = ARCHIVED
            elif expiry_clock > allocation.end_date + datetime.timedelta(
                days=14
            ):
                expiry = STOPPED
            elif expiry_clock > allocation.end_date:
                expiry = EXPIRED
            else:
                expiry = NONE
        else:
            expiry = UNKNOWN
    else:
        expiry = NONE
    if mod_date + datetime.timedelta(days=21) < today:
        # Approval SLA is 2 to 3 weeks.  Past 3 weeks
        urgency = OVERDUE
    elif mod_date + datetime.timedelta(days=14) < today:
        # Approval SLA is 2 to 3 weeks.  In that range
        urgency = WARNING
    elif mod_date + datetime.timedelta(days=7) < today:
        # Getting warm ...
        urgency = ATTENTION
    else:
        urgency = NEW
    return (urgency, expiry)


def get_urgency(allocation):
    """Combined urgency for display on the form.  An active expiry
    takes precedence.
    """
    urgency, expiry = get_urgency_info(allocation)
    return expiry if expiry != NONE else urgency
