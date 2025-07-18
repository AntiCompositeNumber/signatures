#!/usr/bin/env python3
# coding: utf-8
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright 2020 AntiCompositeNumber

import mwparserfromhell as mwph
import json
import datetime
import sys
import logging
import logging.handlers
import os
import html
import itertools
import functools
import operator
import argparse
import datasources
import datatypes
import pathlib
from datatypes import Checks, SigError, SiteData
from typing import Union, Dict, Set, Optional, List, cast, Tuple, TextIO


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
    sig = html.unescape(sig)

    if checks & Checks.LINKS:
        errors.add(check_links(user, sig, sitedata))
    if checks & Checks.LENGTH:
        errors.add(check_length(sig))
    if checks & Checks.FANCY:
        fanciness = check_fanciness(sig)
        if fanciness:
            # This check short circuits -- there's no point in doing the
            # more expensive checks if there's only plain text
            errors.add(fanciness)
            return cast(Set[SigError], errors - {None, SigError.NO_USER_LINKS})
    if checks & Checks.LINT:
        errors.update(get_lint_errors(sig, sitedata, checks))
    if checks & Checks.NESTED_SUBST:
        errors.add(check_tildes(sig, sitedata))
    if checks & Checks.IMAGES:
        errors.add(check_images(sig, sitedata))
    if checks & Checks.TRANSCLUSION:
        errors.add(check_transclusion(sig, sitedata))
    if checks & Checks.SUBST_LENGTH:
        errors.add(check_post_subst_length(sig, sitedata))
    if checks & Checks.LINK_NAME:
        errors.add(check_impersonation(sig, user, sitedata))
    if checks & Checks.FREE_PIPES:
        errors.add(check_pipes(sig))
    if checks & Checks.BREAKS:
        errors.add(check_line_breaks(sig))

    return cast(Set[SigError], errors - {None})


def lint_to_error(error: Dict[str, str]) -> Optional[SigError]:
    try:
        return SigError(error.get("type", ""))
    except ValueError:
        logging.error(f"Lint error '{error['type']}' not found")
        return None


def get_lint_errors(sig: str, sitedata: SiteData, checks: Checks) -> Set[SigError]:
    """Use the REST API to get lint errors from the signature"""
    url = f"https://{sitedata.hostname}/api/rest_v1/transform/wikitext/to/lint"
    data = {"wikitext": evaluate_subst(sig, sitedata)}

    res_json = datasources.backoff_retry("post", url, json=data, output="json")

    errors: Set[Optional[SigError]] = set()
    for error in res_json:
        if error.get("type", "") == "obsolete-tag":
            if checks & Checks.OBSOLETE_TAG:
                if error.get("params", {}).get("name", "") == "font":
                    errors.add(SigError("obsolete-font-tag"))
                else:
                    errors.add(lint_to_error(error))
        else:
            errors.add(lint_to_error(error))
    return cast(Set[SigError], errors - {None})


def check_links(user: str, sig: str, sitedata: SiteData) -> Optional[SigError]:
    """Check for a link to a user, user talk, or contribs page"""
    if compare_links(user, sitedata, sig) is True:
        return None
    else:
        expanded_errors = compare_links(user, sitedata, evaluate_subst(sig, sitedata))
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


def compare_links(
    user: str, sitedata: SiteData, sig: Union[str, mwph.string_mixin.StringMixIn]
) -> Union[bool, Set[str]]:
    """Compare links in a sig to data in sitedata"""
    wikitext = mwph.parse(sig)
    user = datasources.normal_name(user)
    errors = set()
    for link in wikitext.ifilter_wikilinks():
        title = str(link.title).partition("#")[0]
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
                continue  # pragma: no cover
        else:
            ns, sep, page = title.rpartition(":")

        # strip whitespace from ns, page
        ns, page = ns.strip(), page.strip()

        # remove leading colon from namespace
        if ns.startswith(":"):
            ns = ns[1:]

        ns = datasources.normal_name(ns.lower())

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
                    continue  # pragma: no cover
            else:
                continue  # pragma: no cover
    else:
        return errors


def evaluate_subst(text: str, sitedata: SiteData) -> str:
    """Perform substitution by removing "subst:" and expanding the wikitext"""
    if not text:
        return ""
    for subst in sitedata.subst:
        text = text.replace(subst, "")
    data = {
        "action": "expandtemplates",
        "format": "json",
        "text": text,
        "prop": "wikitext",
    }
    url = f"https://{sitedata.hostname}/w/api.php"
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


def check_tildes(sig: str, sitedata: SiteData) -> Optional[SigError]:
    """Check a signature for nested substitution using repeated expansion"""
    if "{" not in sig and "~" not in sig:
        return None
    old_wikitext = sig
    for i in range(0, 5):
        new_wikitext = evaluate_subst(old_wikitext, sitedata)
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


def check_images(sig: str, sitedata: SiteData) -> Optional[SigError]:
    """Check for displayed images in a signature"""
    wikitext = mwph.parse(sig)
    for link in wikitext.ifilter_wikilinks():
        title = link.title
        # if it starts with :, it's not a displayed image
        if title.startswith(":"):
            continue
        # Can't interwiki transclude an image, so the extra safety
        # in check_links isn't required
        ns, sep, page = title.partition(":")
        if not sep:
            continue
        if datasources.normal_name(ns) in sitedata.file:
            return SigError.IMAGES
    else:
        return None


def check_transclusion(sig: str, sitedata: SiteData) -> Optional[SigError]:
    """Checks for template or parser function transclusion in the sig"""
    wikitext = mwph.parse(sig)
    for templ in wikitext.ifilter_templates():
        title = str(templ.name)
        for subst in sitedata.subst:
            # {{!}} isn't actually a template, it's a parser function that
            # is used to escape pipes and should never be subst'd.
            if title.startswith(subst) or title == "!":
                break
        else:
            return SigError.TRANSCLUSION

    return None


def check_post_subst_length(sig: str, sitedata: SiteData) -> Optional[SigError]:
    """Checks for long signatures after substitution"""

    # if the wikitext is already long, don't bother.
    if check_length(sig) is not None:
        return None

    # if the wikitext doesn't have a template, don't bother.
    if "{" not in sig:
        return None
    new_wikitext = evaluate_subst(sig, sitedata)
    if new_wikitext == sig:
        return None
    elif not new_wikitext:
        return None
    elif check_length(new_wikitext) is not None:
        return SigError.SUBST_LENGTH
    else:
        return None


def check_impersonation(sig: str, user: str, sitedata: SiteData) -> Optional[SigError]:
    wikitext = mwph.parse(sig)
    problem = False
    for link in wikitext.ifilter_wikilinks():
        if not link.text:
            continue
        text = datasources.normal_name(link.text)
        if compare_links(user, sitedata, link) is True:
            if text == datasources.normal_name(user):
                # one link matches, that's good enough
                break
            elif datasources.check_user_exists(text, sitedata):
                problem = True

    if problem:
        return SigError.LINK_NAME
    else:
        return None


def check_pipes(sig: str) -> Optional[SigError]:
    wikitext = mwph.parse(sig)
    for text in wikitext.ifilter_text():
        if "|" in text:
            return SigError.FREE_PIPES

    return None


def check_extlinks(sig: str) -> Optional[SigError]:
    wikitext = mwph.parse(sig)
    if wikitext.filter_external_links():
        return SigError.EXTLINKS
    return None


def check_bad_tags(sig: str, bad_tags: Set[str]) -> bool:
    wikitext = mwph.parse(sig)
    tags = {str(t.tag).strip() for t in wikitext.ifilter_tags()}
    return not tags.isdisjoint(bad_tags)


def check_line_breaks(sig: str) -> Optional[SigError]:
    if "\n" in sig or check_bad_tags(sig, {"br", "p", "div"}):
        return SigError.BREAKS
    return None


def check_hrule(sig: str) -> Optional[SigError]:
    if "----" in sig or check_bad_tags(sig, {"hr"}):
        return SigError.HRULE
    return None


def batch_check_lint(
    accumulate: Dict[str, str],
    resultdata: Dict[str, Dict[str, Union[str, List[SigError]]]],
    sitedata: SiteData,
    checks: Checks,
) -> Tuple[Dict[str, str], Dict[str, Dict[str, Union[str, List[SigError]]]]]:
    logger.debug("Contstructing batched request to linter")
    batch = "\n\n".join(accumulate.values())
    lint_errors = get_lint_errors(batch, sitedata, checks)
    if lint_errors:
        # At least one signature has errors. Check them all individually
        userlist = list(accumulate.keys())
        count = 0
        for auser in userlist:
            asig = accumulate.pop(auser)
            indiv_lints = get_lint_errors(asig, sitedata, checks)
            if indiv_lints:
                resultdata.setdefault(auser, {})
                cast(
                    List[Optional[SigError]],
                    resultdata[auser].setdefault("errors", []),
                ).extend(list(indiv_lints))
                resultdata[auser].setdefault("signature", asig)
                count += 1
        logger.debug(f"{count} users with errors found in batch")
    else:
        logger.debug("No errors in batch")
        accumulate = {}

    return accumulate, resultdata


def main(
    hostname: str,
    lastedit: str = "",
    days: int = 30,
    checks: datatypes.Checks = datatypes.Checks.DEFAULT,
    data: Optional[Union[Dict[str, str], List[str]]] = None,
) -> Optional[Dict]:
    """Site-level report mode: Iterate over signatures and check for errors"""
    logger.info(f"Processing signatures for {hostname}")
    total = 0

    sitedata = datasources.get_site_data(hostname)
    dbname = sitedata.dbname

    if data is None:
        sigsource = datasources.iter_active_user_sigs(dbname, lastedit, days)
    elif isinstance(data, list):
        sigsource = datasources.iter_listed_user_sigs(data, dbname)
    elif isinstance(data, dict):
        sigsource = data.items()  # type: ignore
    else:
        raise TypeError(
            "Data is of type %s when None, list, or dict expected" % (type(data))
        )

    resultdata: Dict[str, Dict[str, Union[str, List[SigError]]]] = {}
    accumulate = {}
    for user, sig in sigsource:
        total += 1
        if not sig:
            continue
        try:
            errors = check_sig(
                user, sig, sitedata, hostname, checks=checks ^ Checks.LINT
            )
            if SigError.PLAIN_FANCY_SIG not in errors:
                accumulate[user] = evaluate_subst(sig, sitedata)
        except Exception:
            logger.error(f"Processing User:{user}: {sig}")
            raise
        if errors:
            resultdata[user] = {"signature": sig, "errors": list(errors)}
        # Batch requests to lint, since network requests are slow
        # There is probably a better way to do this with async, but
        # that's more work.
        if len(accumulate) >= 5:
            accumulate, resultdata = batch_check_lint(
                accumulate, resultdata, sitedata, checks
            )

    # Catch any sigs that didn't get linted
    if accumulate:
        accumulate, resultdata = batch_check_lint(
            accumulate, resultdata, sitedata, checks
        )

    # Collect stats, and generate json file
    stats = {}
    stats["total"] = len(resultdata)
    for user, line in resultdata.items():
        line["errors"] = [error.value for error in cast(List[SigError], line["errors"])]  # type: ignore
        for error in line.get("errors", []):
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

    outdata = {
        "errors": stats,
        "meta": meta,
        "sigs": {key: resultdata[key] for key in sorted(resultdata)},
    }

    return outdata


def handle_args(args=sys.argv[1:]):
    check_flags = Checks.__members__
    parser = argparse.ArgumentParser(prog=__file__)
    parser.add_argument("hostnames", nargs="+", help="Hostnames of sites to check.")
    inputsources = parser.add_mutually_exclusive_group()
    inputsources.add_argument(
        "--days",
        type=int,
        default=30,
        help="Only check signatures for users with edits in the last DAYS days",
    )
    parser.add_argument(
        "--checks",
        default=[Checks.DEFAULT],
        type=lambda flag: check_flags[flag.upper()],
        # action="extend",  # removed, not supported until py 3.8
        nargs="+",
        metavar="CHECK",
        help=(
            "List of checks to run on the signatures. Must be at least one of ("
            + ", ".join(f"'{flag.lower()}'" for flag in check_flags.keys())
            + ")."
        ),
    )
    inputsources.add_argument(
        "--input",
        type=argparse.FileType("r"),
        help="JSON file to read user and signature data from "
        "instead of querying the database.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=[""],
        help="Output files or directory. "
        "If output files are specified, a filename must be specified for each site. "
        "If a directory is specified, a <hostname>.json file will be created for "
        "each site. The default location is a data/ directory one directory above "
        "the script.",
        nargs="+",
        # action="extend",  # removed, not supported until py 3.8
    )
    parser.add_argument(
        "--overwrite",
        action="store_const",
        const=True,
        help="Overwrite output files if they already exist (default).",
    )
    parser.add_argument(
        "--no-overwrite",
        action="store_const",
        const=False,
        dest="overwrite",
        help="Do not overwrite existing files",
    )
    args = parser.parse_args(args)

    kwargs = dict(
        days=args.days,
        checks=functools.reduce(operator.or_, args.checks),
        data=json.load(args.input) if args.input else None,
    )
    if len(args.output) == len(args.hostnames):
        outputs = args.output
    elif len(args.output) == 1 and not args.output[0].endswith(".json"):
        # One output location, use for all sites.
        outputs = itertools.repeat(args.output[0], len(args.hostnames))
    else:
        raise ValueError("Number of sites and number of output files does not match")
    if isinstance(kwargs["data"], dict) and len(args.hostnames) != 1:
        raise ValueError(
            "If multiple sites are given, input data must not include signatures"
        )

    for hostname, output in zip(args.hostnames, outputs):
        result = main(hostname, **kwargs)
        with output_file(
            output, hostname, (args.overwrite if args.overwrite is not None else True)
        ) as f:
            json.dump(result, f)


def output_file(output: Optional[str], hostname: str, overwrite: bool) -> TextIO:
    if output == "-":
        return sys.stdout
    else:
        if not output:
            out_dir = (
                pathlib.Path(__file__)
                .resolve(strict=True)
                .parent.parent.joinpath("data")
            )
        else:
            path = pathlib.Path(output)
            if path.is_dir():
                out_dir = path.resolve(strict=True)
            else:
                return path.open("w") if overwrite else path.open("x")

        out_file = out_dir.joinpath(f"{hostname}.json")
        return out_file.open("w") if overwrite else out_file.open("x")


if __name__ == "__main__":
    logging.basicConfig(
        format="%(asctime)s %(levelname)s:%(name)s:%(message)s",
        level=getattr(logging, os.environ.get("LOGLEVEL", "DEBUG").upper()),
    )
    mail = logging.handlers.SMTPHandler(
        "mail.tools.wmflabs.org",
        "tools.signatures@tools.wmflabs.org",
        ["tools.signatures@tools.wmflabs.org"],
        "signatures.sigprobs error",
    )
    mail.setLevel(logging.ERROR)
    logging.getLogger("").addHandler(mail)
    logger = logging.getLogger("sigprobs")

    handle_args()
else:
    logger = logging.getLogger(__name__)
