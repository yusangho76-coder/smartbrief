#!/usr/bin/env python3
"""
ImportantFile 5.pdf로 turbulence 감지 테스트
"""

from georeference_chart import extract_coordinates_from_flight_plan, analyze_chart_with_coordinates
from find_and_analyze_cross_section import find_cross_section_pages, extract_waypoints_from_pdf
from detect_path_color_changes import analyze_path_with_color_changes
from pdf2image import convert_from_path
from PIL import Image

def test_turbulence_detection():
    """ImportantFile 5.pdf로 turbulence 감지 테스트"""
    pdf_path = 'uploads/20251220_113941_06626b8c_ImportantFile_5.pdf'
    
    print("=" * 70)
    print("Turbulence 감지 테스트: ImportantFile 5.pdf")
    print("=" * 70)
    
    # 1. Flight Plan에서 좌표 추출
    print("\n[1단계] Flight Plan에서 좌표 추출 중...")
    waypoints_with_coords = extract_coordinates_from_flight_plan(pdf_path)
    
    if not waypoints_with_coords:
        print("⚠️ 좌표를 추출할 수 없습니다.")
        return
    
    print(f"✅ {len(waypoints_with_coords)}개 waypoint 좌표 추출 완료")
    
    # 2. 크로스 섹션 차트 페이지 찾기
    print("\n[2단계] 크로스 섹션 차트 페이지 찾기...")
    cross_section_pages = find_cross_section_pages(pdf_path)
    
    # ASC 차트도 확인 (21페이지)
    if not cross_section_pages:
        print("⚠️ VWS 키워드로 크로스 섹션 차트를 찾을 수 없습니다.")
        print("  ASC 차트 페이지 확인 중...")
        # 21페이지 확인 (0-based index: 20)
        try:
            import pdfplumber
            with pdfplumber.open(pdf_path) as pdf:
                if len(pdf.pages) > 20:
                    page_text = pdf.pages[20].extract_text() or ''
                    if 'ASC' in page_text.upper() or 'FL180' in page_text.upper():
                        cross_section_pages = [20]
                        print(f"✅ ASC 차트 발견: 페이지 21")
        except:
            pass
    
    if not cross_section_pages:
        print("⚠️ 크로스 섹션 차트를 찾을 수 없습니다.")
        return
    
    print(f"✅ 크로스 섹션 차트 발견: 페이지 {[p+1 for p in cross_section_pages]}")
    
    # 3. Waypoint 목록 추출
    print("\n[3단계] Waypoint 목록 추출 중...")
    waypoint_names = extract_waypoints_from_pdf(pdf_path)
    print(f"✅ {len(waypoint_names)}개 waypoint 추출 완료")
    
    # 4. 각 크로스 섹션 차트 분석
    print("\n[4단계] 크로스 섹션 차트 분석 중...")
    
    all_results = {}
    
    for page_num in cross_section_pages:
        print(f"\n--- 페이지 {page_num} 분석 ---")
        
        try:
            # PDF에서 이미지 추출
            images = convert_from_path(
                pdf_path, 
                first_page=page_num, 
                last_page=page_num, 
                dpi=300
            )
            
            if not images:
                print(f"⚠️ 페이지 {page_num} 이미지를 추출할 수 없습니다.")
                continue
            
            chart_image = images[0]
            
            # 방법 1: 좌표 기반 분석 시도
            print("  [방법 1] 좌표 기반 분석 시도...")
            try:
                coord_result = analyze_chart_with_coordinates(pdf_path, chart_image)
                
                if coord_result and coord_result.get('turbulence'):
                    print("  ✅ 좌표 기반 분석 성공")
                    all_results[f'page_{page_num}_coords'] = coord_result
                else:
                    print("  ⚠️ 좌표 기반 분석 결과 없음")
            except Exception as e:
                print(f"  ⚠️ 좌표 기반 분석 실패: {e}")
            
            # 방법 2: 색상 변화 기반 분석 (fallback)
            print("  [방법 2] 색상 변화 기반 분석 시도...")
            try:
                color_result = analyze_path_with_color_changes(
                    chart_image, 
                    waypoint_names, 
                    '#df485f'
                )
                
                if color_result:
                    print("  ✅ 색상 변화 기반 분석 성공")
                    all_results[f'page_{page_num}_color'] = {
                        'waypoints': waypoint_names,
                        'turbulence': color_result
                    }
            except Exception as e:
                print(f"  ⚠️ 색상 변화 기반 분석 실패: {e}")
        
        except Exception as e:
            print(f"⚠️ 페이지 {page_num} 분석 중 오류: {e}")
            import traceback
            traceback.print_exc()
    
    # 5. 결과 요약
    print("\n" + "=" * 70)
    print("TURBULENCE 감지 결과 요약")
    print("=" * 70)
    
    if not all_results:
        print("⚠️ Turbulence를 감지하지 못했습니다.")
        return
    
    # 좌표 기반 결과 출력 (구간 단위)
    for key, result in all_results.items():
        if 'coords' in key:
            print(f"\n[{key}] 좌표 기반 분석 결과 (구간 단위):")
            turbulence = result.get('turbulence', {})
            
            light_segments = turbulence.get('light', [])
            moderate_segments = turbulence.get('moderate', [])
            severe_segments = turbulence.get('severe', [])
            
            print(f"\n  Light Turbulence: {len(light_segments)}개 구간")
            if light_segments:
                for seg in light_segments:
                    start_wp = seg.get('start_waypoint', 'Unknown')
                    end_wp = seg.get('end_waypoint', 'Unknown')
                    print(f"    - {start_wp} ~ {end_wp}")
            
            print(f"\n  Moderate Turbulence: {len(moderate_segments)}개 구간")
            if moderate_segments:
                for seg in moderate_segments:
                    start_wp = seg.get('start_waypoint', 'Unknown')
                    end_wp = seg.get('end_waypoint', 'Unknown')
                    print(f"    - {start_wp} ~ {end_wp}")
            
            print(f"\n  Severe Turbulence: {len(severe_segments)}개 구간")
            if severe_segments:
                for seg in severe_segments:
                    start_wp = seg.get('start_waypoint', 'Unknown')
                    end_wp = seg.get('end_waypoint', 'Unknown')
                    print(f"    - {start_wp} ~ {end_wp}")
            
            if not light_segments and not moderate_segments and not severe_segments:
                print("  ⚠️ Turbulence 구간이 감지되지 않았습니다.")
        
        elif 'color' in key:
            print(f"\n[{key}] 색상 변화 기반 분석 결과:")
            turbulence = result.get('turbulence', {})
            waypoints = result.get('waypoints', [])
            
            # Turbulence가 있는 waypoint 찾기
            turb_waypoints = []
            for wp in waypoints:
                wp_turb = turbulence.get(wp, {})
                if any(wp_turb.values()):
                    types = []
                    if wp_turb.get('light'):
                        types.append("Light")
                    if wp_turb.get('moderate'):
                        types.append("Moderate")
                    if wp_turb.get('severe'):
                        types.append("Severe")
                    turb_waypoints.append((wp, types))
            
            if turb_waypoints:
                print(f"  Turbulence 감지된 Waypoint ({len(turb_waypoints)}개):")
                for wp, types in turb_waypoints:
                    print(f"    {wp}: {', '.join(types)}")
            else:
                print("  Turbulence 감지되지 않음")
    
    print("\n" + "=" * 70)


if __name__ == '__main__':
    test_turbulence_detection()

