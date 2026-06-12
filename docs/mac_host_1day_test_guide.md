# Mac mini Host 1-day v0.5 test guide

## Target paths

- Project: `/Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform`
- Source logs: `/Volumes/EXTERNAL_USB/dev/log/logdata/source`
- Runtime logs: `/Volumes/EXTERNAL_USB/dev/log/runtime`
- DB: `127.0.0.1:3306/weblog`
- Kafka: `127.0.0.1:9092`

## Copy files into project

```bash
cd /Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform

mkdir -p deploy/env
cp ~/Downloads/run_v05_reliability_pipeline_commerce_mac_host.sh deploy/
cp ~/Downloads/reset_v05_commerce_pipeline_mac_host.sh deploy/reset_v05_commerce_pipeline.sh
cp ~/Downloads/truncate_v05_runtime_tables_mac_host.sh deploy/
cp ~/Downloads/mac_host_prod.env deploy/env/

chmod +x deploy/run_v05_reliability_pipeline_commerce_mac_host.sh
chmod +x deploy/reset_v05_commerce_pipeline.sh
chmod +x deploy/truncate_v05_runtime_tables_mac_host.sh
```

## Prepare runtime directories

```bash
mkdir -p /Volumes/EXTERNAL_USB/dev/log/logdata/source
mkdir -p /Volumes/EXTERNAL_USB/dev/log/runtime
mkdir -p /Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform/artifacts/logs
```

## Run 1-day baseline

```bash
cd /Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform
source deploy/env/mac_host_prod.env
source .venv/bin/activate

/opt/homebrew/bin/bash \
  deploy/run_v05_reliability_pipeline_commerce_mac_host.sh \
  2026-05-21 baseline 0
```

## Quick DB check

```bash
mysql -h 127.0.0.1 -P 3306 -u nethru -p weblog -e "
SELECT overall_risk_score, final_risk_level
FROM unified_reliability_score_day_v05
ORDER BY target_date DESC, run_id DESC
LIMIT 5;
"
```
