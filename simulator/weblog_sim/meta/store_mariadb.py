from __future__ import annotations

from datetime import timedelta, timezone
from typing import Any, Dict, Optional

import pymysql

from .store_base import LogFormatMeta, MetaStore


class MariaDBMetaStore(MetaStore):
    def __init__(self, db: Dict[str, Any], default_meta: Optional[LogFormatMeta] = None):
        self.db = db
        self.default_meta = default_meta or LogFormatMeta()

    def get(self, site_key: str) -> LogFormatMeta:
        try:
            conn = pymysql.connect(
                host=self.db["host"],
                port=int(self.db.get("port", 3306)),
                user=self.db["user"],
                password=self.db["password"],
                database=self.db["dbname"],
                charset="utf8mb4",
                autocommit=True,
                cursorclass=pymysql.cursors.DictCursor,
            )
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT site_key, template, http_version, tz_offset_min
                    FROM log_format_meta
                    WHERE site_key=%s AND enabled=1
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """,
                    (site_key,),
                )
                row = cur.fetchone()
            conn.close()
            if not row:
                return self.default_meta
            return LogFormatMeta(
                site_key=row.get("site_key", site_key),
                tz=timezone(timedelta(minutes=int(row.get("tz_offset_min", 540)))),
                http_version=row.get("http_version") or self.default_meta.http_version,
                template=row.get("template") or self.default_meta.template,
            )
        except Exception:
            return self.default_meta
