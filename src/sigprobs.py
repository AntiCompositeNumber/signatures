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
import mwparserfromhell as mwph
import toolforge
import json
import pymysql
import time
import datetime
import itertools
import sys
import logging
import os

session = requests.Session()
session.headers.update(
    {"User-Agent": "sigprobs " + toolforge.set_user_agent("signatures")}
)


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


def iter_active_user_sigs(dbname, startblock=0, lastedit=None, days=365):
    """Get usernames and signatures from the replica database"""
    if lastedit is None:
        lastedit = (
            datetime.datetime.utcnow() - datetime.timedelta(days=days)
        ).strftime("%Y%m%d%H%M%S")
    conn = toolforge.connect(f"{dbname}_p", cluster="analytics")
    with conn.cursor(cursor=pymysql.cursors.SSCursor) as cur:
        # Break query into 100 queries paginated by last digits of user id
        for i in range(startblock, 100):
            cur.execute(
                """
                SELECT user_name, up_value
                FROM
                    user_properties
                    JOIN `user` ON user_id = up_user
                WHERE
                    RIGHT(up_user, 2) = %s AND
                    up_property = "nickname" AND
                    user_name IN (SELECT actor_name
                                  FROM revision_userindex
                                  JOIN actor_revision ON rev_actor = actor_id
                                  WHERE rev_timestamp > %s) AND
                    up_user IN (SELECT up_user
                                FROM user_properties
                                WHERE up_property = "fancysig" AND up_value = 1) AND
                    up_value != user_name
                ORDER BY up_user ASC""",
                args=(str(i), lastedit),
            )
            logger.info(f"Block {i}")
            for username, signature in cur.fetchall_unbuffered():
                yield username.decode(encoding="utf-8"), signature.decode(
                    encoding="utf-8"
                )


def get_user_properties(user, dbname):
    """Get signature and fancysig values for a user from the replica db"""
    logger.info("Getting user properties")
    conn = toolforge.connect(f"{dbname}_p")
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT up_property, up_value
            FROM
                user_properties
            WHERE
                up_user = (SELECT user_id
                           FROM `user`
                           WHERE user_name = "{user}")
            """,
        )
        resultset = cur.fetchall()
    logger.debug(resultset)
    if not resultset:
        return {}
    data = {key.decode("utf-8"): value.decode("utf-8") for key, value in resultset}
    data["fancysig"] = bool(int(data.get("fancysig", "0")))
    return data


def get_site_data(hostname):
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
    res = session.get(url, params=data)
    res.raise_for_status()

    namespaces = {}
    all_namespaces = res.json()["query"]["namespaces"]
    namespace_aliases = res.json()["query"]["namespacealiases"]
    for namespace, nsdata in all_namespaces.items():
        namespaces.setdefault(namespace, set()).update(
            [
                normal_name(nsdata.get("canonical", "")),
                normal_name(nsdata.get("name", "")),
            ]
        )

    for nsdata in namespace_aliases:
        namespaces.setdefault(str(nsdata["id"]), set()).add(
            normal_name(nsdata.get("alias", ""))
        )

    specialpages = {
        item["realname"]: item["aliases"]
        for item in res.json()["query"]["specialpagealiases"]
    }
    magicwords = {
        item["name"]: item["aliases"] for item in res.json()["query"]["magicwords"]
    }
    general = res.json()["query"]["general"]

    contribs = {normal_name(name) for name in specialpages["Contributions"]}

    subst = list(
        itertools.chain(
            magicwords.get("subst", ["SUBST"]),
            [item.lower() for item in magicwords.get("subst", ["SUBST"])],
            [item[0] + item[1:].lower() for item in magicwords.get("subst", ["SUBST"])],
        )
    )

    sitedata = {
        "user": namespaces["2"] - {""},
        "user talk": namespaces["3"] - {""},
        "special": namespaces["-1"] - {""},
        "contribs": contribs,
        "subst": subst,
        "dbname": general["wikiid"],
    }
    return sitedata


def normal_name(name):
    """Make first letter uppercase and replace spaces with underscores"""
    if name == "":
        return ""
    name = str(name)
    return (name[0].upper() + name[1:]).replace(" ", "_")


def check_sig(user, sig, sitedata, hostname):
    """Run a signature through the test suite and return any errors"""
    errors = set()
    try:
        errors.update(get_lint_errors(sig, hostname))
    except Exception:
        for i in range(0, 5):
            logger.info(f"Request failed, sleeping for {3**i}")
            time.sleep(3 ** i)
            errors.update(get_lint_errors(sig, hostname))
            break
        else:
            raise

    errors.add(check_tildes(sig, sitedata, hostname))
    errors.add(check_links(user, sig, sitedata, hostname))
    errors.add(check_fanciness(sig))
    errors.add(check_length(sig))
    return errors - {""}


def get_lint_errors(sig, hostname):
    """Use the REST API to get lint errors from the signature"""
    url = f"https://{hostname}/api/rest_v1/transform/wikitext/to/lint"
    data = {"wikitext": sig}
    res = session.post(url, json=data)
    res.raise_for_status()
    errors = set()
    for error in res.json():
        if (
            error.get("type", "") == "obsolete-tag"
            and error.get("params", {}).get("name", "") == "font"
        ):
            errors.add("obsolete-font-tag")
        else:
            errors.add(error.get("type"))
    return errors


def check_links(user, sig, sitedata, hostname):
    """Check for a link to a user, user talk, or contribs page"""
    if compare_links(user, sitedata, sig) is True:
        return ""
    else:
        expanded_errors = compare_links(
            user, sitedata, evaluate_subst(sig, sitedata, hostname)
        )
        if expanded_errors is True:
            return ""
        else:
            if "link-username-mismatch" in expanded_errors:
                return "link-username-mismatch"
            elif "interwiki-user-link" in expanded_errors:
                return "interwiki-user-link"
            else:
                return "no-user-links"


def compare_links(user, sitedata, sig):
    """Compare links in a sig to data in sitedata"""
    wikitext = mwph.parse(sig)
    user = normal_name(user)
    errors = set()
    for link in wikitext.ifilter_wikilinks():
        # Extract normalized namespace and page.
        # Interwiki prefixes are left in the namespace
        ns, sep, page = str(link.title).rpartition(":")
        ns, page = normal_name(ns.strip()), page.strip()

        # remove leading colon from namespace
        if ns.startswith(":"):
            ns = ns[1:]

        # Check if linking to user or user talk
        if not sep:
            continue
        elif ":" in ns:
            errors.add("interwiki-user-link")
        elif ns in sitedata["user"] or ns in sitedata["user talk"]:
            # Check that it's the right user or user_talk
            if normal_name(page) == user:
                return True
            else:
                errors.add("link-username-mismatch")
                continue
        elif ns in sitedata["special"]:
            # Could be a contribs page, check
            # split page and normalize names
            specialpage, slash, target = page.partition("/")
            specialpage = normal_name(specialpage.strip())
            target = normal_name(target.strip())
            if specialpage in sitedata["contribs"]:
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


def evaluate_subst(text, sitedata, hostname):
    """Perform substitution by removing "subst:" and expanding the wikitext"""
    for subst in sitedata["subst"]:
        text = text.replace(subst, "")
    data = {
        "action": "expandtemplates",
        "format": "json",
        "text": text,
        "prop": "wikitext",
    }
    url = f"https://{hostname}/w/api.php"
    res = session.get(url, params=data)
    res.raise_for_status()
    return res.json()["expandtemplates"]["wikitext"]


def check_fanciness(sig):
    """Check if a signature contains any wikitext formatting

    A lack of formatting indicates that fancysig may be incorrectly set"""
    fancychars = {"'", "<", "[", "{"}
    for letter in sig:
        if letter in fancychars:
            return ""
    else:
        return "plain-fancy-sig"


def check_tildes(sig, sitedata, hostname):
    """Check a signature for nested substitution using repeated expansion"""
    if "{" not in sig and "~" not in sig:
        return ""
    old_wikitext = sig
    for i in range(0, 5):
        new_wikitext = evaluate_subst(old_wikitext, sitedata, hostname)
        if "~~~" in sig:
            break
        elif new_wikitext == old_wikitext:
            return ""
    return "nested-subst"


def check_length(sig):
    """Check if a signature is more than 255 characters long"""
    if len(sig) > 255:
        return "sig-too-long"
    else:
        return ""


def main(hostname, startblock=0, lastedit=None, days=30):
    """Site-level report mode: Iterate over signatures and check for errors"""
    logger.info(f"Processing signatures for {hostname}")
    config = load_config(hostname)  # noqa
    bad = 0
    total = 0

    sitedata = get_site_data(hostname)
    dbname = sitedata["dbname"]

    filename = os.path.realpath(
        os.path.join(os.path.dirname(__file__), f"../data/{hostname}.json")
    )
    # Clear file to begin
    if not startblock:
        with open(filename + "l", "w") as f:
            f.write("")

    # Collect data into json lines file
    # Data is written directly as json lines to prevent data loss on database error
    for user, sig in iter_active_user_sigs(dbname, startblock, lastedit, days):
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
        sigerror = {"username": user, "signature": sig, "errors": list(errors)}
        with open(filename + "l", "a") as f:
            f.write(json.dumps(sigerror) + "\n")
        bad += 1
        if bad % 10 == 0:
            logger.info(f"{bad} bad sigs found in {total} so far")

    # Read back data, collect stats, and generate json file
    fulldata = {}
    stats = {}
    stats["total"] = bad
    with open(filename + "l") as f:
        for rawline in f:
            line = json.loads(rawline)
            for error in line.get("errors"):
                stats[error] = stats.setdefault(error, 0) + 1
            fulldata[line.pop("username")] = line

    meta = {"last_update": datetime.datetime.utcnow().isoformat(), "site": hostname}
    if lastedit:
        meta["active_since"] = datetime.datetime.strparse(
            lastedit, "%Y%m%d%H%M%S"
        ).isoformat()
    else:
        meta["active_since"] = (
            datetime.datetime.utcnow() - datetime.timedelta(days=days)
        ).isoformat()
    with open(filename, "w") as f:
        json.dump(
            {"errors": stats, "meta": meta, "sigs": fulldata},
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
