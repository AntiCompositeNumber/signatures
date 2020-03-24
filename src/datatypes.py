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

from typing import NamedTuple, Set, List


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
