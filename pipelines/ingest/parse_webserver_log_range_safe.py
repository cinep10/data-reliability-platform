#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import re
from datetime import datetime, date
from pathlib import Path
from urllib.parse import urlparse

LOG_RE = re.compile(
    r'^(?P<ip>\S+)\s+\S+\s+\S+\s+\[(?P<ts>[^\]]+)\]\s+"(?P<method>[A-Z]+)\s+(?P<url_raw>\S+)\s+HTTP/[^"]+"\s+'
    r'(?P<status>\d{3})\s+(?P<bytes>\S+)\s+"(?P<ref>[^"]*)"\s+"(?P<ua>[^"]*)"(?:\s+"(?P<kv_raw>.*)")?$'
)
TS_FMT = "%d/%b/%Y:%H:%M:%S %z"

HEADER = [
    "dt","ts","ip","method","url_raw","url_full","url_norm","host","path","query",
    "status","bytes","latency_ms","ref","ref_host","ua","kv_raw","uid","pcid","sid",
    "device_type","evt","accept_lang","cc","page_type"
]

def extract_kv(kv_raw: str | None, key: str):
    if not kv_raw:
        return None
    for delim in ["&",";","|",","]:
        if delim in kv_raw:
            parts = [x.strip() for x in kv_raw.split(delim)]
            for part in parts:
                if part.startswith(f"{key}="):
                    v = part.split("=", 1)[1].strip()
                    return v or None
    marker = f"{key}="
    idx = kv_raw.find(marker)
    if idx >= 0:
        tail = kv_raw[idx+len(marker):]
        for stop in [" ", "\t", "\n", "&", ";", "|", ","]:
            if stop in tail:
                tail = tail.split(stop, 1)[0]
        return tail.strip() or None
    return None

def infer_device_type(ua: str):
    x = (ua or "").lower()
    if "iphone" in x or "android" in x or "mobile" in x:
        return "mobile"
    if "ipad" in x or "tablet" in x:
        return "tablet"
    return "desktop"

def infer_evt(path: str):
    p = (path or "").lower()
    if "/submit" in p:
        return "submit"
    if "/success" in p or "/complete" in p:
        return "success"
    return "view"

def infer_page_type(path: str):
    p = (path or "").lower()
    if "/apply" in p:
        return "apply"
    if "/submit" in p:
        return "submit"
    if "/success" in p or "/complete" in p:
        return "success"
    if "/detail" in p or "/view" in p:
        return "detail"
    if "/list" in p:
        return "list"
    return "page" if p else None

def normalize_url(base_url: str, url_raw: str):
    if url_raw.startswith("http://") or url_raw.startswith("https://"):
        full = url_raw
    else:
        full = f"{base_url.rstrip('/')}/{url_raw.lstrip('/')}"
    parsed = urlparse(full)
    url_norm = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    return full, url_norm, parsed.netloc, parsed.path, parsed.query

def main():
    ap = argparse.ArgumentParser(description="Range-safe parser for append-only web logs")
    ap.add_argument("src_log")
    ap.add_argument("dst_tsv")
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--dt-from", required=True)
    ap.add_argument("--dt-to", required=True)
    ap.add_argument("--dedup", action="store_true")
    args = ap.parse_args()

    dt_from = date.fromisoformat(args.dt_from)
    dt_to = date.fromisoformat(args.dt_to)

    src = Path(args.src_log)
    dst = Path(args.dst_tsv)
    dst.parent.mkdir(parents=True, exist_ok=True)

    seen = set()
    total = matched = ts_parsed = written = skipped_dup = 0

    with src.open("r", encoding="utf-8", errors="replace") as f_in, dst.open("w", encoding="utf-8", newline="") as f_out:
        writer = csv.writer(f_out, delimiter="\t")
        writer.writerow(HEADER)

        for line in f_in:
            total += 1
            line = line.rstrip("\n")
            m = LOG_RE.match(line)
            if not m:
                continue
            matched += 1

            ts = datetime.strptime(m.group("ts"), TS_FMT)
            ts_naive = ts.astimezone().replace(tzinfo=None)
            dt_val = ts_naive.date()

            if dt_val < dt_from or dt_val > dt_to:
                continue
            ts_parsed += 1

            ip = m.group("ip")
            method = m.group("method")
            url_raw = m.group("url_raw")
            status = int(m.group("status"))
            bytes_raw = m.group("bytes")
            bytes_val = 0 if bytes_raw == "-" else int(bytes_raw)
            ref = m.group("ref") or ""
            ua = m.group("ua") or ""
            kv_raw = m.group("kv_raw") or ""

            url_full, url_norm, host, path, query = normalize_url(args.base_url, url_raw)
            ref_host = urlparse(ref).netloc if ref else ""
            uid = extract_kv(kv_raw, "uid") or extract_kv(kv_raw, "nth_uid")
            pcid = extract_kv(kv_raw, "pcid") or extract_kv(kv_raw, "nth_pcid")
            sid = extract_kv(kv_raw, "sid") or extract_kv(kv_raw, "nth_sid")
            latency_ms = extract_kv(kv_raw, "latency_ms")
            device_type = infer_device_type(ua)
            evt = extract_kv(kv_raw, "evt") or infer_evt(path)
            accept_lang = extract_kv(kv_raw, "accept_lang")
            cc = extract_kv(kv_raw, "cc")
            page_type = extract_kv(kv_raw, "page_type") or infer_page_type(path)

            sig = (dt_val.isoformat(), ts_naive.isoformat(sep=" "), ip, method, url_raw, status, uid or "", pcid or "", sid or "")
            if args.dedup:
                if sig in seen:
                    skipped_dup += 1
                    continue
                seen.add(sig)

            writer.writerow([
                dt_val.isoformat(),
                ts_naive.strftime("%Y-%m-%d %H:%M:%S"),
                ip, method, url_raw, url_full, url_norm, host, path, query,
                status, bytes_val, latency_ms, ref, ref_host, ua, kv_raw, uid, pcid, sid,
                device_type, evt, accept_lang, cc, page_type
            ])
            written += 1

    print(f"[parse_webserver_log_range_safe] total={total} matched={matched} ts_parsed={ts_parsed} written={written} skipped_dup={skipped_dup} out={dst}")

if __name__ == "__main__":
    main()
