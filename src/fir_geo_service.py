from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict


@lru_cache(maxsize=1)
def load_fir_geojson() -> Dict[str, Any]:
    geojson_path = Path(__file__).resolve().parent.parent / "NavData" / "fir.geojson"
    with geojson_path.open(encoding="utf-8") as f:
        return json.load(f)

