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


import requests
import toolforge
import itertools
import logging
import time
from datatypes import SiteData
from typing import Dict, Set
import datasources


session = requests.Session()
session.headers.update(
    {"User-Agent": "sigprobs " + toolforge.set_user_agent("signatures")}
)

logger = logging.getLogger(__name__)


def backoff_retry(method, url, output="text", **kwargs):
    for i in range(0, 5):
        try:
            res = session.request(method, url, **kwargs)

            res.raise_for_status()
            if output == "json":
                return res.json()
            elif output == "text":
                return res.text
        except Exception as err:
            if i >= 4:
                raise err
            logger.info(f"Request failed, sleeping for {3**i}")
            time.sleep(3 ** i)


def get_site_data(hostname: str) -> SiteData:
    """Get metadata about a site from the API"""
    url = f"https://{hostname}/w/api.php"
    data = dict(
        action="query",
        meta="siteinfo",
        siprop="|".join(
            [
                "namespaces",
                "namespacealiases",
                "specialpagealiases",
                "magicwords",
                "general",
            ]
        ),
        formatversion="2",
        format="json",
    )
    res_json = backoff_retry("get", url, params=data, output="json")

    namespaces: Dict[str, Set[str]] = {}
    all_namespaces = res_json["query"]["namespaces"]
    namespace_aliases = res_json["query"]["namespacealiases"]
    for namespace, nsdata in all_namespaces.items():
        namespaces.setdefault(namespace, set()).update(
            [
                datasources.normal_name(nsdata.get("canonical", "")),
                datasources.normal_name(nsdata.get("name", "")),
            ]
        )

    for nsdata in namespace_aliases:
        namespaces.setdefault(str(nsdata["id"]), set()).add(
            datasources.normal_name(nsdata.get("alias", ""))
        )

    specialpages = {
        item["realname"]: item["aliases"]
        for item in res_json["query"]["specialpagealiases"]
    }
    magicwords = {
        item["name"]: item["aliases"] for item in res_json["query"]["magicwords"]
    }
    general = res_json["query"]["general"]

    contribs = {datasources.normal_name(name) for name in specialpages["Contributions"]}

    subst = list(
        itertools.chain(
            magicwords.get("subst", ["SUBST"]),
            [item.lower() for item in magicwords.get("subst", ["SUBST"])],
            [item[0] + item[1:].lower() for item in magicwords.get("subst", ["SUBST"])],
        )
    )

    sitedata = SiteData(
        user=namespaces["2"] - {""},
        user_talk=namespaces["3"] - {""},
        file=namespaces["6"] - {""},
        special=namespaces["-1"] - {""},
        contribs=contribs,
        subst=subst,
        dbname=general["wikiid"],
        hostname=hostname,
    )
    return sitedata


def _check_user_exists(user: str, hostname: str) -> bool:
    params = {"action": "query", "format": "json", "list": "users", "ususers": user}
    url = f"https://{hostname}/w/api.php"
    result = backoff_retry("get", url, output="json", params=params)
    return bool(result["query"]["users"][0].get("missing", True))
