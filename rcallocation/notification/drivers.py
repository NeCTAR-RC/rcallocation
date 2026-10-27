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

"""Notification drivers (stevedore namespace ``rcallocation.notifier``)."""

from oslo_config import cfg
from oslo_log import log as logging

from rcallocation.common import clients
from rcallocation.common import keystone


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class NotifierBase:
    def send(self, allocation, subject, body):
        """Send ``body`` to the allocation contact. Returns a reference."""
        raise NotImplementedError


class TaynacNotifier(NotifierBase):
    """Send through the Nectar taynac email service.

    taynac owns the envelope (From and Reply-To); messages are tagged
    ``allocation-<id>`` so replies land on the allocation's ticket.
    """

    def send(self, allocation, subject, body):
        taynac = clients.get_taynacclient(keystone.get_session())
        message = taynac.messages.send(
            subject=subject,
            body=body,
            recipient=allocation.contact_email,
            cc=list(CONF.notifications.cc),
            tags=[f"allocation-{allocation.id}"],
        )
        LOG.info(
            "Allocation %s: created taynac message backend_id=%s "
            "recipient=%s cc=%s",
            allocation.id,
            getattr(message, "backend_id", None),
            allocation.contact_email,
            list(CONF.notifications.cc),
        )
        return getattr(message, "backend_id", None)


class LoggingNotifier(NotifierBase):
    def send(self, allocation, subject, body):
        LOG.info(
            "Allocation %s: notification to %s cc=%s\nSubject: %s\n%s",
            allocation.id,
            allocation.contact_email,
            list(CONF.notifications.cc),
            subject,
            body,
        )
        return None


class NoopNotifier(NotifierBase):
    def send(self, allocation, subject, body):
        return None


BUILTIN = {
    "taynac": TaynacNotifier,
    "logging": LoggingNotifier,
    "noop": NoopNotifier,
}
