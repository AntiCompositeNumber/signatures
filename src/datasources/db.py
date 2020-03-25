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

import pymysql
import datetime
import toolforge
import logging
from datatypes import UserProps
from typing import Iterator, Tuple, Dict, List, cast, Any

logger = logging.getLogger(__name__)


def wmcs() -> bool:
    try:
        f = open("/etc/wmcs-project")
    except FileNotFoundError:
        return False
    else:
        f.close()
        return True


def iter_active_user_sigs(
    dbname: str, startblock: int = 0, lastedit: str = None, days: int = 365
) -> Iterator[Tuple[str, str]]:
    """Get usernames and signatures from the replica database"""
    if lastedit is None:
        lastedit = (
            datetime.datetime.utcnow() - datetime.timedelta(days=days)
        ).strftime("%Y%m%d%H%M%S")
    conn = toolforge.connect(f"{dbname}_p", cluster="analytics")
    with cast(
        pymysql.cursors.SSCursor, conn.cursor(cursor=pymysql.cursors.SSCursor),
    ) as cur:

        # Break query into 100 queries paginated by last digits of user id
        for i in range(startblock, 100):
            cur.execute(
                """
                SELECT user_name, up_value
                FROM
                    user_properties
                    JOIN `user` ON user_id = up_user
                WHERE
                    RIGHT(up_user, 2) = %s AND
                    up_property = "nickname" AND
                    user_name IN (SELECT actor_name
                                  FROM revision_userindex
                                  JOIN actor_revision ON rev_actor = actor_id
                                  WHERE rev_timestamp > %s) AND
                    up_user IN (SELECT up_user
                                FROM user_properties
                                WHERE up_property = "fancysig" AND up_value = 1) AND
                    up_value != user_name
                ORDER BY up_user ASC""",
                args=(str(i), lastedit),
            )
            logger.info(f"Block {i}")
            for username, signature in cast(
                Iterator[Tuple[bytes, bytes]], cur.fetchall_unbuffered()
            ):
                yield username.decode(encoding="utf-8"), signature.decode(
                    encoding="utf-8"
                )


def get_user_properties(user: str, dbname: str) -> UserProps:
    """Get signature and fancysig values for a user from the replica db"""
    logger.info("Getting user properties")
    conn = toolforge.connect(f"{dbname}_p")
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT up_property, up_value
            FROM
                user_properties
            WHERE
                up_user = (SELECT user_id
                           FROM `user`
                           WHERE user_name = %s)
            """,
            (user),
        )
        resultset = cast(List[Tuple[bytes, bytes]], cur.fetchall())
    logger.debug(resultset)

    data: Dict[str, str] = {
        key.decode("utf-8"): value.decode("utf-8") for key, value in resultset
    }
    return UserProps(
        nickname=data.get("nickname", ""), fancysig=bool(int(data.get("fancysig", "0")))
    )


def iter_listed_user_sigs(userlist: list, dbname: str) -> Iterator[Tuple[str, str]]:
    """Iterate users and signatures from a list of usernames"""
    for user in userlist:
        props = get_user_properties(user, dbname)
        if props.fancysig and props.nickname:
            yield user, props.nickname


def do_db_query(db_name: str, query: str, **kwargs) -> Any:
    """Uses the toolforge library to query the replica databases"""
    if not wmcs():
        raise ConnectionError("Not running on Toolforge, database unavailable")

    conn = toolforge.connect(db_name)
    with conn.cursor() as cur:
        cur.execute(query, kwargs)
        res = cur.fetchall()
    return res


def get_sitematrix() -> Iterator[str]:
    """Try to get the sitematrix from the db, falling back to the API"""
    query = "SELECT url FROM meta_p.wiki WHERE is_closed = 0;"
    try:
        sitematrix = do_db_query("meta_p", query)

        for site in sitematrix:
            yield site[0].rpartition("//")[2]
    except ConnectionError:
        return [""]


def check_user_exists(dbname: str, user: str) -> bool:
    query = "SELECT user_id FROM `user` WHERE user_name = %(user)s"
    res = do_db_query(dbname, query, user=user)
    return bool(res)
