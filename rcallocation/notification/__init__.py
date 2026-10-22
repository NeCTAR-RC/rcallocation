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

"""Email notifications on allocation state changes.

Acknowledgements go out when a request is created, submitted or amended
(statuses N, E and X) and a decline notice when it is declined (R and J).
Nothing is sent on approval or deletion. The rendered template's first
paragraph is the subject, the rest the HTML body, as in the dashboard.
"""

import os

import jinja2
from oslo_config import cfg
from oslo_log import log as logging
from stevedore import driver as stevedore_driver

from rcallocation import choices
from rcallocation.extensions import db
from rcallocation import forcodes
from rcallocation import models
from rcallocation.notification import drivers
from rcallocation import utils


CONF = cfg.CONF
LOG = logging.getLogger(__name__)

NAMESPACE = "rcallocation.notifier"
TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")

ACKNOWLEDGE = "acknowledge"
REJECTED = "rejected"


def get_driver(name=None):
    name = name or CONF.notifications.driver
    try:
        return stevedore_driver.DriverManager(
            namespace=NAMESPACE, name=name, invoke_on_load=True
        ).driver
    except Exception:
        # Entry points are only available once the package is installed;
        # fall back to the built-in drivers.
        if name in drivers.BUILTIN:
            return drivers.BUILTIN[name]()
        raise


def _for_display(code):
    name = forcodes.FOR_CODES_ALL.get(code)
    return f"{code} {name}" if name else code


def _environment():
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(TEMPLATE_DIR),
        autoescape=jinja2.select_autoescape(["html"]),
        trim_blocks=False,
        lstrip_blocks=False,
    )
    env.filters["for_display"] = _for_display
    return env


def render(allocation, template):
    """Render a notification; returns ``(subject, body)``."""
    previous = (
        db.session.query(models.AllocationRequest)
        .filter_by(parent_request_id=allocation.id, provisioned=True)
        .order_by(models.AllocationRequest.modified_time.desc())
        .first()
    )
    context = {
        "allocation": allocation,
        "quotas": allocation.get_quotas_context(),
        "quotas_previous": (
            previous.get_quotas_context() if previous else None
        ),
        "interested_sites": utils.get_interested_sites(allocation),
        "base_url": CONF.notifications.dashboard_url.rstrip("/"),
    }
    text = (
        _environment()
        .get_template(f"email_alert_{template}.html")
        .render(context)
    )
    subject, _, body = text.strip().partition("\n\n")
    return subject.strip(), body


def send(allocation, template):
    """Render and send a notification to the allocation contact.

    Returns True unless the attempt to send failed. Failures are logged
    rather than raised so a notification problem cannot abort the state
    change that triggered it.
    """
    if not allocation.notifications or not CONF.notifications.enabled:
        return True
    try:
        subject, body = render(allocation, template)
        get_driver().send(allocation, subject, body)
    except Exception:
        LOG.exception(
            "Allocation %s: failed to send '%s' notification to '%s'",
            allocation.id,
            template,
            allocation.contact_email,
        )
        return False
    return True


def send_notifications(allocation):
    """Send the notification appropriate to the allocation's status.

    A request in status N (new, not yet notified) is moved to E once the
    acknowledgement has gone out.
    """
    if allocation.status in (
        choices.NEW,
        choices.SUBMITTED,
        choices.UPDATE_PENDING,
    ):
        sent = send(allocation, ACKNOWLEDGE)
        if allocation.status == choices.NEW and sent:
            allocation.status = choices.SUBMITTED
            db.session.commit()
    elif allocation.is_rejected():
        send(allocation, REJECTED)
