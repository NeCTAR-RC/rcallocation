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

"""Fields of Research code lists and allocation trees.

The unsuffixed ``for-codes`` and ``for-tree`` routes serve the 2008
series, as the old API did.
"""

from rcallocation.api.v1 import base
from rcallocation.common import policies
from rcallocation import forcodes
from rcallocation import fortree


def _codes_view(key, codes):
    def get(self):
        self.require("codes")
        return fortree.cached(key, lambda: codes)

    return get


def _tree_view(key, codes):
    def get(self):
        self.require("tree")
        return fortree.cached(key, lambda: fortree.for_tree(codes))

    return get


ROUTES = [
    ("for-codes", "codes", forcodes.FOR_CODES_2008),
    ("for-codes-2008", "codes", forcodes.FOR_CODES_2008),
    ("for-codes-2020", "codes", forcodes.FOR_CODES_2020),
    ("for-codes-all", "codes", forcodes.FOR_CODES_ALL),
    ("for-tree", "tree", forcodes.FOR_CODES_2008),
    ("for-tree-2008", "tree", forcodes.FOR_CODES_2008),
    ("for-tree-2020", "tree", forcodes.FOR_CODES_2020),
    ("for-tree-all", "tree", forcodes.FOR_CODES_ALL),
]

BLUEPRINTS = []

for _path, _kind, _codes in ROUTES:
    _blp = base.v1_blueprint(
        _path.replace("-", "_"),
        __name__,
        _path,
        description="Fields of Research "
        + ("codes" if _kind == "codes" else "allocation tree"),
    )
    _view = _codes_view if _kind == "codes" else _tree_view
    _cls = type(
        _path.title().replace("-", ""),
        (base.Resource,),
        {
            "POLICY_PREFIX": policies.FOR_PREFIX,
            "get": _view(_path, _codes),
        },
    )
    _blp.route("/")(_cls)
    BLUEPRINTS.append(_blp)
