#!/usr/bin/env python3
# coding: utf-8
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright 2020 AntiCompositeNumber

import enum
from typing import NamedTuple, Set, List, Optional


def N_(text: str) -> str:
    """Translatable string marker"""
    return text


UserProps = NamedTuple("UserProps", [("nickname", str), ("fancysig", bool)])

SiteData = NamedTuple(
    "SiteData",
    [
        ("user", Set[str]),
        ("user_talk", Set[str]),
        ("file", Set[str]),
        ("special", Set[str]),
        ("contribs", Set[str]),
        ("subst", List[str]),
        ("dbname", str),
        ("hostname", str),
    ],
)


UserCheck = NamedTuple(
    "UserCheck",
    [
        ("site", str),
        ("username", str),
        ("errors", List),
        ("signature", str),
        ("failure", Optional[bool]),
        ("html_sig", str),
        ("replag", str),
    ],
)


class Checks(enum.Flag):
    """Enum of signature tests and test groups"""

    LINT = enum.auto()
    OBSOLETE_TAG = enum.auto()
    NESTED_SUBST = enum.auto()
    LINKS = enum.auto()
    LENGTH = enum.auto()
    FANCY = enum.auto()
    BREAKS = enum.auto()

    IMAGES = enum.auto()
    TRANSCLUSION = enum.auto()
    SUBST_LENGTH = enum.auto()
    LINK_NAME = enum.auto()
    FREE_PIPES = enum.auto()
    EXTLINKS = enum.auto()
    HRULE = enum.auto()

    DEFAULT = LINT | NESTED_SUBST | LINKS | LENGTH | FANCY | BREAKS | SUBST_LENGTH

    EXTENDED = (
        IMAGES | TRANSCLUSION | SUBST_LENGTH | LINK_NAME | FREE_PIPES | EXTLINKS | HRULE
    )


class Result(str, enum.Enum):
    def __new__(cls, value, desc="", test=None):
        obj = str.__new__(cls, [value])
        obj._value_ = value
        obj.desc = desc
        obj.test = test
        return obj


@enum.unique
class SigError(Result):
    """Enum of possible signature errors"""

    # Lint errors
    HTML5_MISNESTING = N_("html5-misnesting"), N_("html5-misnesting-help"), Checks.LINT
    MISC_TIDY = (
        N_("misc-tidy-replacement-issues"),
        N_("misc-tidy-replacement-issues-help"),
        Checks.LINT,
    )
    MISNESTED_TAG = N_("misnested-tag"), N_("misnested-tag-help"), Checks.LINT
    MISSING_END_TAG = N_("missing-end-tag"), N_("missing-end-tag-help"), Checks.LINT
    MULTIPLE_UNCLOSED = (
        N_("multiple-unclosed-formatting-tags"),
        N_("multiple-unclosed-formatting-tags-help"),
        Checks.LINT,
    )
    OBSOLETE_TAG = N_("obsolete-tag"), N_("obsolete-tag-help"), Checks.LINT
    OBSOLETE_FONT_TAG = (
        N_("obsolete-font-tag"),
        N_("obsolete-font-tag-help"),
        Checks.LINT,
    )
    SELF_CLOSED_TAG = N_("self-closed-tag"), N_("self-closed-tag-help"), Checks.LINT
    STRIPPED_TAG = N_("stripped-tag"), N_("stripped-tag-help"), Checks.LINT
    TIDY_FONT_BUG = N_("tidy-font-bug"), N_("tidy-font-bug-help"), Checks.LINT
    TIDY_WHITESPACE = (
        N_("tidy-whitespace-bug"),
        N_("tidy-whitespace-bug-help"),
        Checks.LINT,
    )
    WIKILINK_IN_EXTLINK = (
        N_("wikilink-in-extlink"),
        N_("wikilink-in-extlink-help"),
        Checks.LINT,
    )
    MULTI_COLON_ESCAPE = (
        N_("lint/multi-colon-escape"),
        N_("lint/multi-colon-escape-help"),
        Checks.LINT,
    )
    INLINE_MEDIA_CAPTION = (
        N_("inline-media-caption"),
        N_("inline-media-caption-help"),
        Checks.LINT,
    )
    BOGUS_IMAGE_OPTIONS = (
        N_("bogus-image-options"),
        N_("bogus-image-options-help"),
        Checks.LINT,
    )

    # Default set errors
    INTERWIKI_USER_LINK = (
        N_("interwiki-user-link"),
        N_("interwiki-user-link-help"),
        Checks.LINKS,
    )
    LINK_USER_MISMATCH = (
        N_("link-username-mismatch"),
        N_("link-username-mismatch-help"),
        Checks.LINKS,
    )
    NESTED_SUBST = N_("nested-subst"), N_("nested-subst-help"), Checks.NESTED_SUBST
    COMPLEX_TEMPL = (
        N_("complex-template"),
        N_("complex-template-help"),
        Checks.NESTED_SUBST,
    )
    NO_USER_LINKS = N_("no-user-links"), N_("no-user-links-help"), Checks.LINKS
    PLAIN_FANCY_SIG = N_("plain-fancy-sig"), N_("plain-fancy-sig-help"), Checks.FANCY
    SIG_TOO_LONG = N_("sig-too-long"), N_("sig-too-long-help"), Checks.LENGTH

    # Extended set errors
    IMAGES = N_("images-in-sig"), N_("images-in-sig-help"), Checks.IMAGES
    TRANSCLUSION = (
        N_("transcluded-templates"),
        N_("transcluded-templates-help"),
        Checks.TRANSCLUSION,
    )
    SUBST_LENGTH = (
        N_("sig-too-long-post-subst"),
        N_("sig-too-long-post-subst-help"),
        Checks.SUBST_LENGTH,
    )
    LINK_NAME = (
        N_("link-name-impersonation"),
        N_("link-name-impersonation-help"),
        Checks.LINK_NAME,
    )
    FREE_PIPES = N_("unescaped-pipes"), N_("unescaped-pipes-help"), Checks.FREE_PIPES
    EXTLINKS = N_("external-links"), N_("external-links-help"), Checks.EXTLINKS
    BREAKS = N_("line-breaks"), N_("line-breaks-help"), Checks.BREAKS
    HRULE = N_("horizontal-rule"), N_("horizontal-rule-help"), Checks.HRULE


class WebAppMessage(Result):
    DEFAULT_SIG = N_("default-sig"), N_("default-sig-help")
    NO_ERRORS = N_("no-errors"), N_("no-errors-help")
    SIG_NOT_FANCY = N_("sig-not-fancy"), N_("sig-not-fancy-help")
    USER_DOES_NOT_EXIST = N_("user-does-not-exist"), N_("user-does-not-exist-help")
