#!/usr/bin/env python3
# Compatibility wrapper. The safe builder is now the schema-aware rich builder.
from pipelines.commerce.ml.feature_store.build_v05_ml_feature_snapshot import main

if __name__ == "__main__":
    raise SystemExit(main())
