from __future__ import annotations

from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def apache_time(dt: datetime) -> str:
    return f"{dt.day:02d}/{MONTH_ABBR[dt.month - 1]}/{dt.year}:{dt.hour:02d}:{dt.minute:02d}:{dt.second:02d} +0900"
