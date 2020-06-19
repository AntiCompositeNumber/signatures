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
from flask_restx import Api, Resource, fields  # type: ignore

from . import resources

bp = flask.Blueprint("api", __name__, url_prefix="/api")
api = Api(bp, prefix="/v1", title="Signatures API", version="1.0")

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
        """Checks a single user's signature for problems"""
        signature = flask.request.values.get("signature", "")

        data = resources.check_user(site, username, signature)

        return data._asdict()


@api.route("/reports")
class Reports(Resource):
    def get(self):
        """Lists sites for which a batch report is available"""
        sites = resources.list_report_sites(flask.current_app.config)
        return sites


@api.route("/reports/<string:site>")
class ReportsSite(Resource):
    @api.response(200, "Success")
    @api.response(404, "Report not found")
    def get(self, site):
        """Batch report for a single site, organized by user"""
        try:
            with open(
                os.path.join(flask.current_app.config["data_dir"], site + ".json")
            ) as f:
                data = json.load(f)
        except FileNotFoundError:
            flask.abort(404)
        return data


@api.route("/reports/<string:site>/error")
class ReportsSiteErrors(Resource):
    @api.response(200, "Success")
    @api.response(404, "Report not found")
    def get(self, site):
        """Batch report for a single site, organized by error"""
        try:
            with open(
                os.path.join(flask.current_app.config["data_dir"], site + ".json")
            ) as f:
                raw_data = json.load(f)
        except FileNotFoundError:
            flask.abort(404)

        raw_data["errors"].pop("total")
        errors = raw_data["errors"].keys()
        data = {
            error: [
                user
                for user, info in raw_data["sigs"].items()
                if error in info["errors"]
            ]
            for error in errors
        }
        return {"errors": data, "meta": raw_data["meta"]}


@api.param(
    "format", "Output format; may be 'json' (default), 'plain', or 'massmessage'"
)
@api.produces("application/json,text/plain")
@api.route("/reports/<string:site>/error/<string:error>")
class ReportsSiteSingleError(Resource):
    @api.response(200, "Success")
    @api.response(404, "Report not found")
    @api.response(400, "Specified error does not exist in data")
    def get(self, site, error):
        """Batch report for a single error on a single site"""
        try:
            with open(
                os.path.join(flask.current_app.config["data_dir"], site + ".json")
            ) as f:
                raw_data = json.load(f)
        except FileNotFoundError:
            flask.abort(404)

        raw_data["errors"].pop("total")
        errors = raw_data["errors"].keys()
        if error not in errors:
            flask.abort(400)

        data = [
            user for user, info in raw_data["sigs"].items() if error in info["errors"]
        ]

        out_format = flask.request.values.get("format", "json")
        if out_format == "json":
            meta = raw_data["meta"]
            meta["error"] = error
            return {"errors": data, "meta": meta}
        elif out_format == "plain":
            return flask.Response(
                response="\n".join(data), status=200, mimetype="text/plain"
            )
        elif out_format == "massmessage":
            return flask.Response(
                response="\n".join(f"User talk:{user}@{site}" for user in data),
                status=200,
                mimetype="text/plain",
            )
