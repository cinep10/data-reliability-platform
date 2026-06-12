from __future__ import annotations
import argparse, json
from pathlib import Path
from datetime import datetime
import pymysql

def parse_args():
    p=argparse.ArgumentParser(description="Load v0.5 Phase1 transaction/state JSONL into raw persistence tables.")
    p.add_argument("--db-host", required=True); p.add_argument("--db-port", type=int, required=True)
    p.add_argument("--db-user", required=True); p.add_argument("--db-pass", required=True); p.add_argument("--db-name", required=True)
    p.add_argument("--profile-id", required=True); p.add_argument("--target-date", required=True); p.add_argument("--run-id", type=int, required=True)
    p.add_argument("--source-gen-run-id", type=int); p.add_argument("--input-dir", required=True); p.add_argument("--truncate-target", action="store_true")
    return p.parse_args()

def conn(a):
    return pymysql.connect(host=a.db_host, port=a.db_port, user=a.db_user, password=a.db_pass, database=a.db_name, charset="utf8mb4", autocommit=False, cursorclass=pymysql.cursors.DictCursor)

def dt(s):
    if not s: return None
    return datetime.fromisoformat(str(s).replace('Z','+00:00')).replace(tzinfo=None)

def read_jsonl(path: Path):
    with path.open('r', encoding='utf-8') as f:
        for i,line in enumerate(f,1):
            line=line.strip()
            if not line: continue
            yield i,json.loads(line)

def load_tx(cur,a,path):
    sql="""INSERT INTO v05_transaction_log_raw(profile_id,target_date,run_id,source_gen_run_id,source_file_path,source_row_number,event_time,journey_id,transaction_event,customer_id,product_id,cart_id,coupon_id,order_id,payment_id,delivery_id,amount,currency,source_system,behavior_anchor_stage,behavior_anchor_offset_sec,transaction_delay_ms,anomaly_flag,payload_json)
    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"""
    rows=[]
    for i,r in read_jsonl(path):
        rows.append((a.profile_id,a.target_date,a.run_id,a.source_gen_run_id,str(path),i,dt(r.get('event_time')),r.get('journey_id'),r.get('transaction_event'),r.get('customer_id'),r.get('product_id'),r.get('cart_id'),r.get('coupon_id'),r.get('order_id'),r.get('payment_id'),r.get('delivery_id'),r.get('amount'),r.get('currency'),r.get('source_system'),r.get('behavior_anchor_stage'),r.get('behavior_anchor_offset_sec'),r.get('transaction_delay_ms'),1 if r.get('anomaly_flag') else 0,json.dumps(r,ensure_ascii=False,default=str)))
    if rows: cur.executemany(sql, rows)
    return len(rows)

def load_state(cur,a,path):
    sql="""INSERT INTO v05_state_log_raw(profile_id,target_date,run_id,source_gen_run_id,source_file_path,source_row_number,event_time,journey_id,state_event,customer_id,order_id,payment_id,delivery_id,coupon_id,order_amount,expected_amount,state_status,source_system,behavior_anchor_stage,behavior_anchor_offset_sec,state_transition_delay_ms,anomaly_flag,payload_json)
    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"""
    rows=[]
    for i,r in read_jsonl(path):
        rows.append((a.profile_id,a.target_date,a.run_id,a.source_gen_run_id,str(path),i,dt(r.get('event_time')),r.get('journey_id'),r.get('state_event'),r.get('customer_id'),r.get('order_id'),r.get('payment_id'),r.get('delivery_id'),r.get('coupon_id'),r.get('order_amount'),r.get('expected_amount'),r.get('state_status'),r.get('source_system'),r.get('behavior_anchor_stage'),r.get('behavior_anchor_offset_sec'),r.get('state_transition_delay_ms'),1 if r.get('anomaly_flag') else 0,json.dumps(r,ensure_ascii=False,default=str)))
    if rows: cur.executemany(sql, rows)
    return len(rows)

def main():
    a=parse_args(); d=Path(a.input_dir)
    tx=next(iter(sorted(d.glob('*_transaction.jsonl'))), None); st=next(iter(sorted(d.glob('*_state.jsonl'))), None)
    if not tx: raise SystemExit(f"transaction jsonl missing in {d}")
    if not st: raise SystemExit(f"state jsonl missing in {d}")
    c=conn(a)
    try:
        with c.cursor() as cur:
            if a.truncate_target:
                for t in ['v05_transaction_log_raw','v05_state_log_raw']:
                    cur.execute(f"DELETE FROM {t} WHERE profile_id=%s AND target_date=%s AND run_id=%s", (a.profile_id,a.target_date,a.run_id))
            n1=load_tx(cur,a,tx); n2=load_state(cur,a,st)
        c.commit(); print(f"[load_v05_transaction_state_raw] transaction={n1} state={n2}")
    except Exception:
        c.rollback(); raise
    finally: c.close()
if __name__=='__main__': main()
