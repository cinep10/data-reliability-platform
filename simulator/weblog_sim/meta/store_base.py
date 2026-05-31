from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta, timezone


@dataclass
class LogFormatMeta:
    site_key: str = "default"
    tz: timezone = timezone(timedelta(hours=9))
    http_version: str = "HTTP/1.1"
    template: str = '{ip} [{ts}] "{method} {path} {httpv}" {status} {bytes} "{ref}" "{ua}" "{kv}"'


class MetaStore:
    def get(self, site_key: str) -> LogFormatMeta:
        raise NotImplementedError
