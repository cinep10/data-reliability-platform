from __future__ import annotations

import argparse
import json
from pathlib import Path

import pymysql


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument('--profile-id', required=True)
    ap.add_argument('--target-date', required=True)
    ap.add_argument('--scenario-id', required=True)
    ap.add_argument('--file', required=True)
    ap.add_argument('--db-host', required=True)
    ap.add_argument('--db-port', required=True, type=int)
    ap.add_argument('--db-user', required=True)
    ap.add_argument('--db-pass', required=True)
    ap.add_argument('--db-name', required=True)
    return ap.parse_args()


def connect(args):
    return pymysql.connect(host=args.db_host, port=args.db_port, user=args.db_user, password=args.db_pass,
                           database=args.db_name, charset='utf8mb4', autocommit=True)


def main():
    args = parse_args()
    p = Path(args.file)
    row_count = drift_on = drift_off = affected = weather_alias = schema_version = scenario_id_count = fin = 0
    if p.exists():
        with p.open('r', encoding='utf-8', errors='replace') as f:
            for line in f:
                row_count += 1
                drift_on += int('drift=on' in line)
                drift_off += int('drift=off' in line)
                affected += int('affected=1' in line)
                weather_alias += int('weather=' in line)
                schema_version += int('schema_version=' in line)
                scenario_id_count += int('scenario_id=' in line)
                fin += int('financial_product=' in line)
    status = 'PASS'
    reasons = []
    if weather_alias:
        status='FAIL'; reasons.append('weather_alias_present')
    if row_count and schema_version != row_count:
        status='FAIL'; reasons.append('schema_version_missing')
    if row_count and scenario_id_count != row_count:
        status='FAIL'; reasons.append('scenario_id_missing')
    if args.scenario_id == 'baseline':
        if drift_on != 0 or drift_off == 0:
            status='FAIL'; reasons.append('baseline_drift_contract_failed')
    elif args.scenario_id != 'source_no_data':
        if drift_on == 0 or affected == 0:
            status='FAIL'; reasons.append('anomaly_not_activated')
    details = {'reasons': reasons}
    conn = connect(args)
    with conn.cursor() as cur:
        cur.execute('''
        CREATE TABLE IF NOT EXISTS source_cookie_contract_validation_v1 (
          validation_id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
          profile_id VARCHAR(100) NOT NULL,
          target_date DATE NOT NULL,
          scenario_id VARCHAR(100) NOT NULL,
          validation_status VARCHAR(32) NOT NULL DEFAULT 'UNKNOWN',
          row_count BIGINT NOT NULL DEFAULT 0,
          drift_on_count BIGINT NOT NULL DEFAULT 0,
          drift_off_count BIGINT NOT NULL DEFAULT 0,
          affected_count BIGINT NOT NULL DEFAULT 0,
          weather_alias_count BIGINT NOT NULL DEFAULT 0,
          schema_version_count BIGINT NOT NULL DEFAULT 0,
          scenario_id_count BIGINT NOT NULL DEFAULT 0,
          financial_placeholder_count BIGINT NOT NULL DEFAULT 0,
          details_json JSON NULL,
          created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
          KEY idx_sccv_lookup (profile_id, target_date, scenario_id, created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        ''')
        cur.execute('''
        INSERT INTO source_cookie_contract_validation_v1
        (profile_id,target_date,scenario_id,source_file_path,validation_status,row_count,drift_on_count,drift_off_count,affected_count,
         weather_alias_count,schema_version_count,scenario_id_count,financial_placeholder_count,details_json)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ''', (args.profile_id,args.target_date,args.scenario_id,args.file,status,row_count,drift_on,drift_off,affected,
              weather_alias,schema_version,scenario_id_count,fin,json.dumps(details, ensure_ascii=False)))
    print(json.dumps({
        'status': status, 'row_count': row_count, 'drift_on': drift_on, 'drift_off': drift_off,
        'affected': affected, 'weather_alias': weather_alias, 'reasons': reasons
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
