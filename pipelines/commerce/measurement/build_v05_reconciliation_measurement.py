from __future__ import annotations
import argparse, json, math
from decimal import Decimal
import pymysql


def parse_args():
    p = argparse.ArgumentParser(description='Materialize v0.5 Phase3 reconciliation measurements from Phase2 mapping metadata. No risk scoring.')
    p.add_argument('--db-host', required=True); p.add_argument('--db-port', type=int, required=True)
    p.add_argument('--db-user', required=True); p.add_argument('--db-pass', required=True); p.add_argument('--db-name', required=True)
    p.add_argument('--profile-id', required=True); p.add_argument('--target-date', required=True); p.add_argument('--run-id', type=int, required=True)
    p.add_argument('--source-gen-run-id', type=int); p.add_argument('--scenario-name', default='baseline')
    p.add_argument('--truncate-target', action='store_true')
    return p.parse_args()


def conn(a):
    return pymysql.connect(host=a.db_host, port=a.db_port, user=a.db_user, password=a.db_pass, database=a.db_name, charset='utf8mb4', autocommit=False, cursorclass=pymysql.cursors.DictCursor)


def scope(a, alias=''):
    p = f'{alias}.' if alias else ''
    where = f"{p}profile_id=%s AND {p}target_date=%s AND {p}run_id=%s"
    vals = [a.profile_id, a.target_date, a.run_id]
    if a.source_gen_run_id is not None:
        where += f" AND {p}source_gen_run_id=%s"
        vals.append(a.source_gen_run_id)
    return where, vals


def one(cur, sql, params):
    cur.execute(sql, params)
    row = cur.fetchone() or {}
    return next(iter(row.values())) if row else 0


def pct(num, den):
    if not den:
        return Decimal('0')
    return Decimal(str(round(float(num) / float(den), 6)))


def percentile(values, p):
    vals = sorted([int(v) for v in values if v is not None])
    if not vals:
        return None
    idx = int(math.ceil((p / 100.0) * len(vals))) - 1
    return vals[max(0, min(idx, len(vals)-1))]


def avg(values):
    vals = [int(v) for v in values if v is not None]
    return int(sum(vals) / len(vals)) if vals else None


def fetch_gaps(cur, table, a, statuses):
    wh, params = scope(a)
    placeholders = ','.join(['%s'] * len(statuses))
    cur.execute(f"SELECT time_gap_ms FROM {table} WHERE {wh} AND mapping_status IN ({placeholders}) AND time_gap_ms IS NOT NULL", params + list(statuses))
    return [r['time_gap_ms'] for r in cur.fetchall()]


def main():
    a = parse_args(); c = conn(a)
    try:
        with c.cursor() as cur:
            wh, params = scope(a)
            if a.truncate_target:
                cur.execute(f"DELETE FROM v05_reconciliation_measurement_day WHERE {wh}", params)

            b_cnt = one(cur, f"SELECT COUNT(*) FROM canonical_behavior_events WHERE {wh}", params)
            t_cnt = one(cur, f"SELECT COUNT(*) FROM canonical_transaction_events WHERE {wh}", params)
            s_cnt = one(cur, f"SELECT COUNT(*) FROM canonical_state_events WHERE {wh}", params)

            btm_total = one(cur, f"SELECT COUNT(*) FROM behavior_transaction_mapping WHERE {wh}", params)
            btm_matched = one(cur, f"SELECT COUNT(*) FROM behavior_transaction_mapping WHERE {wh} AND mapping_status='matched'", params)
            behavior_only = one(cur, f"SELECT COUNT(*) FROM behavior_transaction_mapping WHERE {wh} AND mapping_status='behavior_only'", params)
            transaction_only = one(cur, f"SELECT COUNT(*) FROM behavior_transaction_mapping WHERE {wh} AND mapping_status='transaction_only'", params)
            btm_dup = one(cur, f"SELECT COUNT(*) FROM behavior_transaction_mapping WHERE {wh} AND duplicate_flag=1", params)

            tsm_total = one(cur, f"SELECT COUNT(*) FROM transaction_state_mapping WHERE {wh}", params)
            tsm_matched = one(cur, f"SELECT COUNT(*) FROM transaction_state_mapping WHERE {wh} AND mapping_status='matched'", params)
            orphan_state = one(cur, f"SELECT COUNT(*) FROM transaction_state_mapping WHERE {wh} AND mapping_status='orphan_state'", params)
            tx_without_state = one(cur, f"SELECT COUNT(*) FROM transaction_state_mapping WHERE {wh} AND mapping_status='transaction_without_state'", params)
            tsm_dup = one(cur, f"SELECT COUNT(*) FROM transaction_state_mapping WHERE {wh} AND duplicate_flag=1", params)

            payment_count = one(cur, f"SELECT COUNT(*) FROM canonical_transaction_events WHERE {wh} AND transaction_event IN ('payment_approved','payment_requested')", params)
            order_created = one(cur, f"SELECT COUNT(*) FROM canonical_transaction_events WHERE {wh} AND transaction_event='order_created'", params)
            refund_completed = one(cur, f"SELECT COUNT(*) FROM canonical_transaction_events WHERE {wh} AND transaction_event='refund_completed'", params)
            refund_state = one(cur, f"SELECT COUNT(*) FROM canonical_state_events WHERE {wh} AND state_event='refund_status_completed'", params)
            coupon_tx = one(cur, f"SELECT COUNT(*) FROM canonical_transaction_events WHERE {wh} AND transaction_event='coupon_applied'", params)
            coupon_behavior = one(cur, f"SELECT COUNT(*) FROM canonical_behavior_events WHERE {wh} AND (coupon_id IS NOT NULL AND coupon_id <> '')", params)

            duplicate_order = one(cur, f"SELECT COUNT(*) FROM (SELECT order_id, COUNT(*) c FROM canonical_transaction_events WHERE {wh} AND order_id IS NOT NULL AND order_id <> '' GROUP BY order_id HAVING c > 3) x", params)
            duplicate_payment = one(cur, f"SELECT COUNT(*) FROM (SELECT payment_id, transaction_event, COUNT(*) c FROM canonical_transaction_events WHERE {wh} AND payment_id IS NOT NULL AND payment_id <> '' GROUP BY payment_id, transaction_event HAVING c > 1) x", params)

            btm_gaps = fetch_gaps(cur, 'behavior_transaction_mapping', a, ['matched'])
            tsm_gaps = fetch_gaps(cur, 'transaction_state_mapping', a, ['matched'])

            payment_delay = one(cur, f"SELECT AVG(transaction_delay_ms) FROM canonical_transaction_events WHERE {wh} AND transaction_event IN ('payment_requested','payment_approved')", params)
            delivery_delay = one(cur, f"SELECT AVG(state_transition_delay_ms) FROM canonical_state_events WHERE {wh} AND state_event LIKE 'delivery_%%'", params)
            refund_delay = one(cur, f"SELECT AVG(state_transition_delay_ms) FROM canonical_state_events WHERE {wh} AND state_event LIKE 'refund_%%'", params)

            conversion_gap = pct(abs(int(btm_matched) - int(order_created)), max(int(btm_matched), int(order_created), 1))
            payment_order_gap = pct(abs(int(payment_count) - int(order_created)), max(int(payment_count), 1))
            refund_transition_gap = pct(abs(int(refund_completed) - int(refund_state)), max(int(refund_completed), 1))
            coupon_gap = pct(abs(int(coupon_behavior) - int(coupon_tx)), max(int(coupon_behavior), 1))
            propagation_distortion = int(behavior_only or 0) + int(transaction_only or 0) + int(orphan_state or 0) + int(tx_without_state or 0) + int(btm_dup or 0) + int(tsm_dup or 0)

            payload = {
                'principle': 'Phase3 measurement materializes cross-log gaps only; risk interpretation is Phase4.',
                'counts': {'behavior': b_cnt, 'transaction': t_cnt, 'state': s_cnt},
                'mapping_counts': {'behavior_transaction': btm_total, 'transaction_state': tsm_total},
                'delay_basis': {'btm_gap_rows': len(btm_gaps), 'tsm_gap_rows': len(tsm_gaps)}
            }
            sql = """
            REPLACE INTO v05_reconciliation_measurement_day(
              run_id,profile_id,source_gen_run_id,target_date,scenario_name,
              behavior_event_count,transaction_event_count,state_event_count,
              behavior_transaction_total_count,behavior_transaction_matched_count,behavior_only_count,transaction_only_count,behavior_transaction_match_rate,conversion_gap,
              transaction_state_total_count,transaction_state_matched_count,orphan_state_count,transaction_without_state_count,transaction_state_match_rate,payment_order_gap,refund_transition_gap,
              avg_behavior_transaction_gap_ms,p95_behavior_transaction_gap_ms,avg_transaction_state_gap_ms,p95_transaction_state_gap_ms,payment_processing_delay_ms,delivery_state_delay_ms,refund_delay_ms,
              duplicate_order_count,duplicate_payment_count,coupon_reconciliation_gap,propagation_distortion_count,measurement_payload_json
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """
            cur.execute(sql, (
                a.run_id, a.profile_id, a.source_gen_run_id, a.target_date, a.scenario_name,
                b_cnt, t_cnt, s_cnt,
                btm_total, btm_matched, behavior_only, transaction_only, pct(btm_matched, btm_total), conversion_gap,
                tsm_total, tsm_matched, orphan_state, tx_without_state, pct(tsm_matched, tsm_total), payment_order_gap, refund_transition_gap,
                avg(btm_gaps), percentile(btm_gaps, 95), avg(tsm_gaps), percentile(tsm_gaps, 95), int(payment_delay or 0), int(delivery_delay or 0), int(refund_delay or 0),
                duplicate_order, duplicate_payment, coupon_gap, propagation_distortion, json.dumps(payload, ensure_ascii=False)
            ))
        c.commit()
        print('[build_v05_reconciliation_measurement] OK')
    except Exception:
        c.rollback(); raise
    finally:
        c.close()

if __name__ == '__main__':
    main()
