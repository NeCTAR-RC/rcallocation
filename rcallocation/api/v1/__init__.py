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

from rcallocation.api.v1.resources import allocation
from rcallocation.api.v1.resources import fortree
from rcallocation.api.v1.resources import organisation
from rcallocation.api.v1.resources import quota
from rcallocation.api.v1.resources import reference
from rcallocation.api.v1.resources import related
from rcallocation.api.v1.resources import versions


# Every blueprint's url_prefix already carries the /v1 prefix.
BLUEPRINTS = (
    [versions.blp, allocation.blp, quota.blp, organisation.blp]
    + reference.BLUEPRINTS
    + related.BLUEPRINTS
    + fortree.BLUEPRINTS
)


def register(api):
    for blp in BLUEPRINTS:
        api.register_blueprint(blp)
