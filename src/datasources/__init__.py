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

from datatypes import SiteData
from . import api, db
from .api import *  # noqa: F403, F401
from .db import *  # noqa: F403, F401
import pymysql


def normal_name(name: str) -> str:
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
