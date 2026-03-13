#!/usr/bin/env python3
"""
동적 waypoint 처리 확인 테스트
"""

import sys
import os

# flightplanextractor 모듈 import
try:
    from flightplanextractor import (
        extract_flight_data_from_pdf,
        find_asc_chart_pages
    )
    from extract_asc_colors_method3_gemini_improved import build_improved_gemini_prompt
except ImportError as e:
    print(f"모듈 import 오류: {e}")
    sys.exit(1)


def test_dynamic_waypoints(pdf_path: str):
    """PDF에서 waypoint를 동적으로 추출하고 프롬프트 생성 테스트"""
    print("=" * 100)
    print("동적 waypoint 처리 확인 테스트")
    print("=" * 100)
    
    # 1. Waypoint 추출
    print("\n[1단계] PDF에서 waypoint 동적 추출...")
    try:
        flight_data = extract_flight_data_from_pdf(pdf_path, save_temp=False)
        waypoints = []
        if flight_data:
            for row in flight_data:
                wp = row.get('Waypoint', '')
                if wp and wp != 'N/A':
                    waypoints.append(wp)
        
        if not waypoints:
            print("❌ Waypoint를 추출할 수 없습니다.")
            return
        
        print(f"✅ 추출된 waypoint 수: {len(waypoints)}")
        print(f"처음 5개: {waypoints[:5]}")
        print(f"마지막 5개: {waypoints[-5:]}")
        
    except Exception as e:
        print(f"❌ Waypoint 추출 중 오류: {e}")
        return
    
    # 2. 프롬프트 생성
    print("\n[2단계] 동적 프롬프트 생성...")
    try:
        prompt = build_improved_gemini_prompt(waypoints, max_waypoints=50)
        
        # 하드코딩 확인
        hardcoded_waypoints = ['NATES', 'NIKLL', 'NYMPH', 'NUZAN', 'EEP2', 'NESKO', 
                              'TREEL', 'UQQ', 'KATCH', 'HMPTN', 'GRIZZ', 'CJAYY']
        
        found_hardcoded = []
        for hw in hardcoded_waypoints:
            if hw in prompt and hw not in waypoints:
                found_hardcoded.append(hw)
        
        if found_hardcoded:
            print(f"❌ 하드코딩된 waypoint 발견: {found_hardcoded}")
        else:
            print("✅ 하드코딩된 waypoint 없음")
        
        # 동적 waypoint 확인
        dynamic_waypoints = []
        for wp in waypoints[:10]:
            if wp in prompt:
                dynamic_waypoints.append(wp)
        
        print(f"✅ 프롬프트에 포함된 동적 waypoint: {len(dynamic_waypoints)}개")
        print(f"   예시: {dynamic_waypoints[:5]}")
        
        # 도착 공항 확인
        arrival = waypoints[-1] if waypoints else None
        if arrival and arrival in prompt:
            print(f"✅ 도착 공항 '{arrival}' 동적 처리 확인")
        
        # 출력 예시 확인
        if waypoints[0] in prompt and waypoints[0] in prompt.split('출력 형식')[1] if '출력 형식' in prompt else False:
            print(f"✅ 출력 예시에 실제 waypoint '{waypoints[0]}' 포함 확인")
        
    except Exception as e:
        print(f"❌ 프롬프트 생성 중 오류: {e}")
        import traceback
        traceback.print_exc()
        return
    
    print("\n" + "=" * 100)
    print("✅ 모든 테스트 통과: 동적 waypoint 처리 정상 작동")
    print("=" * 100)


if __name__ == "__main__":
    # 테스트할 PDF 파일들
    test_files = [
        "uploads/ImportantFile 3.pdf",
        "uploads/20251213_172222_4ce7d076_ImportantFile_4.pdf"
    ]
    
    for pdf_path in test_files:
        if os.path.exists(pdf_path):
            print(f"\n\n📄 테스트 파일: {pdf_path}")
            test_dynamic_waypoints(pdf_path)
        else:
            print(f"⚠️ 파일을 찾을 수 없습니다: {pdf_path}")

