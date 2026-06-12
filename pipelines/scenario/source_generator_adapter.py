from __future__ import annotations
import argparse, json, pymysql
from collections import defaultdict

def connect_mysql(args):
    return pymysql.connect(host=args.db_host, port=args.db_port, user=args.db_user, password=args.db_pass,
                           database=args.db_name, charset='utf8mb4', autocommit=False,
                           cursorclass=pymysql.cursors.DictCursor)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--db-host', default='127.0.0.1'); ap.add_argument('--db-port', type=int, default=3306)
    ap.add_argument('--db-user', required=True); ap.add_argument('--db-pass', default=''); ap.add_argument('--db-name', required=True)
    ap.add_argument('--profile-id', required=True); ap.add_argument('--dt-from', required=True); ap.add_argument('--dt-to', required=True)
    args = ap.parse_args()
    conn = connect_mysql(args)
    try:
        with conn.cursor() as cur:
            cur.execute("""SELECT dt, hh, scenario_name, weather_type, campaign_flag, system_flag, volume_multiplier, conversion_multiplier, timeout_multiplier, retry_multiplier, composition_shift_json FROM exogenous_state_timeline WHERE profile_id=%s AND dt BETWEEN %s AND %s ORDER BY dt, hh""", (args.profile_id, args.dt_from, args.dt_to))
            rows = cur.fetchall()
        out = defaultdict(list)
        for r in rows:
            out[r['dt'].isoformat()].append({
                'hh': r['hh'], 'scenario_name': r['scenario_name'], 'weather_type': r['weather_type'],
                'campaign_flag': r['campaign_flag'], 'system_flag': r['system_flag'],
                'volume_multiplier': float(r['volume_multiplier']), 'conversion_multiplier': float(r['conversion_multiplier']),
                'timeout_multiplier': float(r['timeout_multiplier']), 'retry_multiplier': float(r['retry_multiplier']),
                'composition_shift_json': json.loads(r['composition_shift_json'] or '{}')
            })
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    finally:
        conn.close()

if __name__ == '__main__':
    main()
