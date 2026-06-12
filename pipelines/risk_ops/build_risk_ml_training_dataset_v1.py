#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, math, os
from datetime import datetime, timedelta
from decimal import Decimal
import pymysql

FEATURE_VERSION = 'phase3_ml_v1'

def f(v, default=0.0):
    try:
        if v is None: return float(default)
        return float(v)
    except Exception:
        return float(default)

def connect(args):
    return pymysql.connect(host=args.db_host, port=args.db_port, user=args.db_user, password=args.db_pass,
                           database=args.db_name, charset='utf8mb4', autocommit=False,
                           cursorclass=pymysql.cursors.DictCursor)

def table_exists(cur, name):
    cur.execute("SELECT COUNT(*) AS c FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=%s", (name,))
    return int(cur.fetchone()['c']) > 0

def cols(cur, name):
    if not table_exists(cur, name): return set()
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s", (name,))
    return {r['column_name'] for r in cur.fetchall()}

def one(cur, sql, params):
    cur.execute(sql, params)
    return cur.fetchone() or {}

def scalar(cur, sql, params, key='v', default=0):
    r = one(cur, sql, params)
    return r.get(key, default)

def date_range(a,b):
    d = datetime.strptime(a, '%Y-%m-%d').date(); e = datetime.strptime(b, '%Y-%m-%d').date()
    while d <= e:
        yield d
        d += timedelta(days=1)

def scenario_type(name):
    if name in ('lag_spike','no_data'): return 'operational'
    if name in ('weather_drop','partial_missing','campaign_spike'): return 'stream'
    if name == 'baseline': return 'baseline'
    return 'unknown'

def grade(score):
    score = f(score)
    if score < 20: return 'stable'
    if score < 40: return 'watch'
    if score < 70: return 'degraded'
    return 'critical'

def resolve_scenario(cur, profile_id, dt):
    if table_exists(cur, 'scenario_experiment_run'):
        c = cols(cur, 'scenario_experiment_run')
        date_clause = 'dt_from<=%s AND dt_to>=%s' if {'dt_from','dt_to'} <= c else '1=1'
        if 'scenario_name' in c:
            sql = f"SELECT scenario_name FROM scenario_experiment_run WHERE profile_id=%s AND {date_clause} ORDER BY scenario_run_id DESC LIMIT 1"
            params = (profile_id, dt, dt) if date_clause != '1=1' else (profile_id,)
            r = one(cur, sql, params)
            if r.get('scenario_name'): return str(r['scenario_name'])
    if table_exists(cur, 'risk_layer_score_day_v2') and 'scenario_name' in cols(cur, 'risk_layer_score_day_v2'):
        r = one(cur, "SELECT scenario_name FROM risk_layer_score_day_v2 WHERE profile_id=%s AND dt=%s LIMIT 1", (profile_id, dt))
        if r.get('scenario_name'): return str(r['scenario_name'])
    return 'baseline'

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--db-host', default=os.getenv('DB_HOST','127.0.0.1'))
    ap.add_argument('--db-port', type=int, default=int(os.getenv('DB_PORT','3306')))
    ap.add_argument('--db-user', default=os.getenv('DB_USER','nethru'))
    ap.add_argument('--db-pass', default=os.getenv('DB_PASSWORD','nethru1234'))
    ap.add_argument('--db-name', default=os.getenv('DB_NAME','weblog'))
    ap.add_argument('--profile-id', required=True)
    ap.add_argument('--dt-from', required=True)
    ap.add_argument('--dt-to', required=True)
    ap.add_argument('--truncate-target', action='store_true')
    args = ap.parse_args()
    conn = connect(args)
    try:
        with conn.cursor() as cur:
            if args.truncate_target:
                cur.execute('DELETE FROM risk_ml_training_dataset_v1 WHERE profile_id=%s AND dt BETWEEN %s AND %s', (args.profile_id,args.dt_from,args.dt_to))
                cur.execute('DELETE FROM ml_risk_feature_day WHERE profile_id=%s AND dt BETWEEN %s AND %s AND feature_version=%s', (args.profile_id,args.dt_from,args.dt_to,FEATURE_VERSION))
            rows_built = 0
            hist_scores=[]; hist_stream=[]; hist_perf=[]; hist_avail=[]; hist_op=[]
            prev_score = 0.0
            for dt_obj in date_range(args.dt_from,args.dt_to):
                dt = str(dt_obj)
                scenario = resolve_scenario(cur,args.profile_id,dt)
                stype = scenario_type(scenario)
                rs = {}
                if table_exists(cur,'risk_layer_score_day_v2'):
                    c=cols(cur,'risk_layer_score_day_v2')
                    rs = one(cur, "SELECT * FROM risk_layer_score_day_v2 WHERE profile_id=%s AND dt=%s ORDER BY updated_at DESC LIMIT 1" if 'updated_at' in c else "SELECT * FROM risk_layer_score_day_v2 WHERE profile_id=%s AND dt=%s LIMIT 1", (args.profile_id,dt))
                root = rs.get('dominant_root_cause_code') or rs.get('root_cause_code')
                if not root and table_exists(cur,'risk_root_cause_day'):
                    c=cols(cur,'risk_root_cause_day')
                    order = 'confidence_score DESC' if 'confidence_score' in c else 'root_cause_rank ASC'
                    r = one(cur, f"SELECT root_cause_code, confidence_score FROM risk_root_cause_day WHERE profile_id=%s AND dt=%s ORDER BY {order} LIMIT 1", (args.profile_id,dt))
                    root = r.get('root_cause_code')
                if not root:
                    root = 'baseline_ok' if scenario == 'baseline' else 'scenario_applied'
                # metrics
                sre = one(cur, "SELECT COUNT(*) AS event_count FROM stream_replay_event WHERE profile_id=%s AND target_date=%s", (args.profile_id,dt)) if table_exists(cur,'stream_replay_event') else {}
                event_count = int(sre.get('event_count') or 0)
                ss = one(cur, "SELECT MAX(missing_rate) missing_rate, MAX(duplicate_ratio) duplicate_ratio, MAX(ordering_gap_score) ordering_gap_score, MAX(avg_event_delay_ms) avg_event_delay_ms, MAX(stream_risk_score) stream_risk_score FROM stream_risk_signal_day WHERE profile_id=%s AND dt=%s", (args.profile_id,dt)) if table_exists(cur,'stream_risk_signal_day') else {}
                perf = one(cur, "SELECT MAX(performance_risk_score) performance_risk_score, MAX(consumer_lag_component) consumer_lag, MAX(backlog_component) backlog_size, MAX(throughput_component) throughput_drop FROM performance_risk_score WHERE pipeline_name=%s AND dt=%s", (args.profile_id,dt)) if table_exists(cur,'performance_risk_score') else {}
                avail = one(cur, "SELECT MAX(availability_risk_score) availability_risk_score, MAX(downtime_component) downtime, MAX(no_data_component) no_data_gap FROM availability_risk_score WHERE pipeline_name=%s AND dt=%s", (args.profile_id,dt)) if table_exists(cur,'availability_risk_score') else {}
                op = one(cur, "SELECT MAX(score)*100 operational_risk_score FROM operational_risk_signal_day WHERE profile_id=%s AND dt=%s", (args.profile_id,dt)) if table_exists(cur,'operational_risk_signal_day') else {}
                lag = one(cur, "SELECT MAX(lag_adj_ms_p95) lag_adj_ms_p95, MAX(lag_deviation_ms) lag_deviation_ms FROM pipeline_lag_normalized_minute WHERE profile_id=%s AND dt=%s", (args.profile_id,dt)) if table_exists(cur,'pipeline_lag_normalized_minute') else {}
                data = one(cur, "SELECT MAX(final_risk_score)*100 data_risk_score FROM data_risk_score_day_v3 WHERE profile_id=%s AND dt=%s", (args.profile_id,dt)) if table_exists(cur,'data_risk_score_day_v3') else {}
                final_score = f(rs.get('final_risk_score'))
                stream_score = max(f(rs.get('stream_risk_score')), f(ss.get('stream_risk_score')))
                perf_score = max(f(rs.get('performance_risk_score')), f(perf.get('performance_risk_score')))
                avail_score = max(f(rs.get('availability_risk_score')), f(avail.get('availability_risk_score')))
                op_score = max(f(rs.get('operational_risk_score')), f(op.get('operational_risk_score')))
                data_score = max(f(rs.get('data_risk_score')), f(data.get('data_risk_score')))
                if final_score <= 0:
                    final_score = max(data_score,stream_score,perf_score,avail_score,op_score)
                binary = 0 if final_score < 20 and root in ('baseline_ok','scenario_applied',None) else 1
                label = root or ('baseline_ok' if binary == 0 else str(rs.get('dominant_risk_type') or 'risk'))
                hist_scores.append(final_score); hist_stream.append(stream_score); hist_perf.append(perf_score); hist_avail.append(avail_score); hist_op.append(op_score)
                ma = lambda xs: sum(xs[-7:])/max(1,len(xs[-7:]))
                row = dict(
                    profile_id=args.profile_id, dt=dt, scenario_name=scenario, scenario_type=stype, service_domain='all', event_count=event_count,
                    stream_missing_rate=f(ss.get('missing_rate')), stream_duplicate_ratio=f(ss.get('duplicate_ratio')), stream_ordering_gap_score=f(ss.get('ordering_gap_score')), stream_delay_p95=f(ss.get('avg_event_delay_ms')), stream_risk_score=stream_score,
                    throughput_drop_ratio=f(perf.get('throughput_drop')), consumer_lag_p95=f(perf.get('consumer_lag')), backlog_size_p95=f(perf.get('backlog_size')), performance_risk_score=perf_score,
                    availability_downtime_sec=f(avail.get('downtime'))*100, no_data_gap_minutes=f(avail.get('no_data_gap'))*100, availability_risk_score=avail_score,
                    lag_adj_ms_p95=f(lag.get('lag_adj_ms_p95')), lag_deviation_ms=f(lag.get('lag_deviation_ms')), operational_risk_score=op_score, data_risk_score=data_score,
                    risk_signal_count=1 if final_score >= 20 else 0, max_signal_score=f(rs.get('max_component_score'), final_score), max_component_score=f(rs.get('max_component_score'), max(data_score,stream_score,perf_score,avail_score,op_score)), weighted_average_score=f(rs.get('weighted_average_score')), persistence_score=f(rs.get('persistence_score')), cross_signal_boost=f(rs.get('cross_signal_boost')), cause_confidence_score=f(rs.get('cause_confidence_score')), cause_impact_score=f(rs.get('cause_impact_score')),
                    dominant_risk_type=rs.get('dominant_risk_type'), dominant_signal_name=rs.get('dominant_signal_name'), root_cause_code=root, root_cause_confidence=f(rs.get('cause_confidence_score')), final_risk_score=final_score, final_risk_grade=rs.get('final_risk_grade') or grade(final_score), ml_label=label, binary_label=binary,
                    dayofweek=dt_obj.weekday(), month_no=dt_obj.month, is_weekend=1 if dt_obj.weekday()>=5 else 0, prev_final_risk_score=prev_score, final_risk_score_diff=final_score-prev_score,
                    final_risk_score_ma7=ma(hist_scores), stream_score_ma7=ma(hist_stream), performance_score_ma7=ma(hist_perf), availability_score_ma7=ma(hist_avail), operational_score_ma7=ma(hist_op), feature_version=FEATURE_VERSION)
                prev_score = final_score
                columns = list(row.keys())
                ph = ','.join(['%s']*len(columns))
                updates = ','.join([f"{c}=VALUES({c})" for c in columns if c not in ('profile_id','dt','service_domain')])
                cur.execute(f"INSERT INTO risk_ml_training_dataset_v1 ({','.join(columns)}) VALUES ({ph}) ON DUPLICATE KEY UPDATE {updates}", [row[c] for c in columns])
                # Long feature rows
                numeric_features = {k:v for k,v in row.items() if isinstance(v,(int,float)) and k not in ('binary_label','dayofweek','month_no','is_weekend')}
                text_features = {'scenario_name':scenario,'scenario_type':stype,'dominant_risk_type':str(row.get('dominant_risk_type') or ''),'root_cause_code':str(root or '')}
                for k,v in numeric_features.items():
                    cur.execute("REPLACE INTO ml_risk_feature_day (profile_id,dt,feature_group,feature_name,feature_value,feature_text,feature_version) VALUES (%s,%s,%s,%s,%s,NULL,%s)", (args.profile_id,dt,'numeric',k,v,FEATURE_VERSION))
                for k,v in text_features.items():
                    cur.execute("REPLACE INTO ml_risk_feature_day (profile_id,dt,feature_group,feature_name,feature_value,feature_text,feature_version) VALUES (%s,%s,%s,%s,NULL,%s,%s)", (args.profile_id,dt,'categorical',k,v,FEATURE_VERSION))
                rows_built += 1
        conn.commit()
        print(f"[OK] built risk_ml_training_dataset_v1 rows={rows_built} profile_id={args.profile_id} dt_range={args.dt_from}..{args.dt_to}")
    finally:
        conn.close()

if __name__ == '__main__':
    main()
