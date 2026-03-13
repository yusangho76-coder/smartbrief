#!/usr/bin/env python3
"""build_wind_shear_inversion_table_for_route 수직/수평 shear 테스트.
split 텍스트만 있을 때 wind block에서 waypoint 순서를 추출해 mock legs 구성 후 호출.
"""
import re
import sys
from pathlib import Path

# 프로젝트 루트
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.flight_plan_analyzer import (
    _extract_wind_temp_block,
    _parse_wind_temp_grid,
    build_wind_shear_inversion_table_for_route,
)


def _wind_temp_waypoint_order(block: str):
    """Wind/Temp 블록에서 등장 순서대로 waypoint 리스트 반환."""
    order = []
    for raw in block.splitlines():
        line = raw.strip()
        if not line:
            continue
        u = line.upper()
        if u.startswith("START OF WIND") or u.startswith("FL ISA") or u.startswith("PAGE -"):
            continue
        if not re.search(r"\d", line):
            tokens = line.split()
            if tokens and all(re.match(r"^[A-Z0-9]+$", t) for t in tokens):
                for t in tokens:
                    if t not in order:
                        order.append(t)
    return order


def build_mock_legs_from_text(text: str):
    """OFP 텍스트에서 wind block을 파싱해 legs 리스트 생성 (Waypoint, FL (Flight Level))."""
    block = _extract_wind_temp_block(text)
    grid = _parse_wind_temp_grid(block)
    if not grid:
        return []
    order = _wind_temp_waypoint_order(block)
    wp_levels: dict = {}
    for (wp, fl) in grid.keys():
        wp_levels.setdefault(wp, []).append(fl)
    for wp in wp_levels:
        wp_levels[wp] = sorted(wp_levels[wp])

    legs = []
    for wp in order:
        levels = wp_levels.get(wp)
        if not levels:
            continue
        # 370 있으면 우선, 없으면 첫 FL
        fl = 370 if 370 in levels else levels[0]
        legs.append({"Waypoint": wp, "FL (Flight Level)": str(fl)})
    return legs


def main():
    path = ROOT / "temp" / "20260304_193339_7b6687a8_ImportantFile_14_split.txt"
    if not path.exists():
        print(f"파일 없음: {path}")
        return
    text = path.read_text(encoding="utf-8", errors="replace")
    legs = build_mock_legs_from_text(text)
    print(f"Mock legs 수: {len(legs)}")
    if legs:
        print("첫 5개:", [f"{l['Waypoint']}/FL{l['FL (Flight Level)']}" for l in legs[:5]])
        print("끝 5개:", [f"{l['Waypoint']}/FL{l['FL (Flight Level)']}" for l in legs[-5:]])

    rows = build_wind_shear_inversion_table_for_route(text, legs)
    print(f"\n[순항 고도 주변 Wind/Temperature 특이 구간] 행 수: {len(rows)}")
    for r in rows:
        print(f"  위치: {r['location']}")
        print(f"  결과: {r['issue']}")
        print()


if __name__ == "__main__":
    main()
