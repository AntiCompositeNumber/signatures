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

import enum
from typing import NamedTuple, Set, List, Optional


UserProps = NamedTuple("UserProps", [("nickname", str), ("fancysig", bool)])

SiteData = NamedTuple(
    "SiteData",
    [
        ("user", Set[str]),
        ("user_talk", Set[str]),
        ("special", Set[str]),
        ("contribs", Set[str]),
        ("subst", List[str]),
        ("dbname", str),
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
    ],
)


class Checks(enum.Flag):
    """Enum of signature tests and test groups"""

    LINT = enum.auto()
    NESTED_SUBST = enum.auto()
    LINKS = enum.auto()
    LENGTH = enum.auto()
    FANCY = enum.auto()
    DEFAULT = LINT | NESTED_SUBST | LINKS | LENGTH | FANCY
