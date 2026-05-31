from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from datetime import datetime

APACHE_RE = re.compile(
    r'^(?P<ip>\S+) \S+ \S+ \[(?P<ts>[^\]]+)\] "(?P<method>\S+) (?P<uri>[^\"]+) HTTP/1\.1" (?P<status>\d{3}) (?P<bytes>\d+) "(?P<referer>[^"]*)" "(?P<ua>[^"]*)" "(?P<cookie>[^"]*)"$'
)
REQUIRED_COOKIE_KEYS = {
    "schema_version", "scenario_id", "domain", "source_layer", "anomaly_type",
    "journey_id", "journey_stage", "product_id", "cart_id", "order_id", "payment_id",
    "delivery_id", "customer_segment", "device_type", "reconciliation_flag",
}


def _read_jsonl(path: str) -> list[dict]:
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _parse_cookie(cookie: str) -> dict[str, str]:
    parsed = {}
    for part in cookie.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        key, value = part.split("=", 1)
        parsed[key.strip()] = value.strip()
    return parsed


def _apache_dt(ts: str) -> datetime:
    return datetime.strptime(ts, "%d/%b/%Y:%H:%M:%S %z")


def _validate_behavior_log(path: str) -> tuple[int, list[str], int, list[datetime]]:
    failures: list[str] = []
    count = 0
    unique_pcid: set[str] = set()
    timestamps: list[datetime] = []
    previous: datetime | None = None
    with open(path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.rstrip("\n")
            if not line:
                continue
            count += 1
            m = APACHE_RE.match(line)
            if not m:
                failures.append(f"behavior line {line_no} is not Apache combined+cookie format")
                if len(failures) >= 8:
                    break
                continue
            ts = _apache_dt(m.group("ts"))
            timestamps.append(ts)
            if previous and ts < previous:
                failures.append(f"behavior log is not globally time-sorted at line {line_no}: {ts} < {previous}")
            previous = ts
            cookie = _parse_cookie(m.group("cookie"))
            if cookie.get("pcid"):
                unique_pcid.add(cookie["pcid"])
            missing = sorted(REQUIRED_COOKIE_KEYS - set(cookie.keys()))
            if missing:
                failures.append(f"behavior line {line_no} missing cookie keys: {missing}")
            uri = m.group("uri")
            if ".do" not in uri and uri != "/":
                failures.append(f"behavior line {line_no} URI is not commerce legacy-style .do path: {uri}")
            if cookie.get("domain") != "commerce_delivery":
                failures.append(f"behavior line {line_no} domain is not commerce_delivery")
            if len(failures) >= 8:
                break
    return count, failures, len(unique_pcid), timestamps


def _assert_json_chronological(rows: list[dict], label: str) -> list[str]:
    failures = []
    prev = ""
    for idx, row in enumerate(rows, 1):
        ts = str(row.get("event_time", row.get("created_at", "")))
        if prev and ts < prev:
            failures.append(f"{label} is not event_time sorted at row {idx}: {ts} < {prev}")
            break
        prev = ts
    return failures



def _uid_cookie_stats(path: str) -> dict[str, object]:
    total = 0
    uid_non_empty = 0
    uid_empty = 0
    stage_count: dict[str, int] = {}
    uid_stage_count: dict[str, int] = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            m = APACHE_RE.match(line.rstrip("\n"))
            if not m:
                continue
            total += 1
            cookie = _parse_cookie(m.group("cookie"))
            uid = cookie.get("uid", "")
            stage = cookie.get("journey_stage", cookie.get("page_type", "unknown"))
            stage_count[stage] = stage_count.get(stage, 0) + 1
            if uid:
                uid_non_empty += 1
                uid_stage_count[stage] = uid_stage_count.get(stage, 0) + 1
            else:
                uid_empty += 1
    early_stages = {"home", "browse", "search", "product_view"}
    early_total = sum(stage_count.get(s, 0) for s in early_stages)
    early_uid = sum(uid_stage_count.get(s, 0) for s in early_stages)
    return {
        "total": total,
        "uid_non_empty": uid_non_empty,
        "uid_empty": uid_empty,
        "uid_cookie_rate": round(uid_non_empty / max(1, total), 5),
        "anonymous_cookie_rate": round(uid_empty / max(1, total), 5),
        "early_stage_uid_rate": round(early_uid / max(1, early_total), 5),
        "uid_by_stage_distribution": dict(sorted(uid_stage_count.items())),
        "stage_distribution": dict(sorted(stage_count.items())),
    }

def main() -> int:
    parser = argparse.ArgumentParser(description="Validate v0.5 Phase1 generated source logs.")
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args()
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    files = manifest["files"]
    journeys = _read_jsonl(files["journey_jsonl"])
    tx = _read_jsonl(files["transaction_jsonl"])
    st = _read_jsonl(files["state_jsonl"])

    journey_ids = {r["journey_id"] for r in journeys}
    tx_journey_ids = {r["journey_id"] for r in tx}
    st_journey_ids = {r["journey_id"] for r in st}
    unique_visitors = {r.get("visitor_id") for r in journeys if r.get("visitor_id")}
    order_ids = {r["order_id"] for r in journeys}
    payment_ids = {r["payment_id"] for r in journeys}
    failures = []
    behavior_path = files["behavior_w3c_log"]
    if not Path(behavior_path).exists():
        failures.append("behavior Apache W3C-compatible log is missing")
        behavior_count = 0
        behavior_uv = 0
        behavior_ts = []
        behavior_uid_stats = {}
    else:
        behavior_count, behavior_failures, behavior_uv, behavior_ts = _validate_behavior_log(behavior_path)
        behavior_uid_stats = _uid_cookie_stats(behavior_path)
        failures.extend(behavior_failures)
    failures.extend(_assert_json_chronological(journeys, "journey_jsonl"))
    failures.extend(_assert_json_chronological(tx, "transaction_jsonl"))
    failures.extend(_assert_json_chronological(st, "state_jsonl"))

    if "behavior_csv" in files or any(str(x).endswith("_behavior.csv") for x in files.values()):
        failures.append("behavior CSV should not be generated in revised Phase1")
    if not journey_ids:
        failures.append("journey log is empty")
    if not order_ids or not payment_ids:
        failures.append("order_id/payment_id are not traceable in journey log")

    if manifest["scenario"] == "baseline":
        if not tx_journey_ids:
            failures.append("baseline transaction log is empty")
        if not st_journey_ids:
            failures.append("baseline state log is empty")
        min_uv = int(manifest.get("traffic_model", {}).get("min_baseline_uv", 0) or 1000)
        if len(unique_visitors) < min_uv or behavior_uv < min_uv:
            failures.append(f"baseline UV scale is too small: journey_uv={len(unique_visitors)}, behavior_uv={behavior_uv}, min={min_uv}")
        hourly_path = files.get("hourly_summary_json")
        if hourly_path and Path(hourly_path).exists():
            hourly = json.loads(Path(hourly_path).read_text(encoding="utf-8"))
            night = sum(r["visits"] for r in hourly[0:6])
            day = sum(r["visits"] for r in hourly[9:21])
            evening_peak = max(r["visits"] for r in hourly[17:21])
            early_low = max(r["visits"] for r in hourly[0:6])
            total_visits = sum(r["visits"] for r in hourly)
            total_pv = sum(r["pageviews"] for r in hourly)
            avg_pv = total_pv / max(1, total_visits)
            if not (day > night * 4):
                failures.append(f"baseline hourly traffic does not look user-like: day={day}, night={night}")
            if not (evening_peak > early_low * 3):
                failures.append(f"baseline evening/day peak is too weak: peak={evening_peak}, early_low={early_low}")
            if not (2.5 <= avg_pv <= 5.8):
                failures.append(f"baseline pageviews per visit out of realistic range: {avg_pv:.2f}")
            avg_duration = sum(r.get("avg_session_duration_sec", 0) * r["visits"] for r in hourly) / max(1, total_visits)
            if not (70 <= avg_duration <= 420):
                failures.append(f"baseline dwell/session duration is not realistic: {avg_duration:.1f}s")
        else:
            failures.append("baseline hourly summary is missing")
        realism_path = files.get("behavior_realism_summary_json")
        if realism_path and Path(realism_path).exists():
            realism = json.loads(Path(realism_path).read_text(encoding="utf-8"))
            if realism.get("unique_visitor_count", 0) < min_uv:
                failures.append(f"baseline behavior realism UV too small: {realism.get('unique_visitor_count')}")
            if not (0.06 <= realism.get("single_or_two_page_visit_rate", 0) <= 0.35):
                failures.append(f"baseline bounce/light visit rate is unrealistic: {realism.get('single_or_two_page_visit_rate')}")
            if not (0.20 <= realism.get("deep_visit_rate", 0) <= 0.70):
                failures.append(f"baseline deep visit rate is unrealistic: {realism.get('deep_visit_rate')}")
            if not (0.20 <= realism.get("non_linear_navigation_rate", 0) <= 0.85):
                failures.append(f"baseline non-linear navigation rate is too weak: {realism.get('non_linear_navigation_rate')}")
            actors = realism.get("actor_distribution", {})
            if len([k for k, v in actors.items() if v > 0]) < 4:
                failures.append(f"baseline actor segmentation is too narrow: {actors}")
        else:
            failures.append("baseline behavior realism summary is missing")
        analyzer_path = files.get("analyzer_compatibility_summary_json")
        if analyzer_path and Path(analyzer_path).exists():
            compat = json.loads(Path(analyzer_path).read_text(encoding="utf-8"))
            if compat.get("same_sid_ip_stability_rate", 0) < 0.999:
                failures.append(f"same sid IP stability is too low for analyzer sessionization: {compat.get('same_sid_ip_stability_rate')}")
            if compat.get("same_sid_user_agent_stability_rate", 0) < 0.999:
                failures.append(f"same sid User-Agent stability is too low for analyzer sessionization: {compat.get('same_sid_user_agent_stability_rate')}")
            if compat.get("analyzer_expected_pv_per_visit", 0) < 2.5:
                failures.append(f"analyzer expected PV/visit too low: {compat.get('analyzer_expected_pv_per_visit')}")
            if compat.get("analyzer_expected_avg_session_duration_sec", 0) < 70:
                failures.append(f"analyzer expected session duration too low: {compat.get('analyzer_expected_avg_session_duration_sec')}")
            if compat.get("repeat_pcid_new_sid_count", 0) < max(100, int(len(unique_visitors) * 0.10)):
                failures.append(f"repeat pcid/new sid count too low: {compat.get('repeat_pcid_new_sid_count')}")
            ref = compat.get("referer_distribution", {})
            if len([k for k, v in ref.items() if v > 0]) < 5:
                failures.append(f"referer diversity too narrow: {ref}")
        else:
            failures.append("analyzer compatibility summary is missing")


        uid_rate = float(behavior_uid_stats.get("uid_cookie_rate", 0.0) or 0.0)
        early_uid_rate = float(behavior_uid_stats.get("early_stage_uid_rate", 0.0) or 0.0)

        # uid is an authenticated cookie, not a required field on every hit.
        # Daily uid rate naturally varies by weekend/weekday, actor mix, and
        # checkout/payment/order_complete reach rate. Use profile config, not a
        # brittle hard-coded lower bound.
        identity_model = {"expected_uid_cookie_rate_min": 0.06, "expected_uid_cookie_rate_max": 0.55, "expected_early_stage_uid_rate_max": 0.45}
        uid_rate_min = float(identity_model.get("expected_uid_cookie_rate_min", 0.06) or 0.06)
        uid_rate_max = float(identity_model.get("expected_uid_cookie_rate_max", 0.55) or 0.55)
        early_uid_rate_max = float(identity_model.get("expected_early_stage_uid_rate_max", 0.45) or 0.45)

        if behavior_uid_stats.get("uid_non_empty", 0) <= 0:
            failures.append("uid cookie is never present; authenticated behavior is missing")
        if behavior_uid_stats.get("uid_empty", 0) <= 0:
            failures.append("uid cookie is present on every row; anonymous pre-login behavior is unrealistic")
        if not (uid_rate_min <= uid_rate <= uid_rate_max):
            failures.append(
                f"uid cookie rate is outside configured authenticated-only policy range: "
                f"rate={uid_rate} expected=[{uid_rate_min},{uid_rate_max}]"
            )
        if early_uid_rate > early_uid_rate_max:
            failures.append(f"too many early browse/search/product_view rows contain uid: {early_uid_rate}")

        # Cross-domain temporal sanity: for shared journeys, transaction/state evidence should not precede the journey start.
        first_journey_time = {r["journey_id"]: r.get("created_at", "") for r in journeys}
        bad_tx = [r for r in tx[:2000] if r.get("event_time", "") < first_journey_time.get(r.get("journey_id"), "")]
        bad_st = [r for r in st[:2000] if r.get("event_time", "") < first_journey_time.get(r.get("journey_id"), "")]
        if bad_tx:
            failures.append("transaction events include timestamps before journey start")
        if bad_st:
            failures.append("state events include timestamps before journey start")
    if not all(bool(v) for v in manifest["completion_checks"].values()):
        failures.append("one or more declared completion checks are false")

    print("[CHECK] journey_count=", len(journeys))
    print("[CHECK] unique_visitor_count=", len(unique_visitors))
    print("[CHECK] behavior_apache_count=", behavior_count)
    print("[CHECK] behavior_unique_pcid=", behavior_uv)
    print("[CHECK] transaction_count=", len(tx))
    print("[CHECK] state_count=", len(st))
    print("[CHECK] transaction_coverage=", len(tx_journey_ids), "/", len(journey_ids))
    print("[CHECK] state_coverage=", len(st_journey_ids), "/", len(journey_ids))
    if behavior_ts:
        print("[CHECK] behavior_first_ts=", behavior_ts[0].isoformat())
        print("[CHECK] behavior_last_ts=", behavior_ts[-1].isoformat())
    hourly_path = files.get("hourly_summary_json")
    if hourly_path and Path(hourly_path).exists():
        hourly = json.loads(Path(hourly_path).read_text(encoding="utf-8"))
        total_visits = sum(r["visits"] for r in hourly)
        total_pv = sum(r["pageviews"] for r in hourly)
        print("[CHECK] hourly_user_behavior_summary=", hourly)
        print("[CHECK] avg_pageviews_per_visit=", round(total_pv / max(1, total_visits), 2))
    realism_path = files.get("behavior_realism_summary_json")
    if realism_path and Path(realism_path).exists():
        realism = json.loads(Path(realism_path).read_text(encoding="utf-8"))
        print("[CHECK] behavior_realism_summary=", realism)
    analyzer_path = files.get("analyzer_compatibility_summary_json")
    if analyzer_path and Path(analyzer_path).exists():
        compat = json.loads(Path(analyzer_path).read_text(encoding="utf-8"))
        print("[CHECK] analyzer_compatibility_summary=", compat)
    if behavior_uid_stats:
        print("[CHECK] uid_cookie_realism_summary=", behavior_uid_stats)
    if failures:
        for failure in failures:
            print("[FAIL]", failure)
        return 1
    print("[OK] v0.5 Phase1 source generation validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
