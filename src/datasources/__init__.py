#!/usr/bin/env python3
# coding: utf-8
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright 2020 AntiCompositeNumber

from datatypes import SiteData
from . import api, db
from .api import *  # noqa: F403, F401
from .db import *  # noqa: F403, F401
from typing import Union
from mwparserfromhell.string_mixin import StringMixIn
import pymysql


def normal_name(name: Union[str, StringMixIn]) -> str:
    """Make first letter uppercase and replace spaces with underscores"""
    if name == "":
        return ""
    name = str(name)
    return (name[0].upper() + name[1:]).replace(" ", "_")


def check_user_exists(user: str, sitedata: SiteData) -> bool:
    """Check if a user exists on the given wiki.

    Uses database if available, falling back to the API if not.
    """
    try:
        result = db._check_user_exists(user, sitedata.dbname)
    except (ConnectionError, pymysql.err.OperationalError):
        result = api._check_user_exists(user, sitedata.hostname)
    return result


def get_sitematrix():
    """Get list of domains for Wikimedia site matrix

    Uses database if available, falling back to the API if not.
    """
    try:
        result = list(db._get_sitematrix())
    except (ConnectionError, pymysql.err.OperationalError):
        result = list(api._get_sitematrix())
    return result
