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
from flask_babel import Babel
import subprocess
import toolforge
import requests
from . import sigprobs
from typing import Iterator, Any, Tuple

app = flask.Flask(__name__)
babel = Babel(app)
session = requests.Session()
session.headers.update(
    {"User-Agent": "sigprobs " + toolforge.set_user_agent("anticompositebot")}
)

rev = subprocess.run(
    ["git", "rev-parse", "--short", "HEAD"],
    universal_newlines=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
)
app.config["version"] = rev.stdout


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
    return flask.request.accept_languages.best_match(
        [loc.language for loc in babel.list_translations()]
    )


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


@app.route("/check/<site>/<username>")
def check_result(site, username):
    sigprobs
    return flask.render_template("check_result.html")


@app.route("/report")
def report():
    return flask.render_template("report.html")


@app.route("/report/<site>")
def report_site(site):
    return flask.render_template("report_site.html")
