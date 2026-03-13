#!/usr/bin/env python3
"""
Flight plan에서 waypoint 좌표(lat/lon) 추출이 제대로 되는지 확인하는 스크립트.
사용법: python test_flightplan_coords.py <PDF 경로>
예: python test_flightplan_coords.py uploads/20260216_215456_b0fb45f8_ImportantFile_10.pdf
"""
import sys
import os

def main():
    if len(sys.argv) < 2:
        print("사용법: python test_flightplan_coords.py <PDF 경로>")
        sys.exit(1)
    pdf_path = sys.argv[1]
    if not os.path.isfile(pdf_path):
        print(f"파일 없음: {pdf_path}")
        sys.exit(1)

    from flightplanextractor import extract_flight_data_from_pdf

    print(f"PDF 로드: {pdf_path}\n")
    data = extract_flight_data_from_pdf(pdf_path, save_temp=False)
    if not data:
        print("Flight plan 데이터가 추출되지 않았습니다.")
        sys.exit(1)

    print(f"총 waypoint 수: {len(data)}\n")
    print(f"{'Waypoint':<12} {'lat':<12} {'lon':<12} {'FL':<6} {'ACTM':<8} {'ETO':<8}")
    print("-" * 60)
    has_coords = 0
    missing = []
    for row in data:
        wp = row.get("Waypoint", "")
        lat = row.get("lat")
        lon = row.get("lon")
        fl = row.get("FL (Flight Level)", "N/A")
        actm = row.get("ACTM (Accumulated Time)", "N/A")
        eto = row.get("Estimated Time (Z)", "N/A")
        if lat is not None and lon is not None:
            has_coords += 1
            print(f"{wp:<12} {lat:<12.6f} {lon:<12.6f} {fl:<6} {actm:<8} {eto:<8}")
        else:
            missing.append(wp)
            lat_s = f"{lat:.6f}" if lat is not None else "N/A"
            lon_s = f"{lon:.6f}" if lon is not None else "N/A"
            print(f"{wp:<12} {lat_s:<12} {lon_s:<12} {fl:<6} {actm:<8} {eto:<8}  <- 좌표 없음")

    print("-" * 60)
    print(f"\n좌표 추출됨: {has_coords}/{len(data)}")
    if missing:
        print(f"좌표 없는 waypoint: {', '.join(missing)}")
    else:
        print("모든 waypoint에 좌표가 추출되었습니다.")

if __name__ == "__main__":
    main()
