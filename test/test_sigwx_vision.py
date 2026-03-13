#!/usr/bin/env python3
"""
SIGWX 차트에서 터뷸런스 정보 추출 테스트 스크립트 (Gemini Vision API 사용)

SIGWX 차트에서 추출할 정보:
1. 핑크색 점선: MOD turbulence 지역
2. 빨간색 점선: SEV turbulence 지역
3. 초록색 구름모양 실선: 구름 위치 (예: OCNL CB 320 XXX = occasional cumulonimbus, top FL320, bottom unknown)
"""

import pdfplumber
import re
from typing import List, Dict, Optional
from PIL import Image
import io
import base64

# pdf2image 사용 (이미지 추출용)
try:
    from pdf2image import convert_from_path
    PDF2IMAGE_AVAILABLE = True
except ImportError as e:
    PDF2IMAGE_AVAILABLE = False
    # 메인 함수에서만 경고 메시지 출력 (여기서는 출력하지 않음)

# Gemini API 사용
try:
    import google.generativeai as genai
    from dotenv import load_dotenv
    import os
    load_dotenv()
    GEMINI_AVAILABLE = True
    
    # Gemini API 설정
    api_key = os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
    if api_key:
        genai.configure(api_key=api_key)
        # Vision API를 사용하려면 gemini-pro-vision 또는 gemini-1.5-flash 사용
        try:
            model = genai.GenerativeModel('gemini-2.5-flash-lite')
        except:
            try:
                model = genai.GenerativeModel('gemini-pro-vision')
            except:
                model = genai.GenerativeModel('gemini-pro')
    else:
        print("GEMINI_API_KEY가 설정되지 않았습니다.")
        GEMINI_AVAILABLE = False
except ImportError:
    GEMINI_AVAILABLE = False
    genai = None
    model = None

def find_sigwx_pages(pdf_path: str) -> List[int]:
    """
    PDF에서 SIGWX 차트가 있는 페이지 번호를 찾습니다.
    
    Args:
        pdf_path: PDF 파일 경로
        
    Returns:
        SIGWX 차트가 있는 페이지 번호 리스트 (0-based index)
    """
    sigwx_pages = []
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                page_text = page.extract_text()
                if page_text:
                    # SIGWX 키워드 찾기
                    if re.search(r'SIGWX', page_text, re.IGNORECASE):
                        sigwx_pages.append(i)
                        print(f"Page {i+1}: SIGWX 차트 발견")
                        # 차트 정보 출력
                        sigwx_match = re.search(r'SIGWX\s+([^\n]+)', page_text)
                        if sigwx_match:
                            print(f"  차트 정보: {sigwx_match.group(1)}")
    except Exception as e:
        print(f"PDF 파일을 읽는 중 오류가 발생했습니다: {e}")
    
    return sigwx_pages

def extract_page_as_image(pdf_path: str, page_num: int) -> Optional[Image.Image]:
    """
    PDF 페이지를 이미지로 추출합니다.
    
    Args:
        pdf_path: PDF 파일 경로
        page_num: 페이지 번호 (0-based, 1-based로 변환)
        
    Returns:
        PIL Image 객체 또는 None
    """
    if not PDF2IMAGE_AVAILABLE:
        return None
    
    try:
        # pdf2image는 1-based 인덱스를 사용, 해상도를 높여서 색상 구분을 더 잘 하도록
        images = convert_from_path(pdf_path, first_page=page_num + 1, last_page=page_num + 1, dpi=300)
        if images:
            return images[0]
        return None
    except Exception as e:
        print(f"페이지 이미지 추출 중 오류: {e}")
        return None

def get_waypoints_before_target(waypoints: List[str], target: str) -> List[str]:
    """
    특정 waypoint 이전의 waypoint 목록을 반환합니다.
    
    Args:
        waypoints: 비행 순서대로 정렬된 waypoint 목록
        target: 기준이 되는 waypoint
        
    Returns:
        target 이전의 waypoint 목록
    """
    if target not in waypoints:
        return []
    
    target_index = waypoints.index(target)
    return waypoints[:target_index]

def build_sigwx_prompt(waypoints: List[str], waypoints_before_katch: List[str] = None) -> str:
    """
    SIGWX 차트 분석을 위한 동적 프롬프트를 생성합니다.
    
    Args:
        waypoints: 분석할 waypoint 목록
        waypoints_before_katch: KATCH 이전 waypoint 목록 (None이면 자동으로 찾음)
        
    Returns:
        생성된 프롬프트 문자열
    """
    # KATCH 이전 waypoint 자동 감지
    if waypoints_before_katch is None:
        waypoints_before_katch = get_waypoints_before_target(waypoints, 'KATCH')
    
    waypoints_str = ', '.join(waypoints[:30])  # 처음 30개만
    
    # KATCH 이전 waypoint가 있으면 동적으로 추가
    before_katch_section = ""
    if waypoints_before_katch:
        before_katch_list = ', '.join(waypoints_before_katch)
        before_katch_section = f"""
**매우 중요 - KATCH 이전 구간 분석:**
비행 경로를 따라가면서, KATCH 이전 waypoint들({before_katch_list})이 빨간색 점선(SEV turbulence) 영역에 있는지 반드시 확인하세요.
- KATCH 자체는 MOD turbulence(핑크색 점선)일 수 있지만, 그 이전 구간에 SEV turbulence(빨간색 점선)가 있을 수 있습니다.
- 비행 경로에서 KATCH 이전 구간을 따라가면서 빨간색 점선이 있는지 매우 주의 깊게 확인하세요.
"""
    
    prompt = f"""
이것은 SIGWX (Significant Weather) 차트 이미지입니다.

**분석할 Waypoint 목록 (비행 순서대로):**
{waypoints_str}
{before_katch_section}
**SIGWX 차트에서 찾아야 할 정보 (매우 중요 - 색상을 정확히 구분하세요):**
1. **핑크색 점선 (Pink/Magenta dashed lines)**: MOD (Moderate) turbulence 지역
   - 핑크색 또는 마젠타색 점선으로 표시됨
   - 비행 경로와 교차하거나 가까운 위치에 있을 수 있음

2. **빨간색 점선 (Red dashed lines)**: SEV (Severe) turbulence 지역
   - **매우 중요**: 빨간색 점선은 핑크색 점선과 색상이 다릅니다. 빨간색 점선을 반드시 찾아주세요.
   - **특히 중요**: 이륙 후 초기 구간에서 **KATCH 이전 waypoint들**을 주의 깊게 확인하세요.
   - **KATCH 자체가 아닌, KATCH 이전 구간에 빨간색 점선이 있을 수 있습니다.**
   - 빨간색 점선은 보통 핑크색보다 더 진하고 선명한 빨간색입니다.
   - 비행 경로와 교차하거나 가까운 위치에 있을 수 있음
   - **KATCH 이전 waypoint들이 빨간색 점선 영역에 있는지 반드시 확인하세요**

3. **초록색 구름모양 실선 (Green cloud-shaped solid lines)**: 구름 위치
   - 예: "OCNL CB 320 XXX" = Occasional Cumulonimbus, Top FL320, Bottom Unknown
   - 예: "ISOL CB 340 280" = Isolated Cumulonimbus, Top FL340, Bottom FL280
   - 예: "OCNL CB FL310 230/420" = Occasional Cumulonimbus, Top FL310, Base FL230, Top FL420

**요청사항 (매우 중요):**
위 waypoint 목록 중에서, SIGWX 차트 이미지를 **매우 자세히** 분석하여 다음 정보를 찾아주세요:

1. 각 waypoint가 **핑크색 점선**(MOD turbulence) 영역에 있는지 - 색상을 정확히 구분하세요
   - KATCH는 MOD turbulence일 수 있습니다.

2. 각 waypoint가 **빨간색 점선**(SEV turbulence) 영역에 있는지 - **매우 중요**
   - **KATCH 이전 waypoint들을 특히 주의 깊게 확인하세요.**
   - **KATCH 자체가 아닌, KATCH 이전 구간에 빨간색 점선이 있을 수 있습니다.**
   - **비행 경로에서 KATCH 이전 구간을 따라가면서 빨간색 점선이 있는지 반드시 확인하세요.**
   - 빨간색 점선이 있으면 해당 waypoint의 sev_turbulence를 true로 설정하세요.

3. 각 waypoint 주변에 구름 정보가 있는지 (예: "OCNL CB 320 XXX")

**색상 구분 체크리스트:**
- 비행 경로 주변의 모든 점선을 확인하세요
- 핑크색/마젠타색 점선과 빨간색 점선을 명확히 구분하세요
- **특히 KATCH 이전 waypoint들이 빨간색 점선 영역에 있는지 반드시 확인하세요**
- KATCH 자체는 MOD turbulence일 수 있지만, 그 이전 구간에 SEV turbulence가 있을 수 있습니다

**색상 구분 중요사항:**
- 핑크색/마젠타색 점선 ≠ 빨간색 점선
- 빨간색 점선은 더 진한 빨간색으로 표시됩니다
- 비행 경로 주변의 모든 점선을 색상별로 정확히 구분하세요

**출력 형식 (JSON만 출력, 다른 설명 없이):**
{{
  "waypoint_name": {{
    "mod_turbulence": true/false,
    "sev_turbulence": true/false,
    "cloud_info": "OCNL CB 320 XXX" 또는 null
  }}
}}
"""
    return prompt

def analyze_sigwx_with_gemini_vision(pdf_path: str, waypoints: List[str], sigwx_pages: List[int]) -> Dict[str, Dict]:
    """
    Gemini Vision API를 사용하여 SIGWX 차트 이미지에서 터뷸런스 정보를 추출합니다.
    
    Args:
        pdf_path: PDF 파일 경로
        waypoints: 분석할 waypoint 리스트
        sigwx_pages: SIGWX 차트가 있는 페이지 번호 리스트
        
    Returns:
        각 waypoint의 터뷸런스 정보 딕셔너리
    """
    result = {}
    
    # 각 waypoint에 대해 초기값 설정
    for wp in waypoints:
        result[wp] = {
            'mod_turbulence': False,  # 핑크색 점선
            'sev_turbulence': False,  # 빨간색 점선
            'cloud_info': None,  # 구름 정보 (예: "OCNL CB 320 XXX")
            'sigwx_page': None  # SIGWX 차트가 있는 페이지 번호
        }
    
    if not GEMINI_AVAILABLE or not model:
        print("Gemini Vision API를 사용할 수 없습니다.")
        return result
    
    try:
        for page_num in sigwx_pages:
            print(f"\n=== Page {page_num + 1} 분석 (Gemini Vision) ===")
            
            # PDF 페이지를 이미지로 추출
            page_image = extract_page_as_image(pdf_path, page_num)
            
            if not page_image:
                print(f"  ⚠️ Page {page_num + 1} 이미지 추출 실패 (pdf2image 필요 또는 오류)")
                # 텍스트 기반 폴백
                try:
                    with pdfplumber.open(pdf_path) as pdf:
                        page = pdf.pages[page_num]
                        page_text = page.extract_text()
                        if page_text:
                            print(f"  텍스트 기반 분석 시도...")
                            # 동적 프롬프트 생성
                            prompt = build_sigwx_prompt(waypoints)
                            prompt += f"\n**차트 텍스트 정보:**\n{page_text[:3000]}"
                            response = model.generate_content(prompt)
                except Exception as e:
                    print(f"  텍스트 기반 분석 오류: {e}")
                continue
            
            # 이미지를 바이트로 변환
            img_byte_arr = io.BytesIO()
            page_image.save(img_byte_arr, format='PNG')
            img_byte_arr.seek(0)
            
            # 동적 프롬프트 생성
            prompt = build_sigwx_prompt(waypoints)
            
            try:
                # 이미지와 프롬프트를 함께 전달
                response = model.generate_content([prompt, page_image])
                
                print(f"Gemini 응답: {response.text[:500]}...")  # 처음 500자만 출력
                
                # JSON 파싱 시도
                response_text = response.text
                # 마크다운 코드 블록 제거 (```json ... ```)
                response_text = re.sub(r'```json\s*', '', response_text)
                response_text = re.sub(r'```\s*', '', response_text)
                # JSON 부분만 추출
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    import json
                    try:
                        waypoint_data = json.loads(json_match.group(0))
                        for wp, info in waypoint_data.items():
                            if wp in result:
                                # OR 연산: 한 페이지에서라도 true가 발견되면 true로 유지
                                result[wp]['mod_turbulence'] = result[wp]['mod_turbulence'] or info.get('mod_turbulence', False)
                                result[wp]['sev_turbulence'] = result[wp]['sev_turbulence'] or info.get('sev_turbulence', False)
                                # cloud_info는 마지막 발견된 것으로 업데이트 (또는 첫 번째로 발견된 것으로 유지)
                                if info.get('cloud_info'):
                                    result[wp]['cloud_info'] = info.get('cloud_info')
                                # sigwx_page는 첫 번째 발견된 페이지로 유지
                                if not result[wp]['sigwx_page']:
                                    result[wp]['sigwx_page'] = page_num + 1
                    except json.JSONDecodeError as e:
                        print(f"JSON 파싱 오류: {e}")
                
            except Exception as e:
                print(f"Gemini Vision API 호출 중 오류: {e}")
    
    except Exception as e:
        print(f"SIGWX 차트 분석 중 오류가 발생했습니다: {e}")
    
    return result

def main():
    """메인 함수"""
    pdf_path = "uploads/20251213_172222_4ce7d076_ImportantFile_4.pdf"
    
    print("=" * 80)
    print("SIGWX 차트 터뷸런스 정보 추출 테스트 (Gemini Vision API)")
    print("=" * 80)
    
    # Flight Plan에서 waypoint 추출
    print("\n1. Flight Plan에서 waypoint 추출 중...")
    try:
        from flightplanextractor import extract_flight_data_from_pdf
        flight_data = extract_flight_data_from_pdf(pdf_path, save_temp=False)
        
        waypoints = []
        if flight_data:
            for row in flight_data:
                wp = row.get('Waypoint', '')
                if wp and wp != 'N/A':
                    waypoints.append(wp)
        
        print(f"추출된 waypoint 수: {len(waypoints)}")
        print(f"Waypoints: {', '.join(waypoints[:20])}...")  # 처음 20개만 출력
        
    except Exception as e:
        print(f"Waypoint 추출 중 오류: {e}")
        waypoints = []
    
    # SIGWX 차트 페이지 찾기
    print("\n2. SIGWX 차트 페이지 찾기...")
    sigwx_pages = find_sigwx_pages(pdf_path)
    
    if not sigwx_pages:
        print("SIGWX 차트를 찾을 수 없습니다.")
        return
    
    # Gemini Vision API로 SIGWX 차트 분석
    print("\n3. Gemini Vision API로 SIGWX 차트 분석 중...")
    if not GEMINI_AVAILABLE:
        print("Gemini API를 사용할 수 없습니다. 환경 변수를 확인해주세요.")
        return
    
    turbulence_info = analyze_sigwx_with_gemini_vision(pdf_path, waypoints, sigwx_pages)
    
    # 결과 출력
    print("\n" + "=" * 80)
    print("추출 결과 요약")
    print("=" * 80)
    
    has_info = False
    for wp, info in turbulence_info.items():
        if any([info['mod_turbulence'], info['sev_turbulence'], info['cloud_info']]):
            has_info = True
            print(f"\n{wp}:")
            if info['mod_turbulence']:
                print(f"  - MOD Turbulence (핑크색 점선): 발견")
            if info['sev_turbulence']:
                print(f"  - SEV Turbulence (빨간색 점선): 발견")
            if info['cloud_info']:
                print(f"  - 구름 정보: {info['cloud_info']}")
            if info['sigwx_page']:
                print(f"  - SIGWX 차트 페이지: {info['sigwx_page']}")
    
    if not has_info:
        print("\n터뷸런스 정보가 발견되지 않았습니다.")
        print("참고: 텍스트 기반 분석만으로는 색상 정보를 정확히 추출하기 어렵습니다.")
        print("이미지 분석을 위해서는 pdf2image 라이브러리로 PDF 페이지를 이미지로 변환한 후")
        print("Gemini Vision API에 이미지를 직접 전달해야 합니다.")
    
    print("\n" + "=" * 80)

if __name__ == "__main__":
    main()

