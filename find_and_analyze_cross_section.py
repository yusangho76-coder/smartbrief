#!/usr/bin/env python3
"""
PDF에서 크로스 섹션 차트를 찾아서 분석하는 통합 스크립트
"""

import sys
import os
import re
from typing import List, Dict, Tuple, Optional
from PIL import Image
import numpy as np
import cv2

# PDF 처리
try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False

try:
    from pdf2image import convert_from_path
    PDF2IMAGE_AVAILABLE = True
except ImportError:
    PDF2IMAGE_AVAILABLE = False


# 크로스 차트 페이지 식별용 범례 키워드 (상단 우측 "Wind Isotach Isotherm VWS")
CROSS_CHART_LEGEND_KEYWORDS = ("WIND", "ISOTACH", "ISOTHERM", "VWS")


def find_cross_chart_page_by_legend(pdf_path: str) -> List[int]:
    """
    PDF에서 상단 우측에 'Wind Isotach Isotherm VWS' 범례가 있는 크로스 차트 페이지를 찾습니다.
    
    Args:
        pdf_path: PDF 파일 경로
        
    Returns:
        크로스 차트 페이지 번호 리스트 (0-based index)
    """
    pages = []
    if not PDFPLUMBER_AVAILABLE:
        return pages
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                page_text = page.extract_text() or ""
                page_upper = page_text.upper()
                if all(kw in page_upper for kw in CROSS_CHART_LEGEND_KEYWORDS):
                    pages.append(i)
    except Exception as e:
        print(f"크로스 차트 페이지 검색 중 오류: {e}")
    return pages


# 'cross' 라벨 다음에 오는 NOTAM 구간 식별용
NOTAM_PACKAGE_MARKER = "KOREAN AIR NOTAM PACKAGE 1"

# KOREAN AIR NOTAM PACKAGE 1 직전 기상 차트 라벨 (split.txt 순서: sigwx1, asc, cross)
WEATHER_CHART_LABELS = ("sigwx1", "asc", "cross")


def find_weather_chart_pages_before_notam(pdf_path: str) -> Dict[str, int]:
    """
    PDF에서 'KOREAN AIR NOTAM PACKAGE 1' 이전에 나오는 sigwx1, asc, cross
    라벨 페이지를 찾아 각 라벨별 페이지 번호(0-based)를 반환합니다.
    
    Args:
        pdf_path: PDF 파일 경로
        
    Returns:
        {"sigwx1": page_index, "asc": page_index, "cross": page_index} (찾은 것만 포함)
    """
    result: Dict[str, int] = {}
    if not PDFPLUMBER_AVAILABLE:
        return result
    try:
        with pdfplumber.open(pdf_path) as pdf:
            page_list = pdf.pages
            notam_start = None
            for i, page in enumerate(page_list):
                page_text = page.extract_text() or ""
                page_upper = page_text.upper()
                if NOTAM_PACKAGE_MARKER in page_upper:
                    notam_start = i
                    break
            if notam_start is None:
                return result
            for i, page in enumerate(page_list):
                if i >= notam_start:
                    break
                page_text = page.extract_text() or ""
                for line in page_text.splitlines():
                    label = line.strip().lower()
                    if label in WEATHER_CHART_LABELS:
                        result[label] = i
                        break
    except Exception as e:
        print(f"기상 차트 페이지(sigwx1/asc/cross) 검색 중 오류: {e}")
    return result


def find_cross_chart_page_by_label(pdf_path: str) -> List[int]:
    """
    PDF에서 'KOREAN AIR NOTAM PACKAGE 1' 이전에 나오는 'cross' 페이지를 찾습니다.
    (split.txt에서 … wintem1, wintem2, sigwx1, asc, cross, KOREAN AIR NOTAM PACKAGE 1
    순일 때, 그 'cross'에 해당하는 페이지 = 크로스 차트 페이지)
    
    Args:
        pdf_path: PDF 파일 경로
        
    Returns:
        크로스 차트 페이지 번호 리스트 (0-based index), 보통 1개
    """
    pages = []
    if not PDFPLUMBER_AVAILABLE:
        return pages
    try:
        with pdfplumber.open(pdf_path) as pdf:
            page_list = pdf.pages
            for i, page in enumerate(page_list):
                page_text = page.extract_text() or ""
                has_cross = any(line.strip().lower() == "cross" for line in page_text.splitlines())
                if not has_cross:
                    continue
                # 다음 페이지에 KOREAN AIR NOTAM PACKAGE 1 이 있으면 이 'cross'가 우리가 찾는 페이지
                if i + 1 < len(page_list):
                    next_text = page_list[i + 1].extract_text() or ""
                    if NOTAM_PACKAGE_MARKER in next_text.upper():
                        pages.append(i)
                        break
                # 마지막 페이지가 cross인 경우도 허용 (다음 페이지 없음)
                if i + 1 >= len(page_list):
                    pages.append(i)
                    break
    except Exception as e:
        print(f"크로스 차트 페이지(라벨 cross) 검색 중 오류: {e}")
    return pages


def export_cross_chart_page_to_jpg(
    pdf_path: str,
    page_index: int,
    output_path: Optional[str] = None,
    dpi: int = 200,
) -> Optional[str]:
    """
    PDF의 지정 페이지를 이미지로 변환하여 JPG로 저장합니다.
    
    Args:
        pdf_path: PDF 파일 경로
        page_index: 페이지 번호 (0-based)
        output_path: 저장 경로. None이면 PDF와 같은 디렉터리에 {pdf_basename}_cross_chart.jpg
        dpi: 이미지 해상도
        
    Returns:
        저장된 JPG 파일 경로, 실패 시 None
    """
    if not PDF2IMAGE_AVAILABLE:
        print("pdf2image를 사용할 수 없습니다.")
        return None
    if output_path is None:
        base = os.path.splitext(os.path.basename(pdf_path))[0]
        dir_path = os.path.dirname(os.path.abspath(pdf_path))
        output_path = os.path.join(dir_path, f"{base}_cross_chart.jpg")
    try:
        images = convert_from_path(
            pdf_path,
            first_page=page_index + 1,
            last_page=page_index + 1,
            dpi=dpi,
        )
        if not images:
            return None
        images[0].save(output_path, "JPEG", quality=92)
        return output_path
    except Exception as e:
        print(f"JPG 저장 중 오류: {e}")
        return None


def find_cross_section_pages(pdf_path: str) -> List[int]:
    """
    PDF에서 크로스 섹션 차트가 있는 페이지를 찾습니다.
    - 상단 우측 범례 'Wind Isotach Isotherm VWS' 포함 페이지 우선
    - 또는 VWS 키워드가 있는 페이지
    """
    cross_section_pages = []
    
    if not PDFPLUMBER_AVAILABLE:
        print("pdfplumber를 사용할 수 없습니다.")
        return cross_section_pages
    
    try:
        # 1) 범례 키워드로 크로스 차트 페이지 찾기 (Wind Isotach Isotherm VWS)
        by_legend = find_cross_chart_page_by_legend(pdf_path)
        if by_legend:
            cross_section_pages = by_legend
            for i in by_legend:
                print(f"크로스 섹션 차트 페이지 {i+1} 발견 (범례: Wind Isotach Isotherm VWS)")
            return cross_section_pages

        # 2) split.txt에 나오는 'cross' 라벨 페이지 찾기 (기상 차트가 이미지일 때)
        by_label = find_cross_chart_page_by_label(pdf_path)
        if by_label:
            cross_section_pages = by_label
            for i in by_label:
                print(f"크로스 섹션 차트 페이지 {i+1} 발견 (라벨: cross)")
            return cross_section_pages

        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                page_text = page.extract_text() or ""
                page_upper = page_text.upper()
                
                # VWS가 있으면 크로스 섹션 차트로 판단
                has_vws = 'VWS' in page_upper or 'VERTICAL WIND SHEAR' in page_upper
                keywords = [
                    'CROSS SECTION', 'CROSS-SECTION', 'VERTICAL CROSS',
                    'PROFILE', 'UKMET', 'ROUTE PROFILE', 'ALT X 100FT',
                    'HPA', 'ISOTHERM', 'TROPOPAUSE', 'TROPO'
                ]
                keyword_count = sum(1 for keyword in keywords if keyword in page_upper)
                has_chart_features = (
                    'HPA' in page_upper or 'ALT' in page_upper or 'ISOTHERM' in page_upper or
                    'WIND' in page_upper or 'TROPOPAUSE' in page_upper or 'TROPO' in page_upper
                )
                has_waypoints = bool(re.search(r'\b[A-Z]{2,}\b', page_text))
                
                if has_vws:
                    cross_section_pages.append(i)
                    print(f"크로스 섹션 차트 후보 페이지 {i+1} 발견")
                    print(f"  키워드 매칭: {keyword_count}개")
                    if has_chart_features:
                        print(f"  차트 특징 발견")
                    if has_waypoints:
                        print(f"  Waypoint 패턴 발견")
    except Exception as e:
        print(f"PDF 파일을 읽는 중 오류가 발생했습니다: {e}")
    
    return cross_section_pages


def detect_path_line(image: Image.Image, path_color_hex: str = "#df485f") -> List[Tuple[int, int]]:
    """
    이미지에서 경로(빨간색 선)를 감지합니다.
    
    Args:
        image: PIL Image 객체
        path_color_hex: 경로 색상 HEX 코드 (기본값: #df485f)
    """
    img_array = np.array(image)
    
    if img_array.shape[2] == 4:
        img_array = cv2.cvtColor(img_array, cv2.COLOR_RGBA2RGB)
    
    # UKMET cross 차트에서 항로는 마젠타 계열의 실선으로 표시됨.
    # 실제 이미지 팔레트 분석 결과, 대략 RGB(200, 120, 155) 주변 색이 항로에 해당.
    # path_color_hex 인자는 현재 사용하지 않고, 마젠타 계열 범위를 고정 사용.
    lower_bound = np.array([170, 80, 130], dtype=np.uint8)
    upper_bound = np.array([230, 170, 200], dtype=np.uint8)
    red_mask = cv2.inRange(img_array, lower_bound, upper_bound)
    
    # 모폴로지 연산으로 선을 더 잘 연결
    kernel = np.ones((3, 3), np.uint8)
    red_mask = cv2.morphologyEx(red_mask, cv2.MORPH_CLOSE, kernel)
    red_mask = cv2.morphologyEx(red_mask, cv2.MORPH_OPEN, kernel)
    
    edges = cv2.Canny(red_mask, 30, 100)  # 임계값 낮춤
    lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=30, minLineLength=30, maxLineGap=20)  # 임계값 낮춤
    
    path_points = []
    if lines is not None:
        for line in lines:
            x1, y1, x2, y2 = line[0]
            num_points = max(abs(x2-x1), abs(y2-y1))
            for i in range(num_points + 1):
                if num_points > 0:
                    x = int(x1 + (x2-x1) * i / num_points)
                    y = int(y1 + (y2-y1) * i / num_points)
                    path_points.append((x, y))
    
    return path_points


def detect_turbulence_lines(image: Image.Image) -> Dict[str, List[Tuple[int, int]]]:
    """
    UKMET cross 섹션 차트용 VWS(강한 수직 wind shear) 영역 감지.
    - 밝은 초록색 영역(VWS > 특정 threshold)을 turbulence proxy로 사용.
    - 현재는 모두 'yellow'(Moderate)로 매핑하고, light/severe는 사용하지 않음.
    """
    img_array = np.array(image)

    if img_array.shape[2] == 4:
        img_array = cv2.cvtColor(img_array, cv2.COLOR_RGBA2RGB)

    # 강한 VWS 영역: 밝은 초록색 (팔레트 분석 기준 대략 R<80, G>200, B<80)
    lower = np.array([0, 200, 0], dtype=np.uint8)
    upper = np.array([80, 255, 100], dtype=np.uint8)
    mask = cv2.inRange(img_array, lower, upper)

    ys, xs = np.where(mask > 0)

    turbulence_lines: Dict[str, List[Tuple[int, int]]] = {
        "green": [],
        "yellow": [],
        "red": [],
    }

    # 연산량을 줄이기 위해 일부 샘플링 (3픽셀마다 하나)
    for i in range(0, len(xs), 3):
        turbulence_lines["yellow"].append((int(xs[i]), int(ys[i])))

    return turbulence_lines


def find_intersections(path_points: List[Tuple[int, int]], 
                      turbulence_points: List[Tuple[int, int]], 
                      threshold: int = 5) -> List[Tuple[int, int]]:
    """경로와 터뷸런스 선의 교차점을 찾습니다."""
    intersections = []
    
    for turb_point in turbulence_points:
        for path_point in path_points:
            distance = np.sqrt((turb_point[0] - path_point[0])**2 + 
                             (turb_point[1] - path_point[1])**2)
            if distance <= threshold:
                intersections.append(path_point)
                break
    
    return intersections


def extract_waypoints_from_pdf(pdf_path: str) -> List[str]:
    """PDF에서 waypoint 목록을 추출합니다."""
    try:
        from flightplanextractor import extract_flight_data_from_pdf
        
        flight_data = extract_flight_data_from_pdf(pdf_path, save_temp=False)
        waypoints = []
        
        if flight_data:
            for row in flight_data:
                wp = row.get('Waypoint', '')
                if wp and wp != 'N/A':
                    waypoints.append(wp)
        
        return waypoints
    except Exception as e:
        print(f"⚠️ Waypoint 추출 실패: {e}")
        return []


def analyze_cross_section_image(image: Image.Image, waypoints: List[str], path_color_hex: str = "#df485f") -> Dict[str, Dict]:
    """
    크로스 섹션 차트 이미지를 분석합니다.
    경로 색상 변화 감지 방식 사용: 경로(#df485f)를 따라가면서 색상이 변하는 지점을 찾습니다.
    
    Args:
        image: PIL Image 객체
        waypoints: waypoint 목록 (x축 순서대로)
        path_color_hex: 경로 색상 HEX 코드 (기본값: #df485f)
        
    Returns:
        {waypoint_name: {'light': bool, 'moderate': bool, 'severe': bool}}
    """
    # 1) 경로 픽셀 추출
    path_points = detect_path_line(image, path_color_hex=path_color_hex)
    if not waypoints:
        return {}
    # 결과 초기화
    result: Dict[str, Dict[str, bool]] = {
        wp: {"light": False, "moderate": False, "severe": False} for wp in waypoints
    }
    if not path_points:
        return result

    xs = [p[0] for p in path_points]
    x_min, x_max = min(xs), max(xs)
    width = max(1, x_max - x_min)

    # 2) 터뷸런스 색상 선 추출
    turb_lines = detect_turbulence_lines(image)

    # 3) 경로와 터뷸런스 선 교차점 계산
    intersections: Dict[str, List[Tuple[int, int]]] = {}
    for color_key, pts in turb_lines.items():
        intersections[color_key] = find_intersections(path_points, pts, threshold=5)

    # 4) 교차점 x좌표를 waypoint 인덱스로 매핑 (경로 상 min_x~max_x를 균등 분할)
    n_wp = len(waypoints)
    if n_wp <= 1:
        return result

    def _assign(level_key: str, color_key: str) -> None:
        pts = intersections.get(color_key, [])
        for x, _y in pts:
            ratio = (x - x_min) / width
            ratio = max(0.0, min(1.0, ratio))
            idx = int(round(ratio * (n_wp - 1)))
            wp = waypoints[idx]
            result[wp][level_key] = True

    _assign("light", "green")
    _assign("moderate", "yellow")
    _assign("severe", "red")

    return result


def analyze_cross_section_from_pdf(pdf_path: str) -> Dict[str, Dict]:
    """
    PDF에서 크로스 섹션 차트를 찾아서 분석합니다.
    
    Args:
        pdf_path: PDF 파일 경로
        
    Returns:
        {waypoint_name: {'light': bool, 'moderate': bool, 'severe': bool}}
    """
    print("=" * 80)
    print("크로스 섹션 차트 분석")
    print("=" * 80)
    print(f"PDF 파일: {pdf_path}")
    print()
    
    # 1. Waypoint 추출
    print("[1단계] Waypoint 추출...")
    waypoints = extract_waypoints_from_pdf(pdf_path)
    if not waypoints:
        print("⚠️ Waypoint를 추출할 수 없습니다.")
        return {}
    print(f"✅ 추출된 waypoint 수: {len(waypoints)}")
    print(f"   Waypoints: {', '.join(waypoints[:10])}...")
    print()
    
    # 2. 크로스 섹션 차트 페이지 찾기
    print("[2단계] 크로스 섹션 차트 페이지 찾기...")
    cross_section_pages = find_cross_section_pages(pdf_path)
    
    if not cross_section_pages:
        print("⚠️ 크로스 섹션 차트를 찾을 수 없습니다.")
        return {}
    
    print(f"✅ 크로스 섹션 차트 페이지 발견: {[p+1 for p in cross_section_pages]}")
    print()
    
    # 3. 각 페이지 분석
    if not PDF2IMAGE_AVAILABLE:
        print("⚠️ pdf2image를 사용할 수 없습니다.")
        return {}
    
    all_results = {}
    
    for page_num in cross_section_pages:
        print(f"[3단계] 페이지 {page_num + 1} 분석 중...")
        try:
            # PDF 페이지를 이미지로 변환 (고해상도)
            images = convert_from_path(pdf_path, first_page=page_num + 1, last_page=page_num + 1, dpi=600)
            if not images:
                print(f"  ⚠️ 페이지 {page_num + 1} 이미지 변환 실패")
                continue
            
            page_image = images[0]
            
            # 이미지 분석
            page_result = analyze_cross_section_image(page_image, waypoints)
            
            # 결과 병합 (OR 로직: 한 페이지라도 터뷸런스가 있으면 True)
            for wp_name, info in page_result.items():
                if wp_name not in all_results:
                    all_results[wp_name] = {
                        'light': False,
                        'moderate': False,
                        'severe': False
                    }
                all_results[wp_name]['light'] |= info.get('light', False)
                all_results[wp_name]['moderate'] |= info.get('moderate', False)
                all_results[wp_name]['severe'] |= info.get('severe', False)
            
            print(f"  ✅ 페이지 {page_num + 1} 분석 완료")
            
        except Exception as e:
            print(f"  ❌ 페이지 {page_num + 1} 분석 중 오류: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    return all_results


def main():
    """메인 함수"""
    if len(sys.argv) < 2:
        print("사용법: python3 find_and_analyze_cross_section.py <PDF_파일_경로>")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    
    if not os.path.exists(pdf_path):
        print(f"❌ 파일을 찾을 수 없습니다: {pdf_path}")
        sys.exit(1)
    
    # 분석 수행
    results = analyze_cross_section_from_pdf(pdf_path)
    
    # 결과 출력
    print("\n" + "=" * 80)
    print("분석 결과")
    print("=" * 80)
    
    if not results:
        print("터뷸런스 정보를 찾을 수 없습니다.")
        return
    
    # 터뷸런스가 있는 waypoint만 출력
    has_turbulence = False
    for wp_name, info in results.items():
        if any([info['light'], info['moderate'], info['severe']]):
            has_turbulence = True
            print(f"\n📍 {wp_name}:")
            if info['light']:
                print("  - Light Turbulence (Green) 감지")
            if info['moderate']:
                print("  - Moderate Turbulence (Yellow) 감지")
            if info['severe']:
                print("  - Severe Turbulence (Red) 감지")
    
    if not has_turbulence:
        print("경로상에 터뷸런스가 감지되지 않았습니다.")
    
    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()

