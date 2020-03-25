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


import pytest  # type: ignore
import unittest.mock as mock
import os
import sys

sys.path.append(os.path.realpath(os.path.dirname(__file__) + "/../src"))
import sigprobs  # noqa: E402
from datatypes import SigError  # noqa: E402
import datasources  # noqa: E402


@pytest.fixture(
    scope="module",
    params=[
        dict(
            domain="en.wikipedia.org",
            user="User",
            talk="User talk",
            contribs="Special:Contribs",
            contributions="Special:Contributions",
            subst="subst",
        ),
        dict(
            domain="de.wikipedia.org",
            user="Benutzerin",
            talk="Benutzerin Diskussion",
            contribs="Spezial:Beiträge",
            contributions="Special:Contributions",
            subst="ers",
        ),
    ],
)
def site(request):
    return request.param


@pytest.fixture(scope="module")
def sitedata(site):
    data = datasources.get_site_data(site["domain"])
    return data


@pytest.mark.parametrize(
    "sig,expected",
    [
        (
            '<font face="arial, helvetica" size="1"><sub>'
            "[[{user}:Example]]</sub></font>",
            {SigError("obsolete-font-tag")},
        ),
        ("<i>Example''", {SigError("missing-end-tag")}),
        (
            """[[{user}:Example|'''<span style="color:#FFFFFF">Example''']]</span>""",
            {SigError("misnested-tag")},
        ),
        ("<tt>[[{user}:Example|Example]]</tt>", {SigError("obsolete-tag")}),
        ("[[{user}:Example|Example]] ([[{talk}:Example|talk]])", set()),
    ],
)
def test_get_lint_errors(sig, expected, site):
    errors = sigprobs.get_lint_errors(sig.format(**site), site["domain"])
    assert errors == expected


@pytest.mark.parametrize(
    "sig,expected",
    [
        ("~~~~", SigError("nested-subst")),
        ("%(user)s:Example", None),
        (
            "~~{{%(subst)s:1x{{%(subst)s:1x|{{%(subst)s:!}}}}}}~~",
            SigError("nested-subst"),
        ),
        ("&ndash;&nbsp;[[%(user)s:Foo {{%(subst)s:ampersand}} Bar]]", None),
        ("{{subst:#switch:{{subst:REVISIONUSER}}|foo=Sig}}", None),
        ("{{subst:#switch:{{subst:REVISIONUSER}}|foo=~~~~}}", SigError("nested-subst")),
    ],
)
def test_check_tildes(sig, expected, sitedata, site):
    errors = sigprobs.check_tildes(sig % site, sitedata, site["domain"])
    assert errors == expected


@pytest.mark.parametrize(
    "sig,expected",
    [
        ("[[{user}:Example]]", None),
        ("[[{talk}:Example]]", None),
        ("[[{contributions}/Example]]", None),
        ("[[{contribs}/Example]]", None),
        ("{user}:Example", SigError("no-user-links")),
        ("[[{user}:Example2|Example]]", SigError("link-username-mismatch")),
        ("[[meta:{user}:Example|Example]]", SigError("interwiki-user-link")),
        ("[[meta:{user}:Example|Example]] ([[{talk}:Example|talk]])", None),
        ("[[meta:{contribs}/Example]]", SigError("interwiki-user-link")),
    ],
)
def test_check_links(sig, expected, sitedata, site):
    error = sigprobs.check_links(
        "Example", sig.format(**site), sitedata, site["domain"]
    )
    assert error == expected


@pytest.mark.parametrize(
    "sig,expected",
    [
        ("[[{user}:(:Example:)|(:Example:)]]", None),
        ("[[{contributions}/(:Example:)]]", None),
        ("[[meta:{user}:(:Example:)]]", SigError("interwiki-user-link")),
    ],
)
def test_check_links_colonuser(sig, expected, sitedata, site):
    error = sigprobs.check_links(
        "(:Example:)", sig.format(**site), sitedata, site["domain"]
    )
    assert error == expected


@pytest.mark.parametrize(
    "sig,expected",
    [("{user}:Example", SigError("no-user-links")), ("[[{user}:Example]]", None)],
)
def test_check_links_expansion(sig, expected, sitedata, site):
    mock_subst = mock.Mock()
    mock_subst.return_value = sig.format(**site)
    with mock.patch("sigprobs.evaluate_subst", mock_subst):
        error = sigprobs.check_links(
            "Example",
            "{{%(subst)s:%(user)s:Example/sig}}" % site,
            sitedata,
            site["domain"],
        )
    assert error == expected
    mock_subst.assert_called_once_with(
        "{{%(subst)s:%(user)s:Example/sig}}" % site, sitedata, site["domain"]
    )


@pytest.mark.parametrize(
    "sig,expected",
    [
        ("Example", SigError("plain-fancy-sig")),
        ("[[{user}:Example]]", None),
        ("'''Example'''", None),
        ("<span>Example</span>", None),
        ("{{{{{subst}:{user}:Example/sig}}}}", None),
    ],
)
def test_check_fanciness(sig, expected):
    error = sigprobs.check_fanciness(sig)
    assert error == expected


@pytest.mark.parametrize(
    "sig,expected",
    [("a" * 200, None), ("a" * 265, SigError("sig-too-long")), ("a" * 255, None)],
    ids=["200", "265", "255"],
)
def test_check_length(sig, expected):
    error = sigprobs.check_length(sig)
    assert error == expected
