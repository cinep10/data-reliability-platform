from __future__ import annotations
import pymysql
from typing import Any

class SimulatorRunRegistry:
    def __init__(self, host: str, port: int, user: str, password: str, db: str):
        self.conn = pymysql.connect(host=host, port=port, user=user, password=password, database=db, charset='utf8mb4', autocommit=False, cursorclass=pymysql.cursors.DictCursor)

    def close(self):
        self.conn.close()

    def create_source_generation_run(self, **kwargs: Any) -> int:
        sql = '''INSERT INTO source_generation_run
        (profile_id, target_date, scenario_name, scenario_mode, source_mode, exogenous_mode, simulator_version, status, created_by, note)
        VALUES (%(profile_id)s,%(target_date)s,%(scenario_name)s,%(scenario_mode)s,%(source_mode)s,%(exogenous_mode)s,%(simulator_version)s,%(status)s,%(created_by)s,%(note)s)'''
        with self.conn.cursor() as cur:
            cur.execute(sql, kwargs)
            self.conn.commit()
            return cur.lastrowid

    def create_exogenous_snapshot(self, source_gen_run_id: int, profile_id: str, target_date: str, **rec: Any) -> int:
        rec = dict(rec)
        rec.update({'source_gen_run_id': source_gen_run_id, 'profile_id': profile_id, 'target_date': target_date})
        sql = '''INSERT INTO exogenous_state_snapshot
        (source_gen_run_id, profile_id, target_date, enabled, weather_type, campaign_flag, system_flag, volume_multiplier, conversion_multiplier, timeout_multiplier, retry_multiplier, source, as_of_ts, raw_payload_json)
        VALUES (%(source_gen_run_id)s,%(profile_id)s,%(target_date)s,%(enabled)s,%(weather_type)s,%(campaign_flag)s,%(system_flag)s,%(volume_multiplier)s,%(conversion_multiplier)s,%(timeout_multiplier)s,%(retry_multiplier)s,%(source)s,%(as_of_ts)s,%(raw_payload_json)s)'''
        with self.conn.cursor() as cur:
            cur.execute(sql, rec)
            self.conn.commit()
            return cur.lastrowid

    def bulk_insert_source_file_manifests(self, manifests: list[dict[str, Any]]) -> None:
        if not manifests:
            return
        sql = '''INSERT INTO source_file_manifest
        (source_gen_run_id, exogenous_snapshot_id, profile_id, target_date, service_domain, file_path, file_name, file_size_bytes, checksum, record_count)
        VALUES (%(source_gen_run_id)s,%(exogenous_snapshot_id)s,%(profile_id)s,%(target_date)s,%(service_domain)s,%(file_path)s,%(file_name)s,%(file_size_bytes)s,%(checksum)s,%(record_count)s)'''
        with self.conn.cursor() as cur:
            cur.executemany(sql, manifests)
        self.conn.commit()

    def mark_source_generation_run_completed(self, source_gen_run_id: int) -> None:
        with self.conn.cursor() as cur:
            cur.execute('UPDATE source_generation_run SET status=%s, ended_at=NOW() WHERE source_gen_run_id=%s', ('completed', source_gen_run_id))
        self.conn.commit()

    def mark_source_generation_run_failed(self, source_gen_run_id: int, note: str) -> None:
        with self.conn.cursor() as cur:
            cur.execute('UPDATE source_generation_run SET status=%s, ended_at=NOW(), note=%s WHERE source_gen_run_id=%s', ('failed', note[:1000], source_gen_run_id))
        self.conn.commit()
