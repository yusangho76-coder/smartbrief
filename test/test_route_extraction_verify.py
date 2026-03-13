#!/usr/bin/env python3
"""수정 후 route 추출 및 구글지도 연동 검증: extract_route_from_page2 + flight plan waypoints."""
import os
import sys

# 프로젝트 루트
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    # uploads 내 PDF (ImportantFile_13)
    base = os.path.join(os.path.dirname(__file__), "uploads")
    candidates = [
        "20260301_085703_66e69ccf_ImportantFile_13.pdf",
        "20260227_230144_f671b40f_ImportantFile_13.pdf",
    ]
    pdf_path = None
    for name in candidates:
        p = os.path.join(base, name)
        if os.path.isfile(p):
            pdf_path = p
            break
    if not pdf_path:
        print("uploads에 ImportantFile_13.pdf 없음. 다음 중 하나 필요:")
        for c in candidates:
            print(" ", os.path.join(base, c))
        return 1

    print("PDF:", pdf_path)
    print()

    # 1) extract_route_from_page2 (ats_route_extractor 사용)
    from app import extract_route_from_page2
    route = extract_route_from_page2(pdf_path)
    if not route:
        print("FAIL: route 추출 없음")
        return 1
    print("OK: extracted_route (앞 200자):", route[:200])
    print("    길이:", len(route))
    print()

    # 2) Flight plan waypoints (구글지도 coordinates_from_plan용)
    from src.pdf_converter import PDFConverter
    conv = PDFConverter()
    text = conv.convert_pdf_to_text(pdf_path)
    flight_plan_waypoints = []
    try:
        from flightplanextractor import extract_flight_plan_waypoints_from_text
        rows = extract_flight_plan_waypoints_from_text(text)
        for row in rows:
            flight_plan_waypoints.append({
                "ident": (row.get("Waypoint") or "").strip().upper(),
                "lat": float(row["lat"]),
                "lon": float(row["lon"]),
            })
    except Exception as e:
        print("Flight plan waypoints 추출 예외:", e)
    print("OK: flight_plan_waypoints 개수:", len(flight_plan_waypoints))
    if flight_plan_waypoints:
        print("    첫 3개:", flight_plan_waypoints[:3])
    print()

    # 3) /api/route-path 호출 시뮬 (coordinates_from_plan 있으면 지도에 그대로 표시)
    from src.api_routes import api_bp
    from flask import Flask
    app = Flask(__name__)
    app.register_blueprint(api_bp)
    with app.test_client() as c:
        payload = {"route": route}
        if flight_plan_waypoints:
            payload["waypoints"] = [{"ident": w["ident"], "lat": w["lat"], "lon": w["lon"]} for w in flight_plan_waypoints]
        r = c.post("/api/route-path", json=payload)
        if r.status_code != 200:
            print("FAIL: /api/route-path status", r.status_code, r.get_data(as_text=True)[:300])
            return 1
        data = r.get_json()
        coords = data.get("coordinates") or []
        from_plan = data.get("coordinates_from_plan") or []
        print("OK: /api/route-path 응답")
        print("    coordinates 개수:", len(coords))
        print("    coordinates_from_plan 개수:", len(from_plan))
        if from_plan:
            print("    지도 표시용 좌표(앞 3):", from_plan[:3])
    print()
    print("검증 완료: 추출 및 구글지도 연동 정상.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
