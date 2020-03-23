#!/usr/bin/env python3
# coding: utf-8
# SPDX-License-Identifier: Apache-2.0


# Copyright 2020 AntiCompositeNumber

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#   http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import flask
import os
import json
from flask_restx import Api, Resource, fields

from . import resources

bp = flask.Blueprint("api", __name__, url_prefix="/api")
api = Api(bp, prefix="/v1")

check_model = api.model(
    "UserReport",
    {
        "site": fields.String(example="en.wikipedia.org"),
        "username": fields.String(example="Example"),
        "errors": fields.List(fields.String(example="link-username-mismatch")),
        "signature": fields.String(
            example="[[User:Example2|Example]] ([[User talk:Example2|talk]])"
        ),
        "html_sig": fields.String(
            example='<p id="mwAQ"><a rel="mw:WikiLink" '
            'href="https://en.wikipedia.org/wiki/User:Example2" '
            'title="User:Example2" id="mwAg">Example</a> '
            '(<a rel="mw:WikiLink" '
            'href="https://en.wikipedia.org/wiki/User_talk:Example2" '
            'title="User talk:Example2" id="mwAw" '
            'class="mw-redirect">talk</a>)</p>'
        ),
    },
)


@api.route("/check/<site>/<username>")
@api.param("signature", "")
class Check(Resource):
    @api.doc(model=check_model)
    def get(self, site, username):
        signature = flask.request.values.get("signature", "")

        data = resources.check_user(site, username, signature)

        return data


@api.route("/reports")
class Reports(Resource):
    def get(self):
        sites = resources.list_report_sites(flask.current_app.config)
        return sites


@api.route("/reports/<site>")
class ReportsSite(Resource):
    def get(site):
        try:
            with open(
                os.path.join(flask.current_app.config["data_dir"], site + ".json")
            ) as f:
                data = json.load(f)
        except FileNotFoundError:
            flask.abort(404)
        return data
