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


import mwparserfromhell as mwph  # type: ignore
import json
import datetime
import sys
import logging
import os
import datasources
from datatypes import Checks, SigError, SiteData
from typing import Union, Dict, Set, Optional, List, cast


def load_config(site):
    conf_file = os.path.realpath(
        os.path.join(os.path.dirname(__file__), "../config.json")
    )
    default_file = os.path.realpath(
        os.path.join(os.path.dirname(__file__), "../default_config.json")
    )
    with open(default_file) as f:
        defaults = json.load(f)
    config = defaults
    try:
        with open(conf_file) as f:
            conf = json.load(f)
    except FileNotFoundError:
        pass
    else:
        config.update(conf.get("default", {}))
        config.update(conf.get(site, {}))
    return config


def check_sig(
    user: str,
    sig: str,
    sitedata: SiteData,
    hostname: str,
    checks: Checks = Checks.DEFAULT,
) -> Set[SigError]:
    """Run a signature through the test suite and return any errors"""
    errors = set()

    if checks & Checks.LINKS:
        errors.add(check_links(user, sig, sitedata, hostname))
    if checks & Checks.LENGTH:
        errors.add(check_length(sig))
    if checks & Checks.FANCY:
        fanciness = check_fanciness(sig)
        if fanciness:
            # This check short circuits -- there's no point in doing the
            # more expensive checks if there's only plain text
            errors.add(fanciness)
            return cast(Set[SigError], errors - {None})
    if checks & Checks.LINT:
        errors.update(get_lint_errors(sig, hostname))
    if checks & Checks.NESTED_SUBST:
        errors.add(check_tildes(sig, sitedata, hostname))

    return cast(Set[SigError], errors - {None})


def get_lint_errors(sig: str, hostname: str) -> Set[SigError]:
    """Use the REST API to get lint errors from the signature"""
    url = f"https://{hostname}/api/rest_v1/transform/wikitext/to/lint"
    data = {"wikitext": sig}

    res_json = datasources.backoff_retry("post", url, json=data, output="json")

    errors = set()
    for error in res_json:
        if (
            error.get("type", "") == "obsolete-tag"
            and error.get("params", {}).get("name", "") == "font"
        ):
            errors.add(SigError("obsolete-font-tag"))
        else:
            errors.add(SigError(error.get("type")))
    return errors


def check_links(
    user: str, sig: str, sitedata: SiteData, hostname: str
) -> Optional[SigError]:
    """Check for a link to a user, user talk, or contribs page"""
    if compare_links(user, sitedata, sig) is True:
        return None
    else:
        expanded_errors = compare_links(
            user, sitedata, evaluate_subst(sig, sitedata, hostname)
        )
        if expanded_errors is True:
            return None
        else:
            expanded_errors = cast(Set[str], expanded_errors)
            if "link-username-mismatch" in expanded_errors:
                return SigError.LINK_USER_MISMATCH
            elif "interwiki-user-link" in expanded_errors:
                return SigError.INTERWIKI_USER_LINK
            else:
                return SigError.NO_USER_LINKS


def compare_links(user: str, sitedata: SiteData, sig: str) -> Union[bool, Set[str]]:
    """Compare links in a sig to data in sitedata"""
    wikitext = mwph.parse(sig)
    user = datasources.normal_name(user)
    errors = set()
    for link in wikitext.ifilter_wikilinks():
        title = str(link.title)
        # Extract namespace and page.
        # Interwiki prefixes are left in the namespace
        if ":" in user:
            # Colons in usernames break the partitioning
            if title.endswith(f":{user}"):
                ns = title.replace(f":{user}", "")
                sep = ":"
                page = title.replace(f"{ns}:", "")
            elif title.endswith(f"/{user}"):
                raw = title.replace(f"/{user}", "")
                ns, sep, page = raw.rpartition(":")
                page += f"/{user}"
            else:
                continue
        else:
            ns, sep, page = title.rpartition(":")
        # normalize namespace and strip whitespace from both
        ns, page = datasources.normal_name(ns.strip()), page.strip()

        # remove leading colon from namespace
        if ns.startswith(":"):
            ns = ns[1:]

        # Check if linking to user or user talk
        if not sep:
            continue
        elif ":" in ns:
            errors.add("interwiki-user-link")
        elif ns in sitedata.user or ns in sitedata.user_talk:
            # Check that it's the right user or user_talk
            if datasources.normal_name(page) == user:
                return True
            else:
                errors.add("link-username-mismatch")
                continue
        elif ns in sitedata.special:
            # Could be a contribs page, check
            # split page and normalize names
            specialpage, slash, target = page.partition("/")
            specialpage = datasources.normal_name(specialpage.strip())
            target = datasources.normal_name(target.strip())
            if specialpage in sitedata.contribs:
                # It's contribs
                if target == user:
                    # The right one
                    return True
                else:
                    errors.add("link-username-mismatch")
                    continue
            else:
                continue
    else:
        return errors


def evaluate_subst(text: str, sitedata: SiteData, hostname: str) -> str:
    """Perform substitution by removing "subst:" and expanding the wikitext"""
    for subst in sitedata.subst:
        text = text.replace(subst, "")
    data = {
        "action": "expandtemplates",
        "format": "json",
        "text": text,
        "prop": "wikitext",
    }
    url = f"https://{hostname}/w/api.php"
    res = datasources.backoff_retry("get", url, params=data, output="json")
    return res["expandtemplates"]["wikitext"]


def check_fanciness(sig: str) -> Optional[SigError]:
    """Check if a signature contains any wikitext formatting

    A lack of formatting indicates that fancysig may be incorrectly set"""
    fancychars = {"'", "<", "[", "{"}
    for letter in sig:
        if letter in fancychars:
            return None
    else:
        return SigError.PLAIN_FANCY_SIG


def check_tildes(sig: str, sitedata: SiteData, hostname: str) -> Optional[SigError]:
    """Check a signature for nested substitution using repeated expansion"""
    if "{" not in sig and "~" not in sig:
        return None
    old_wikitext = sig
    for i in range(0, 5):
        new_wikitext = evaluate_subst(old_wikitext, sitedata, hostname)
        if "~~~" in new_wikitext:
            break
        elif new_wikitext == old_wikitext:
            return None
        elif not new_wikitext:
            # They're using some sort of ParserFunction,
            # likely evaluating REVISIONUSER, that doesn't have a default
            # I'm not going to bother to try to fill in that information,
            # so just fall back to a tilde count.
            if old_wikitext.count("~") >= 3:
                break
            else:
                return None
        else:
            old_wikitext = new_wikitext
    else:
        # after 5 rounds of substitution, the wikitext keeps changing.
        return SigError.COMPLEX_TEMPL
    return SigError.NESTED_SUBST


def check_length(sig: str) -> Optional[SigError]:
    """Check if a signature is more than 255 characters long"""
    if len(sig) > 255:
        return SigError.SIG_TOO_LONG
    else:
        return None


def main(
    hostname: str,
    startblock: int = 0,
    lastedit: Optional[str] = None,
    days: int = 30,
    data: Optional[Union[Dict[str, str], List[str]]] = None,
) -> None:
    """Site-level report mode: Iterate over signatures and check for errors"""
    logger.info(f"Processing signatures for {hostname}")
    bad = 0
    total = 0

    sitedata = datasources.get_site_data(hostname)
    dbname = sitedata.dbname

    filename = os.path.realpath(
        os.path.join(os.path.dirname(__file__), f"../data/{hostname}.json")
    )

    if data is None:
        sigsource = datasources.iter_active_user_sigs(
            dbname, startblock, lastedit, days
        )
    elif isinstance(data, list):
        sigsource = datasources.iter_listed_user_sigs(data, dbname)
    elif isinstance(data, dict):
        sigsource = data.items()  # type: ignore

    resultdata = {}
    for user, sig in sigsource:
        total += 1
        if not sig:
            continue
        try:
            errors = check_sig(user, sig, sitedata, hostname)
        except Exception:
            logger.error(f"Processing User:{user}: {sig}")
            raise
        if not errors:
            continue
        resultdata[user] = {"signature": sig, "errors": list(errors)}
        bad += 1
        if bad % 10 == 0:
            logger.info(f"{bad} bad sigs found in {total} so far")

    # Collect stats, and generate json file
    stats = {}
    stats["total"] = bad
    for user, line in resultdata.items():
        for error in cast(list, line.get("errors")):
            stats[error] = stats.setdefault(error, 0) + 1

    meta = {"last_update": datetime.datetime.utcnow().isoformat(), "site": hostname}
    if lastedit:
        meta["active_since"] = datetime.datetime.strptime(
            lastedit, "%Y%m%d%H%M%S"
        ).isoformat()
    else:
        meta["active_since"] = (
            datetime.datetime.utcnow() - datetime.timedelta(days=days)
        ).isoformat()
    with open(filename, "w") as f:
        json.dump(
            {"errors": stats, "meta": meta, "sigs": resultdata},
            f,
            sort_keys=True,
            indent=4,
        )


if __name__ == "__main__":
    logging.basicConfig(
        format="%(asctime)s %(levelname)s:%(name)s:%(message)s", level=logging.DEBUG,
    )
    logger = logging.getLogger("sigprobs")
    main(sys.argv[1])
else:
    logger = logging.getLogger(__name__)
