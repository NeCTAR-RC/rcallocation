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

from rcallocation import choices
from rcallocation.tests.unit.api.v1 import common
from rcallocation.tests.unit import factories


class FORTests(common.AllocationApiTestCase):
    def setUp(self):
        super().setUp()
        self.as_anon()

    def test_for_codes(self):
        response = self.client.get('/v1/for-codes/')
        self.assertEqual(response.status_code, 200)
        for_dict = response.json
        self.assertIn('0599', for_dict)
        self.assertEqual('OTHER ENVIRONMENTAL SCIENCES', for_dict['0599'])

    def test_for_codes_2008(self):
        response = self.client.get('/v1/for-codes-2008/')
        self.assertEqual(response.status_code, 200)
        for_dict = response.json
        self.assertIn('0599', for_dict)
        self.assertEqual('OTHER ENVIRONMENTAL SCIENCES', for_dict['0599'])

    def test_for_codes_2020(self):
        response = self.client.get('/v1/for-codes-2020/')
        self.assertEqual(response.status_code, 200)
        for_dict = response.json
        self.assertIn('3007', for_dict)
        self.assertEqual('Forestry sciences', for_dict['3007'])

    def test_for_codes_all(self):
        response = self.client.get('/v1/for-codes-all/')
        self.assertEqual(response.status_code, 200)
        for_dict = response.json
        self.assertIn('0599', for_dict)
        self.assertEqual('OTHER ENVIRONMENTAL SCIENCES', for_dict['0599'])
        self.assertIn('3007', for_dict)
        self.assertEqual('Forestry sciences', for_dict['3007'])

    def _build_test_allocations(self, for_codes):
        res = []
        for codes in for_codes:
            res.append(
                factories.create_allocation(
                    field_of_research_1=codes[0],
                    for_percentage_1=int(codes[1]),
                    field_of_research_2=codes[2],
                    for_percentage_2=int(codes[3]),
                    field_of_research_3=codes[4],
                    for_percentage_3=int(codes[5]),
                    quota_value=1,
                    status=choices.APPROVED,
                )
            )
        return res

    def _find_child(self, node, name):
        for child in node['children']:
            if child['name'] == name:
                return child
        return None

    def _check_tree_nodes(self, tree, code, allocation, quota):
        # NB: this test is based on the assumption that there is
        # exactly one allocation quota for each FoR code "bucket"
        # in the test allocations
        code_2 = code[:2]
        code_4 = code[:4]
        code_6 = code[:6]

        node_2 = self._find_child(tree, code_2)
        self.assertIsNotNone(node_2)
        node_4 = self._find_child(node_2, code_4)
        self.assertIsNotNone(node_4)
        node_6 = self._find_child(node_4, code_6)
        self.assertIsNotNone(node_6)
        self.assertEqual(1, len(node_6["children"]))
        self.assertEqual(
            {
                'national': allocation.national,
                'instanceQuota': quota,
                'coreQuota': quota,
                'budgetQuota': quota,
                'id': allocation.id,
                'institution': 'example.com',
                'name': allocation.project_description,
            },
            node_6["children"][0],
        )

    def test_for_tree(self):
        allocations = self._build_test_allocations(
            [
                ['01', 50, '02', 30, '03', 20],
                ['0401', 70, '0402', 30, None, 0],
                ['050102', 100, None, 0, None, 0],
            ]
        )
        response = self.client.get('/v1/for-tree/')
        self.assertEqual(response.status_code, 200)
        tree = response.json
        self.assertIn('name', tree.keys())
        self.assertIn('children', tree.keys())
        self.assertEqual('allocations', tree['name'])
        self.assertEqual(5, len(tree['children']))
        for child in tree['children']:
            name = child['name']
            grandchildren = child['children']
            for grandchild in grandchildren:
                self.assertTrue(grandchild['name'].startswith(name))

        self._check_tree_nodes(tree, '01', allocations[0], 0.5)
        self._check_tree_nodes(tree, '02', allocations[0], 0.3)
        self._check_tree_nodes(tree, '03', allocations[0], 0.2)
        self._check_tree_nodes(tree, '0401', allocations[1], 0.7)
        self._check_tree_nodes(tree, '0402', allocations[1], 0.3)
        self._check_tree_nodes(tree, '050102', allocations[2], 1.0)

    def test_for_tree_2020(self):
        response = self.client.get('/v1/for-tree-2020/')
        self.assertEqual(response.status_code, 200)
        tree = response.json
        self.assertIn('name', tree.keys())
        self.assertIn('children', tree.keys())
        self.assertEqual('allocations', tree['name'])
        self.assertTrue(len(tree['children']) == 0)
