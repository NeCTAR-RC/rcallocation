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

import unittest

from werkzeug import datastructures

from rcallocation.api.v1 import pagination


class FakeQuery:
    def __init__(self, items):
        self.items = items
        self._offset = 0
        self._limit = None

    def order_by(self, *args):
        return self

    def count(self):
        return len(self.items)

    def offset(self, value):
        self._offset = value
        return self

    def limit(self, value):
        self._limit = value
        return self

    def all(self):
        end = None if self._limit is None else self._offset + self._limit
        return self.items[self._offset : end]


class TestPagination(unittest.TestCase):
    URL = "http://localhost/v1/allocations/?status=A&limit=2"

    def paginate(self, items, url, default=100, maximum=1000):
        args = datastructures.MultiDict(
            [tuple(p.split("=")) for p in url.split("?")[1].split("&")]
            if "?" in url
            else []
        )
        with unittest.mock.patch.object(pagination.CONF, "api") as api_conf:
            api_conf.page_size = default
            api_conf.max_page_size = maximum
            return pagination.paginate(
                FakeQuery(items), list, args=args, url=url
            )

    def test_first_page(self):
        result = self.paginate(list(range(5)), self.URL)
        self.assertEqual(5, result["count"])
        self.assertEqual([0, 1], result["results"])
        self.assertIsNone(result["previous"])
        self.assertEqual(
            "http://localhost/v1/allocations/?limit=2&offset=2&status=A",
            result["next"],
        )

    def test_middle_page(self):
        result = self.paginate(list(range(5)), self.URL + "&offset=2")
        self.assertEqual([2, 3], result["results"])
        self.assertEqual(
            "http://localhost/v1/allocations/?limit=2&offset=4&status=A",
            result["next"],
        )
        self.assertEqual(
            "http://localhost/v1/allocations/?limit=2&status=A",
            result["previous"],
        )

    def test_last_page(self):
        result = self.paginate(list(range(5)), self.URL + "&offset=4")
        self.assertEqual([4], result["results"])
        self.assertIsNone(result["next"])
        self.assertEqual(
            "http://localhost/v1/allocations/?limit=2&offset=2&status=A",
            result["previous"],
        )

    def test_offset_beyond_count(self):
        result = self.paginate(list(range(5)), self.URL + "&offset=9")
        self.assertEqual([], result["results"])
        self.assertIsNone(result["next"])

    def test_empty(self):
        result = self.paginate([], "http://localhost/v1/allocations/")
        self.assertEqual(
            {"count": 0, "next": None, "previous": None, "results": []},
            result,
        )

    def test_default_limit(self):
        result = self.paginate(
            list(range(150)), "http://localhost/v1/allocations/"
        )
        self.assertEqual(100, len(result["results"]))
        self.assertEqual(
            "http://localhost/v1/allocations/?limit=100&offset=100",
            result["next"],
        )

    def test_invalid_limit_falls_back(self):
        for bad in ("0", "-1", "abc"):
            result = self.paginate(
                list(range(5)), f"http://localhost/v1/allocations/?limit={bad}"
            )
            self.assertEqual(5, len(result["results"]))

    def test_invalid_offset_is_zero(self):
        result = self.paginate(
            list(range(5)), "http://localhost/v1/allocations/?offset=x"
        )
        self.assertEqual(5, len(result["results"]))

    def test_limit_capped(self):
        result = self.paginate(
            list(range(5)),
            "http://localhost/v1/allocations/?limit=5000",
            maximum=3,
        )
        self.assertEqual([0, 1, 2], result["results"])
