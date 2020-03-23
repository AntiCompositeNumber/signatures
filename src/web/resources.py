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
import toolforge
import logging
import requests
import os
from typing import Iterator, Any

logger = logging.getLogger(__name__)

# Create requests HTTP session
session = requests.Session()
session.headers.update({"User-Agent": toolforge.set_user_agent("signatures")})


def wmcs():
    try:
        f = open("/etc/wmcs-project")
    except FileNotFoundError:
        return False
    else:
        f.close()
        return True


def do_db_query(db_name: str, query: str, **kwargs) -> Any:
    """Uses the toolforge library to query the replica databases"""
    if not wmcs():
        raise ConnectionError("Not running on Toolforge, database unavailable")

    conn = toolforge.connect(db_name)
    with conn.cursor() as cur:
        cur.execute(query, kwargs)
        res = cur.fetchall()
    return res


def get_sitematrix() -> Iterator[str]:
    """Try to get the sitematrix from the db, falling back to the API"""
    query = "SELECT url FROM meta_p.wiki WHERE is_closed = 0;"
    try:
        sitematrix = do_db_query("meta_p", query)

        for site in sitematrix:
            yield site[0].rpartition("//")[2]
    except ConnectionError:
        return [""]


def validate_username(user):
    invalid_chars = {"#", "<", ">", "[", "]", "|", "{", "}", "/"}
    if invalid_chars.isdisjoint(set(user)):
        return
    else:
        raise ValueError("Username contains invalid characters")


def get_default_sig(site, user="$1", nickname="$2"):
    url = f"https://{site}/w/index.php"
    params = {"title": "MediaWiki:Signature", "action": "raw"}
    res = session.get(url, params=params)
    res.raise_for_status()
    return res.text.replace("$1", user).replace("$2", nickname)


def check_user_exists(dbname, user):
    query = "SELECT user_id FROM `user` WHERE user_name = %(user)s"
    res = do_db_query(dbname, query, user=user)
    return bool(res)


def check_user(site, user, sig=""):
    validate_username(user)
    errors = set()
    failure = None
    html_sig = ""
    sitedata = sigprobs.get_site_data(site)
    dbname = sitedata.dbname

    if not sig:
        # signature not supplied, get data from database
        user_props = sigprobs.get_user_properties(user, dbname)
        logger.debug(user_props)

        if not user_props.nickname:
            # user does not exist or uses default sig
            if not check_user_exists(dbname, user):
                # user does not exist
                errors.add("user-does-not-exist")
                failure = True
            else:
                # user exists but uses default signature
                errors.add("default-sig")
                sig = get_default_sig(site, user, user)
                failure = False
        elif not user_props.fancysig:
            # user exists but uses non-fancy sig with nickname
            errors.add("sig-not-fancy")
            sig = get_default_sig(site, user, user_props.nickname)
            failure = False
        else:
            # user exists and has custom fancy sig, check it
            sig = user_props.nickname

    if failure is None:
        # OK so far, actually check the signature
        errors = sigprobs.check_sig(user, sig, sitedata, site)
        html_sig = get_rendered_sig(site, sig)
        logger.debug(errors)

    if not errors:
        # check returned no errors
        errors.add("no-errors")
        failure = False

    data = {
        "site": site,
        "username": user,
        "errors": list(errors),
        "signature": sig,
        "failure": failure,
        "html_sig": html_sig,
    }
    return data


def get_rendered_sig(site, wikitext):
    url = f"https://{site}/api/rest_v1/transform/wikitext/to/html"
    payload = {"wikitext": wikitext, "body_only": True}
    res = session.post(url, json=payload)
    res.raise_for_status()
    return res.text.replace("./", f"https://{site}/wiki/")


def list_report_sites(config):
    sites = [
        item.rpartition(".json")[0]
        for item in os.listdir(config["data_dir"])
        if item.endswith(".json")
    ]
    return sites
