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

"""Tests for the request parsing, filtering and error plumbing.

A throwaway resource is registered on the test app so the behaviour is
exercised end to end through Flask rather than by calling helpers.
"""

import datetime

import marshmallow as ma
import sqlalchemy as sa
from werkzeug import datastructures

from rcallocation.api.v1 import base as api_base
from rcallocation.api.v1 import filtering
from rcallocation.api.v1.schemas import base as schemas
from rcallocation.common import exceptions
from rcallocation.extensions import db
from rcallocation.tests.unit import base


class Widget(db.Model):
    __tablename__ = "test_widget"
    id = sa.Column(sa.Integer, primary_key=True)
    name = sa.Column(sa.String(64))
    enabled = sa.Column(sa.Boolean, default=True)
    size = sa.Column(sa.Integer)
    created = sa.Column(sa.DateTime)
    parent_id = sa.Column(sa.Integer, sa.ForeignKey("test_widget.id"))


class WidgetSchema(schemas.BaseSchema):
    name = ma.fields.String(required=True)
    enabled = ma.fields.Boolean(load_default=True)
    size = ma.fields.Integer(allow_none=True)
    tags = ma.fields.List(ma.fields.String())
    created = schemas.DRFDateTime()


class WidgetFilterSet(filtering.FilterSet):
    filters = {
        "name": filtering.F(
            Widget.name,
            [
                "exact",
                "iexact",
                "contains",
                "icontains",
                "startswith",
                "regex",
                "in",
            ],
        ),
        "enabled": filtering.F(Widget.enabled),
        "size": filtering.F(Widget.size, ["exact", "lt", "gte", "in"]),
        "created": filtering.F(Widget.created, ["lt", "gte", "year", "date"]),
        "parent": filtering.F(Widget.parent_id, ["exact", "isnull"]),
    }


blp = api_base.v1_blueprint("test_widgets", __name__, "test-widgets")


@blp.route("/")
class Widgets(api_base.Resource):
    POLICY_PREFIX = "rcallocation:versions:%s"
    filterset = WidgetFilterSet

    @blp.response(200)
    def get(self):
        query = self.filter(db.session.query(Widget).order_by(Widget.id))
        return {"results": [w.name for w in query.all()]}

    @blp.arguments(WidgetSchema)
    @blp.response(201)
    def post(self, data):
        return WidgetSchema().dump(data)


@blp.route("/<int:widget_id>/")
class WidgetItem(api_base.Resource):
    POLICY_PREFIX = "rcallocation:versions:%s"

    @blp.arguments(WidgetSchema(partial=True))
    @blp.response(200)
    def patch(self, data, widget_id):
        return data

    def get(self, widget_id):
        raise exceptions.ActionError("nope")


class FrameworkTestCase(base.ApiTestCase):
    def create_app(self):
        app = super().create_app()
        app.extensions["rcallocation_api"].register_blueprint(blp)
        return app


class TestBodyParsing(FrameworkTestCase):
    def test_json_body(self):
        response = self.client.post(
            "/v1/test-widgets/",
            json={"name": "a", "size": 3, "tags": ["x", "y"], "junk": 1},
        )
        self.assertEqual(201, response.status_code)
        self.assertEqual(
            {"name": "a", "enabled": True, "size": 3, "tags": ["x", "y"]},
            response.json,
        )

    def test_form_body_matches_json(self):
        response = self.client.post(
            "/v1/test-widgets/",
            data=datastructures.MultiDict(
                [
                    ("name", "a"),
                    ("size", "3"),
                    ("tags", "x"),
                    ("tags", "y"),
                    ("junk", "1"),
                ]
            ),
        )
        self.assertEqual(201, response.status_code)
        self.assertEqual(
            {"name": "a", "enabled": True, "size": 3, "tags": ["x", "y"]},
            response.json,
        )

    def test_form_booleans(self):
        response = self.client.post(
            "/v1/test-widgets/", data={"name": "a", "enabled": "False"}
        )
        self.assertEqual(201, response.status_code)
        self.assertFalse(response.json["enabled"])

    def test_form_empty_string_for_nullable_is_none(self):
        response = self.client.post(
            "/v1/test-widgets/", data={"name": "a", "size": ""}
        )
        self.assertEqual(201, response.status_code)
        self.assertIsNone(response.json["size"])

    def test_form_empty_string_for_non_nullable_is_dropped(self):
        response = self.client.post(
            "/v1/test-widgets/", data={"name": "a", "enabled": ""}
        )
        self.assertEqual(201, response.status_code)
        self.assertTrue(response.json["enabled"])

    def test_empty_body(self):
        response = self.client.post("/v1/test-widgets/")
        self.assertEqual(400, response.status_code)
        self.assertEqual({"name": ["This field is required."]}, response.json)

    def test_validation_error_shape(self):
        response = self.client.post(
            "/v1/test-widgets/", json={"name": "a", "size": "big"}
        )
        self.assertEqual(400, response.status_code)
        self.assertEqual(
            {"size": ["A valid integer is required."]}, response.json
        )

    def test_invalid_json(self):
        response = self.client.post(
            "/v1/test-widgets/",
            data="{not json",
            content_type="application/json",
        )
        self.assertEqual(400, response.status_code)
        self.assertIn("JSON parse error", response.json["detail"])

    def test_partial_patch(self):
        response = self.client.patch("/v1/test-widgets/1/", data={"size": "4"})
        self.assertEqual(200, response.status_code)
        self.assertEqual({"size": 4}, response.json)

    def test_datetime_round_trip(self):
        response = self.client.post(
            "/v1/test-widgets/",
            json={"name": "a", "created": "2024-01-02T03:04:05+10:00"},
        )
        self.assertEqual(201, response.status_code)
        self.assertEqual("2024-01-01T17:04:05Z", response.json["created"])

    def test_action_error_body(self):
        response = self.client.get("/v1/test-widgets/1/")
        self.assertEqual(400, response.status_code)
        self.assertEqual({"error": "nope"}, response.json)


class TestFiltering(FrameworkTestCase):
    def setUp(self):
        super().setUp()
        parent = Widget(
            id=1,
            name="Parent",
            enabled=True,
            size=10,
            created=datetime.datetime(2023, 5, 1, 12, 0),
        )
        db.session.add(parent)
        db.session.add_all(
            [
                Widget(
                    id=2,
                    name="alpha",
                    enabled=True,
                    size=1,
                    parent_id=1,
                    created=datetime.datetime(2024, 1, 1, 0, 0),
                ),
                Widget(
                    id=3,
                    name="Beta",
                    enabled=False,
                    size=5,
                    parent_id=1,
                    created=datetime.datetime(2024, 6, 1, 0, 0),
                ),
                Widget(
                    id=4,
                    name="gamma_x",
                    enabled=True,
                    size=None,
                    created=datetime.datetime(2025, 1, 1, 0, 0),
                ),
            ]
        )
        db.session.commit()

    def names(self, query_string):
        response = self.client.get(f"/v1/test-widgets/?{query_string}")
        self.assertEqual(200, response.status_code, response.json)
        return response.json["results"]

    def test_exact(self):
        self.assertEqual(["alpha"], self.names("name=alpha"))

    def test_iexact(self):
        self.assertEqual(["Beta"], self.names("name__iexact=beta"))

    def test_contains_and_escaping(self):
        self.assertEqual(["gamma_x"], self.names("name__contains=a_x"))
        self.assertEqual([], self.names("name__contains=aXx"))

    def test_icontains(self):
        self.assertEqual(["Beta"], self.names("name__icontains=BET"))

    def test_startswith(self):
        self.assertEqual(["gamma_x"], self.names("name__startswith=gamm"))

    def test_regex(self):
        self.assertEqual(["alpha", "gamma_x"], self.names("name__regex=^[ag]"))

    def test_in_csv_and_repeated(self):
        self.assertEqual(["alpha", "Beta"], self.names("name__in=alpha,Beta"))
        self.assertEqual(
            ["alpha", "Beta"], self.names("name__in=alpha&name__in=Beta")
        )
        self.assertEqual(["alpha", "Beta"], self.names("size__in=1,5"))

    def test_boolean(self):
        self.assertEqual(["Beta"], self.names("enabled=False"))
        self.assertEqual(["Beta"], self.names("enabled=false"))
        self.assertEqual(
            ["Parent", "alpha", "gamma_x"], self.names("enabled=True")
        )
        # unparsable booleans are ignored
        self.assertEqual(4, len(self.names("enabled=maybe")))

    def test_isnull(self):
        self.assertEqual(
            ["Parent", "gamma_x"], self.names("parent__isnull=True")
        )
        self.assertEqual(["alpha", "Beta"], self.names("parent__isnull=False"))

    def test_numeric_lookups(self):
        self.assertEqual(["alpha"], self.names("size__lt=5"))
        self.assertEqual(["Parent", "Beta"], self.names("size__gte=5"))

    def test_date_lookups(self):
        self.assertEqual(["alpha", "Beta"], self.names("created__year=2024"))
        self.assertEqual(["Beta"], self.names("created__date=2024-06-01"))
        self.assertEqual(
            ["gamma_x"], self.names("created__gte=2024-12-31T00:00:00")
        )
        self.assertEqual(["Parent"], self.names("created__lt=2024-01-01"))

    def test_unknown_param_ignored(self):
        self.assertEqual(4, len(self.names("bogus=1&name__bogus=2")))

    def test_disallowed_lookup_ignored(self):
        self.assertEqual(4, len(self.names("enabled__contains=T")))

    def test_empty_value_ignored(self):
        self.assertEqual(4, len(self.names("name=")))

    def test_invalid_value_is_400(self):
        response = self.client.get("/v1/test-widgets/?size=big")
        self.assertEqual(400, response.status_code)
        self.assertEqual({"size": ["Enter a valid value."]}, response.json)
        response = self.client.get("/v1/test-widgets/?created__year=x")
        self.assertEqual(400, response.status_code)
        self.assertEqual(
            {"created__year": ["Enter a whole number."]}, response.json
        )


class TestParseBool(base.TestCase):
    def test_values(self):
        self.assertTrue(filtering.parse_bool("True"))
        self.assertTrue(filtering.parse_bool("true"))
        self.assertTrue(filtering.parse_bool("1"))
        self.assertFalse(filtering.parse_bool("False"))
        self.assertFalse(filtering.parse_bool("0"))
        self.assertIsNone(filtering.parse_bool("yes"))
        self.assertTrue(filtering.parse_bool(True))
