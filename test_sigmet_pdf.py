#!/usr/bin/env python3
"""
uploads/20260314_163925_010f4b32_ImportantFile_19.pdf 기준 SIGMET 분석 테스트.
- 최신 SIGMET 다운로드(aviationweather.gov API)
- 경로·고도·시간 매칭 및 유효 시간대 표시 확인
"""
import os
import re
import sys
from datetime import datetime, timezone

# 프로젝트 루트
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

PDF_PATH = os.path.join(ROOT, "uploads", "20260314_163925_010f4b32_ImportantFile_19.pdf")

def main():
    if not os.path.isfile(PDF_PATH):
        print(f"❌ PDF 없음: {PDF_PATH}")
        return 1

    print("=" * 60)
    print("SIGMET 분석 테스트 (PDF 기준)")
    print("=" * 60)
    print(f"PDF: {PDF_PATH}\n")

    # 1) flight_data 추출
    from flightplanextractor import extract_flight_data_from_pdf
    flight_data = extract_flight_data_from_pdf(PDF_PATH, save_temp=False)
    if not flight_data:
        print("❌ flight_data 추출 실패")
        return 1
    print(f"✅ Waypoint 수: {len(flight_data)}개")
    # 샘플 3개만 출력
    for i, row in enumerate(flight_data[:3]):
        print(f"   {row.get('Waypoint','')} lat={row.get('lat')} lon={row.get('lon')} "
              f"FL={row.get('FL (Flight Level)')} Time={row.get('Estimated Time (Z)')}")
    if len(flight_data) > 3:
        print("   ...")
    print()

    # 2) OFP 날짜 파싱 (app.py와 동일)
    ofp_date = None
    try:
        import pdfplumber
        with pdfplumber.open(PDF_PATH) as pdf:
            text = ""
            for p in pdf.pages[:5]:
                t = p.extract_text()
                if t:
                    text += t + "\n"
        month_map = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,
                     'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
        m = re.search(r'(\d{2})/([A-Z]{3})/(\d{2,4})', text[:5000])
        if m:
            day = int(m.group(1))
            mon = month_map.get(m.group(2), 1)
            yr = int(m.group(3)) if len(m.group(3)) == 4 else 2000 + int(m.group(3))
            ofp_date = datetime(yr, mon, day, 0, 0, 0, tzinfo=timezone.utc)
            print(f"✅ OFP 날짜: {ofp_date.date()}")
        else:
            print("⚠️ OFP 날짜 미발견 → 오늘 날짜 사용")
    except Exception as e:
        print(f"⚠️ OFP 날짜 파싱 실패: {e}")

    # 3) SIGMET 경로 매칭 (최신 API 호출)
    from src.sigwx_analyzer import fetch_and_match_sigmet_for_route
    print("\n--- aviationweather.gov 최신 SIGMET 조회 및 경로 매칭 ---\n")
    sigmet_route_table = fetch_and_match_sigmet_for_route(flight_data, ofp_date=ofp_date)

    # 4) 결과 출력 (유효 시간대 포함)
    if not sigmet_route_table:
        print("결과: 0건")
        return 0

    warning = [r for r in sigmet_route_table if r.get("_warning_row")]
    info = [r for r in sigmet_route_table if r.get("_info_row")]
    normal = [r for r in sigmet_route_table if not r.get("_warning_row") and not r.get("_info_row")]

    if warning:
        print("[OFP 날짜 불일치 경고]")
        print(warning[0].get("warn_msg", ""))
        print()
    if info:
        print("[안내]")
        print(info[0].get("info_msg", ""))
        print()
    if normal:
        print(f"✅ 경로 영향 SIGMET/G-AIRMET: {len(normal)}건 (유효 시간대 표시)")
        print("-" * 60)
        for r in normal:
            valid_from = r.get("valid_from", "—")
            valid_to   = r.get("valid_to", "—")
            print(f"  유효 시간: {valid_from} ~ {valid_to}  |  {r.get('label','')}  |  {r.get('affect_type','')}")
            print(f"    구간: {r.get('first_wp','')} ~ {r.get('last_wp','')}  FL{r.get('base_fl','')}~FL{r.get('top_fl','')}  FIR: {r.get('fir','')}")
        print("-" * 60)
    else:
        print("경로·고도·시간 기준 매칭된 SIGMET 0건 (위 안내/경고 참고)")

    print("\n테스트 완료.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
