#!/usr/bin/env python3
from __future__ import annotations
import argparse, pymysql

def parse_args():
    p=argparse.ArgumentParser()
    for k in ["db-host","db-user","db-pass","db-name"]: p.add_argument("--"+k, required=True)
    p.add_argument("--db-port", type=int, required=True)
    return p.parse_args()

DDL = [
"""CREATE TABLE IF NOT EXISTS v05_ml_prediction_day (
 id BIGINT AUTO_INCREMENT PRIMARY KEY, run_id BIGINT NOT NULL, profile_id VARCHAR(100) NOT NULL,
 source_gen_run_id BIGINT NULL, target_date DATE NOT NULL, scenario_name VARCHAR(100) NOT NULL,
 model_source VARCHAR(100) NOT NULL, model_version VARCHAR(255) NULL,
 predicted_risk_class VARCHAR(100) NOT NULL, predicted_risk_score DOUBLE NOT NULL DEFAULT 0,
 predicted_risk_level VARCHAR(50) NOT NULL DEFAULT 'unknown',
 reconciliation_failure_probability DOUBLE NOT NULL DEFAULT 0, score_gap DOUBLE NOT NULL DEFAULT 0,
 prediction_status VARCHAR(50) NOT NULL DEFAULT 'PASS',
 feature_vector_json JSON NULL, prediction_payload_json JSON NULL,
 created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 KEY idx_scope(profile_id,target_date,scenario_name,run_id,source_gen_run_id), KEY idx_status(prediction_status))""",
"""CREATE TABLE IF NOT EXISTS v05_ml_output_verification_day (
 id BIGINT AUTO_INCREMENT PRIMARY KEY, run_id BIGINT NOT NULL, profile_id VARCHAR(100) NOT NULL,
 source_gen_run_id BIGINT NULL, target_date DATE NOT NULL, scenario_name VARCHAR(100) NOT NULL,
 feature_snapshot_flag TINYINT(1) NOT NULL DEFAULT 0, calibration_flag TINYINT(1) NOT NULL DEFAULT 0,
 prediction_flag TINYINT(1) NOT NULL DEFAULT 0, baseline_no_false_escalation_flag TINYINT(1) NOT NULL DEFAULT 0,
 score_gap_review_flag TINYINT(1) NOT NULL DEFAULT 0, label_concentration_review_flag TINYINT(1) NOT NULL DEFAULT 0,
 verification_status VARCHAR(50) NOT NULL, verification_reason TEXT NULL, verification_payload_json JSON NULL,
 created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 KEY idx_scope(profile_id,target_date,scenario_name,run_id,source_gen_run_id), KEY idx_status(verification_status))""",
"""CREATE TABLE IF NOT EXISTS v05_ml_feature_diagnostics_day (
 id BIGINT AUTO_INCREMENT PRIMARY KEY, run_id BIGINT NOT NULL, profile_id VARCHAR(100) NOT NULL,
 source_gen_run_id BIGINT NULL, target_date DATE NOT NULL, scenario_name VARCHAR(100) NOT NULL,
 feature_name VARCHAR(100) NOT NULL, feature_value DOUBLE NOT NULL DEFAULT 0, baseline_mean DOUBLE NULL,
 baseline_std DOUBLE NULL, z_score DOUBLE NULL, drift_flag TINYINT(1) NOT NULL DEFAULT 0,
 importance_score DOUBLE NOT NULL DEFAULT 0, diagnostic_status VARCHAR(50) NOT NULL DEFAULT 'PASS',
 diagnostic_payload_json JSON NULL, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 KEY idx_scope(profile_id,target_date,scenario_name,run_id,source_gen_run_id), KEY idx_feature(profile_id,feature_name,target_date))""",
"""CREATE TABLE IF NOT EXISTS v05_ai_validation_detail_day (
 id BIGINT AUTO_INCREMENT PRIMARY KEY, run_id BIGINT NOT NULL, profile_id VARCHAR(100) NOT NULL,
 source_gen_run_id BIGINT NULL, target_date DATE NOT NULL, scenario_name VARCHAR(100) NOT NULL,
 validation_type VARCHAR(100) NOT NULL, validation_status VARCHAR(50) NOT NULL,
 evidence_count INT NOT NULL DEFAULT 0, issue_count INT NOT NULL DEFAULT 0,
 missing_evidence_flag TINYINT(1) NOT NULL DEFAULT 0, unsupported_explanation_flag TINYINT(1) NOT NULL DEFAULT 0,
 hallucination_flag TINYINT(1) NOT NULL DEFAULT 0, wrong_action_flag TINYINT(1) NOT NULL DEFAULT 0,
 validation_reason TEXT NULL, validation_payload_json JSON NULL, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 KEY idx_scope(profile_id,target_date,scenario_name,run_id,source_gen_run_id), KEY idx_type(validation_type,validation_status))""",
"""CREATE TABLE IF NOT EXISTS v05_llm_execution_log_day (
 id BIGINT AUTO_INCREMENT PRIMARY KEY, run_id BIGINT NOT NULL, profile_id VARCHAR(100) NOT NULL,
 source_gen_run_id BIGINT NULL, target_date DATE NOT NULL, scenario_name VARCHAR(100) NOT NULL,
 provider VARCHAR(100) NOT NULL DEFAULT 'none', model_name VARCHAR(255) NULL, prompt_tokens INT NOT NULL DEFAULT 0,
 completion_tokens INT NOT NULL DEFAULT 0, total_tokens INT NOT NULL DEFAULT 0, latency_ms INT NOT NULL DEFAULT 0,
 api_status VARCHAR(100) NOT NULL DEFAULT 'not_called', api_error TEXT NULL, fallback_used TINYINT(1) NOT NULL DEFAULT 1,
 llm_cost_usd DOUBLE NOT NULL DEFAULT 0, governance_status VARCHAR(50) NOT NULL DEFAULT 'PASS',
 execution_payload_json JSON NULL, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 KEY idx_scope(profile_id,target_date,scenario_name,run_id,source_gen_run_id), KEY idx_status(governance_status))"""
]

def main():
    a=parse_args()
    con=pymysql.connect(host=a.db_host,port=a.db_port,user=a.db_user,password=a.db_pass,database=a.db_name,charset="utf8mb4",autocommit=True)
    try:
        with con.cursor() as cur:
            for ddl in DDL: cur.execute(ddl)
    finally: con.close()
    print("[OK] ensured v0.5 ML/AI governance tables")
if __name__=="__main__": main()
