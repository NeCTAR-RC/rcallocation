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
    Allocation = models.AllocationRequest
    # The last approved allocation
    approval = (
        db.session.query(Allocation)
        .filter(
            Allocation.status == choices.APPROVED,
            Allocation.parent_request_id == allocation.id,
        )
        .order_by(Allocation.modified_time.desc())
        .first()
    )
    if approval is None:
        return None
    # The first amendment after the last approval
    return (
        db.session.query(Allocation)
        .filter(
            Allocation.status == choices.UPDATE_PENDING,
            sa.or_(
                Allocation.parent_request_id == allocation.id,
                Allocation.id == allocation.id,
            ),
            Allocation.modified_time > approval.modified_time,
        )
        .order_by(Allocation.modified_time)
        .first()
    )


def get_urgency_info(allocation):
    """Derive the urgency info for the urgency field from the modification
    date for the current allocation request and the project's inferred
    expiration state ... if the allocation past its end date.  This does not
    take account of ticket holds.  (That would require a Keystone "project
    show" and the Approver doesn't have permission to do that.)
    """
    today = datetime.date.today()
    mod_date = allocation.modified_time.date()
    if allocation.end_date and allocation.end_date < today:
        # Allocations that are expiring.  The urgency corresponds to
        # the expiry state at the point that we infer that the expiry
        # clock was stopped.
        clockstop = get_clockstop_amendment(allocation)
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
