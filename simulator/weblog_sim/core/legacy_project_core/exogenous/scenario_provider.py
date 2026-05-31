from __future__ import annotations
import argparse, json, pymysql

def connect_mysql(args):
    return pymysql.connect(host=args.host, port=args.port, user=args.user, password=args.password,
                           database=args.db, charset='utf8mb4', autocommit=False,
                           cursorclass=pymysql.cursors.DictCursor)

def resolve_intensity_multiplier(intensity: str) -> float:
    return {'light': 0.7, 'medium': 1.0, 'severe': 1.4}.get(intensity, 1.0)

def derive_multipliers(row: dict) -> dict:
    mult = resolve_intensity_multiplier(row.get('scenario_intensity') or 'medium')
    out = {'volume_multiplier': 1.0, 'conversion_multiplier': 1.0, 'timeout_multiplier': 1.0, 'retry_multiplier': 1.0}
    campaign = (row.get('campaign_flag') or '').lower()
    weather = (row.get('weather_type') or '').lower()
    system = (row.get('system_flag') or '').lower()
    if campaign in {'card_promo','loan_promo','deposit_promo','salary_day','tax_season'}:
        out['volume_multiplier'] = round(1.0 + 0.35 * mult, 6)
    if weather in {'rain','snow'}:
        out['conversion_multiplier'] = round(1.0 - 0.05 * mult, 6)
    if system == 'degraded':
        out['timeout_multiplier'] = round(1.0 + 1.2 * mult, 6)
        out['retry_multiplier'] = round(1.0 + 0.8 * mult, 6)
    elif system == 'auth_delay':
        out['timeout_multiplier'] = round(1.0 + 1.5 * mult, 6)
    elif system == 'collector_drop':
        out['retry_multiplier'] = round(1.0 + 1.0 * mult, 6)
    elif system == 'submit_partial_loss':
        out['conversion_multiplier'] = round(1.0 - 0.45 * mult, 6)
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--host', default='127.0.0.1'); ap.add_argument('--port', type=int, default=3306)
    ap.add_argument('--user', required=True); ap.add_argument('--password', default=''); ap.add_argument('--db', required=True)
    ap.add_argument('--profile-id', required=True); ap.add_argument('--dt-from', required=True); ap.add_argument('--dt-to', required=True)
    args = ap.parse_args()
    conn = connect_mysql(args)
    try:
        with conn.cursor() as cur:
            cur.execute("""SELECT * FROM scenario_plan WHERE profile_id=%s AND active_flag=1 AND dt_to >= %s AND dt_from <= %s ORDER BY dt_from, scenario_plan_id""", (args.profile_id, args.dt_from, args.dt_to))
            rows = cur.fetchall()
            payload = []
            for row in rows:
                payload.append({
                    'scenario_plan_id': row['scenario_plan_id'],
                    'scenario_name': row['scenario_name'],
                    'scenario_type': row['scenario_type'],
                    'scenario_intensity': row['scenario_intensity'],
                    'dt_from': str(row['dt_from']),
                    'dt_to': str(row['dt_to']),
                    'derived_multipliers': derive_multipliers(row),
                })
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    finally:
        conn.close()

if __name__ == '__main__':
    main()
