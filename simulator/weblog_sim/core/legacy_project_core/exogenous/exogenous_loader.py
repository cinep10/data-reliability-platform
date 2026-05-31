from __future__ import annotations

import pymysql


class ExogenousTimelineLoader:
    def __init__(self, host: str, port: int, user: str, password: str, db: str):
        self.conn = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=db,
            charset="utf8mb4",
            autocommit=True,
            cursorclass=pymysql.cursors.DictCursor,
        )

    def get_hour_state(self, profile_id: str, dt: str, hh: int) -> dict:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM exogenous_state_timeline
                WHERE profile_id=%s
                  AND dt=%s
                  AND hh=%s
                """,
                (profile_id, dt, hh),
            )
            row = cur.fetchone()
        return row or {}

    def close(self) -> None:
        self.conn.close()
