from __future__ import annotations
import argparse
from datetime import datetime
import pymysql

def parse_args():
    p=argparse.ArgumentParser(description="Build v0.5 behavior-transaction and transaction-state mapping metadata. No risk scoring here.")
    p.add_argument("--db-host", required=True); p.add_argument("--db-port", type=int, required=True)
    p.add_argument("--db-user", required=True); p.add_argument("--db-pass", required=True); p.add_argument("--db-name", required=True)
    p.add_argument("--profile-id", required=True); p.add_argument("--target-date", required=True); p.add_argument("--run-id", type=int, required=True)
    p.add_argument("--source-gen-run-id", type=int); p.add_argument("--truncate-target", action="store_true")
    return p.parse_args()

def conn(a):
    return pymysql.connect(host=a.db_host, port=a.db_port, user=a.db_user, password=a.db_pass, database=a.db_name, charset="utf8mb4", autocommit=False, cursorclass=pymysql.cursors.DictCursor)

def gap_ms(a,b):
    if not a or not b: return None
    return int((b-a).total_seconds()*1000)

def key(*v): return '|'.join(str(x or '') for x in v)

def fetch(cur,table,a):
    where="profile_id=%s AND target_date=%s AND run_id=%s"; params=[a.profile_id,a.target_date,a.run_id]
    if a.source_gen_run_id:
        where += " AND source_gen_run_id=%s"; params.append(a.source_gen_run_id)
    cur.execute(f"SELECT * FROM {table} WHERE {where}", params)
    return cur.fetchall()

def build_btm(cur,a):
    b=fetch(cur,'canonical_behavior_events',a); t=fetch(cur,'canonical_transaction_events',a)
    tx_by_journey={}
    for r in t: tx_by_journey.setdefault(r.get('journey_id'),[]).append(r)
    behavior_anchors=[r for r in b if r.get('journey_stage') in ('checkout','payment','order_complete','refund') or r.get('order_id') or r.get('payment_id')]
    matched_tx=set(); vals=[]
    dup_keys={}
    for r in t:
        dk=key(r.get('journey_id'),r.get('order_id'),r.get('payment_id'),r.get('transaction_event'))
        dup_keys[dk]=dup_keys.get(dk,0)+1
    for br in behavior_anchors:
        candidates=[x for x in tx_by_journey.get(br.get('journey_id'),[]) if (not br.get('order_id') or x.get('order_id')==br.get('order_id'))]
        tr=min(candidates, key=lambda x: abs((x.get('event_time')-br.get('event_time')).total_seconds()) if x.get('event_time') and br.get('event_time') else 10**9, default=None)
        if tr:
            matched_tx.add(tr.get('canonical_transaction_event_id'))
            status='matched'; orphan=0; dup=1 if dup_keys.get(key(tr.get('journey_id'),tr.get('order_id'),tr.get('payment_id'),tr.get('transaction_event')),0)>1 else 0
            vals.append((a.run_id,a.profile_id,br.get('source_gen_run_id'),a.target_date,br.get('journey_id'),br.get('order_id'),br.get('payment_id'),br.get('canonical_behavior_event_id'),tr.get('canonical_transaction_event_id'),br.get('journey_stage'),tr.get('transaction_event'),status,orphan,dup,'not_evaluated',gap_ms(br.get('event_time'),tr.get('event_time')),key(br.get('journey_id'),br.get('order_id'),br.get('payment_id'))))
        else:
            vals.append((a.run_id,a.profile_id,br.get('source_gen_run_id'),a.target_date,br.get('journey_id'),br.get('order_id'),br.get('payment_id'),br.get('canonical_behavior_event_id'),None,br.get('journey_stage'),None,'behavior_only',1,0,'not_evaluated',None,key(br.get('journey_id'),br.get('order_id'),br.get('payment_id'))))
    for tr in t:
        if tr.get('canonical_transaction_event_id') in matched_tx: continue
        vals.append((a.run_id,a.profile_id,tr.get('source_gen_run_id'),a.target_date,tr.get('journey_id'),tr.get('order_id'),tr.get('payment_id'),None,tr.get('canonical_transaction_event_id'),None,tr.get('transaction_event'),'transaction_only',1,1 if dup_keys.get(key(tr.get('journey_id'),tr.get('order_id'),tr.get('payment_id'),tr.get('transaction_event')),0)>1 else 0,'not_evaluated',None,key(tr.get('journey_id'),tr.get('order_id'),tr.get('payment_id'))))
    sql="""INSERT INTO behavior_transaction_mapping(run_id,profile_id,source_gen_run_id,target_date,journey_id,order_id,payment_id,canonical_behavior_event_id,canonical_transaction_event_id,behavior_stage,transaction_event,mapping_status,orphan_flag,duplicate_flag,state_transition_flag,time_gap_ms,mapping_key) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"""
    if vals: cur.executemany(sql, vals)
    return len(vals)

def build_tsm(cur,a):
    t=fetch(cur,'canonical_transaction_events',a); s=fetch(cur,'canonical_state_events',a)
    st_by_journey={}
    for r in s: st_by_journey.setdefault(r.get('journey_id'),[]).append(r)
    expect={'order_created':['order_status_created'],'payment_approved':['order_status_created'],'refund_completed':['refund_status_completed']}
    matched=set(); vals=[]
    dup_keys={}
    for r in s:
        dk=key(r.get('journey_id'),r.get('order_id'),r.get('payment_id'),r.get('delivery_id'),r.get('state_event'))
        dup_keys[dk]=dup_keys.get(dk,0)+1
    for tr in t:
        expected=expect.get(tr.get('transaction_event'),[])
        candidates=[x for x in st_by_journey.get(tr.get('journey_id'),[]) if (not expected or x.get('state_event') in expected)]
        sr=min(candidates, key=lambda x: abs((x.get('event_time')-tr.get('event_time')).total_seconds()) if x.get('event_time') and tr.get('event_time') else 10**9, default=None)
        if sr:
            matched.add(sr.get('canonical_state_event_id'))
            status='matched'; flag='observed'; orphan=0; dup=1 if dup_keys.get(key(sr.get('journey_id'),sr.get('order_id'),sr.get('payment_id'),sr.get('delivery_id'),sr.get('state_event')),0)>1 else 0
            vals.append((a.run_id,a.profile_id,tr.get('source_gen_run_id'),a.target_date,tr.get('journey_id'),tr.get('order_id'),tr.get('payment_id'),tr.get('delivery_id'),tr.get('canonical_transaction_event_id'),sr.get('canonical_state_event_id'),tr.get('transaction_event'),sr.get('state_event'),status,orphan,dup,flag,gap_ms(tr.get('event_time'),sr.get('event_time')),key(tr.get('journey_id'),tr.get('order_id'),tr.get('payment_id'),tr.get('delivery_id'))))
        elif expected:
            vals.append((a.run_id,a.profile_id,tr.get('source_gen_run_id'),a.target_date,tr.get('journey_id'),tr.get('order_id'),tr.get('payment_id'),tr.get('delivery_id'),tr.get('canonical_transaction_event_id'),None,tr.get('transaction_event'),None,'transaction_without_state',1,0,'missing',None,key(tr.get('journey_id'),tr.get('order_id'),tr.get('payment_id'),tr.get('delivery_id'))))
    for sr in s:
        if sr.get('canonical_state_event_id') in matched: continue
        vals.append((a.run_id,a.profile_id,sr.get('source_gen_run_id'),a.target_date,sr.get('journey_id'),sr.get('order_id'),sr.get('payment_id'),sr.get('delivery_id'),None,sr.get('canonical_state_event_id'),None,sr.get('state_event'),'orphan_state',1,1 if dup_keys.get(key(sr.get('journey_id'),sr.get('order_id'),sr.get('payment_id'),sr.get('delivery_id'),sr.get('state_event')),0)>1 else 0,'orphan',None,key(sr.get('journey_id'),sr.get('order_id'),sr.get('payment_id'),sr.get('delivery_id'))))
    sql="""INSERT INTO transaction_state_mapping(run_id,profile_id,source_gen_run_id,target_date,journey_id,order_id,payment_id,delivery_id,canonical_transaction_event_id,canonical_state_event_id,transaction_event,state_event,mapping_status,orphan_flag,duplicate_flag,state_transition_flag,time_gap_ms,mapping_key) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"""
    if vals: cur.executemany(sql, vals)
    return len(vals)

def main():
    a=parse_args(); c=conn(a)
    try:
        with c.cursor() as cur:
            if a.truncate_target:
                for tab in ['behavior_transaction_mapping','transaction_state_mapping']:
                    cur.execute(f"DELETE FROM {tab} WHERE profile_id=%s AND target_date=%s AND run_id=%s", (a.profile_id,a.target_date,a.run_id))
            n1=build_btm(cur,a); n2=build_tsm(cur,a)
        c.commit(); print(f"[build_v05_reconciliation_mapping] behavior_transaction={n1} transaction_state={n2}")
    except Exception:
        c.rollback(); raise
    finally: c.close()
if __name__=='__main__': main()
