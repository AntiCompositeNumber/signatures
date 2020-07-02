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

import sigprobs
import logging
import datetime
import os
import datasources
import json
import flask
from datatypes import WebAppMessage, UserCheck, Result
from typing import Any, cast, Dict, List, Set

logger = logging.getLogger(__name__)


def validate_username(user: str) -> None:
    invalid_chars = {"#", "<", ">", "[", "]", "|", "{", "}", "/"}
    if invalid_chars.isdisjoint(set(user)):
        return
    else:
        raise ValueError("Username contains invalid characters")


def get_default_sig(site: str, user: str = "$1", nickname: str = "$2") -> str:
    url = f"https://{site}/w/index.php"
    params = {"title": "MediaWiki:Signature", "action": "raw"}
    text = datasources.backoff_retry("get", url, output="text", params=params)
    return text.replace("$1", user).replace("$2", nickname)


def check_user(site: str, user: str, sig: str = "") -> UserCheck:
    validate_username(user)
    errors: Set[Result] = set()
    failure = None
    html_sig = ""
    sitedata = datasources.get_site_data(site)
    dbname = sitedata.dbname

    if not sig:
        # signature not supplied, get data from database
        user_props = datasources.get_user_properties(user, dbname)
        logger.debug(user_props)

        if not user_props.nickname:
            # user does not exist or uses default sig
            if not datasources.check_user_exists(user, sitedata):
                # user does not exist
                errors.add(WebAppMessage.USER_DOES_NOT_EXIST)
                failure = True
            else:
                # user exists but uses default signature
                errors.add(WebAppMessage.DEFAULT_SIG)
                sig = get_default_sig(site, user, user)
                failure = False
        elif not user_props.fancysig:
            # user exists but uses non-fancy sig with nickname
            errors.add(WebAppMessage.SIG_NOT_FANCY)
            sig = get_default_sig(site, user, user_props.nickname)
            failure = False
        else:
            # user exists and has custom fancy sig, check it
            sig = user_props.nickname

    if failure is None:
        # OK so far, actually check the signature
        errors = cast(Set[Result], sigprobs.check_sig(user, sig, sitedata, site))
        html_sig = get_rendered_sig(site, sig)
        logger.debug(errors)

    if not errors:
        # check returned no errors
        errors.add(WebAppMessage.NO_ERRORS)
        failure = False

    data = UserCheck(
        site=site,
        username=user,
        errors=list(errors),
        signature=sig,
        failure=failure,
        html_sig=html_sig,
    )
    return data


def get_rendered_sig(site: str, wikitext: str) -> str:
    url = f"https://{site}/api/rest_v1/transform/wikitext/to/html"
    payload = {"wikitext": wikitext, "body_only": True}
    text = datasources.backoff_retry("post", url, json=payload)
    text = text.replace("./", f"https://{site}/wiki/")
    _, sep1, rest = text.partition(">")
    inside, sep2, _ = rest.rpartition("</")
    if not sep1 or not sep2:
        return text
    else:
        return inside


def list_report_sites(config: Dict[str, Any]) -> List[str]:
    sites = [
        item.rpartition(".json")[0]
        for item in os.listdir(config["data_dir"])
        if item.endswith(".json")
    ]
    return sites


def purge_site(site: str) -> bool:
    try:
        with open(
            os.path.join(flask.current_app.config["data_dir"], site + ".json")
        ) as f:
            raw_data = json.load(f)
    except FileNotFoundError:
        raw_data = {}

    if raw_data and datetime.datetime.now() - datetime.datetime.fromisoformat(
        raw_data["meta"]["last_update"]
    ) < datetime.timedelta(days=1):
        return False

    result = sigprobs.main(site)
    with sigprobs.output_file("", site, True) as f:
        json.dump(result, f)
    return True
