#!/usr/bin/env python3
from __future__ import annotations
import argparse, datetime as dt
from decimal import Decimal
import pymysql


def d(x):
    if x is None:
        return Decimal("0")
    return Decimal(str(x))

def q(x):
    return str(Decimal(str(x)).quantize(Decimal("0.000001")))

def connect_mysql(args):
    return pymysql.connect(host=args.db_host, port=args.db_port, user=args.db_user, password=args.db_pass, database=args.db_name, charset="utf8mb4", autocommit=False, cursorclass=pymysql.cursors.DictCursor)

def table_exists(cur, name):
    cur.execute("SELECT COUNT(*) cnt FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=%s", (name,))
    return int(cur.fetchone()["cnt"] or 0) == 1

def ensure(cur):
    cur.execute("""
    CREATE TABLE IF NOT EXISTS stream_validation_result_day (
      validation_id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
      profile_id VARCHAR(100) NOT NULL,
      dt DATE NOT NULL,
      run_id BIGINT NOT NULL,
      rule_name VARCHAR(100) NOT NULL,
      rule_group VARCHAR(50) NOT NULL,
      observed_value DECIMAL(18,6) NOT NULL DEFAULT 0,
      expected_value DECIMAL(18,6) NOT NULL DEFAULT 0,
      diff_value DECIMAL(18,6) NOT NULL DEFAULT 0,
      validation_status VARCHAR(20) NOT NULL,
      severity VARCHAR(20) NOT NULL,
      note VARCHAR(255) NULL,
      created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
      KEY idx_stream_validation_lookup (profile_id, dt, run_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS stream_validation_summary_day (
      profile_id VARCHAR(100) NOT NULL,
      dt DATE NOT NULL,
      run_id BIGINT NOT NULL,
      total_rules INT NOT NULL DEFAULT 0,
      pass_count INT NOT NULL DEFAULT 0,
      warn_count INT NOT NULL DEFAULT 0,
      fail_count INT NOT NULL DEFAULT 0,
      highest_severity VARCHAR(20) NULL,
      validation_score DECIMAL(18,6) NOT NULL DEFAULT 0,
      note VARCHAR(255) NULL,
      created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      PRIMARY KEY (profile_id, dt, run_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

def add(rows, profile_id, day, run_id, name, group, observed, expected, status, sev, note):
    rows.append((profile_id, day, run_id, name, group, q(observed), q(expected), q(d(observed)-d(expected)), status, sev, note))

def days(start, end):
    s=dt.date.fromisoformat(start); e=dt.date.fromisoformat(end); cur=s
    while cur <= e:
        yield cur.isoformat(); cur += dt.timedelta(days=1)

def count_or_zero(cur, sql, params, table_names):
    for t in table_names:
        if not table_exists(cur, t):
            return 0
    cur.execute(sql, params); return int((cur.fetchone() or {}).get("cnt") or 0)

def main():
    ap=argparse.ArgumentParser(description="Validate v0.4 stream evidence tables. Schema-aware and Kafka-off fallback-safe.")
    ap.add_argument("--db-host", default="127.0.0.1"); ap.add_argument("--db-port", type=int, default=3306)
    ap.add_argument("--db-user", required=True); ap.add_argument("--db-pass", default=""); ap.add_argument("--db-name", required=True)
    ap.add_argument("--profile-id", required=True); ap.add_argument("--dt-from", required=True); ap.add_argument("--dt-to", required=True)
    ap.add_argument("--run-id", type=int, required=True); ap.add_argument("--truncate", action="store_true")
    args=ap.parse_args(); c=connect_mysql(args); all_rows=[]
    try:
        with c.cursor() as cur:
            ensure(cur)
            if args.truncate:
                cur.execute("DELETE FROM stream_validation_result_day WHERE profile_id=%s AND dt BETWEEN %s AND %s AND run_id=%s", (args.profile_id,args.dt_from,args.dt_to,args.run_id))
                cur.execute("DELETE FROM stream_validation_summary_day WHERE profile_id=%s AND dt BETWEEN %s AND %s AND run_id=%s", (args.profile_id,args.dt_from,args.dt_to,args.run_id))
            for day in days(args.dt_from,args.dt_to):
                canonical_cnt=count_or_zero(cur,"SELECT COUNT(*) cnt FROM canonical_events WHERE profile_id=%s AND target_date=%s AND run_id=%s",(args.profile_id,day,args.run_id),["canonical_events"])
                stream_cnt=count_or_zero(cur,"SELECT COUNT(*) cnt FROM stg_event_stream WHERE profile_id=%s AND dt=%s AND run_id=%s",(args.profile_id,day,args.run_id),["stg_event_stream"])
                if stream_cnt == 0 and canonical_cnt > 0:
                    status="fail"; sev="high"
                elif stream_cnt != canonical_cnt:
                    status="warn"; sev="medium"
                else:
                    status="pass"; sev="info"
                add(all_rows,args.profile_id,day,args.run_id,"canonical_stream_count_aligned","lineage",stream_cnt,canonical_cnt,status,sev,"stg_event_stream should be materialized from canonical_events when Kafka is off")
                missing=count_or_zero(cur,"SELECT COUNT(*) cnt FROM stg_event_stream WHERE profile_id=%s AND dt=%s AND run_id=%s AND canonical_event_id IS NULL",(args.profile_id,day,args.run_id),["stg_event_stream"])
                miss_rate=Decimal(missing)/Decimal(max(stream_cnt,1))
                add(all_rows,args.profile_id,day,args.run_id,"canonical_event_id_present","completeness",miss_rate,0,"pass" if missing==0 else "warn","medium" if missing else "info","canonical_event_id should be present in stream fallback")
                dup=count_or_zero(cur,"SELECT COUNT(*) cnt FROM (SELECT canonical_event_id FROM stg_event_stream WHERE profile_id=%s AND dt=%s AND run_id=%s AND canonical_event_id IS NOT NULL GROUP BY canonical_event_id HAVING COUNT(*)>1) x",(args.profile_id,day,args.run_id),["stg_event_stream"])
                dup_rate=Decimal(dup)/Decimal(max(stream_cnt,1))
                add(all_rows,args.profile_id,day,args.run_id,"duplicate_canonical_key_check","duplicate",dup_rate,0,"pass" if dup==0 else "warn","medium" if dup else "info","duplicate canonical keys are warning evidence, not authoritative risk")
                risk=Decimal("0")
                if table_exists(cur,"stream_reliability_summary_day"):
                    cur.execute("SELECT COALESCE(MAX(stream_risk_score),0) score FROM stream_reliability_summary_day WHERE profile_id=%s AND dt=%s", (args.profile_id,day))
                    risk=d((cur.fetchone() or {}).get("score"))
                add(all_rows,args.profile_id,day,args.run_id,"stream_summary_available","risk",risk,0,"pass" if table_exists(cur,"stream_reliability_summary_day") else "warn","info" if table_exists(cur,"stream_reliability_summary_day") else "medium","stream_reliability_summary_day should exist; score is evidence only")
            if all_rows:
                cur.executemany("""
                INSERT INTO stream_validation_result_day
                (profile_id, dt, run_id, rule_name, rule_group, observed_value, expected_value, diff_value, validation_status, severity, note)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, all_rows)
            for day in days(args.dt_from,args.dt_to):
                cur.execute("""
                SELECT COUNT(*) total_rules, SUM(validation_status='pass') pass_count, SUM(validation_status='warn') warn_count,
                       SUM(validation_status='fail') fail_count,
                       MAX(CASE severity WHEN 'high' THEN 4 WHEN 'medium' THEN 3 WHEN 'low' THEN 2 WHEN 'info' THEN 1 ELSE 0 END) sev_rank
                FROM stream_validation_result_day WHERE profile_id=%s AND dt=%s AND run_id=%s
                """, (args.profile_id,day,args.run_id))
                r=cur.fetchone() or {}; total=int(r.get("total_rules") or 0); fail=int(r.get("fail_count") or 0); warn=int(r.get("warn_count") or 0)
                score=(fail*2+warn)/max(total,1); sev={4:"high",3:"medium",2:"low",1:"info",0:None}.get(int(r.get("sev_rank") or 0))
                cur.execute("""
                REPLACE INTO stream_validation_summary_day
                (profile_id, dt, run_id, total_rules, pass_count, warn_count, fail_count, highest_severity, validation_score, note)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (args.profile_id,day,args.run_id,total,int(r.get("pass_count") or 0),warn,fail,sev,q(score),"v04 stream evidence validation; not authoritative v0.5 risk"))
        c.commit(); print(f"[stream_validation_v04] done dates={len(list(days(args.dt_from,args.dt_to)))} results={len(all_rows)}")
    except Exception:
        c.rollback(); raise
    finally:
        c.close()
if __name__ == "__main__": main()
