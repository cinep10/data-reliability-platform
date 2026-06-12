from __future__ import annotations

from datetime import timedelta, timezone
from pathlib import Path
from typing import Dict

import yaml

from .store_base import LogFormatMeta, MetaStore


class FileMetaStore(MetaStore):
    def __init__(self, path: str):
        self.path = Path(path)
        self.payload: Dict = {}
        if self.path.exists():
            self.payload = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}

    def get(self, site_key: str) -> LogFormatMeta:
        tz_offset_min = int(self.payload.get("tz_offset_min", 540))
        tz = timezone(timedelta(minutes=tz_offset_min))
        return LogFormatMeta(
            site_key=str(self.payload.get("site_key", site_key)),
            tz=tz,
            http_version=str(self.payload.get("http_version", "HTTP/1.1")),
            template=str(self.payload.get("template", LogFormatMeta().template)),
        )
