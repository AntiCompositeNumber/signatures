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
from flask_babel import gettext, ngettext, format_datetime  # type: ignore  # noqa: F401
import flask_babel
import os
import subprocess
import logging
import json


# Set up logging
logging.basicConfig(
    format="%(asctime)s %(levelname)s:%(name)s:%(message)s",
    level=logging.DEBUG,
    filename="app.log",
)
logger = logging.getLogger(__name__)


def create_app():
    # Load Flask config
    app = flask.Flask(__name__)
    try:
        with open(
            os.path.realpath(os.path.join(os.path.dirname(__file__), "../config.json"))
        ) as f:
            conf = json.load(f)
            app.config.update(conf.get("flask", ""))
    except FileNotFoundError:
        pass
    app.config.setdefault(
        "data_dir", os.path.realpath(os.path.join(os.path.dirname(__file__), "../data"))
    )
    # Put the short hash of the current git commit in the config
    rev = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        universal_newlines=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    app.config["version"] = rev.stdout
    app.config["SWAGGER_UI_DOC_EXPANSION"] = "full"
    # Setup i18n extensions
    babel = flask_babel.Babel(app)
    app.jinja_env.add_extension("jinja2.ext.i18n")

    @babel.localeselector
    def get_locale():
        translations = [locale.language for locale in babel.list_translations()]
        use_lang = flask.request.args.get("uselang")
        if use_lang in translations:
            return use_lang
        elif flask.request.cookies.get("lang") in translations:
            return flask.request.cookies["lang"]
        else:
            return flask.request.accept_languages.best_match(translations)

    @app.context_processor
    def locale_data():
        """Used to always pass l10n data to template"""

        def setlang_url(lang):
            return flask.url_for(
                flask.request.endpoint,
                setlang=lang,
                **flask.request.view_args,
                **flask.request.args
            )

        return dict(
            current_locale=flask_babel.get_locale(),
            available_locales=babel.list_translations(),
            setlang_url=setlang_url,
        )

    from web import frontend, api

    app.register_blueprint(frontend.bp)
    app.register_blueprint(api.bp)

    return app, babel


app, babel = create_app()
