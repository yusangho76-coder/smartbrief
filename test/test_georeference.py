#!/usr/bin/env python3
"""
Flight Plan 좌표 기반 차트 분석 테스트
"""

from georeference_chart import analyze_chart_with_coordinates, extract_coordinates_from_flight_plan
from pdf2image import convert_from_path
from PIL import Image

def test_coordinate_extraction():
    """Flight Plan에서 좌표 추출 테스트"""
    pdf_path = 'uploads/20251220_113941_06626b8c_ImportantFile_5.pdf'
    
    print("=== Flight Plan 좌표 추출 테스트 ===\n")
    waypoints = extract_coordinates_from_flight_plan(pdf_path)
    
    print(f"\n총 {len(waypoints)}개 waypoint 추출:")
    for wp in waypoints[:10]:  # 처음 10개만 출력
        print(f"  {wp['waypoint']}: {wp['lat']:.4f}, {wp['lon']:.4f} (FL={wp['fl']}, SR={wp['sr']})")
    
    if len(waypoints) > 10:
        print(f"  ... 외 {len(waypoints) - 10}개")


def test_chart_analysis():
    """차트 분석 테스트"""
    pdf_path = 'uploads/20251220_113941_06626b8c_ImportantFile_5.pdf'
    
    # ASC 차트 페이지 찾기 (예: 21페이지)
    # 실제로는 find_cross_section_pages 등을 사용해야 함
    chart_page = 21
    
    print(f"\n=== 차트 분석 테스트 (페이지 {chart_page}) ===\n")
    
    # PDF에서 차트 이미지 추출
    images = convert_from_path(pdf_path, first_page=chart_page, last_page=chart_page, dpi=300)
    if not images:
        print("⚠️ 차트 이미지를 찾을 수 없습니다.")
        return
    
    chart_image = images[0]
    
    # 차트 분석
    result = analyze_chart_with_coordinates(pdf_path, chart_image)
    
    if result:
        print(f"\n✅ 분석 완료:")
        print(f"  Waypoint: {len(result['waypoints'])}개")
        print(f"  항로 점: {len(result['route_points'])}개")
        print(f"  Turbulence:")
        print(f"    Light: {len(result['turbulence']['light'])}개")
        print(f"    Moderate: {len(result['turbulence']['moderate'])}개")
        print(f"    Severe: {len(result['turbulence']['severe'])}개")
    else:
        print("⚠️ 분석 실패")


if __name__ == '__main__':
    test_coordinate_extraction()
    # test_chart_analysis()  # 필요시 주석 해제

