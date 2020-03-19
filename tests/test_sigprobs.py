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


import pytest
import unittest.mock as mock

import src.sigprobs as sigprobs  # noqa :E402


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
    data = sigprobs.get_site_data(site["domain"])
    return data


@pytest.mark.parametrize(
    "sig,expected",
    [
        (
            '<font face="arial, helvetica" size="1"><sub>'
            "[[{user}:Example]]</sub></font>",
            {"obsolete-font-tag"},
        ),
        ("<i>Example''", {"missing-end-tag"}),
        (
            """[[{user}:Example|'''<span style="color:#FFFFFF">Example''']]</span>""",
            {"misnested-tag"},
        ),
        ("<tt>[[{user}:Example|Example]]</tt>", {"obsolete-tag"}),
        ("[[{user}:Example|Example]] ([[{talk}:Example|talk]])", set()),
    ],
)
def test_get_lint_errors(sig, expected, site):
    errors = sigprobs.get_lint_errors(sig.format(**site), site["domain"])
    assert errors == expected


@pytest.mark.parametrize(
    "sig,expected",
    [
        ("~~~~", "nested-subst"),
        ("%(user)s:Example", ""),
        ("~~{{%(subst)s:1x{{%(subst)s:1x|{{%(subst)s:!}}}}}}~~", "nested-subst"),
        ("&ndash;&nbsp;[[%(user)s:Foo {{%(subst)s:ampersand}} Bar]]", "")
    ],
)
def test_check_tildes(sig, expected, sitedata, site):
    errors = sigprobs.check_tildes(sig % site, sitedata, site["domain"])
    assert errors == expected


@pytest.mark.parametrize(
    "sig,expected",
    [
        ("[[{user}:Example]]", ""),
        ("[[{talk}:Example]]", ""),
        ("[[{contributions}/Example]]", ""),
        ("[[{contribs}/Example]]", ""),
        ("{user}:Example", "no-user-links"),
        ("[[{user}:Example2|Example]]", "link-username-mismatch"),
        ("[[meta:{user}:Example|Example]]", "interwiki-user-link"),
    ],
)
def test_check_links(sig, expected, sitedata, site):
    error = sigprobs.check_links(
        "Example", sig.format(**site), sitedata, site["domain"]
    )
    assert error == expected


@pytest.mark.parametrize(
    "sig,expected", [("{user}:Example", "no-user-links"), ("[[{user}:Example]]", "")]
)
def test_check_links_expansion(sig, expected, sitedata, site):
    mock_subst = mock.Mock()
    mock_subst.return_value = sig.format(**site)
    with mock.patch("src.sigprobs.evaluate_subst", mock_subst):
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
        ("Example", "plain-fancy-sig"),
        ("[[{user}:Example]]", ""),
        ("'''Example'''", ""),
        ("<span>Example</span>", ""),
        ("{{{{{subst}:{user}:Example/sig}}}}", ""),
    ],
)
def test_check_fanciness(sig, expected):
    error = sigprobs.check_fanciness(sig)
    assert error == expected


@pytest.mark.parametrize(
    "sig,expected",
    [("a" * 200, ""), ("a" * 265, "sig-too-long"), ("a" * 255, "")],
    ids=["200", "265", "255"],
)
def test_check_length(sig, expected):
    error = sigprobs.check_length(sig)
    assert error == expected
