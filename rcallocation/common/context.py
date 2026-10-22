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

from oslo_context import context as oslo_context


class RequestContext(oslo_context.RequestContext):
    """Request context with the extras the allocation policy needs.

    ``is_anonymous`` distinguishes an unauthenticated caller (public read
    access is allowed on some resources) and ``user_name`` is exposed to
    oslo.policy because allocation ownership is keyed on the keystone
    username, which in Nectar is the contact email address.
    """

    @property
    def is_anonymous(self):
        return not self.user_id

    def to_policy_values(self):
        # oslo.context treats keys added to its mapping as deprecated and
        # warns when policy reads them, so build a plain dict instead.
        values = dict(super().to_policy_values())
        values["user_name"] = self.user_name
        return values


def anonymous():
    return RequestContext(overwrite=False)
