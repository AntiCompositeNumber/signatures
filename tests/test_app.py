#!/usr/bin/env python3
# coding: utf-8
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright 2020 AntiCompositeNumber

import pytest  # type: ignore
import unittest.mock as mock
import sys
import os
import urllib.parse
from bs4 import BeautifulSoup  # type: ignore

sys.path.append(os.path.realpath(os.path.dirname(__file__) + "/../src"))
import app  # noqa: E402
from web import resources  # noqa: E402
import datatypes  # noqa: E402
import datasources  # noqa: E402

with app.app.app_context():
    translated = pytest.mark.skipif(
        len(app.babel.list_translations()) < 3,
        reason="No non-English translations to test with",
    )


@pytest.fixture(scope="module")
def flask_app():
    flask_app = app.create_app()[0]
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture
def client(flask_app):
    with flask_app.test_client() as client:
        yield client


@pytest.fixture(
    scope="module",
    params=[
        dict(
            domain="en.wikipedia.org",
            dbname="enwiki",
            user="User",
            talk="User talk",
            file="File",
            contribs="Special:Contribs",
            contributions="Special:Contributions",
            subst="subst",
        ),
    ],
)
def site(request):
    return request.param


@pytest.fixture(scope="module")
def sitedata(site):
    data = datasources.get_site_data(site["domain"])
    return data


def test_index(client):
    res = client.get("/")
    assert res.status_code == 200


def test_about(client):
    res = client.get("/about")
    assert res.status_code == 200


@translated
def test_uselang(client):
    en = client.get("/")
    en_soup = BeautifulSoup(en.data, "html.parser")
    en_lang = en_soup.find(id="currentLang").contents[0]
    assert en_lang == "English"

    fr = client.get("/?uselang=fr")
    fr_soup = BeautifulSoup(fr.data, "html.parser")
    fr_lang = fr_soup.find(id="currentLang").contents[0]
    assert fr_lang == "français"

    en2 = client.get("/")
    en_soup2 = BeautifulSoup(en2.data, "html.parser")
    en_lang2 = en_soup2.find(id="currentLang").contents[0]
    assert en_lang2 == "English"


@translated
def test_setlang(client):
    en = client.get("/")
    en_soup = BeautifulSoup(en.data, "html.parser")
    en_lang = en_soup.find(id="currentLang").contents[0]
    assert en_lang == "English"

    fr = client.get("/?setlang=fr", follow_redirects=True)
    fr_soup = BeautifulSoup(fr.data, "html.parser")
    fr_lang = fr_soup.find(id="currentLang").contents[0]
    assert fr_lang == "français"

    fr2 = client.get("/")
    fr_soup2 = BeautifulSoup(fr2.data, "html.parser")
    fr_lang2 = fr_soup2.find(id="currentLang").contents[0]
    assert fr_lang2 == "français"

    en2 = client.get("/?setlang=en", follow_redirects=True)
    en_soup2 = BeautifulSoup(en2.data, "html.parser")
    en_lang2 = en_soup2.find(id="currentLang").contents[0]
    assert en_lang2 == "English"


@mock.patch("datasources.get_sitematrix", return_value=[])
def test_check(get_sitematrix, client):
    req = client.get("/check")
    assert req.status_code == 200


def test_check_redirect(client):
    req = client.get(
        "/check?site=en.wikipedia.org&username=Example&sig=[[User:Example]]",
        follow_redirects=False,
    )
    assert 300 <= req.status_code < 400
    parsed = urllib.parse.urlparse(req.headers["Location"])
    assert parsed.path == "/check/en.wikipedia.org/Example"
    assert urllib.parse.parse_qs(parsed.query, strict_parsing=True) == {
        "sig": ["[[User:Example]]"]
    }


@pytest.mark.parametrize("badchar", ["#", "<", ">", "[", "]", "|", "{", "}", "/"])
def test_validate_username(badchar):
    with pytest.raises(ValueError):
        resources.validate_username(f"Example{badchar}User")


def test_validate_username_pass():
    resources.validate_username("Example")
    resources.validate_username("foo@bar.com")  # Grandfathered usernames have @


@pytest.mark.parametrize(
    "site,expected",
    [
        (
            "en.wikipedia.org",
            "[[User:user|nick]] ([[User talk:user|talk]])",
        ),
        (
            "eo.wikipedia.org",
            "[[Uzanto:user|nick]] ([[Uzanto-Diskuto:user|diskuto]])",
        ),
    ],
)
def test_get_default_sig(site, expected):
    sig = resources.get_default_sig(site, user="user", nickname="nick")

    assert sig == expected


@pytest.mark.parametrize("userid,expected", [(((12345,),), True), ((), False)])
def test_check_user_exists(userid, expected, site, sitedata):
    db_query = mock.Mock(return_value=userid)
    with mock.patch("datasources.db.do_db_query", db_query):
        exists = datasources.check_user_exists("Example", sitedata)
        assert expected == exists
    db_query.assert_called_once_with(site["dbname"], mock.ANY, user="Example")


@pytest.mark.parametrize(
    "sig,failure", [("[[User:Example]]", False), ("[[User:Example2]]", None)]
)
def test_check_user_passed(sig, failure, site, sitedata):
    data = resources.check_user("en.wikipedia.org", "example", sig)
    assert data.signature == sig
    assert data.failure is failure
    assert data.username == "Example"
    assert data.site == "en.wikipedia.org"


@pytest.mark.parametrize(
    "name,expected",
    [("Example", "Example"), ("example", "Example"), ("example_user", "Example user")],
)
def test_check_user_username(name, expected):
    data = resources.check_user("en.wikipedia.org", name, "[[User:Example]]")
    assert data.username == expected


@pytest.mark.parametrize(
    "props,failure,errors",
    [
        (
            datatypes.UserProps(nickname="[[User:Example]]", fancysig=True),
            False,
            datatypes.WebAppMessage.NO_ERRORS,
        ),
        (datatypes.UserProps(nickname="[[User:Example2]]", fancysig=True), None, ""),
        (
            datatypes.UserProps(nickname="Example2", fancysig=False),
            False,
            datatypes.WebAppMessage.SIG_NOT_FANCY,
        ),
    ],
)
def test_check_user_db(props, failure, errors):
    user_props = mock.Mock(return_value=props)
    with mock.patch("datasources.get_user_properties", user_props):
        data = resources.check_user("en.wikipedia.org", "Example")

    assert data.signature
    if errors:
        assert errors in data.errors
    assert data.failure is failure
    user_props.assert_called_once_with("Example", "enwiki")


@pytest.mark.parametrize(
    "exists,failure,errors",
    [
        (False, True, datatypes.WebAppMessage.USER_DOES_NOT_EXIST),
        (True, False, datatypes.WebAppMessage.DEFAULT_SIG),
    ],
)
def test_check_user_db_nosig(exists, failure, errors):
    user_props = mock.Mock(
        return_value=datatypes.UserProps(nickname="", fancysig=False)
    )
    user_exists = mock.Mock(return_value=exists)
    with mock.patch("datasources.get_user_properties", user_props):
        with mock.patch("datasources.check_user_exists", user_exists):
            data = resources.check_user("en.wikipedia.org", "Example")

    user_exists.assert_called_once_with("Example", mock.ANY)
    user_props.assert_called_once_with("Example", "enwiki")
    assert data.failure is failure
    assert errors in data.errors


@pytest.mark.parametrize(
    "wikitext,html",
    [
        (
            "[[User:Example]]",
            '<a rel="mw:WikiLink" '
            'href="https://en.wikipedia.org/wiki/User:Example" '
            'title="User:Example" id="mwAw">User:Example</a>',
        )
    ],
)
def test_get_rendered_sig(wikitext, html):
    assert resources.get_rendered_sig("en.wikipedia.org", wikitext) == html


@pytest.mark.skip
def test_check_result():
    pass


def test_report(client):
    listdir = mock.Mock(return_value=["foo.example.org.json"])
    with mock.patch("os.listdir", listdir):
        res = client.get("/reports")

    assert res.status_code == 200
    assert b"foo.example.org" in res.data
