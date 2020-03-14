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
import sigprobs
from typing import Iterator, Any, Tuple

logging.basicConfig(filename="log.log")
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
    "translation_dir", os.path.join(os.path.dirname(__file__), "/i18n")
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


def check_user(site, user, sig=""):
    sitedata = sigprobs.get_site_data(site)
    dbname = sitedata["dbname"]
    if not sig:
        user_props = sigprobs.get_user_properties(user, dbname)
    if not user_props:
        return {"failure": True, "error": "no-user-or-sig"}
    elif not user_props.get("fancysig"):
        return {"failure": True, "error": "sig-not-fancy"}
    sig = user_props["nickname"]
    errors = sigprobs.check_sig(user, sig, sitedata, site)
    if not errors:
        return {"failure": True, "error": "no-errors"}
    else:
        return {
            "site": site,
            "username": user,
            "signature": sig,
            "errors": list(errors),
        }


def get_rendered_sig(site, wikitext):
    url = f"https://{site}/api/rest_v1/transform/wikitext/to/html"
    payload = {"wikitext": wikitext, "body_only": True}
    res = session.post(url, json=payload)
    res.raise_for_status()
    return res.text.replace("./", f"https://{site}/wiki/")


@app.route("/check/<site>/<username>")
def check_result(site, username):
    data = check_user(site, username)
    # data = {
    #     "site": site,
    #     "username": username,
    #     "signature": "[[User:AntiCompositeNumber|AntiCompositeNumber]] "
    #     "([[User talk:AntiCompositeNumber|talk]])",
    #     "errors": [
    #         "html5-misnesting",
    #         "misc-tidy-replacement-issues",
    #         "misnested-tag",
    #         "missing-end-tag",
    #         "multiple-unclosed-formatting-tags",
    #         "nested-subst",
    #         "no-user-links",
    #         "obsolete-tag",
    #         "obsolete-font-tag",
    #         "plain-fancy-sig",
    #         "self-closed-tag",
    #         "sig-too-long",
    #         "stripped-tag",
    #         "tidy-font-bug",
    #         "tidy-whitespace-bug",
    #         "wikilink-in-extlink",
    #     ],
    # }

    if data.get("failure", False):
        return flask.render_template("check_result_err.html", error=data["error"],)

    html_sig = get_rendered_sig(site, data["signature"])
    return flask.render_template("check_result.html", html_sig=html_sig, **data)


@app.route("/report")
def report():
    return flask.render_template("report.html")


@app.route("/report/<site>")
def report_site(site):
    return flask.render_template("report_site.html")
