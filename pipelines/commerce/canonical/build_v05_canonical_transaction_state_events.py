from __future__ import annotations
import argparse, json, re
import pymysql

PAIR_RE = re.compile(r"\s*([^=;\s]+)=([^;]*)")

def parse_args():
    p=argparse.ArgumentParser(description="Build v0.5 canonical behavior/transaction/state events. Canonical = business normalization, not risk scoring.")
    p.add_argument("--db-host", required=True); p.add_argument("--db-port", type=int, required=True)
    p.add_argument("--db-user", required=True); p.add_argument("--db-pass", required=True); p.add_argument("--db-name", required=True)
    p.add_argument("--profile-id", required=True); p.add_argument("--target-date", required=True); p.add_argument("--run-id", type=int, required=True)
    p.add_argument("--source-gen-run-id", type=int); p.add_argument("--truncate-target", action="store_true")
    return p.parse_args()

def conn(a):
    return pymysql.connect(host=a.db_host, port=a.db_port, user=a.db_user, password=a.db_pass, database=a.db_name, charset="utf8mb4", autocommit=False, cursorclass=pymysql.cursors.DictCursor)

def parse_kv(kv: str|None) -> dict[str,str]:
    out={}
    if not kv: return out
    for part in kv.split(';'):
        part=part.strip()
        if '=' in part:
            k,v=part.split('=',1); out[k.strip()]=v.strip()
    return out

def num(v):
    if v in (None,''): return None
    try: return float(v)
    except Exception: return None

def dup_key(*vals):
    return '|'.join(str(v or '') for v in vals)

def build_behavior(cur,a):
    where="profile_id=%s AND target_date=%s AND run_id=%s"; params=[a.profile_id,a.target_date,a.run_id]
    if a.source_gen_run_id:
        where += " AND source_gen_run_id=%s"; params.append(a.source_gen_run_id)
    cur.execute(f"SELECT * FROM canonical_events WHERE {where} ORDER BY event_time, canonical_event_id", params)
    rows=cur.fetchall(); vals=[]
    sql="""INSERT INTO canonical_behavior_events(canonical_event_id,run_id,profile_id,source_gen_run_id,target_date,event_time,event_type,uid,pcid,session_id,journey_id,journey_stage,product_id,cart_id,coupon_id,order_id,payment_id,delivery_id,customer_segment,device_type,page_type,funnel_stage,amount_expected,amount_actual,scenario_id,anomaly_type,reconciliation_flag,canonical_payload_json)
    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"""
    for r in rows:
        kv=parse_kv(r.get('kv_raw'))
        journey_id=kv.get('journey_id')
        if not journey_id: continue
        vals.append((r.get('canonical_event_id'),a.run_id,a.profile_id,r.get('source_gen_run_id'),r.get('target_date'),r.get('event_time'),r.get('event_type'),r.get('uid'),r.get('pcid'),r.get('session_id'),journey_id,kv.get('journey_stage') or r.get('funnel_stage'),kv.get('product_id'),kv.get('cart_id'),kv.get('coupon_id'),kv.get('order_id'),kv.get('payment_id'),kv.get('delivery_id'),kv.get('customer_segment'),kv.get('device_type') or r.get('device_type'),r.get('page_type'),kv.get('funnel_stage') or r.get('funnel_stage'),num(kv.get('amount_expected')),num(kv.get('amount_actual')),r.get('scenario_id'),r.get('anomaly_type'),r.get('reconciliation_flag'),json.dumps({'canonical_events':r,'commerce_cookie':kv},ensure_ascii=False,default=str)))
    if vals: cur.executemany(sql, vals)
    return len(vals)

def build_tx(cur,a):
    where="profile_id=%s AND target_date=%s AND run_id=%s"; params=[a.profile_id,a.target_date,a.run_id]
    if a.source_gen_run_id:
        where += " AND source_gen_run_id=%s"; params.append(a.source_gen_run_id)
    cur.execute(f"SELECT * FROM v05_transaction_log_raw WHERE {where} ORDER BY event_time, raw_transaction_id", params)
    rows=cur.fetchall(); vals=[]
    sql="""INSERT INTO canonical_transaction_events(raw_transaction_id,run_id,profile_id,source_gen_run_id,target_date,event_time,journey_id,transaction_event,transaction_type,customer_id,product_id,cart_id,coupon_id,order_id,payment_id,delivery_id,amount,currency,source_system,behavior_anchor_stage,transaction_delay_ms,duplicate_key,anomaly_flag,canonical_payload_json)
    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"""
    for r in rows:
        t=r.get('transaction_event')
        vals.append((r.get('raw_transaction_id'),a.run_id,a.profile_id,r.get('source_gen_run_id'),r.get('target_date'),r.get('event_time'),r.get('journey_id'),t,t,r.get('customer_id'),r.get('product_id'),r.get('cart_id'),r.get('coupon_id'),r.get('order_id'),r.get('payment_id'),r.get('delivery_id'),r.get('amount'),r.get('currency'),r.get('source_system'),r.get('behavior_anchor_stage'),r.get('transaction_delay_ms'),dup_key(r.get('journey_id'),r.get('order_id'),r.get('payment_id'),t),r.get('anomaly_flag'),json.dumps(r,ensure_ascii=False,default=str)))
    if vals: cur.executemany(sql, vals)
    return len(vals)

def state_entity(name):
    if str(name).startswith('delivery_'): return 'delivery'
    if str(name).startswith('refund_'): return 'refund'
    if str(name).startswith('order_'): return 'order'
    return 'unknown'

def build_state(cur,a):
    where="profile_id=%s AND target_date=%s AND run_id=%s"; params=[a.profile_id,a.target_date,a.run_id]
    if a.source_gen_run_id:
        where += " AND source_gen_run_id=%s"; params.append(a.source_gen_run_id)
    cur.execute(f"SELECT * FROM v05_state_log_raw WHERE {where} ORDER BY event_time, raw_state_id", params)
    rows=cur.fetchall(); vals=[]
    sql="""INSERT INTO canonical_state_events(raw_state_id,run_id,profile_id,source_gen_run_id,target_date,event_time,journey_id,state_event,state_entity,state_status,customer_id,order_id,payment_id,delivery_id,coupon_id,order_amount,expected_amount,source_system,behavior_anchor_stage,state_transition_delay_ms,duplicate_key,anomaly_flag,canonical_payload_json)
    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"""
    for r in rows:
        s=r.get('state_event')
        vals.append((r.get('raw_state_id'),a.run_id,a.profile_id,r.get('source_gen_run_id'),r.get('target_date'),r.get('event_time'),r.get('journey_id'),s,state_entity(s),r.get('state_status'),r.get('customer_id'),r.get('order_id'),r.get('payment_id'),r.get('delivery_id'),r.get('coupon_id'),r.get('order_amount'),r.get('expected_amount'),r.get('source_system'),r.get('behavior_anchor_stage'),r.get('state_transition_delay_ms'),dup_key(r.get('journey_id'),r.get('order_id'),r.get('payment_id'),r.get('delivery_id'),s),r.get('anomaly_flag'),json.dumps(r,ensure_ascii=False,default=str)))
    if vals: cur.executemany(sql, vals)
    return len(vals)

def main():
    a=parse_args(); c=conn(a)
    try:
        with c.cursor() as cur:
            if a.truncate_target:
                for t in ['canonical_behavior_events','canonical_transaction_events','canonical_state_events']:
                    cur.execute(f"DELETE FROM {t} WHERE profile_id=%s AND target_date=%s AND run_id=%s", (a.profile_id,a.target_date,a.run_id))
            nb=build_behavior(cur,a); nt=build_tx(cur,a); ns=build_state(cur,a)
        c.commit(); print(f"[build_v05_canonical_transaction_state_events] behavior={nb} transaction={nt} state={ns}")
    except Exception:
        c.rollback(); raise
    finally: c.close()
if __name__=='__main__': main()
