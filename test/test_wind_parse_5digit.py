#!/usr/bin/env python3
"""5자리 바람 2+3 파싱 검증: 풍향 2자리×10 + 풍속 3자리 (26101→260°/101kt, 33001→330°/1kt)."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.flight_plan_analyzer import _parse_wind_temp_grid

# 최소 Wind/Temp 블록: 5자리(2+3) + 6자리(3+3) 혼합
block = """
START OF WIND AND TEMPERATURE SUMMARY ICN TO YVR
FL ISA WIND CMP TMP WIND CMP TMP WIND CMP TMP WIND CMP TMP
350 -54 26101+074-52 33001+050-55 26092+068-52 330001+050-55
PILIT ESNEG OTHER SIX
"""

grid = _parse_wind_temp_grid(block)

# 5자리: 풍향2×10 + 풍속3 → 26101=260°/101kt, 33001=330°/1kt, 26092=260°/92kt
# 6자리: 풍향3 + 풍속3 → 330001=330°/1kt
cases = [
    ("26101", "PILIT", 350, 260, 101),
    ("33001", "ESNEG", 350, 330, 1),
    ("26092", "OTHER", 350, 260, 92),
    ("330001", "SIX", 350, 330, 1),
]

print("바람 파싱 검증 (5자리 2+3 / 6자리 3+3)\n")
all_ok = True
for _label, wp, fl, exp_dir, exp_spd in cases:
    cell = grid.get((wp, fl))
    if not cell:
        print(f"  {wp} FL{fl}: 셀 없음 (실패)")
        all_ok = False
        continue
    d, s = int(cell["dir"]), int(cell["spd"])
    ok = (d == exp_dir and s == exp_spd)
    if not ok:
        all_ok = False
    status = "OK" if ok else "FAIL"
    print(f"  {wp} FL{fl}: dir={d}°, spd={s}kt  (기대: {exp_dir}°, {exp_spd}kt) [{status}]")

print()
if all_ok:
    print("모든 케이스 통과: 26101→260°/101kt, 33001→330°/1kt, 26092→260°/92kt")
else:
    print("일부 케이스 실패")
    sys.exit(1)
