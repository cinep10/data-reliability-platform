#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from typing import Any

import pymysql


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Validate realistic CASE-OBS-001 iOS app/SDK/event-specific WC collection missing scenarios.")
    p.add_argument('--db-host', default='127.0.0.1')
    p.add_argument('--db-port', type=int, default=3306)
    p.add_argument('--db-user', required=True)
    p.add_argument('--db-pass', default='')
    p.add_argument('--db-name', required=True)
    p.add_argument('--profile-id', required=True)
    p.add_argument('--target-date', required=True)
    p.add_argument('--scenario-name', required=True)
    p.add_argument('--run-id', type=int, required=True)
    p.add_argument('--source-gen-run-id', type=int, required=True)
    p.add_argument('--scenario-type', choices=['app_version', 'sdk_version', 'purchase_event'], required=True)
    p.add_argument('--expected-app-version', default='ios-app-5.2.1')
    p.add_argument('--expected-sdk-version', default='wc-ios-3.2.1')
    p.add_argument('--min-app-missing-rate', type=float, default=0.20)
    p.add_argument('--min-sdk-missing-rate', type=float, default=0.20)
    p.add_argument('--min-conversion-gap-rate', type=float, default=0.20)
    p.add_argument('--max-pv-gap-rate', type=float, default=1.0)
    p.add_argument('--require-interpretation', action='store_true', help='Require r_v05_observability_interpretation_day to contain the expected app/sdk signal. Use only after Step 6.06.')
    p.add_argument('--require-targeted-page-rows', action='store_true', help='Require source rows for the scenario-specific target segment/event. For null_uid/rewrite_url scenarios, rows may be mutated rather than dropped.')
    p.add_argument('--min-identity-gap-rate', type=float, default=0.20)
    p.add_argument('--min-url-semantic-shift', type=float, default=0.20)
    return p.parse_args()


def conn(a: argparse.Namespace):
    return pymysql.connect(
        host=a.db_host,
        port=a.db_port,
        user=a.db_user,
        password=a.db_pass,
        database=a.db_name,
        charset='utf8mb4',
        autocommit=True,
        cursorclass=pymysql.cursors.DictCursor,
    )


def f(x: Any) -> float:
    try:
        return float(x or 0)
    except Exception:
        return 0.0


def tokens(value: str) -> list[str]:
    return [x.strip() for x in str(value or '').split(',') if x.strip()]


def sql_in_clause(values: list[str]) -> tuple[str, tuple[str, ...]]:
    if not values:
        return "('')", tuple()
    return '(' + ','.join(['%s'] * len(values)) + ')', tuple(values)


def one(cur, sql: str, params: tuple[Any, ...]) -> dict[str, Any]:
    cur.execute(sql, params)
    return cur.fetchone() or {}


def target_queries_for(a: argparse.Namespace) -> tuple[tuple[str, tuple[Any, ...]], tuple[str, tuple[Any, ...]]]:
    web_common = (a.profile_id, a.target_date, a.source_gen_run_id)
    wc_common = (a.profile_id, a.target_date, a.source_gen_run_id)
    if a.scenario_type == 'app_version':
        web_sql = """
            SELECT COUNT(*) AS targeted_page_rows
            FROM stg_webserver_log_hit s
            WHERE s.profile_id=%s AND s.dt=%s AND s.source_gen_run_id=%s
              AND s.app_platform='ios_app'
              AND s.app_version=%s
              AND COALESCE(s.page_type,'') <> ''
        """
        wc_sql = """
            SELECT COUNT(*) AS targeted_wc_rows
            FROM stg_wc_log_hit w
            WHERE w.profile_id=%s AND w.dt=%s AND w.source_gen_run_id=%s
              AND w.app_platform='ios_app'
              AND w.app_version=%s
              AND COALESCE(w.page_type,'') <> ''
        """
        return (web_sql, web_common + (a.expected_app_version,)), (wc_sql, wc_common + (a.expected_app_version,))
    if a.scenario_type == 'sdk_version':
        vals = tokens(a.expected_sdk_version)
        clause, params = sql_in_clause(vals)
        web_sql = f"""
            SELECT COUNT(*) AS targeted_page_rows
            FROM stg_webserver_log_hit s
            WHERE s.profile_id=%s AND s.dt=%s AND s.source_gen_run_id=%s
              AND s.sdk_version IN {clause}
              AND COALESCE(s.page_type,'') <> ''
        """
        wc_sql = f"""
            SELECT COUNT(*) AS targeted_wc_rows
            FROM stg_wc_log_hit w
            WHERE w.profile_id=%s AND w.dt=%s AND w.source_gen_run_id=%s
              AND w.sdk_version IN {clause}
              AND COALESCE(w.page_type,'') <> ''
        """
        return (web_sql, web_common + params), (wc_sql, wc_common + params)
    # Purchase-event scenario must validate only explicit critical event rows.
    # This prevents generic payment/checkout page views from being counted as PV loss.
    event_names = ('purchase','purchase_success','payment_success','order_complete','conversion')
    clause, params = sql_in_clause(list(event_names))
    web_sql = f"""
        SELECT COUNT(*) AS targeted_page_rows
        FROM stg_webserver_log_hit s
        WHERE s.profile_id=%s AND s.dt=%s AND s.source_gen_run_id=%s
          AND s.app_platform='ios_app'
          AND (COALESCE(s.is_conversion,0)=1 OR LOWER(COALESCE(s.evt, s.event_type, '')) IN {clause})
    """
    wc_sql = f"""
        SELECT COUNT(*) AS targeted_wc_rows
        FROM stg_wc_log_hit w
        WHERE w.profile_id=%s AND w.dt=%s AND w.source_gen_run_id=%s
          AND w.app_platform='ios_app'
          AND (COALESCE(w.is_conversion,0)=1 OR LOWER(COALESCE(w.evt, w.event_type, '')) IN {clause})
    """
    return (web_sql, web_common + params), (wc_sql, wc_common + params)

def main() -> int:
    a = parse_args()
    fails: list[str] = []
    con = conn(a)
    try:
        with con.cursor() as cur:
            base = (a.profile_id, a.target_date, a.scenario_name, a.run_id, a.source_gen_run_id)
            app = one(cur, "SELECT app_platform, app_version, sdk_version, webserver_events, wc_events, missing_rate, conversion_missing_rate, pv_missing_rate FROM v05_obs_app_version_measurement_day WHERE profile_id=%s AND target_date=%s AND scenario_name=%s AND run_id=%s AND source_gen_run_id=%s AND app_platform='ios_app' AND app_version=%s ORDER BY missing_rate DESC LIMIT 1", base + (a.expected_app_version,))
            
            sdk_vals = tokens(a.expected_sdk_version)
            sdk_clause, sdk_params = sql_in_clause(sdk_vals)
            sdk = one(cur, f"SELECT app_platform, sdk_version, webserver_events, wc_events, missing_rate, conversion_missing_rate, pv_missing_rate FROM v05_obs_sdk_version_measurement_day WHERE profile_id=%s AND target_date=%s AND scenario_name=%s AND run_id=%s AND source_gen_run_id=%s AND sdk_version IN {sdk_clause} ORDER BY missing_rate DESC LIMIT 1", base + sdk_params)
            conv = one(cur, "SELECT MAX(gap_rate) AS max_conversion_gap FROM v05_obs_metric_gap_day WHERE profile_id=%s AND target_date=%s AND scenario_name=%s AND run_id=%s AND source_gen_run_id=%s AND metric_name='conversion' AND dimension_type IN ('app_version','sdk_version','app_sdk','app_platform','all')", base)
            pv = one(cur, "SELECT MAX(gap_rate) AS max_pv_gap FROM v05_obs_metric_gap_day WHERE profile_id=%s AND target_date=%s AND scenario_name=%s AND run_id=%s AND source_gen_run_id=%s AND metric_name='pv' AND dimension_type IN ('app_version','sdk_version','app_sdk','app_platform','all')", base)
            identity = one(cur, "SELECT MAX(identity_integrity_gap) AS max_identity_gap, MAX(uid_missing_rate) AS max_uid_missing_rate, MAX(login_user_gap_rate) AS max_login_user_gap_rate FROM v05_obs_identity_gap_day WHERE profile_id=%s AND target_date=%s AND scenario_name=%s AND run_id=%s AND source_gen_run_id=%s", base)
            semantic_shift = one(cur, "SELECT MAX(distribution_shift_score) AS max_url_semantic_shift, MAX(under_rate) AS max_under_rate, MAX(over_rate) AS max_over_rate FROM v05_obs_url_semantic_gap_day WHERE profile_id=%s AND target_date=%s AND scenario_name=%s AND run_id=%s AND source_gen_run_id=%s", base)
            cur.execute("SELECT root_cause_rank, root_cause_dimension, root_cause_value, root_cause_confidence, affected_metrics, analysis_status FROM r_v05_observability_interpretation_day WHERE profile_id=%s AND target_date=%s AND scenario_name=%s AND run_id=%s AND source_gen_run_id=%s ORDER BY root_cause_rank LIMIT 5", base)
            interp = cur.fetchall()
            (web_q, web_p), (wc_q, wc_p) = target_queries_for(a)
            target_web_rows = one(cur, web_q, web_p)
            target_wc_rows = one(cur, wc_q, wc_p)
    finally:
        con.close()

    app_missing = f(app.get('missing_rate'))
    sdk_missing = f(sdk.get('missing_rate'))
    conv_gap = f(conv.get('max_conversion_gap'))
    pv_gap = f(pv.get('max_pv_gap'))
    targeted_page_rows = int(f(target_web_rows.get('targeted_page_rows')))
    targeted_wc_rows = int(f(target_wc_rows.get('targeted_wc_rows')))
    targeted_missing_rows = max(targeted_page_rows - targeted_wc_rows, 0)
    identity_gap = f(identity.get('max_identity_gap'))
    uid_missing_rate = f(identity.get('max_uid_missing_rate'))
    login_user_gap_rate = f(identity.get('max_login_user_gap_rate'))
    url_semantic_shift = f(semantic_shift.get('max_url_semantic_shift'))
    url_under_rate = f(semantic_shift.get('max_under_rate'))
    url_over_rate = f(semantic_shift.get('max_over_rate'))

    print('[IOS_COLLECTION_SCENARIO]')
    print(f"scenario={a.scenario_name} type={a.scenario_type} run_id={a.run_id} source_gen_run_id={a.source_gen_run_id}")
    print(f"app_version={a.expected_app_version} app_missing_rate={app_missing:.6f} app_conversion_missing_rate={f(app.get('conversion_missing_rate')):.6f} app_pv_missing_rate={f(app.get('pv_missing_rate')):.6f}")
    print(f"sdk_version={a.expected_sdk_version} sdk_missing_rate={sdk_missing:.6f} sdk_conversion_missing_rate={f(sdk.get('conversion_missing_rate')):.6f} sdk_pv_missing_rate={f(sdk.get('pv_missing_rate')):.6f}")
    print(f"metric_conversion_gap={conv_gap:.6f} metric_pv_gap={pv_gap:.6f}")
    print(f"targeted_page_rows={targeted_page_rows} targeted_wc_rows={targeted_wc_rows} targeted_missing_rows={targeted_missing_rows}")
    print(f"identity_gap={identity_gap:.6f} uid_missing_rate={uid_missing_rate:.6f} login_user_gap_rate={login_user_gap_rate:.6f}")
    print(f"url_semantic_shift={url_semantic_shift:.6f} url_under_rate={url_under_rate:.6f} url_over_rate={url_over_rate:.6f}")
    for r in interp:
        print(f"  - rank={r.get('root_cause_rank')} dim={r.get('root_cause_dimension')} value={r.get('root_cause_value')} confidence={f(r.get('root_cause_confidence')):.6f} affected_metrics={r.get('affected_metrics')} status={r.get('analysis_status')}")

    if a.require_targeted_page_rows and targeted_page_rows <= 0:
        fails.append('targeted_page_rows must be > 0; scenario was not applied as a targeted segment')
    if a.require_targeted_page_rows and targeted_missing_rows <= 0 and a.scenario_type == 'purchase_event':
        fails.append('targeted_missing_rows must be > 0; collector did not drop targeted purchase rows')

    if a.scenario_type == 'app_version':
        if not app:
            fails.append(f'missing ios app_version measurement for {a.expected_app_version}')
        if identity_gap < a.min_identity_gap_rate:
            fails.append(f'identity gap too low {identity_gap:.6f} < {a.min_identity_gap_rate:.6f}')
        has_app_signal = any(str(r.get('root_cause_dimension')) in {'app_version', 'metric_app_version', 'metric_app_sdk'} and a.expected_app_version in str(r.get('root_cause_value')) for r in interp)
        if a.require_interpretation and not has_app_signal:
            fails.append('interpretation does not include expected app_version signal')
        elif not interp:
            print('[INFO] interpretation rows not available yet; app_version interpretation check deferred until Step 6.061')
    elif a.scenario_type == 'sdk_version':
        if not sdk:
            fails.append(f'missing ios sdk_version measurement for {a.expected_sdk_version}')
        if url_semantic_shift < a.min_url_semantic_shift:
            fails.append(f'url semantic shift too low {url_semantic_shift:.6f} < {a.min_url_semantic_shift:.6f}')
        has_sdk_signal = any(str(r.get('root_cause_dimension')) in {'sdk_version', 'metric_sdk_version', 'metric_app_sdk'} and any(v in str(r.get('root_cause_value')) for v in tokens(a.expected_sdk_version)) for r in interp)
        if a.require_interpretation and not has_sdk_signal:
            fails.append('interpretation does not include expected sdk_version signal')
        elif not interp:
            print('[INFO] interpretation rows not available yet; sdk_version interpretation check deferred until Step 6.061')
    elif a.scenario_type == 'purchase_event':
        if conv_gap < a.min_conversion_gap_rate:
            fails.append(f'conversion gap too low {conv_gap:.6f} < {a.min_conversion_gap_rate:.6f}')
        if pv_gap > a.max_pv_gap_rate:
            fails.append(f'pv gap too high for purchase-event case {pv_gap:.6f} > {a.max_pv_gap_rate:.6f}')

    if a.scenario_type == 'purchase_event' and conv_gap < a.min_conversion_gap_rate:
        fails.append(f'conversion gap too low {conv_gap:.6f} < {a.min_conversion_gap_rate:.6f}')
    if fails:
        print('[FAIL] ' + '; '.join(fails))
        return 1
    print('[OK] validate_v05_ios_collection_missing_scenario passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
