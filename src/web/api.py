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

from . import resources

bp = flask.Blueprint("api", __name__, url_prefix="/api")


@bp.route("/v1/check/<site>/<username>")
def api_check_result(site, username):
    data = resources.check_user(site, username)

    if data.get("signature"):
        data["html_sig"] = resources.get_rendered_sig(site, data["signature"])
    else:
        data["html_sig"] = ""

    return flask.jsonify(data)


@bp.route("/v1/reports")
def api_report():
    sites = [
        item.rpartition(".json")[0]
        for item in os.listdir(flask.current_app.config["data_dir"])
        if item.endswith(".json")
    ]
    return flask.jsonify(sites)


@bp.route("/v1/reports/<site>")
def api_report_site(site):
    try:
        with open(
            os.path.join(flask.current_app.config["data_dir"], site + ".json")
        ) as f:
            data = json.load(f)
    except FileNotFoundError:
        flask.abort(404)
    return flask.jsonify(data)
