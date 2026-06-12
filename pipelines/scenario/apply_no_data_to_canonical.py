from __future__ import annotations
import argparse
import pymysql

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--db-host", required=True)
    p.add_argument("--db-port", type=int, required=True)
    p.add_argument("--db-user", required=True)
    p.add_argument("--db-pass", required=True)
    p.add_argument("--db-name", required=True)
    p.add_argument("--profile-id", required=True)
    p.add_argument("--dt-from", required=True)
    p.add_argument("--dt-to", required=True)
    p.add_argument("--run-id", type=int, required=True)
    p.add_argument("--window-from", required=True)
    p.add_argument("--window-to", required=True)
    return p.parse_args()

def main():
    args = parse_args()
    conn = pymysql.connect(
        host=args.db_host, port=args.db_port, user=args.db_user,
        password=args.db_pass, database=args.db_name, autocommit=True,
        charset="utf8mb4", cursorclass=pymysql.cursors.Cursor
    )
    try:
        with conn.cursor() as cur:
            deleted = cur.execute("""
                DELETE FROM canonical_events
                WHERE profile_id=%s
                  AND target_date BETWEEN %s AND %s
                  AND run_id=%s
                  AND event_time >= %s
                  AND event_time < %s
            """, (args.profile_id, args.dt_from, args.dt_to, args.run_id, args.window_from, args.window_to))
            cur.execute("""
                REPLACE INTO operational_scenario_window
                (profile_id, dt, scenario_name, intensity, stage_name, window_start, window_end, parameters_json, created_at)
                VALUES (%s, %s, 'no_data', 'n/a', 'canonical_gate', %s, %s, JSON_OBJECT('deleted_rows', %s), NOW())
            """, (args.profile_id, args.dt_from, args.window_from, args.window_to, deleted))
            print(f"[DONE] no-data applied to canonical_events deleted_rows={deleted}")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
