#!/usr/bin/env python3
"""
v0.4 batch_quality_diagnostic_v04.py

DDL 기준 테이블:
- mapping_coverage_day
- event_mapping_suggestion
- batch_quality_diagnostic_v04

원칙:
1) 기존 v0.4 DDL을 기준으로 Python을 맞춘다.
2) batch_quality_diagnostic_v04는 diagnostic_type / diagnostic_key를 사용한다.
3) diagnostic_name 컬럼은 사용하지 않는다.
4) mapping coverage denominator가 0이면 coverage=1.0으로 normalize 한다.
5) SQL LIKE '%'는 PyMySQL 포맷 충돌을 피하기 위해 파라미터로 전달한다.
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pymysql
from pymysql.cursors import DictCursor


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--db-host", default="127.0.0.1")
    p.add_argument("--db-port", type=int, default=3306)
    p.add_argument("--db-user", required=True)
    p.add_argument("--db-pass", required=True)
    p.add_argument("--db-name", required=True)
    p.add_argument("--profile-id", required=True)
    p.add_argument("--dt-from", required=True)
    p.add_argument("--dt-to", required=True)
    p.add_argument("--run-id", default="")
    p.add_argument("--truncate", action="store_true")
    p.add_argument("--domain", default="default")
    return p.parse_args()


def connect(args: argparse.Namespace):
    return pymysql.connect(
        host=args.db_host,
        port=args.db_port,
        user=args.db_user,
        password=args.db_pass,
        database=args.db_name,
        charset="utf8mb4",
        autocommit=False,
        cursorclass=DictCursor,
    )


def daterange(dt_from: str, dt_to: str) -> Iterable[str]:
    cur = date.fromisoformat(dt_from)
    end = date.fromisoformat(dt_to)
    while cur <= end:
        yield cur.isoformat()
        cur += timedelta(days=1)


def table_exists(cur, db: str, table: str) -> bool:
    cur.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM information_schema.tables
        WHERE table_schema=%s AND table_name=%s
        """,
        (db, table),
    )
    return int(cur.fetchone()["cnt"] or 0) > 0


def get_columns(cur, db: str, table: str) -> List[str]:
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema=%s AND table_name=%s
        ORDER BY ordinal_position
        """,
        (db, table),
    )
    return [r["column_name"] for r in cur.fetchall()]


def has_col(cols: Sequence[str], col: str) -> bool:
    return col in set(cols)


def path_expr(alias: str = "l") -> str:
    return f"""
    CASE
      WHEN {alias}.url_norm REGEXP '^https?://' THEN
        CASE
          WHEN LOCATE('/', {alias}.url_norm, LOCATE('//', {alias}.url_norm) + 2) > 0 THEN
            SUBSTRING_INDEX(SUBSTRING({alias}.url_norm, LOCATE('/', {alias}.url_norm, LOCATE('//', {alias}.url_norm) + 2)), '?', 1)
          ELSE '/'
        END
      ELSE SUBSTRING_INDEX({alias}.url_norm, '?', 1)
    END
    """


def choose_source_table(cur, db: str) -> str:
    for t in ("stg_wc_log_hit", "stg_event_batch", "stg_webserver_log_hit"):
        if table_exists(cur, db, t):
            return t
    raise RuntimeError("No source table found among stg_wc_log_hit, stg_event_batch, stg_webserver_log_hit")


def get_source_counts(cur, db: str, source_table: str, profile_id: str, dt: str) -> Tuple[int, int, int]:
    cols = get_columns(cur, db, source_table)
    profile_where = "profile_id=%s" if has_col(cols, "profile_id") else "1=1"
    dt_col = "dt" if has_col(cols, "dt") else "target_date" if has_col(cols, "target_date") else None
    if not dt_col:
        return (0, 0, 0)
    params: List[Any] = []
    where = []
    if has_col(cols, "profile_id"):
        where.append("profile_id=%s")
        params.append(profile_id)
    where.append(f"{dt_col}=%s")
    params.append(dt)
    where_sql = " AND ".join(where)

    cur.execute(f"SELECT COUNT(*) AS cnt FROM {source_table} WHERE {where_sql}", tuple(params))
    total = int(cur.fetchone()["cnt"] or 0)

    mapped = 0
    unmapped = 0
    if source_table in ("stg_wc_log_hit", "stg_webserver_log_hit") and has_col(cols, "url_norm") and table_exists(cur, db, "event_mapping"):
        pexpr = path_expr("l")
        cur.execute(
            f"""
            SELECT
              SUM(CASE WHEN m.id IS NOT NULL THEN 1 ELSE 0 END) AS mapped_events,
              SUM(CASE WHEN m.id IS NULL THEN 1 ELSE 0 END) AS unmapped_events
            FROM {source_table} l
            LEFT JOIN event_mapping m
              ON ({pexpr}) LIKE CONCAT(m.url_pattern, %s)
             AND m.is_active=1
            WHERE {where_sql}
            """,
            tuple(["%"] + params),
        )
        r = cur.fetchone() or {}
        mapped = int(r.get("mapped_events") or 0)
        unmapped = int(r.get("unmapped_events") or 0)
    elif source_table == "stg_event_batch":
        # canonical-enriched batch table often already has event_name/event_type.
        event_cols = [c for c in ("event_name", "event_type", "semantic_event_name") if has_col(cols, c)]
        if event_cols:
            c = event_cols[0]
            cur.execute(
                f"""
                SELECT
                  SUM(CASE WHEN {c} IS NOT NULL AND {c} <> '' THEN 1 ELSE 0 END) AS mapped_events,
                  SUM(CASE WHEN {c} IS NULL OR {c} = '' THEN 1 ELSE 0 END) AS unmapped_events
                FROM {source_table}
                WHERE {where_sql}
                """,
                tuple(params),
            )
            r = cur.fetchone() or {}
            mapped = int(r.get("mapped_events") or 0)
            unmapped = int(r.get("unmapped_events") or 0)
        else:
            mapped = total
            unmapped = 0
    else:
        mapped = total
        unmapped = 0

    return total, mapped, unmapped


def normalized_coverage(total: int, mapped: int, unmapped: int) -> float:
    denominator = mapped + unmapped
    if total <= 0 or denominator <= 0:
        return 1.0
    return max(0.0, min(1.0, float(mapped) / float(denominator)))


def upsert_mapping_coverage(cur, db: str, profile_id: str, dt: str, domain: str, total: int, mapped: int, unmapped: int, coverage: float) -> None:
    if not table_exists(cur, db, "mapping_coverage_day"):
        return
    cols = get_columns(cur, db, "mapping_coverage_day")
    row: Dict[str, Any] = {}
    if has_col(cols, "dt"):
        row["dt"] = dt
    if has_col(cols, "profile_id"):
        row["profile_id"] = profile_id
    if has_col(cols, "domain"):
        row["domain"] = domain
    if has_col(cols, "total_events"):
        row["total_events"] = total
    if has_col(cols, "mapped_events"):
        row["mapped_events"] = mapped
    if has_col(cols, "unmapped_events"):
        row["unmapped_events"] = unmapped
    if has_col(cols, "mapping_coverage"):
        row["mapping_coverage"] = coverage
    if has_col(cols, "created_at"):
        row["created_at"] = datetime.now()
    if has_col(cols, "updated_at"):
        row["updated_at"] = datetime.now()

    if not row:
        return
    keys = list(row.keys())
    placeholders = ",".join(["%s"] * len(keys))
    updates = ",".join([f"{k}=VALUES({k})" for k in keys if k not in ("dt", "profile_id", "domain")])
    if not updates:
        updates = f"{keys[-1]}=VALUES({keys[-1]})"
    sql = f"INSERT INTO mapping_coverage_day ({','.join(keys)}) VALUES ({placeholders}) ON DUPLICATE KEY UPDATE {updates}"
    cur.execute(sql, tuple(row[k] for k in keys))


def insert_diagnostic(cur, db: str, profile_id: str, dt: str, run_id: str, diagnostic_type: str, diagnostic_key: str, value: float, threshold: float, status: str, reason: str, row_count: int, sample: Optional[dict] = None) -> None:
    table = "batch_quality_diagnostic_v04"
    if not table_exists(cur, db, table):
        return
    cols = get_columns(cur, db, table)
    row: Dict[str, Any] = {}
    if has_col(cols, "profile_id"):
        row["profile_id"] = profile_id
    if has_col(cols, "dt"):
        row["dt"] = dt
    if has_col(cols, "run_id"):
        row["run_id"] = str(run_id or "")
    if has_col(cols, "diagnostic_type"):
        row["diagnostic_type"] = diagnostic_type
    if has_col(cols, "diagnostic_key"):
        row["diagnostic_key"] = diagnostic_key
    elif has_col(cols, "diagnostic_name"):
        row["diagnostic_name"] = diagnostic_key
    if has_col(cols, "diagnostic_value"):
        row["diagnostic_value"] = value
    if has_col(cols, "observed_value"):
        row["observed_value"] = value
    if has_col(cols, "threshold_value"):
        row["threshold_value"] = threshold
    if has_col(cols, "diagnostic_status"):
        row["diagnostic_status"] = status
    if has_col(cols, "diagnostic_reason"):
        row["diagnostic_reason"] = reason
    if has_col(cols, "row_count"):
        row["row_count"] = row_count
    if has_col(cols, "sample_json"):
        row["sample_json"] = json.dumps(sample or {}, ensure_ascii=False)
    if has_col(cols, "note"):
        row["note"] = reason[:250]
    if has_col(cols, "created_at"):
        row["created_at"] = datetime.now()
    if has_col(cols, "updated_at"):
        row["updated_at"] = datetime.now()

    keys = list(row.keys())
    placeholders = ",".join(["%s"] * len(keys))
    updates = ",".join([f"{k}=VALUES({k})" for k in keys if k not in ("profile_id", "dt", "run_id", "diagnostic_type", "diagnostic_key", "diagnostic_name")])
    if not updates:
        updates = f"{keys[-1]}=VALUES({keys[-1]})"
    sql = f"INSERT INTO {table} ({','.join(keys)}) VALUES ({placeholders}) ON DUPLICATE KEY UPDATE {updates}"
    cur.execute(sql, tuple(row[k] for k in keys))


def delete_scope(cur, db: str, profile_id: str, dt: str, run_id: str) -> None:
    # Only clear diagnostics produced by this runner, not all legacy diagnostics.
    if table_exists(cur, db, "batch_quality_diagnostic_v04"):
        cols = get_columns(cur, db, "batch_quality_diagnostic_v04")
        where = []
        params: List[Any] = []
        if has_col(cols, "profile_id"):
            where.append("profile_id=%s")
            params.append(profile_id)
        if has_col(cols, "dt"):
            where.append("dt=%s")
            params.append(dt)
        if has_col(cols, "run_id"):
            where.append("run_id=%s")
            params.append(str(run_id or ""))
        if has_col(cols, "diagnostic_type"):
            where.append("diagnostic_type IN (%s,%s,%s)")
            params.extend(["mapping", "mapping_coverage", "mapping_suggestion"])
        if where:
            cur.execute(f"DELETE FROM batch_quality_diagnostic_v04 WHERE {' AND '.join(where)}", tuple(params))


def populate_event_mapping_suggestions(cur, db: str, source_table: str, profile_id: str, dt: str, limit: int = 100) -> int:
    if not table_exists(cur, db, "event_mapping_suggestion") or not table_exists(cur, db, "event_mapping"):
        return 0
    cols = get_columns(cur, db, source_table)
    if source_table not in ("stg_wc_log_hit", "stg_webserver_log_hit") or not has_col(cols, "url_norm"):
        return 0
    sug_cols = get_columns(cur, db, "event_mapping_suggestion")
    pexpr = path_expr("l")
    cur.execute(
        f"""
        SELECT path_only, COUNT(*) AS hit_count
        FROM (
          SELECT {pexpr} AS path_only
          FROM {source_table} l
          WHERE l.profile_id=%s AND l.dt=%s
        ) p
        WHERE NOT EXISTS (
          SELECT 1 FROM event_mapping m
          WHERE m.is_active=1
            AND m.url_pattern <> '/'
            AND p.path_only LIKE CONCAT(m.url_pattern, %s)
        )
        GROUP BY path_only
        ORDER BY hit_count DESC
        LIMIT {int(limit)}
        """,
        (profile_id, dt, "%"),
    )
    rows = cur.fetchall()
    inserted = 0
    for r in rows:
        path = r["path_only"] or "/"
        hits = int(r["hit_count"] or 0)
        if path.startswith("/account/"):
            pat = "/account/"
        elif path.startswith("/auth/"):
            pat = "/auth/"
        elif path.startswith("/branch/"):
            pat = "/branch/"
        elif path.startswith("/card/"):
            pat = "/card/"
        elif path.startswith("/customer/"):
            pat = "/customer/"
        elif path.startswith("/deposit/"):
            pat = "/deposit/"
        elif path.startswith("/loan/"):
            pat = "/loan/"
        elif path.startswith("/transfer/"):
            pat = "/transfer/"
        else:
            pat = path
        event_name = pat.strip("/").replace("/", "_").replace(".do", "") or "root_view"
        event_type = "conversion" if ("apply" in pat or "submit" in pat) else "action" if (pat.startswith("/auth/") or pat.startswith("/transfer/")) else "page"
        funnel_stage = "apply" if event_type == "conversion" else "auth" if pat.startswith("/auth/") else "view"
        data: Dict[str, Any] = {}
        if has_col(sug_cols, "suggested_pattern"):
            data["suggested_pattern"] = pat
        if has_col(sug_cols, "suggested_event_name"):
            data["suggested_event_name"] = event_name
        if has_col(sug_cols, "suggested_event_type"):
            data["suggested_event_type"] = event_type
        if has_col(sug_cols, "suggested_funnel_stage"):
            data["suggested_funnel_stage"] = funnel_stage
        if has_col(sug_cols, "suggested_funnel_order"):
            data["suggested_funnel_order"] = 3 if event_type == "conversion" else 2 if event_type == "action" else 1
        if has_col(sug_cols, "total_hits"):
            data["total_hits"] = hits
        if has_col(sug_cols, "review_status"):
            data["review_status"] = "pending"
        if has_col(sug_cols, "created_at"):
            data["created_at"] = datetime.now()
        if not data:
            continue
        keys = list(data.keys())
        placeholders = ",".join(["%s"] * len(keys))
        updates = ",".join([f"{k}=VALUES({k})" for k in keys if k != "suggested_pattern"])
        if not updates:
            updates = f"{keys[-1]}=VALUES({keys[-1]})"
        cur.execute(
            f"INSERT INTO event_mapping_suggestion ({','.join(keys)}) VALUES ({placeholders}) ON DUPLICATE KEY UPDATE {updates}",
            tuple(data[k] for k in keys),
        )
        inserted += 1
    return inserted


def main() -> None:
    args = parse_args()
    conn = connect(args)
    try:
        with conn.cursor() as cur:
            source_table = choose_source_table(cur, args.db_name)
            total_inserted = 0
            for ds in daterange(args.dt_from, args.dt_to):
                if args.truncate:
                    delete_scope(cur, args.db_name, args.profile_id, ds, args.run_id)
                total, mapped, unmapped = get_source_counts(cur, args.db_name, source_table, args.profile_id, ds)
                coverage = normalized_coverage(total, mapped, unmapped)
                upsert_mapping_coverage(cur, args.db_name, args.profile_id, ds, args.domain, total, mapped, unmapped, coverage)
                status = "PASS" if coverage >= 0.98 else "WARN"
                reason = f"normalized_mapping_coverage={coverage:.6f}; total={total}; mapped={mapped}; unmapped={unmapped}; source={source_table}"
                insert_diagnostic(
                    cur,
                    args.db_name,
                    args.profile_id,
                    ds,
                    str(args.run_id or ""),
                    "mapping_coverage",
                    "mapping_coverage_normalized",
                    coverage,
                    0.98,
                    status,
                    reason,
                    total,
                    {"source_table": source_table, "mapped": mapped, "unmapped": unmapped},
                )
                sug = populate_event_mapping_suggestions(cur, args.db_name, source_table, args.profile_id, ds)
                insert_diagnostic(
                    cur,
                    args.db_name,
                    args.profile_id,
                    ds,
                    str(args.run_id or ""),
                    "mapping_suggestion",
                    "event_mapping_suggestion_count",
                    float(sug),
                    0.0,
                    "PASS",
                    f"inserted_or_updated_suggestions={sug}",
                    sug,
                    {"source_table": source_table},
                )
                total_inserted += 2
            conn.commit()
            print(f"[batch_quality_diagnostic_v04] inserted={total_inserted}")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
