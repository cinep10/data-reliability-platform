from __future__ import annotations

import argparse
import csv
import statistics
from collections import defaultdict


def main() -> None:
    ap = argparse.ArgumentParser(description="Recommend a few YAML knobs from hourly DS metric CSV")
    ap.add_argument("csv_path", help="CSV with dt,hh,visit,uv,pageview columns")
    args = ap.parse_args()

    rows = []
    with open(args.csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            try:
                rows.append({
                    "hh": int(r["hh"]),
                    "visit": float(r["visit"]),
                    "uv": float(r["uv"]),
                    "pageview": float(r["pageview"]),
                })
            except Exception:
                continue

    if not rows:
        raise SystemExit("No valid rows")

    by_hh = defaultdict(list)
    pv_per_visit = []
    revisit = []
    for r in rows:
        by_hh[r["hh"]].append(r)
        if r["visit"] > 0:
            pv_per_visit.append(r["pageview"] / r["visit"])
        if r["visit"] > 0:
            revisit.append(max(0.0, min(0.99, 1.0 - (r["uv"] / r["visit"]))))

    hh_multiplier = []
    session_rate = []
    new_ratio = []
    max_visit = max((sum(x["visit"] for x in v) / len(v)) for v in by_hh.values())
    for hh in range(24):
        rs = by_hh.get(hh, [])
        avg_visit = sum(x["visit"] for x in rs) / len(rs) if rs else 0.0
        avg_pvv = sum((x["pageview"] / x["visit"]) for x in rs if x["visit"] > 0) / max(1, sum(1 for x in rs if x["visit"] > 0)) if rs else 0.0
        avg_revisit = sum(max(0.0, min(0.99, 1.0 - (x["uv"] / x["visit"]))) for x in rs if x["visit"] > 0) / max(1, sum(1 for x in rs if x["visit"] > 0)) if rs else 0.0
        hh_multiplier.append(round(avg_visit / max_visit, 3) if max_visit > 0 else 0.0)
        session_rate.append(round(min(0.08, max(0.004, 0.004 + avg_pvv * 0.0025)), 3))
        new_ratio.append(round(max(0.02, min(0.95, 1.0 - avg_revisit)), 3))

    print("target_pv_per_visit_mean:", round(statistics.mean(pv_per_visit), 2))
    print("target_pv_per_visit_std:", round(statistics.pstdev(pv_per_visit), 2) if len(pv_per_visit) > 1 else 1.0)
    print("revisit_ratio_daily:", round(statistics.mean(revisit), 2))
    print("traffic_curve.hh_multiplier:", hh_multiplier)
    print("session_event_rate_by_hh:", session_rate)
    print("new_visit_ratio_by_hh:", new_ratio)


if __name__ == "__main__":
    main()
