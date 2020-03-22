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
from werkzeug.datastructures import MultiDict
from flask_babel import gettext, ngettext, format_datetime  # noqa: F401
import os
import datetime
import json
import functools
import logging

from . import resources

logger = logging.getLogger(__name__)

bp = flask.Blueprint("frontend", __name__)


def setlang(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        set_lang = flask.request.args.get("setlang")
        if set_lang:
            r_args = MultiDict(flask.request.args)
            r_args.pop("setlang")
            response = flask.make_response(
                flask.redirect(
                    flask.url_for(
                        flask.request.endpoint, **flask.request.view_args, **r_args
                    )
                )
            )
            response.set_cookie(
                "lang", set_lang, path=flask.request.script_root, samesite="Lax"
            )
            return response
        return f(*args, **kwargs)

    return decorated_function


@bp.route("/")
@setlang
def index():
    return flask.render_template("index.html")


@bp.route("/about")
@setlang
def about():
    return flask.render_template("about.html")


@bp.route("/check")
@setlang
def check():
    # Convert query string parameters to url params
    site = flask.request.args.get("site")
    username = flask.request.args.get("username")
    if site and username:
        return flask.redirect(
            flask.url_for("frontend.check_result", **flask.request.args)
        )

    return flask.render_template(
        "check_form.html", sitematrix=resources.get_sitematrix()
    )


@bp.route("/check/<site>/<username>")
@setlang
def check_result(site, username):
    signature = flask.request.args.get("signature", "")
    data = resources.check_user(site, username, signature)

    if data.get("signature"):
        data["html_sig"] = resources.get_rendered_sig(site, data["signature"])
    else:
        data["html_sig"] = ""

    logger.debug(data)

    if data.get("failure") is not None:
        return flask.render_template("check_result_err.html", **data)

    return flask.render_template("check_result.html", **data)


@bp.route("/reports")
@setlang
def report():
    sites = [
        item.rpartition(".json")[0]
        for item in os.listdir(flask.current_app.config["data_dir"])
        if item.endswith(".json")
    ]
    return flask.render_template("report.html", sites=sites)


@bp.route("/reports/<site>")
@setlang
def report_site(site):
    try:
        with open(
            os.path.join(flask.current_app.config["data_dir"], site + ".json")
        ) as f:
            data = json.load(f)
    except FileNotFoundError:
        flask.abort(404)
    data["meta"]["last_update"] = format_datetime(
        datetime.datetime.fromisoformat(data["meta"]["last_update"])
    )
    data["meta"]["active_since"] = format_datetime(
        datetime.datetime.fromisoformat(data["meta"]["active_since"])
    )
    return flask.render_template("report_site.html", site=site, d=data)
