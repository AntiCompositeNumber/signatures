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
from flask_babel import Babel, gettext, ngettext  # noqa: F401
import os
import subprocess
import toolforge
import requests
import logging
import json
import sigprobs
from typing import Iterator, Any, Tuple

logging.basicConfig(filename="log.log", level=logging.DEBUG)
app = flask.Flask(__name__)
session = requests.Session()
session.headers.update({"User-Agent": toolforge.set_user_agent("signatures")})

rev = subprocess.run(
    ["git", "rev-parse", "--short", "HEAD"],
    universal_newlines=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
)
app.config["version"] = rev.stdout
app.config.setdefault(
    "data_dir", os.path.realpath(os.path.join(os.path.dirname(__file__), "../data"))
)
babel = Babel(app)
app.jinja_env.add_extension("jinja2.ext.i18n")


def wmcs():
    try:
        f = open("/etc/wmcs-project")
    except FileNotFoundError:
        return False
    else:
        f.close()
        return True


@babel.localeselector
def get_locale():
    translations = [locale.language for locale in babel.list_translations()]
    return flask.request.accept_languages.best_match(translations)


def do_db_query(db_name: str, query: str) -> Any:
    """Uses the toolforge library to query the replica databases"""
    if not wmcs():
        raise ConnectionError("Not running on Toolforge, database unavailable")

    conn = toolforge.connect(db_name)
    with conn.cursor() as cur:
        cur.execute(query)
        res = cur.fetchall()
    return res


def get_sitematrix() -> Iterator[Tuple[str, str]]:
    """Try to get the sitematrix from the db, falling back to the API"""
    query = "SELECT url FROM meta_p.wiki WHERE is_closed = 0;"

    sitematrix = do_db_query("meta_p", query)

    for site in sitematrix:
        yield site.rpartition("//")[2]


@app.route("/")
def index():
    return flask.render_template("index.html")


@app.route("/check")
def check():
    # Convert query string parameters to url params
    site = flask.request.args.get("site")
    username = flask.request.args.get("username")
    if site and username:
        return flask.redirect(
            flask.url_for("check_result", site=site, username=username)
        )

    return flask.render_template(
        "check_form.html", sitematrix=["en.wikipedia.org", "meta.wikimedia.org"]
    )


def get_default_sig(site, user="$1", nickname="$2"):
    url = f"https://{site}/w/index.php"
    params = {"title": "MediaWiki:Signature", "action": "raw"}
    res = session.get(url, params=params)
    res.raise_for_status()
    return res.text.replace("$1", user).replace("$2", nickname)


def check_user_exists(dbname, user):
    query = f'SELECT user_id FROM `user` WHERE user_name = "{user}"'
    return bool(do_db_query(dbname, query))


def check_user(site, user, sig=""):
    data = {"site": site, "username": user, "errors": [], "signature": ""}
    logging.debug(data)
    sitedata = sigprobs.get_site_data(site)
    dbname = sitedata["dbname"]

    if not sig:
        # signature not supplied, get data from database
        user_props = sigprobs.get_user_properties(user, dbname)
        logging.debug(user_props)

    if not user_props.get("nickname"):
        # user does not exist or uses default sig
        if not check_user_exists(dbname, user):
            # user does not exist
            data["errors"].append("user-does-not-exist")
            data["failure"] = True
        else:
            # user exists but uses default signature
            data["errors"].append("default-sig")
            data["signature"] = get_default_sig(
                site, user, user_props.get("nickname", user)
            )
            data["failure"] = False
    elif not user_props.get("fancysig"):
        # user exists but uses non-fancy sig with nickname
        data["errors"].append("sig-not-fancy")
        data["signature"] = get_default_sig(
            site, user, user_props.get("nickname", user)
        )
        data["failure"] = False
    else:
        # user exists and has custom fancy sig, check it
        sig = user_props["nickname"]
        errors = sigprobs.check_sig(user, sig, sitedata, site)
        data["signature"] = sig
        logging.debug(errors)

        if not errors:
            # check returned no errors
            data["errors"].append("no-errors")
            data["failure"] = False
        else:
            # check returned some errors
            data["errors"] = list(errors)

    return data


def get_rendered_sig(site, wikitext):
    url = f"https://{site}/api/rest_v1/transform/wikitext/to/html"
    payload = {"wikitext": wikitext, "body_only": True}
    res = session.post(url, json=payload)
    res.raise_for_status()
    return res.text.replace("./", f"https://{site}/wiki/")


@app.route("/check/<site>/<username>")
def check_result(site, username):
    data = check_user(site, username)

    if data.get("signature"):
        data["html_sig"] = get_rendered_sig(site, data["signature"])
    else:
        data["html_sig"] = ""

    logging.debug(data)

    if data.get("failure") is not None:
        return flask.render_template("check_result_err.html", **data)

    return flask.render_template("check_result.html", **data)


@app.route("/reports")
def report():
    sites = [
        item.rpartition(".json")[0]
        for item in os.listdir(app.config["data_dir"])
    ]
    return flask.render_template("report.html", sites=sites)


@app.route("/reports/<site>")
def report_site(site):
    try:
        with open(os.path.join(app.config["data_dir"], site + ".json")) as f:
            data = json.load(f)
    except FileNotFoundError:
        flask.abort(404)
    return flask.render_template("report_site.html", site=site, d=data)


@app.route("/api/v1/check/<site>/<username>")
def api_check_result(site, username):
    data = check_user(site, username)

    if data.get("signature"):
        data["html_sig"] = get_rendered_sig(site, data["signature"])
    else:
        data["html_sig"] = ""

    return flask.jsonify(data)


@app.route("/api/v1/reports")
def api_report():
    sites = [
        item.rpartition(".json")[0]
        for item in os.listdir(app.config["data_dir"])
    ]
    return flask.jsonify(sites)


@app.route("/api/v1/reports/<site>")
def api_report_site(site):
    try:
        with open(os.path.join(app.config["data_dir"], site + ".json")) as f:
            data = json.load(f)
    except FileNotFoundError:
        flask.abort(404)
    return flask.jsonify(data)
