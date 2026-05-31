#!/usr/bin/env python3
import argparse, json, pymysql
from datetime import date, datetime

DEFAULT_DB = dict(host='127.0.0.1', port=3306, user='nethru', password='nethru1234', db='weblog', charset='utf8mb4', autocommit=False)

def add_db_args(p):
    p.add_argument('--db-host','--host',dest='host',default='127.0.0.1')
    p.add_argument('--db-port','--port',dest='port',type=int,default=3306)
    p.add_argument('--db-user','--user',dest='user',default='nethru')
    p.add_argument('--db-pass','--password',dest='password',default='nethru1234')
    p.add_argument('--db-name','--db',dest='db',default='weblog')
    p.add_argument('--profile-id',required=True)
    p.add_argument('--dt-from',required=True)
    p.add_argument('--dt-to',required=True)
    return p

def connect(args):
    return pymysql.connect(host=args.host, port=args.port, user=args.user, password=args.password, database=args.db, charset='utf8mb4', autocommit=False, cursorclass=pymysql.cursors.DictCursor)

def jdump(x):
    return json.dumps(x, ensure_ascii=False, default=str)

def table_exists(cur, table):
    cur.execute("SELECT COUNT(*) AS c FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=%s", (table,))
    return cur.fetchone()['c'] > 0

def column_exists(cur, table, col):
    cur.execute("SELECT COUNT(*) AS c FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s AND column_name=%s", (table,col))
    return cur.fetchone()['c'] > 0

def rows_for_context(cur, profile_id, dt_from, dt_to):
    # Prefer explicit Phase4 ML result table; fallback to legacy prediction result.
    ml_join = ""
    ml_select = "NULL AS predicted_semantic_risk, NULL AS ml_risk_score, NULL AS score_gap, NULL AS ml_risk_grade"
    if table_exists(cur, 'ml_risk_score_day'):
        ml_select = "ml.predicted_semantic_risk AS predicted_semantic_risk, ml.ml_risk_score AS ml_risk_score, ml.score_gap AS score_gap, ml.ml_risk_grade AS ml_risk_grade"
        ml_join = "LEFT JOIN ml_risk_score_day ml ON ml.profile_id=u.profile_id AND ml.dt=u.dt"
    elif table_exists(cur, 'ml_prediction_result'):
        ml_select = "ml.predicted_risk_status AS predicted_semantic_risk, ml.ml_risk_score AS ml_risk_score, ml.score_gap AS score_gap, ml.predicted_risk_status AS ml_risk_grade"
        ml_join = "LEFT JOIN ml_prediction_result ml ON ml.profile_id=u.profile_id AND ml.dt=u.dt"

    sql = f"""
    SELECT
      u.profile_id, u.dt, COALESCE(u.run_id,'1') AS run_id, u.scenario_name,
      u.dominant_semantic_risk, u.final_risk_level, u.overall_risk_score,
      s.semantic_confidence, s.integrity_score, s.completeness_score, s.timeliness_score, s.consistency_score, s.availability_score,
      r.drift_score, r.propagation_score, r.amplification_score, r.distortion_score, r.baseline_delta, r.correlation_score,
      m.direct_completeness_delta, m.direct_timeliness_delta, m.direct_availability_delta, m.direct_integrity_delta, m.delta_source_type, m.measurement_realism_status,
      a.recommended_action, a.priority,
      {ml_select}
    FROM unified_reliability_score_day u
    LEFT JOIN semantic_interpretation_day s ON s.profile_id=u.profile_id AND s.dt=u.dt AND COALESCE(s.run_id,'1')=COALESCE(u.run_id,'1')
    LEFT JOIN r_reliability_analysis_result_day r ON r.profile_id=u.profile_id AND r.dt=u.dt AND COALESCE(r.run_id,'1')=COALESCE(u.run_id,'1')
    LEFT JOIN measurement_realism_day m ON m.profile_id=u.profile_id AND m.dt=u.dt AND COALESCE(m.run_id,'1')=COALESCE(u.run_id,'1')
    LEFT JOIN action_recommendation_day a ON a.profile_id=u.profile_id AND a.dt=u.dt AND COALESCE(a.run_id,'1')=COALESCE(u.run_id,'1')
    {ml_join}
    WHERE u.profile_id=%s AND u.dt BETWEEN %s AND %s
    ORDER BY u.dt, u.run_id
    """
    cur.execute(sql, (profile_id, dt_from, dt_to))
    return cur.fetchall()

ACTION_MAP = {
    'Completeness': 'ingestion validation',
    'Timeliness': 'queue/backlog check',
    'Integrity': 'reconciliation',
    'Consistency': 'mapping validation',
    'Availability': 'retry/timeout tuning',
    'None': 'no action',
    None: 'no action',
}
