#!/usr/bin/env python3
"""
개선된 SIGWX 차트 분석 테스트 스크립트
"""

import sys
import os

def test_enhanced_sigwx_analysis(pdf_path: str = None):
    """개선된 SIGWX 차트 분석 테스트"""
    
    if not pdf_path:
        # uploads 폴더에서 최신 PDF 찾기
        uploads_dir = "uploads"
        if os.path.exists(uploads_dir):
            pdf_files = [f for f in os.listdir(uploads_dir) if f.endswith('.pdf')]
            if pdf_files:
                pdf_files.sort(key=lambda x: os.path.getmtime(os.path.join(uploads_dir, x)), reverse=True)
                pdf_path = os.path.join(uploads_dir, pdf_files[0])
                print(f"최신 PDF 파일 사용: {pdf_path}")
            else:
                print("❌ uploads 폴더에 PDF 파일이 없습니다.")
                return
        else:
            print("❌ uploads 폴더가 없습니다.")
            return
    
    if not os.path.exists(pdf_path):
        print(f"❌ PDF 파일을 찾을 수 없습니다: {pdf_path}")
        return
    
    print("=" * 80)
    print("개선된 SIGWX 차트 분석 테스트")
    print("=" * 80)
    print(f"PDF 파일: {pdf_path}\n")
    
    try:
        # 1. Flight Plan 데이터 추출
        print("[1단계] Flight Plan 데이터 추출...")
        from flightplanextractor import extract_flight_data_from_pdf
        flight_data = extract_flight_data_from_pdf(pdf_path, save_temp=False)
        
        if not flight_data:
            print("❌ Flight Plan 데이터를 추출할 수 없습니다.")
            return
        
        print(f"✅ {len(flight_data)}개 waypoint 추출됨")
        
        # 2. SIGWX 페이지 찾기
        print("\n[2단계] SIGWX 차트 페이지 찾기...")
        from flightplanextractor import find_sigwx_pages
        sigwx_pages = find_sigwx_pages(pdf_path)
        
        if not sigwx_pages:
            print("⚠️ SIGWX 차트를 찾을 수 없습니다.")
            print("   기존 방법으로 분석을 계속합니다.")
        else:
            print(f"✅ SIGWX 차트 발견: 페이지 {[p+1 for p in sigwx_pages]}")
            
            # 3. 개선된 SIGWX 분석
            print("\n[3단계] 개선된 SIGWX 차트 분석 (하이브리드 접근)...")
            from src.sigwx_analyzer import analyze_sigwx_chart_enhanced
            
            sigwx_analysis = analyze_sigwx_chart_enhanced(
                pdf_path, flight_data, sigwx_pages[0]
            )
            
            if sigwx_analysis:
                print(f"✅ SIGWX 분석 완료: {len(sigwx_analysis)}개 waypoint 분석됨")
                
                # 결과 요약
                print("\n[분석 결과 요약]")
                mod_turb_count = sum(1 for wp in sigwx_analysis.values() if wp.get('mod_turbulence'))
                sev_turb_count = sum(1 for wp in sigwx_analysis.values() if wp.get('sev_turbulence'))
                cb_count = sum(1 for wp in sigwx_analysis.values() if wp.get('cb_clouds'))
                jet_count = sum(1 for wp in sigwx_analysis.values() if wp.get('jet_streams'))
                
                print(f"  - MOD Turbulence: {mod_turb_count}개 waypoint")
                print(f"  - SEV Turbulence: {sev_turb_count}개 waypoint")
                print(f"  - CB Clouds: {cb_count}개 waypoint")
                print(f"  - Jet Streams: {jet_count}개 waypoint")
                
                # 상세 결과 (처음 10개만)
                print("\n[상세 결과 (처음 10개)]")
                for i, (wp_name, wp_data) in enumerate(list(sigwx_analysis.items())[:10]):
                    info_parts = []
                    if wp_data.get('mod_turbulence'):
                        info_parts.append("MOD Turb")
                    if wp_data.get('sev_turbulence'):
                        info_parts.append("SEV Turb")
                    if wp_data.get('cb_clouds'):
                        info_parts.append(f"CB({len(wp_data['cb_clouds'])})")
                    if wp_data.get('jet_streams'):
                        info_parts.append(f"Jet({len(wp_data['jet_streams'])})")
                    
                    info_str = ", ".join(info_parts) if info_parts else "없음"
                    print(f"  {wp_name} ({wp_data.get('estimated_time', 'N/A')}): {info_str}")
            else:
                print("⚠️ SIGWX 분석 결과가 없습니다.")
        
        # 4. 통합 분석 테스트 (기존 함수)
        print("\n[4단계] 통합 분석 테스트 (기존 analyze_turbulence_with_gemini)...")
        print("   (SIGWX 분석 결과가 프롬프트에 포함됨)")
        
        # ETD, ETA 추출 (간단한 버전)
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            full_text = ""
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    full_text += page_text + "\n"
        
        # ETD 추출
        etd_match = re.search(r'ETD\s+([A-Z]{4})\s+(\d{4})Z', full_text)
        etd_str = etd_match.group(2) + 'Z' if etd_match else None
        
        # ETA 추출
        eta_match = re.search(r'ETA\s+([A-Z]{4})\s+(\d{4})Z', full_text)
        eta_str = eta_match.group(2) + 'Z' if eta_match else None
        
        if etd_str:
            from datetime import datetime, timedelta
            try:
                etd_hour = int(etd_str[:2])
                etd_minute = int(etd_str[2:4])
                today = datetime.now()
                etd_time = datetime(today.year, today.month, today.day, etd_hour, etd_minute)
                takeoff_time = etd_time + timedelta(minutes=20)
                takeoff_time_str = takeoff_time.strftime('%H%M') + 'Z'
            except:
                takeoff_time_str = None
        else:
            takeoff_time_str = None
        
        # TURB/CB INFO 추출
        turb_cb_info = []
        if 'TURB/CB INFO' in full_text.upper():
            lines_text = full_text.split('\n')
            for i, line in enumerate(lines_text):
                if 'TURB/CB INFO' in line.upper():
                    turb_cb_info.append(line.strip())
                    for j in range(i + 1, min(i + 10, len(lines_text))):
                        next_line = lines_text[j].strip()
                        if not next_line:
                            break
                        if any(keyword in next_line.upper() for keyword in ['CAUTION', 'CB', 'TURB', 'SIG WX', 'TURBULENCE', 'CHART']):
                            turb_cb_info.append(next_line)
                        elif len(turb_cb_info) <= 4:
                            turb_cb_info.append(next_line)
                    break
        
        if etd_str and takeoff_time_str and eta_str:
            from flightplanextractor import analyze_turbulence_with_gemini
            print("   분석 중... (시간이 걸릴 수 있습니다)")
            result = analyze_turbulence_with_gemini(
                pdf_path, flight_data, etd_str, takeoff_time_str, eta_str, 
                turb_cb_info, None, None, None
            )
            
            if result and not result.startswith("⚠️"):
                print("✅ 통합 분석 완료!")
                print(f"\n[분석 결과 (처음 500자)]")
                print(result[:500])
            else:
                print(f"⚠️ 분석 실패: {result}")
        else:
            print("⚠️ ETD/ETA 정보가 없어 통합 분석을 건너뜁니다.")
        
        print("\n" + "=" * 80)
        print("테스트 완료")
        print("=" * 80)
        
    except Exception as e:
        print(f"❌ 테스트 중 오류 발생: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    import re
    pdf_path = sys.argv[1] if len(sys.argv) > 1 else None
    test_enhanced_sigwx_analysis(pdf_path)

