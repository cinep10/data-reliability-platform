#!/usr/bin/env python3
import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _measurement_utils import connect, count_rows, agg_metric, safe_float, safe_int

def main():
    p = argparse.ArgumentParser(description="Build Phase3 measurement_stream_day from stream measurement assets.")
    p.add_argument("--db-host", default="127.0.0.1")
    p.add_argument("--db-port", type=int, default=3306)
    p.add_argument("--db-user", required=True)
    p.add_argument("--db-pass", required=True)
    p.add_argument("--db-name", required=True)
    p.add_argument("--profile-id", required=True)
    p.add_argument("--dt")
    p.add_argument("--dt-from")
    p.add_argument("--dt-to")
    p.add_argument("--run-id", default="")
    p.add_argument("--scenario-name", default="")
    p.add_argument("--truncate-target", action="store_true")
    args = p.parse_args()
    dt = args.dt or args.dt_from
    if not dt:
        raise SystemExit("--dt or --dt-from required")

    conn = connect(args)
    try:
        with conn.cursor() as cur:
            stream_event_count = count_rows(cur, "stg_event_stream", args.profile_id, dt, args.run_id, ("dt","target_date"))

            duplicate_count = safe_int(agg_metric(cur, "stream_duplicate_result_day", ("duplicate_count","dup_count","duplicate_events"), args.profile_id, dt, args.run_id, "SUM"))
            duplicate_rate = safe_float(agg_metric(cur, "stream_duplicate_result_day", ("duplicate_rate","dup_rate"), args.profile_id, dt, args.run_id, "MAX"))
            if duplicate_rate == 0 and stream_event_count:
                duplicate_rate = duplicate_count / stream_event_count

            ordering_error_count = safe_int(agg_metric(cur, "stream_ordering_result_day", ("ordering_error_count","out_of_order_count","error_count"), args.profile_id, dt, args.run_id, "SUM"))
            ordering_error_rate = safe_float(agg_metric(cur, "stream_ordering_result_day", ("ordering_error_rate","out_of_order_rate","error_rate"), args.profile_id, dt, args.run_id, "MAX"))
            if ordering_error_rate == 0 and stream_event_count:
                ordering_error_rate = ordering_error_count / stream_event_count

            latency_p50_ms = safe_float(agg_metric(cur, "stream_latency_result_day", ("latency_p50_ms","p50_ms","p50_latency_ms"), args.profile_id, dt, args.run_id, "MAX"))
            latency_p95_ms = safe_float(agg_metric(cur, "stream_latency_result_day", ("latency_p95_ms","p95_ms","p95_latency_ms"), args.profile_id, dt, args.run_id, "MAX"))
            latency_max_ms = safe_float(agg_metric(cur, "stream_latency_result_day", ("latency_max_ms","max_ms","max_latency_ms"), args.profile_id, dt, args.run_id, "MAX"))

            completeness_rate = safe_float(agg_metric(cur, "stream_completeness_result_day", ("completeness_rate","complete_rate","match_rate"), args.profile_id, dt, args.run_id, "MAX"))
            if completeness_rate == 0:
                completeness_rate = safe_float(agg_metric(cur, "stream_reliability_summary_day", ("completeness_rate","stream_completeness_rate"), args.profile_id, dt, args.run_id, "MAX"))
            if completeness_rate == 0:
                canonical_count = count_rows(cur, "canonical_events", args.profile_id, dt, args.run_id, ("target_date","dt"))
                completeness_rate = (stream_event_count / canonical_count) if canonical_count else (1.0 if stream_event_count else 0.0)

            throughput_per_minute = safe_float(agg_metric(cur, "stream_reliability_summary_day", ("throughput_per_minute","events_per_minute"), args.profile_id, dt, args.run_id, "MAX"))
            if throughput_per_minute == 0 and stream_event_count:
                throughput_per_minute = stream_event_count / 1440.0

            cur.execute("DELETE FROM measurement_stream_day WHERE profile_id=%s AND dt=%s AND run_id=%s", (args.profile_id, dt, args.run_id or ""))
            cur.execute("""
                INSERT INTO measurement_stream_day (
                  profile_id, dt, run_id, scenario_name,
                  stream_event_count, duplicate_count, duplicate_rate,
                  ordering_error_count, ordering_error_rate,
                  latency_p50_ms, latency_p95_ms, latency_max_ms,
                  completeness_rate, throughput_per_minute
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                args.profile_id, dt, args.run_id or "", args.scenario_name or "",
                stream_event_count, duplicate_count, duplicate_rate,
                ordering_error_count, ordering_error_rate,
                latency_p50_ms, latency_p95_ms, latency_max_ms,
                completeness_rate, throughput_per_minute
            ))
        conn.commit()
    finally:
        conn.close()
    print(f"[MEASUREMENT_STREAM] profile_id={args.profile_id} dt={dt} run_id={args.run_id} stream_event_count={stream_event_count} completeness_rate={completeness_rate:.6f}")

if __name__ == "__main__":
    main()
