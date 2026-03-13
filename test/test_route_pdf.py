#!/usr/bin/env python3
"""
ImportantFile 10.pdf 기준 항로 추출 → analyze_route → 좌표 검증
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import extract_route_from_page2
from src.route_fir_mapper import route_fir_mapper
from src.api_routes import api_route_path

def main():
    pdf_paths = [
        "uploads/ImportantFile 10.pdf",
        "uploads/ImportantFile_10.pdf",
        "ImportantFile 10.pdf",
    ]
    pdf_path = None
    for p in pdf_paths:
        if os.path.isfile(p):
            pdf_path = p
            break
    if not pdf_path:
        print("PDF not found. Simulating with CFP route from conversation.")
        # CFP에서 보인 항로 (RKSI.. ... POOFF..SPY G469 PDN ...)
        route_text = "RKSI EGOBA Y697 LANAT Y51 SAMON Y142 GTC Y512 OATIS R580 OPAKE POOFF SPY G469 PDN N56W150 N53W140 NUDGE TOU MARNR8 KSEA"
    else:
        print(f"Using PDF: {pdf_path}")
        route_text = extract_route_from_page2(pdf_path)
        if not route_text:
            print("extract_route_from_page2 returned empty. Using fallback route.")
            route_text = "RKSI EGOBA Y697 OATIS R580 OPAKE POOFF SPY G469 PDN N56W150 NUDGE TOU KSEA"
        else:
            print(f"Extracted route length: {len(route_text)}")
            print(f"Route (last 120 chars): ...{route_text[-120:]}")
            # 태평양 구간만 확인
            if "POOFF" in route_text and "PDN" in route_text:
                idx = route_text.find("POOFF")
                snippet = route_text[idx:idx+80]
                print(f"Snippet around POOFF: {snippet}")

    print("\n--- analyze_route ---")
    result = route_fir_mapper.analyze_route(route_text)
    points = result.get("points", [])
    idents = [p.get("ident") for p in points]
    print("Idents count:", len(idents))
    # POOFF 주변
    pacific = []
    for i, p in enumerate(points):
        ident = p.get("ident")
        if ident in ("OPAKE", "POOFF", "SPY", "PDN", "NYMPH", "ONEIL", "RULOY", "PINTT", "CREMR"):
            pacific.append((i, ident, p.get("lat"), p.get("lon")))
    print("Pacific segment idents:", [x[1] for x in pacific])
    for i, ident, lat, lon in pacific:
        print(f"  {i} {ident} lat={lat} lon={lon}")

    # API 응답 시뮬레이션 (coordinates만)
    coordinates = []
    for point in result.get("points", []):
        lat, lon = point.get("lat"), point.get("lon")
        if lat is None or lon is None:
            continue
        coordinates.append({"lat": float(lat), "lng": float(lon), "ident": point.get("ident")})

    print("\n--- Coordinates (POOFF/SPY/PDN) ---")
    for c in coordinates:
        if c.get("ident") in ("OPAKE", "POOFF", "SPY", "PDN"):
            print(" ", c)

    # 날짜변경선 분할 시뮬레이션 (프론트와 동일 로직)
    def split_path(coords):
        segments = []
        current = []
        for i, c in enumerate(coords):
            if current:
                prev = current[-1]
                if abs(c["lng"] - prev["lng"]) > 180:
                    segments.append(current)
                    current = []
            current.append({"lat": c["lat"], "lng": c["lng"]})
        if current:
            segments.append(current)
        return segments

    segments = split_path([{"lat": c["lat"], "lng": c["lng"]} for c in coordinates])
    print("\n--- Antimeridian segments (count) ---")
    print("Segments:", len(segments))
    for i, seg in enumerate(segments):
        print(f"  Segment {i}: {len(seg)} points, lng range: {min(p['lng'] for p in seg):.1f} ~ {max(p['lng'] for p in seg):.1f}")

    has_spy = any(p.get("ident") == "SPY" for p in points)
    print("\n--- Conclusion ---")
    print("SPY in points:", has_spy)
    print("Warnings:", result.get("warnings"))

if __name__ == "__main__":
    main()
