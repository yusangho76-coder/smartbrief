#!/usr/bin/env python3
"""PILIT FL350 추출 확인: 280/86 kts, -52°C 기대."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.flight_plan_analyzer import _extract_wind_temp_block, _parse_wind_temp_grid

path = ROOT / "temp" / "20260304_200240_7bcd3272_ImportantFile_14_split.txt"
text = path.read_text(encoding="utf-8", errors="replace")
block = _extract_wind_temp_block(text)
grid = _parse_wind_temp_grid(block)

print(f"파일: {path.name}\n")

# PILIT FL350, DRAPP FL370, OMOTO/OGDEN/OPHET/OLCOT FL380 (데이터 행→헤더 순서 블록)
for label, key, expected in [
    ("PILIT FL350", ("PILIT", 350), (280, 86, -52)),
    ("DRAPP FL370", ("DRAPP", 370), (310, 18, -50)),
    ("OMOTO FL380", ("OMOTO", 380), (300, 38, -61)),
    ("OGDEN FL380", ("OGDEN", 380), (310, 39, -62)),
    ("OPHET FL380", ("OPHET", 380), (310, 42, -61)),
    ("OLCOT FL380", ("OLCOT", 380), (320, 45, -60)),
]:
    cell = grid.get(key)
    print(f"grid[{key}] = {cell}")
    if cell:
        print(f"  → 풍향 {int(cell['dir'])}°, 풍속 {int(cell['spd'])} kts, CMP {int(cell['cmp'])}, 온도 {int(cell['temp'])}°C")
        actual = (int(cell["dir"]), int(cell["spd"]), int(cell["temp"]))
        if actual == expected:
            print(f"  → 기대값 {expected} (dir/spd/°C) 일치.")
        else:
            print(f"  → 기대값 {expected} / 실제 {actual}")
    else:
        print(f"  → 없음 (기대: {expected})")
    print()
