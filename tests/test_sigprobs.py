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
import json
import os
import sys

sys.path.append(os.path.realpath(os.path.dirname(__file__) + "/../src"))
import sigprobs  # noqa: E402
from datatypes import SigError, Checks  # noqa: E402
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


def test_check_tildes_fallthrough():
    mock_subst = mock.Mock(side_effect=[f"{{{{{i}}}}}" for i in range(0, 6)])
    with mock.patch("sigprobs.evaluate_subst", mock_subst):
        errors = sigprobs.check_tildes("{}", None, "")
    assert errors == SigError.COMPLEX_TEMPL


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
        ("[[Foo]] [[meta:foo/bar]] [[{user}:Example]]", None),
        ("[[:{user}:Example]]", None),
        ("[[Special:Log/Example]]", SigError.NO_USER_LINKS),
        ("[[{contribs}/Example2]]", SigError.LINK_USER_MISMATCH),
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
        ("[[Foo]] [[{user}:(:Example:)]]", None),
        ("[[:{user}:(:Example:)]]", None),
        ("[[Foo]]", SigError.NO_USER_LINKS),
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


def test_main(site):
    mock_linter = mock.Mock(return_value=set())
    data = {f"Example{i}": f"[[{site['user']}:Example{i}]]" for i in range(0, 3)}
    data["Example1"] = "''Example1''"
    with mock.patch("sigprobs.get_lint_errors", mock_linter):
        resultdata = sigprobs.main(site["domain"], data=data)

    assert resultdata["errors"].pop("total") == 1
    assert resultdata["errors"].pop(SigError.NO_USER_LINKS.value) == 1
    assert not resultdata["errors"]

    assert resultdata["meta"].pop("site") == site["domain"]
    assert resultdata["meta"].pop("last_update")
    assert resultdata["meta"].pop("active_since")
    assert resultdata["sigs"].pop("Example1") == {
        "signature": data["Example1"],
        "errors": [SigError.NO_USER_LINKS.value],
    }


@pytest.mark.parametrize("count", [10, 3])
def test_main_accumulate(site, count):
    mock_linter = mock.Mock(
        side_effect=lambda asig, host: {SigError.MISSING_END_TAG}
        if "Example2" in asig
        else set()
    )
    data = {f"Example{i}": f"[[{site['user']}:Example{i}]]" for i in range(0, count)}
    data["Example2"] = "<i>[[User:Example2]]'''"
    with mock.patch("sigprobs.get_lint_errors", mock_linter):
        resultdata = sigprobs.main(site["domain"], data=data)
    assert resultdata["errors"].pop("total") == 1
    assert resultdata["errors"].pop("missing-end-tag") == 1
    assert not resultdata["errors"]

    assert resultdata["meta"].pop("site") == site["domain"]
    assert resultdata["meta"].pop("last_update")
    assert resultdata["meta"].pop("active_since")

    e5 = resultdata["sigs"].pop("Example2")
    assert e5 == {
        "signature": data["Example2"],
        "errors": [SigError.MISSING_END_TAG.value],
    }


def test_main_none(site):
    mock_linter = mock.Mock(return_value=set())
    data = {f"Example{i}": f"[[{site['user']}:Example{i}]]" for i in range(0, 5)}
    with mock.patch("sigprobs.get_lint_errors", mock_linter):
        resultdata = sigprobs.main(site["domain"], data=data)

    assert resultdata["errors"].pop("total") == 0
    assert not resultdata["errors"]

    assert resultdata["meta"].pop("site") == site["domain"]
    assert resultdata["meta"].pop("last_update")
    assert resultdata["meta"].pop("active_since")
    assert not resultdata["sigs"]
    mock_linter.assert_called_once()


@mock.patch("datasources.iter_active_user_sigs", return_value=[])
@mock.patch("datasources.iter_listed_user_sigs", return_value=[])
def test_main_sigsource(listed, active):
    # breakpoint()
    sigprobs.main("en.wikipedia.org", data=None)
    active.assert_called_once()
    listed.assert_not_called()
    active.reset_mock()
    listed.reset_mock()

    sigprobs.main("en.wikipedia.org", data=[])
    listed.assert_called_once()
    active.assert_not_called()
    active.reset_mock()
    listed.reset_mock()

    fakedict = mock.MagicMock(return_value=[], __class__=dict)
    sigprobs.main("en.wikipedia.org", data=fakedict)
    listed.assert_not_called()
    active.assert_not_called()
    fakedict.items.assert_called_once()

    with pytest.raises(TypeError):
        sigprobs.main("en.wikipedia.org", data="Foo")
    listed.assert_not_called()
    active.assert_not_called()


def test_main_skipemptysig():
    with mock.patch("sigprobs.check_sig") as m:
        sigprobs.main("en.wikipedia.org", data={"foo": ""})
        m.assert_not_called()


@mock.patch("sigprobs.check_links", return_value=mock.sentinel.check_links)
@mock.patch("sigprobs.check_length", return_value=mock.sentinel.check_length)
@mock.patch("sigprobs.check_fanciness", return_value=mock.sentinel.check_fanciness)
@mock.patch("sigprobs.get_lint_errors", return_value={mock.sentinel.lint_errors, None})
@mock.patch("sigprobs.check_tildes", return_value=mock.sentinel.check_tildes)
def test_check_sig(site, sitedata, *args):
    errors = sigprobs.check_sig("", "", sitedata, site["domain"])
    for function in args:
        function.assert_called_once
    assert set(function.return_value for function in args) == errors


@pytest.mark.parametrize(
    "flags,sentinels",
    [
        (Checks.LINKS, {mock.sentinel.check_links}),
        (Checks.LENGTH, {mock.sentinel.check_length}),
        (Checks.FANCY, {mock.sentinel.check_fanciness}),
        (Checks.LINT, {mock.sentinel.lint_errors}),
        (Checks.NESTED_SUBST, {mock.sentinel.check_tildes}),
        (
            Checks.DEFAULT ^ Checks.LINT,
            {
                mock.sentinel.check_links,
                mock.sentinel.check_length,
                mock.sentinel.check_fanciness,
            },
        ),
    ],
)
def test_check_sig_flags(flags, sentinels, site, sitedata):
    with mock.patch("sigprobs.check_links", return_value=mock.sentinel.check_links):
        with mock.patch(
            "sigprobs.check_length", return_value=mock.sentinel.check_length
        ):
            with mock.patch(
                "sigprobs.check_fanciness", return_value=mock.sentinel.check_fanciness
            ):
                with mock.patch(
                    "sigprobs.get_lint_errors",
                    return_value={mock.sentinel.lint_errors, None},
                ):
                    with mock.patch(
                        "sigprobs.check_tildes", return_value=mock.sentinel.check_tildes
                    ):
                        errors = sigprobs.check_sig(
                            "Example", "{{foo}}", sitedata, site["domain"], checks=flags
                        )
    assert sentinels == errors


@mock.patch("sigprobs.check_fanciness", return_value=mock.sentinel.check_fanciness)
@mock.patch("sigprobs.get_lint_errors", return_value={mock.sentinel.lint_errors, None})
def test_check_sig_shortcircuit(site, sitedata):
    errors = sigprobs.check_sig(
        "Example",
        "{{foo}}",
        sitedata,
        site["domain"],
        checks=Checks.LINT | Checks.FANCY,
    )
    assert errors == {mock.sentinel.check_fanciness}
    sigprobs.get_lint_errors.assert_not_called


def devnull():
    with open(os.devnull, "a") as f:
        yield f


@pytest.mark.parametrize(
    "cliargs,margs,ofargs",
    [
        (
            ["en.wikipedia.org", "--days", "60"],
            [mock.call("en.wikipedia.org", days=60, checks=Checks.DEFAULT, data=None)],
            [mock.call("", "en.wikipedia.org", False)],
        ),
        (
            ["en.wikipedia.org", "--checks", "lint", "links"],
            [
                mock.call(
                    "en.wikipedia.org",
                    days=30,
                    checks=Checks.LINT | Checks.LINKS,
                    data=None,
                )
            ],
            [mock.call("", "en.wikipedia.org", False)],
        ),
        (
            ["en.wikipedia.org", "--output", "data.json"],
            [mock.call("en.wikipedia.org", days=30, checks=Checks.DEFAULT, data=None)],
            [mock.call("data.json", "en.wikipedia.org", False)],
        ),
        (
            ["en.wikipedia.org", "--output", "data.json", "--overwrite"],
            [mock.call("en.wikipedia.org", days=30, checks=Checks.DEFAULT, data=None)],
            [mock.call("data.json", "en.wikipedia.org", True)],
        ),
        (
            ["de.wikipedia.org", "en.wikipedia.org", "--output", "de.json", "en.json"],
            [
                mock.call(
                    "de.wikipedia.org", days=30, checks=Checks.DEFAULT, data=None
                ),
                mock.call(
                    "en.wikipedia.org", days=30, checks=Checks.DEFAULT, data=None
                ),
            ],
            [
                mock.call("de.json", "de.wikipedia.org", False),
                mock.call("en.json", "en.wikipedia.org", False),
            ],
        ),
    ],
)
def test_handle_args(cliargs, margs, ofargs):
    output_file = mock.MagicMock(__enter__=devnull())
    main = mock.MagicMock(return_value="")
    with mock.patch("sigprobs.output_file", output_file):
        with mock.patch("sigprobs.main", main):
            sigprobs.handle_args(cliargs)

    assert output_file.call_args_list == ofargs
    assert main.call_args_list == margs


@pytest.mark.parametrize("data", [{"foo": "bar"}, ["baz", "bin"]])
def test_handle_args_input(tmp_path, data):
    path = tmp_path / "data.json"
    with path.open("w") as f:
        json.dump(data, f)
    cliargs, kwargs, ofargs = (
        ["en.wikipedia.org", "--input", str(path)],
        {"days": 30, "checks": Checks.DEFAULT, "data": data},
        ("", "en.wikipedia.org", False),
    )
    output_file = mock.MagicMock(__enter__=devnull())
    main = mock.MagicMock(return_value="")
    with mock.patch("sigprobs.output_file", output_file):
        with mock.patch("sigprobs.main", main):
            sigprobs.handle_args(cliargs)

    output_file.assert_called_with(*ofargs)
    main.assert_called_with("en.wikipedia.org", **kwargs)


@pytest.mark.parametrize(
    "args,data,expected",
    [
        # (["en.wikipedia.org", "--input", "%(path)s"], {"foo": "bar"}, ValueError),
        (
            ["en.wikipedia.org", "--input", "%(path)s", "--days", "60"],
            {"foo": "bar"},
            SystemExit,
        ),
        (
            ["en.wikipedia.org", "de.wikipedia.org", "--input", "%(path)s"],
            {"foo": "bar"},
            ValueError,
        ),
    ],
)
def test_handle_args_input_validation(args, data, expected, tmp_path):
    path = tmp_path / "data.json"
    with path.open("w") as f:
        json.dump(data, f)

    args = [arg % dict(path=str(path)) for arg in args]
    output_file = mock.MagicMock(__enter__=devnull())
    main = mock.MagicMock(return_value="")
    with mock.patch("sigprobs.output_file", output_file):
        with mock.patch("sigprobs.main", main):
            with pytest.raises(expected):
                sigprobs.handle_args(args)


@pytest.mark.parametrize(
    "args,expected",
    [
        (["en.wikipedia.org", "de.wikipedia.org", "--output", "en.json"], ValueError),
        (["en.wikipedia.org", "--output", "en.json", "de.json"], ValueError),
        ([], SystemExit),
    ],
)
def test_handle_args_validation(args, expected):
    output_file = mock.MagicMock(__enter__=devnull())
    main = mock.MagicMock(return_value="")
    with mock.patch("sigprobs.output_file", output_file):
        with mock.patch("sigprobs.main", main):
            with pytest.raises(expected):
                sigprobs.handle_args(args)
