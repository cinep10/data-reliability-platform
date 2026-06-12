# CASE-OBS-001 Phase2-C1 운영 쉘 재패치

현재 첨부된 `run_v05_reliability_pipeline_commerce_mac_host.sh` 기준으로 누락된 4.12/4.13을 다시 삽입한 패치입니다.

## 적용

```bash
cd /Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform
unzip -o /mnt/data/case_obs_phase2c1_shell_repatch.zip
chmod +x deploy/run_v05_reliability_pipeline_commerce_mac_host.sh
```

## 확인

```bash
grep -n "4.12\|4.13\|RUN_V05_OBS\|073_v05\|074_v05" deploy/run_v05_reliability_pipeline_commerce_mac_host.sh
```

## 실행

```bash
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh 2026-06-01 baseline 0
```

## 기대 로그

```text
[STEP 4.12] CASE-OBS-001 Phase2-B gap measurement layer
[STEP 4.13] CASE-OBS-001 Phase2-C1 baseline foundation
[RUN_R] Rscript ... --include-target-date true
```
