#!/usr/bin/env python3
from pathlib import Path
import shutil
import os
root = Path(os.environ.get('PROJECT_ROOT', '.')).resolve()
src = Path(__file__).resolve().parents[1] / 'pipelines/commerce/validation/validate_v05_authority_evidence_layer.py'
dst = root / 'pipelines/commerce/validation/validate_v05_authority_evidence_layer.py'
if not src.exists():
    raise SystemExit(f'missing source {src}')
if not dst.exists():
    raise SystemExit(f'missing destination {dst}')
backup = dst.with_suffix(dst.suffix + '.bak_phase4c_baseline_signal')
if not backup.exists():
    shutil.copy2(dst, backup)
shutil.copy2(src, dst)
print(f'[OK] patched {dst}')
print(f'[INFO] backup={backup}')
