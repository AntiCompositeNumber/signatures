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
import sys
import os

# import urllib.parse
# from bs4 import BeautifulSoup  # type: ignore

sys.path.append(os.path.realpath(os.path.dirname(__file__) + "/../src"))
# import app  # noqa: E402
# import sigprobs  # noqa: E402
import datasources  # noqa: E402


@pytest.fixture(
    scope="module", params=[dict(domain="en.wikipedia.org", dbname="enwiki")],
)
def site(request):
    return request.param


@pytest.fixture(scope="module")
def sitedata(site):
    data = datasources.get_site_data(site["domain"])
    return data


def test_wmcs_true():
    m = mock.mock_open(read_data="toolforge")
    with mock.patch("datasources.db.open", m):
        assert datasources.wmcs() is True
    m.assert_called_once_with("/etc/wmcs-project")
    m().close.assert_called_once


def test_wmcs_false():
    assert datasources.wmcs() is False


def test_do_db_query_nodb():
    m = mock.Mock(return_value=False)
    with mock.patch("datasources.wmcs", m):
        with pytest.raises(ConnectionError):
            datasources.do_db_query("meta_p", "")


@mock.patch("datasources.db.wmcs", return_value=True)
def test_do_db_query(wmcs):
    cur = mock.MagicMock()
    cur.fetchall.return_value = mock.sentinel.fetchall
    conn = mock.MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    connect = mock.MagicMock(return_value=conn)
    with mock.patch("toolforge.connect", connect):
        res = datasources.do_db_query(
            mock.sentinel.db_name, mock.sentinel.query, foo="bar"
        )

    assert res is mock.sentinel.fetchall
    connect.assert_called_once_with(mock.sentinel.db_name)
    conn.cursor.assert_called_once()
    cur.execute.assert_called_once_with(mock.sentinel.query, {"foo": "bar"})
    cur.fetchall.assert_called_once()


def test_db_get_sitematrix():
    test_data = [
        "en.wikipedia.org",
        "commons.wikimedia.org",
        "fr.wikipedia.org",
    ]
    mock_db_query = mock.Mock()
    mock_db_query.return_value = [("https://" + site,) for site in test_data]
    with mock.patch("datasources.db.do_db_query", mock_db_query):
        sitematrix = list(datasources.get_sitematrix())
    assert sitematrix == test_data

    mock_db_query.assert_called_once_with(
        "meta_p", "SELECT url FROM meta_p.wiki WHERE is_closed = 0;"
    )


def test_api_get_sitematrix():
    test_data = [
        "en.wikipedia.org",
        "commons.wikimedia.org",
        "fr.wikipedia.org",
    ]
    sitematrix = datasources.get_sitematrix()
    for site in test_data:
        assert site in sitematrix
    assert "otrs-wiki.wikimedia.org" not in sitematrix


@pytest.mark.parametrize(
    "user,expected", [("AntiCompositeNumber", True), ("AntiCompositeLetter", False)]
)
def test_api_check_user_exists(user, expected, sitedata):
    result = datasources.check_user_exists(user, sitedata)
    assert result is expected


@pytest.mark.parametrize(
    "user,expected", [("AntiCompositeNumber", True), ("AntiCompositeLetter", False)]
)
def test_db_check_user_exists(user, expected, sitedata):
    with mock.patch(
        "datasources.do_db_query", return_value=((12345,),) if expected else ()
    ):
        result = datasources.check_user_exists(user, sitedata)
    assert result is expected
