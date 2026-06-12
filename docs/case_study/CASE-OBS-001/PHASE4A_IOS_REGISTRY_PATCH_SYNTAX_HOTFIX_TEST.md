# CASE-OBS-001 Phase4-A iOS registry patch syntax hotfix

## Purpose

Fix `deploy/apply_phase4a_ios_collection_missing_registry_patch.py` syntax error:

```text
SyntaxError: unterminated string literal
```

The failed line must be:

```python
path.write_text(text.rstrip() + "\n" + SCENARIOS, encoding="utf-8")
```

## Apply

```bash
cd /Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform
unzip -o /mnt/data/case_obs_phase4a_ios_registry_patch_syntax_hotfix.zip
chmod +x deploy/apply_phase4a_ios_collection_missing_registry_patch.py
python -m py_compile deploy/apply_phase4a_ios_collection_missing_registry_patch.py
PROJECT_ROOT=/Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform \
  python deploy/apply_phase4a_ios_collection_missing_registry_patch.py
```

## Expected

```text
[OK] appended Phase4-A iOS collection missing scenarios ...
```

or, if already applied:

```text
[OK] Phase4-A iOS scenarios already present ...
```

## Next smoke

```bash
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh \
  2026-06-01 source_ios_app_version_collection_missing 0
```
