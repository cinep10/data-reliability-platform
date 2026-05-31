#!/usr/bin/env python3
import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _measurement_utils import connect, count_rows, agg_metric, safe_float, safe_int

def main():
    p = argparse.ArgumentParser(description="Build Phase3 measurement_operational_day from operational measurement assets.")
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
            processed_count = count_rows(cur, "stream_replay_event", args.profile_id, dt, args.run_id, ("target_date","dt"))
            if processed_count == 0:
                processed_count = count_rows(cur, "pipeline_performance_summary_minute", args.profile_id, dt, args.run_id, ("dt","target_date"))

            throughput_per_minute = safe_float(agg_metric(cur, "pipeline_performance_summary_day", ("throughput_per_minute","avg_throughput_per_minute","events_per_minute"), args.profile_id, dt, args.run_id, "MAX"))
            if throughput_per_minute == 0 and processed_count:
                throughput_per_minute = processed_count / 1440.0

            lag_p50_ms = safe_float(agg_metric(cur, "pipeline_performance_summary_day", ("lag_p50_ms","p50_lag_ms","freshness_p50_ms"), args.profile_id, dt, args.run_id, "MAX"))
            lag_p95_ms = safe_float(agg_metric(cur, "pipeline_performance_summary_day", ("lag_p95_ms","p95_lag_ms","freshness_p95_ms","latency_p95_ms"), args.profile_id, dt, args.run_id, "MAX"))
            lag_max_ms = safe_float(agg_metric(cur, "pipeline_performance_summary_day", ("lag_max_ms","max_lag_ms","freshness_max_ms","latency_max_ms"), args.profile_id, dt, args.run_id, "MAX"))

            availability_ratio = safe_float(agg_metric(cur, "pipeline_availability_day", ("availability_ratio","availability_rate","uptime_ratio"), args.profile_id, dt, args.run_id, "MAX"))
            if availability_ratio == 0 and processed_count:
                availability_ratio = 1.0

            no_data_gap_minutes = safe_float(agg_metric(cur, "pipeline_availability_day", ("no_data_gap_minutes","gap_minutes","no_data_minutes","zero_event_minutes"), args.profile_id, dt, args.run_id, "MAX"))
            timeout_count = safe_int(agg_metric(cur, "pipeline_availability_day", ("timeout_count","timeouts"), args.profile_id, dt, args.run_id, "SUM"))
            retry_count = safe_int(agg_metric(cur, "pipeline_availability_day", ("retry_count","retries"), args.profile_id, dt, args.run_id, "SUM"))

            cur.execute("DELETE FROM measurement_operational_day WHERE profile_id=%s AND dt=%s AND run_id=%s", (args.profile_id, dt, args.run_id or ""))
            cur.execute("""
                INSERT INTO measurement_operational_day (
                  profile_id, dt, run_id, scenario_name,
                  processed_count, throughput_per_minute,
                  lag_p50_ms, lag_p95_ms, lag_max_ms,
                  availability_ratio, no_data_gap_minutes,
                  timeout_count, retry_count
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                args.profile_id, dt, args.run_id or "", args.scenario_name or "",
                processed_count, throughput_per_minute,
                lag_p50_ms, lag_p95_ms, lag_max_ms,
                availability_ratio, no_data_gap_minutes,
                timeout_count, retry_count
            ))
        conn.commit()
    finally:
        conn.close()
    print(f"[MEASUREMENT_OPERATIONAL] profile_id={args.profile_id} dt={dt} run_id={args.run_id} processed_count={processed_count} availability_ratio={availability_ratio:.6f}")

if __name__ == "__main__":
    main()
