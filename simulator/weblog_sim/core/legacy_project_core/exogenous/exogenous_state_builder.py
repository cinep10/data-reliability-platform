from __future__ import annotations
import argparse, json, pymysql
from datetime import datetime, timedelta

def daterange(start: str, end: str):
    cur = datetime.strptime(start, '%Y-%m-%d').date()
    end_dt = datetime.strptime(end, '%Y-%m-%d').date()
    while cur <= end_dt:
        yield cur.isoformat()
        cur += timedelta(days=1)

def connect_mysql(args):
    return pymysql.connect(host=args.db_host, port=args.db_port, user=args.db_user, password=args.db_pass,
                           database=args.db_name, charset='utf8mb4', autocommit=False,
                           cursorclass=pymysql.cursors.DictCursor)

def derive_month_position(dt_str: str) -> str:
    day = int(dt_str[-2:])
    return 'start' if day <= 10 else ('middle' if day <= 20 else 'end')

def derive_weekend_flag(dt_str: str) -> int:
    return 1 if datetime.strptime(dt_str, '%Y-%m-%d').date().weekday() >= 5 else 0

def derive_business_day_flag(dt_str: str) -> int:
    return 0 if derive_weekend_flag(dt_str) == 1 else 1

def derive_payday_window(dt_str: str) -> str:
    day = int(dt_str[-2:])
    if day in {24,25,26}: return 'payday'
    if day in {22,23}: return 'before_payday'
    if day in {27,28}: return 'after_payday'
    return 'normal'

def resolve_intensity_multiplier(intensity: str) -> float:
    return {'light': 0.7, 'medium': 1.0, 'severe': 1.4}.get(intensity, 1.0)

def derive_multipliers(row: dict) -> dict:
    mult = resolve_intensity_multiplier(row.get('scenario_intensity') or 'medium')
    vol, conv, tout, retry = 1.0, 1.0, 1.0, 1.0
    shift = {}
    campaign = (row.get('campaign_flag') or '').lower()
    system = (row.get('system_flag') or '').lower()
    weather = (row.get('weather_type') or '').lower()
    if campaign in {'card_promo','loan_promo','deposit_promo','salary_day','tax_season'}:
        vol = round(1.0 + 0.35 * mult, 6)
    if weather in {'rain','snow'}:
        shift['mobile_share_up'] = round(0.05 * mult, 4); conv = round(1.0 - 0.05 * mult, 6)
    elif weather in {'heatwave','coldwave'}:
        shift['branch_page_down'] = round(0.06 * mult, 4)
    if system == 'degraded':
        tout = round(1.0 + 1.2 * mult, 6); retry = round(1.0 + 0.8 * mult, 6)
    elif system == 'auth_delay':
        tout = round(1.0 + 1.5 * mult, 6)
    elif system == 'collector_drop':
        retry = round(1.0 + 1.0 * mult, 6)
    elif system == 'submit_partial_loss':
        conv = round(1.0 - 0.45 * mult, 6)
    return {'volume_multiplier': vol, 'conversion_multiplier': conv, 'timeout_multiplier': tout, 'retry_multiplier': retry, 'composition_shift_json': json.dumps(shift, ensure_ascii=False)}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--db-host', default='127.0.0.1'); ap.add_argument('--db-port', type=int, default=3306)
    ap.add_argument('--db-user', required=True); ap.add_argument('--db-pass', default=''); ap.add_argument('--db-name', required=True)
    ap.add_argument('--profile-id', required=True); ap.add_argument('--dt-from', required=True); ap.add_argument('--dt-to', required=True)
    ap.add_argument('--truncate', action='store_true')
    args = ap.parse_args()
    conn = connect_mysql(args)
    try:
        with conn.cursor() as cur:
            if args.truncate:
                cur.execute("DELETE FROM exogenous_state_timeline WHERE profile_id=%s AND dt BETWEEN %s AND %s", (args.profile_id, args.dt_from, args.dt_to))
            for dt in daterange(args.dt_from, args.dt_to):
                for hh in range(24):
                    cur.execute("INSERT IGNORE INTO exogenous_state_timeline (profile_id, dt, hh) VALUES (%s,%s,%s)", (args.profile_id, dt, hh))
            cur.execute("""SELECT * FROM scenario_plan WHERE profile_id=%s AND active_flag=1 AND dt_to >= %s AND dt_from <= %s ORDER BY scenario_plan_id""", (args.profile_id, args.dt_from, args.dt_to))
            plans = cur.fetchall()
            for dt in daterange(args.dt_from, args.dt_to):
                for hh in range(24):
                    base = {'scenario_plan_id': None, 'scenario_name': None, 'scenario_type': None, 'scenario_intensity': None,
                            'business_day_flag': derive_business_day_flag(dt), 'holiday_flag': 0, 'weekend_flag': derive_weekend_flag(dt),
                            'month_position': derive_month_position(dt), 'payday_window': derive_payday_window(dt), 'campaign_flag': 'none',
                            'business_event_flag': 'none', 'system_flag': 'normal', 'weather_type': 'clear'}
                    for plan in plans:
                        if not (plan['dt_from'].isoformat() <= dt <= plan['dt_to'].isoformat()):
                            continue
                        for k in ['scenario_plan_id','scenario_name','scenario_type','scenario_intensity','campaign_flag','business_event_flag','system_flag','weather_type','month_position','payday_window']:
                            if plan.get(k) not in (None, ''): base[k] = plan.get(k)
                        for k in ['business_day_flag','holiday_flag','weekend_flag']:
                            if plan.get(k) is not None: base[k] = plan.get(k)
                    d = derive_multipliers(base)
                    cur.execute("""UPDATE exogenous_state_timeline SET scenario_plan_id=%s, scenario_name=%s, scenario_type=%s, scenario_intensity=%s, business_day_flag=%s, holiday_flag=%s, weekend_flag=%s, month_position=%s, payday_window=%s, campaign_flag=%s, business_event_flag=%s, system_flag=%s, weather_type=%s, volume_multiplier=%s, composition_shift_json=%s, conversion_multiplier=%s, timeout_multiplier=%s, retry_multiplier=%s WHERE profile_id=%s AND dt=%s AND hh=%s""", (base['scenario_plan_id'], base['scenario_name'], base['scenario_type'], base['scenario_intensity'], base['business_day_flag'], base['holiday_flag'], base['weekend_flag'], base['month_position'], base['payday_window'], base['campaign_flag'], base['business_event_flag'], base['system_flag'], base['weather_type'], d['volume_multiplier'], d['composition_shift_json'], d['conversion_multiplier'], d['timeout_multiplier'], d['retry_multiplier'], args.profile_id, dt, hh))
        conn.commit(); print(f"[OK] exogenous_state_builder completed: profile={args.profile_id}, dt_from={args.dt_from}, dt_to={args.dt_to}")
    finally:
        conn.close()

if __name__ == '__main__':
    main()
