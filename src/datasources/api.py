#!/usr/bin/env python3
# coding: utf-8
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright 2020 AntiCompositeNumber

import requests
import toolforge
import itertools
import logging
import time
from datatypes import SiteData
from typing import Dict, Set, Iterator
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
                datasources.normal_name(nsdata.get("canonical", "").lower()),
                datasources.normal_name(nsdata.get("name", "").lower()),
            ]
        )

    for nsdata in namespace_aliases:
        namespaces.setdefault(str(nsdata["id"]), set()).add(
            datasources.normal_name(nsdata.get("alias", "").lower())
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


def _get_sitematrix() -> Iterator[str]:
    # Construct the request to the Extension:Sitematrix api
    payload = {
        "action": "sitematrix",
        "format": "json",
        "smlangprop": "site",
        "smsiteprop": "url",
    }
    url = "https://meta.wikimedia.org/w/api.php"

    # Send the request, except on HTTP errors, and try to decode the json
    result = backoff_retry("get", url, output="json", params=payload)["sitematrix"]

    # Parse the result into a generator of urls of public open wikis
    for key, lang in result.items():
        if key == "count":
            continue
        elif key == "specials":
            for site in lang:
                if _check_status(site):
                    yield site["url"].rpartition("//")[2]
        else:
            for site in lang["site"]:
                if _check_status(site):
                    yield site["url"].rpartition("//")[2]


def _check_status(checksite: Dict[str, str]) -> bool:
    """Return true only if wiki is public and open"""
    return (
        (checksite.get("closed") is None)
        and (checksite.get("private") is None)
        and (checksite.get("fishbowl") is None)
    )


def _check_user_exists(user: str, hostname: str) -> bool:
    params = {"action": "query", "format": "json", "list": "users", "ususers": user}
    url = f"https://{hostname}/w/api.php"
    result = backoff_retry("get", url, output="json", params=params)
    return bool(result["query"]["users"][0].get("missing", True))
