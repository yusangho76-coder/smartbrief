#!/usr/bin/env python3
"""
차트 이미지의 Georeferencing 및 Waypoint 좌표 기반 항로 재구성

Flight Plan의 위/경도 좌표를 차트의 그리드와 매칭하여 정확한 항로를 재구성합니다.
"""

import numpy as np
import cv2
from PIL import Image
from typing import List, Dict, Tuple, Optional
import re
import math

# 터뷸런스 색상 정의
TURBULENCE_COLORS = {
    'light': (29, 248, 255),      # cyan #1df8ff
    'moderate': (255, 254, 1),   # yellow #fffe01
    'severe': (255, 8, 6)         # red #ff0806
}


def extract_coordinates_from_flight_plan(pdf_path: str) -> List[Dict]:
    """
    Flight Plan PDF에서 waypoint의 위/경도 좌표를 직접 추출합니다.
    
    Args:
        pdf_path: PDF 파일 경로
        
    Returns:
        [
            {
                'waypoint': 'RIC',
                'lat': -33.5967,  # S33 35.8 -> -33.5967
                'lon': 150.7767,  # E150 46.6 -> 150.7767
                'fl': '301',
                'sr': 'N/A',
                'actm': '00.13',
                'estimated_time': '1339Z'
            },
            ...
        ]
    """
    try:
        import pdfplumber
        from flightplanextractor import extract_flight_data_from_pdf
        
        # Flight Plan 데이터 추출
        flight_data = extract_flight_data_from_pdf(pdf_path, save_temp=False)
        if not flight_data:
            return []
        
        # PDF에서 원본 텍스트 추출 (좌표 정보 포함)
        full_text = ""
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    full_text += page_text + "\n"
        
        # Flight Plan 테이블 영역 찾기
        lines = full_text.split('\n')
        start_marker = "DIST LATITUDE"  # "DIST LATITUDE" 또는 "DIST LATITUDE LONGITUDE"
        end_marker = "ROUTE TO ALTN"
        
        in_flight_plan = False
        flight_plan_lines = []
        
        for line in lines:
            stripped_line = line.strip()
            if start_marker in line and not in_flight_plan:
                in_flight_plan = True
                continue
            if stripped_line.startswith(end_marker):
                break
            if in_flight_plan and stripped_line:
                cleaned_line = re.sub(r' +', ' ', stripped_line)
                flight_plan_lines.append(cleaned_line)
        
        if not flight_plan_lines:
            print("⚠️ Flight Plan 테이블을 찾을 수 없습니다.")
            return []
        
        # 좌표 추출
        waypoints_with_coords = []
        i = 0
        
        while i < len(flight_plan_lines):
            current_line = flight_plan_lines[i]
            parts = current_line.split()
            
            if not parts or not parts[0].isdigit():
                i += 1
                continue
            
            # 다음 행에서 waypoint 이름 찾기
            if i + 1 < len(flight_plan_lines):
                next_line = flight_plan_lines[i + 1]
                next_parts = next_line.split()
                
                if next_parts:
                    waypoint_candidate = next_parts[0]
                    
                    # Waypoint 유효성 확인
                    invalid_keywords = ['Page', 'TO', 'TC', 'FIR', '/', '---', 'CLB', 'DSC']
                    is_coordinate = re.match(r'^\d{2}[NS]\d{2}', waypoint_candidate)
                    is_alphanumeric = re.match(r'^[A-Z]+\d+', waypoint_candidate)
                    is_alpha_only = waypoint_candidate.isalpha() and len(waypoint_candidate) >= 2
                    
                    is_valid_waypoint = (
                        (is_coordinate or is_alphanumeric or is_alpha_only) and
                        waypoint_candidate not in invalid_keywords and
                        len(waypoint_candidate) >= 2
                    )
                    
                    if is_valid_waypoint:
                        waypoint = waypoint_candidate
                        
                        # 위도는 현재 행(첫 번째 행)에서, 경도는 다음 행(두 번째 행)에서 추출
                        # 형식:
                        # 첫 번째 줄: "0074 S33 35.8 303 CLB ..." (위도)
                        # 두 번째 줄: "RIC E150 46.6 301 / ..." (경도)
                        lat = None
                        lon = None
                        
                        # 현재 행에서 위도 추출
                        current_parts = current_line.split()
                        for j, part in enumerate(current_parts):
                            # "S33" 또는 "N57" 형식
                            if part.startswith(('S', 'N')) and len(part) >= 2:
                                try:
                                    lat_dir = part[0]
                                    lat_deg = int(part[1:])
                                    
                                    # 다음 부분이 분(minutes)일 수 있음: "S33 35.8"
                                    if j + 1 < len(current_parts):
                                        next_part = current_parts[j + 1]
                                        if '.' in next_part:
                                            try:
                                                lat_min = float(next_part)
                                                lat = lat_deg + lat_min / 60.0
                                                if lat_dir == 'S':
                                                    lat = -lat
                                            except:
                                                lat = float(lat_deg)
                                                if lat_dir == 'S':
                                                    lat = -lat
                                        else:
                                            lat = float(lat_deg)
                                            if lat_dir == 'S':
                                                lat = -lat
                                    else:
                                        lat = float(lat_deg)
                                        if lat_dir == 'S':
                                            lat = -lat
                                    break
                                except:
                                    pass
                        
                        # 다음 행에서 경도 추출
                        next_parts = next_line.split()
                        for j, part in enumerate(next_parts):
                            # "E150" 또는 "W120" 형식
                            if part.startswith(('E', 'W')) and len(part) >= 2:
                                try:
                                    lon_dir = part[0]
                                    lon_deg = int(part[1:])
                                    
                                    # 다음 부분이 분일 수 있음: "E150 46.6"
                                    if j + 1 < len(next_parts):
                                        next_part = next_parts[j + 1]
                                        if '.' in next_part:
                                            try:
                                                lon_min = float(next_part)
                                                lon = lon_deg + lon_min / 60.0
                                                if lon_dir == 'W':
                                                    lon = -lon
                                            except:
                                                lon = float(lon_deg)
                                                if lon_dir == 'W':
                                                    lon = -lon
                                        else:
                                            lon = float(lon_deg)
                                            if lon_dir == 'W':
                                                lon = -lon
                                    else:
                                        lon = float(lon_deg)
                                        if lon_dir == 'W':
                                            lon = -lon
                                    break
                                except:
                                    pass
                        
                        # Flight Plan 데이터에서 추가 정보 가져오기
                        flight_info = None
                        for row in flight_data:
                            if row.get('Waypoint') == waypoint:
                                flight_info = row
                                break
                        
                        if lat is not None and lon is not None:
                            waypoints_with_coords.append({
                                'waypoint': waypoint,
                                'lat': lat,
                                'lon': lon,
                                'fl': flight_info.get('FL (Flight Level)', 'N/A') if flight_info else 'N/A',
                                'sr': flight_info.get('SR (Shear Rate)', 'N/A') if flight_info else 'N/A',
                                'actm': flight_info.get('ACTM (Accumulated Time)', 'N/A') if flight_info else 'N/A',
                                'estimated_time': flight_info.get('Estimated Time (Z)', 'N/A') if flight_info else 'N/A'
                            })
                            print(f"  ✅ {waypoint}: {lat:.4f}, {lon:.4f}")
                        else:
                            print(f"  ⚠️ {waypoint}: 좌표 추출 실패")
                        
                        i += 2
                        continue
            
            i += 1
        
        return waypoints_with_coords
        
    except Exception as e:
        print(f"⚠️ Flight Plan 좌표 추출 실패: {e}")
        import traceback
        traceback.print_exc()
        return []


def detect_grid_lines(image: Image.Image) -> Dict[str, List[Tuple[int, int]]]:
    """
    차트 이미지에서 위도/경도 그리드 라인을 감지합니다.
    
    Args:
        image: PIL Image 객체
        
    Returns:
        {
            'lat_lines': [(x1, y1, x2, y2), ...],  # 수평선 (위도선)
            'lon_lines': [(x1, y1, x2, y2), ...]   # 수직선 (경도선)
        }
    """
    img_array = np.array(image)
    if img_array.shape[2] == 4:
        img_array = cv2.cvtColor(img_array, cv2.COLOR_RGBA2RGB)
    
    # 그레이스케일 변환
    gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
    
    # 엣지 검출
    edges = cv2.Canny(gray, 50, 150)
    
    # 수평선 (위도선) 검출
    horizontal_lines = cv2.HoughLinesP(
        edges, 1, np.pi/180, threshold=100,
        minLineLength=200, maxLineGap=10
    )
    
    # 수직선 (경도선) 검출
    vertical_lines = cv2.HoughLinesP(
        edges, 1, np.pi/180, threshold=100,
        minLineLength=200, maxLineGap=10
    )
    
    lat_lines = []
    lon_lines = []
    
    if horizontal_lines is not None:
        for line in horizontal_lines:
            x1, y1, x2, y2 = line[0]
            # 수평선인지 확인 (y 좌표 차이가 작음)
            if abs(y1 - y2) < 10:
                lat_lines.append((x1, y1, x2, y2))
    
    if vertical_lines is not None:
        for line in vertical_lines:
            x1, y1, x2, y2 = line[0]
            # 수직선인지 확인 (x 좌표 차이가 작음)
            if abs(x1 - x2) < 10:
                lon_lines.append((x1, y1, x2, y2))
    
    print(f"  그리드 라인 감지: 위도선 {len(lat_lines)}개, 경도선 {len(lon_lines)}개")
    
    return {
        'lat_lines': lat_lines,
        'lon_lines': lon_lines
    }


def find_grid_labels_from_pdf(
    pdf_path: str,
    page_index: int,
    image_size: Tuple[int, int],
) -> Dict[str, List[Tuple[float, int, int]]]:
    """
    PDF 해당 페이지 텍스트에서 그리드 라벨(N20, E150 등)을 추출하고
    bbox를 이미지 픽셀 좌표로 변환. Vision API 없이 pdfplumber만 사용.
    
    Args:
        pdf_path: PDF 파일 경로
        page_index: 0-based 페이지 번호
        image_size: (width, height) 픽셀
        
    Returns:
        {'lat_labels': [(lat_value, x_px, y_px), ...], 'lon_labels': [(lon_value, x_px, y_px), ...]}
    """
    lat_labels = []
    lon_labels = []
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            if page_index < 0 or page_index >= len(pdf.pages):
                return {'lat_labels': [], 'lon_labels': []}
            page = pdf.pages[page_index]
            img_w, img_h = image_size
            page_w = float(page.width)
            page_h = float(page.height)
            scale_x = img_w / page_w if page_w else 1.0
            scale_y = img_h / page_h if page_h else 1.0

            words = page.extract_words()
            if not words:
                return {'lat_labels': [], 'lon_labels': []}

            lat_pattern = re.compile(r'^([NS])(\d{1,2})$', re.IGNORECASE)
            lon_pattern = re.compile(r'^([EW])(\d{1,3})$', re.IGNORECASE)

            for w in words:
                text = (w.get('text') or '').strip().upper()
                x0 = float(w.get('x0', 0))
                top = float(w.get('top', 0))
                x1 = float(w.get('x1', x0))
                bottom = float(w.get('bottom', top))
                cx_pt = (x0 + x1) / 2
                cy_pt = (top + bottom) / 2
                x_px = int(cx_pt * scale_x)
                y_px = int(cy_pt * scale_y)

                m = lat_pattern.match(text)
                if m:
                    deg = int(m.group(2))
                    lat_val = deg if m.group(1) == 'N' else -deg
                    lat_labels.append((lat_val, x_px, y_px))
                    continue
                m = lon_pattern.match(text)
                if m:
                    deg = int(m.group(2))
                    lon_val = deg if m.group(1) == 'E' else -deg
                    lon_labels.append((lon_val, x_px, y_px))
    except Exception as e:
        print(f"  ⚠️ PDF 그리드 라벨 추출 실패: {e}")
    return {'lat_labels': lat_labels, 'lon_labels': lon_labels}


def find_grid_labels(image: Image.Image) -> Dict[str, List[Tuple[float, int, int]]]:
    """
    [미사용] 차트 이미지에서 그리드 라벨을 Google Cloud Vision OCR로 찾습니다.
    Vision API 이전 실패 이력으로 인해 차트 파이프라인에서는 호출하지 않습니다.
    그리드는 find_grid_labels_from_pdf(pdf_path, page_index, image_size) 또는 waypoint 기본 변환만 사용.
    
    Args:
        image: PIL Image 객체
        
    Returns:
        {
            'lat_labels': [(lat_value, x, y), ...],  # 위도 값과 위치
            'lon_labels': [(lon_value, x, y), ...]     # 경도 값과 위치
        }
    """
    try:
        from google.cloud import vision
        from google.cloud.vision_v1 import types
        import os
        from pathlib import Path
        import io
        
        # Vision API 인증 확인
        credentials_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
        if not credentials_path:
            return {'lat_labels': [], 'lon_labels': []}
        
        if not os.path.isabs(credentials_path):
            project_root = Path.cwd()
            credentials_path = str(project_root / credentials_path)
            os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = credentials_path
        
        client = vision.ImageAnnotatorClient()
        
        # 이미지를 바이트로 변환
        img_byte_arr = io.BytesIO()
        image.save(img_byte_arr, format='PNG')
        img_byte_arr.seek(0)
        content = img_byte_arr.getvalue()
        
        # Vision API TEXT_DETECTION
        image_vision = types.Image(content=content)
        response = client.text_detection(image=image_vision)
        texts = response.text_annotations
        
        if not texts:
            return {'lat_labels': [], 'lon_labels': []}
        
        lat_labels = []
        lon_labels = []
        
        # 위도/경도 패턴
        lat_pattern = re.compile(r'([NS])(\d{1,2})')
        lon_pattern = re.compile(r'([EW])(\d{1,3})')
        
        for text in texts[1:]:  # 첫 번째는 전체 텍스트이므로 제외
            description = text.description.strip().upper()
            
            # 위도 라벨 찾기 (N10, S20, S30 등)
            lat_match = lat_pattern.match(description)
            if lat_match:
                dir_char = lat_match.group(1)
                deg = int(lat_match.group(2))
                lat_value = deg if dir_char == 'N' else -deg
                
                # 텍스트 위치
                vertices = text.bounding_poly.vertices
                if vertices:
                    valid_vertices = [v for v in vertices if hasattr(v, 'x') and hasattr(v, 'y')]
                    if valid_vertices:
                        x = int(sum(v.x for v in valid_vertices) / len(valid_vertices))
                        y = int(sum(v.y for v in valid_vertices) / len(valid_vertices))
                        lat_labels.append((lat_value, x, y))
            
            # 경도 라벨 찾기 (E150, 180, W150 등)
            lon_match = lon_pattern.match(description)
            if lon_match:
                dir_char = lon_match.group(1)
                deg = int(lon_match.group(2))
                lon_value = deg if dir_char == 'E' else -deg
                
                # 180도는 특별 처리
                if '180' in description:
                    lon_value = 180.0
                
                vertices = text.bounding_poly.vertices
                if vertices:
                    valid_vertices = [v for v in vertices if hasattr(v, 'x') and hasattr(v, 'y')]
                    if valid_vertices:
                        x = int(sum(v.x for v in valid_vertices) / len(valid_vertices))
                        y = int(sum(v.y for v in valid_vertices) / len(valid_vertices))
                        lon_labels.append((lon_value, x, y))
        
        print(f"  그리드 라벨 감지: 위도 {len(lat_labels)}개, 경도 {len(lon_labels)}개")
        
        return {
            'lat_labels': lat_labels,
            'lon_labels': lon_labels
        }
        
    except Exception as e:
        print(f"  ⚠️ 그리드 라벨 OCR 실패: {e}")
        return {'lat_labels': [], 'lon_labels': []}


def georeference_chart(image: Image.Image,
                      waypoints_with_coords: List[Dict],
                      pdf_path: Optional[str] = None,
                      page_index: Optional[int] = None) -> Optional[Dict]:
    """
    차트 이미지를 georeferencing하여 위/경도 좌표를 픽셀 좌표로 변환하는 매핑을 생성합니다.
    pdf_path와 page_index가 주어지면 Vision 대신 pdfplumber로 그리드 라벨 추출을 시도합니다.
    
    Args:
        image: PIL Image 객체
        waypoints_with_coords: Flight Plan에서 추출한 waypoint 좌표 리스트
        pdf_path: PDF 경로 (선택, ASC/Cross 페이지와 일치할 때 권장)
        page_index: 0-based 페이지 번호 (선택)
        
    Returns:
        {
            'lat_to_y': lambda lat: y,  # 위도를 y 픽셀로 변환
            'lon_to_x': lambda lon: x,   # 경도를 x 픽셀로 변환
            'y_to_lat': lambda y: lat,   # y 픽셀을 위도로 변환
            'x_to_lon': lambda x: lon    # x 픽셀을 경도로 변환
        }
    """
    img_width, img_height = image.size

    # 그리드 라벨: PDF 텍스트(pdfplumber)만 사용 (Google Vision API는 사용하지 않음 — 이전 실패 이력)
    lat_labels = []
    lon_labels = []
    if pdf_path is not None and page_index is not None:
        grid_from_pdf = find_grid_labels_from_pdf(pdf_path, page_index, (img_width, img_height))
        lat_labels = grid_from_pdf.get('lat_labels', [])
        lon_labels = grid_from_pdf.get('lon_labels', [])
        if lat_labels or lon_labels:
            print(f"  그리드 라벨(PDF): 위도 {len(lat_labels)}개, 경도 {len(lon_labels)}개")
    if not lat_labels or not lon_labels:
        print("  ⚠️ 그리드 라벨을 찾을 수 없습니다. waypoint 범위로 기본 변환 사용")
        # 기본 변환 (waypoint 좌표 범위 사용)
        if waypoints_with_coords:
            lats = [wp['lat'] for wp in waypoints_with_coords if wp.get('lat') is not None]
            lons = [wp['lon'] for wp in waypoints_with_coords if wp.get('lon') is not None]
            
            if lats and lons:
                min_lat, max_lat = min(lats), max(lats)
                min_lon, max_lon = min(lons), max(lons)
                
                # 간단한 선형 변환
                def lat_to_y(lat):
                    return int(img_height * (1 - (lat - min_lat) / (max_lat - min_lat)))
                
                def lon_to_x(lon):
                    return int(img_width * (lon - min_lon) / (max_lon - min_lon))
                
                def y_to_lat(y):
                    return min_lat + (1 - y / img_height) * (max_lat - min_lat)
                
                def x_to_lon(x):
                    return min_lon + (x / img_width) * (max_lon - min_lon)
                
                return {
                    'lat_to_y': lat_to_y,
                    'lon_to_x': lon_to_x,
                    'y_to_lat': y_to_lat,
                    'x_to_lon': x_to_lon
                }
        
        return None
    
    # 그리드 라벨을 사용한 정확한 georeferencing
    # 위도 라벨을 y 좌표로 정렬
    lat_labels_sorted = sorted(lat_labels, key=lambda x: x[2])  # y 좌표로 정렬
    lon_labels_sorted = sorted(lon_labels, key=lambda x: x[1])  # x 좌표로 정렬
    
    # 선형 보간을 위한 함수 생성
    if len(lat_labels_sorted) >= 2:
        lat_values = [label[0] for label in lat_labels_sorted]
        lat_y_coords = [label[2] for label in lat_labels_sorted]
        
        def lat_to_y(lat):
            if lat <= lat_values[0]:
                return lat_y_coords[0]
            if lat >= lat_values[-1]:
                return lat_y_coords[-1]
            
            # 선형 보간
            for i in range(len(lat_values) - 1):
                if lat_values[i] <= lat <= lat_values[i + 1]:
                    ratio = (lat - lat_values[i]) / (lat_values[i + 1] - lat_values[i])
                    return int(lat_y_coords[i] + ratio * (lat_y_coords[i + 1] - lat_y_coords[i]))
            return lat_y_coords[0]
        
        def y_to_lat(y):
            if y <= lat_y_coords[0]:
                return lat_values[0]
            if y >= lat_y_coords[-1]:
                return lat_values[-1]
            
            for i in range(len(lat_y_coords) - 1):
                if lat_y_coords[i] <= y <= lat_y_coords[i + 1]:
                    ratio = (y - lat_y_coords[i]) / (lat_y_coords[i + 1] - lat_y_coords[i])
                    return lat_values[i] + ratio * (lat_values[i + 1] - lat_values[i])
            return lat_values[0]
    else:
        # 라벨이 하나만 있으면 기본 변환 사용
        def lat_to_y(lat):
            return img_height // 2
        
        def y_to_lat(y):
            return lat_labels_sorted[0][0] if lat_labels_sorted else 0.0
    
    if len(lon_labels_sorted) >= 2:
        lon_values = [label[0] for label in lon_labels_sorted]
        lon_x_coords = [label[1] for label in lon_labels_sorted]
        
        def lon_to_x(lon):
            if lon <= lon_values[0]:
                return lon_x_coords[0]
            if lon >= lon_values[-1]:
                return lon_x_coords[-1]
            
            for i in range(len(lon_values) - 1):
                if lon_values[i] <= lon <= lon_values[i + 1]:
                    ratio = (lon - lon_values[i]) / (lon_values[i + 1] - lon_values[i])
                    return int(lon_x_coords[i] + ratio * (lon_x_coords[i + 1] - lon_x_coords[i]))
            return lon_x_coords[0]
        
        def x_to_lon(x):
            if x <= lon_x_coords[0]:
                return lon_values[0]
            if x >= lon_x_coords[-1]:
                return lon_values[-1]
            
            for i in range(len(lon_x_coords) - 1):
                if lon_x_coords[i] <= x <= lon_x_coords[i + 1]:
                    ratio = (x - lon_x_coords[i]) / (lon_x_coords[i + 1] - lon_x_coords[i])
                    return lon_values[i] + ratio * (lon_values[i + 1] - lon_values[i])
            return lon_values[0]
    else:
        def lon_to_x(lon):
            return img_width // 2
        
        def x_to_lon(x):
            return lon_labels_sorted[0][0] if lon_labels_sorted else 0.0
    
    return {
        'lat_to_y': lat_to_y,
        'lon_to_x': lon_to_x,
        'y_to_lat': y_to_lat,
        'x_to_lon': x_to_lon
    }


def reconstruct_route(image: Image.Image, 
                     waypoints_with_coords: List[Dict],
                     georef: Dict) -> List[Tuple[int, int]]:
    """
    Waypoint 좌표를 사용하여 차트 위에 항로를 재구성합니다.
    
    Args:
        image: PIL Image 객체
        waypoints_with_coords: Flight Plan에서 추출한 waypoint 좌표 리스트
        georef: Georeferencing 변환 함수들
        
    Returns:
        [(x1, y1), (x2, y2), ...] - 항로의 픽셀 좌표 리스트
    """
    route_points = []
    
    for wp in waypoints_with_coords:
        lat = wp.get('lat')
        lon = wp.get('lon')
        
        if lat is not None and lon is not None:
            x = georef['lon_to_x'](lon)
            y = georef['lat_to_y'](lat)
            route_points.append((x, y))
    
    return route_points


def is_similar_color(color1: Tuple[int, int, int], color2: Tuple[int, int, int], tolerance: int = 40) -> bool:
    """두 색상이 유사한지 확인"""
    try:
        return all(abs(int(c1) - int(c2)) <= tolerance for c1, c2 in zip(color1, color2))
    except (ValueError, TypeError):
        return False


def analyze_turbulence_along_route(image: Image.Image,
                                  route_points: List[Tuple[int, int]],
                                  georef: Dict,
                                  waypoints: List[Dict],
                                  path_color_hex: str = None) -> Dict[str, List[Dict]]:
    """
    재구성된 항로의 linear line을 따라가면서 경로 색상이 turbulence 색상으로 변하는 구간을 찾습니다.
    
    Args:
        image: PIL Image 객체
        route_points: 항로의 픽셀 좌표 리스트
        georef: Georeferencing 변환 함수들
        waypoints: Waypoint 정보 리스트 (좌표 포함)
        path_color_hex: 경로 색상 HEX 코드 (기본값: #df485f)
        
    Returns:
        {
            'light': [
                {
                    'start_waypoint': 'KARM',
                    'end_waypoint': 'EGZIG',
                    'start_x': 100,
                    'end_x': 200,
                    'start_lat': -33.5,
                    'end_lat': -32.0,
                    'start_lon': 150.0,
                    'end_lon': 151.0
                },
                ...
            ],
            'moderate': [...],
            'severe': [...]
        }
    """
    img_array = np.array(image)
    if img_array.shape[2] == 4:
        img_array = cv2.cvtColor(img_array, cv2.COLOR_RGBA2RGB)
    
    # 경로 색상 RGB (ASC 차트는 파란색, 크로스 섹션은 빨간색)
    # 파란색 경로도 감지하도록 수정
    if path_color_hex is None:
        # ASC 차트인 경우 파란색 경로 시도
        path_colors = [
            (0, 0, 255),  # 파란색 (BGR)
            (223, 72, 95)  # 빨간색 #df485f (RGB)
        ]
    else:
        path_rgb = tuple(int(path_color_hex[i:i+2], 16) for i in (1, 3, 5))
        path_colors = [path_rgb]
    
    tolerance = 40
    
    # 실제 차트에서 경로 색상 선을 먼저 찾기 (파란색 또는 빨간색)
    path_mask = np.zeros((img_array.shape[0], img_array.shape[1]), dtype=np.uint8)
    
    for path_rgb in path_colors:
        path_lower = np.array([
            max(0, path_rgb[0] - tolerance),
            max(0, path_rgb[1] - tolerance),
            max(0, path_rgb[2] - tolerance)
        ])
        path_upper = np.array([
            min(255, path_rgb[0] + tolerance),
            min(255, path_rgb[1] + tolerance),
            min(255, path_rgb[2] + tolerance)
        ])
        path_mask_temp = cv2.inRange(img_array, path_lower, path_upper)
        path_mask = cv2.bitwise_or(path_mask, path_mask_temp)
    
    # 경로 선 추출 (HoughLinesP 사용)
    edges = cv2.Canny(path_mask, 30, 100)
    lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=30, minLineLength=30, maxLineGap=20)
    
    # 경로 점들 수집
    path_points_set = set()
    if lines is not None:
        for line in lines:
            x1, y1, x2, y2 = line[0]
            num_points = max(abs(x2-x1), abs(y2-y1))
            for i in range(num_points + 1):
                if num_points > 0:
                    x = int(x1 + (x2-x1) * i / num_points)
                    y = int(y1 + (y2-y1) * i / num_points)
                    if 0 <= x < img_array.shape[1] and 0 <= y < img_array.shape[0]:
                        path_points_set.add((x, y))
    
    path_points_detected = sorted(list(path_points_set), key=lambda p: p[0])  # x 좌표로 정렬
    
    print(f"    실제 차트에서 경로 색상 점 {len(path_points_detected)}개 감지")
    
    if len(path_points_detected) == 0:
        print("    ⚠️ 차트에서 경로 색상을 찾을 수 없습니다. 재구성된 경로 사용")
        # 재구성된 경로 사용 (fallback)
        path_points_detected = route_points
    
    # 경로 점들을 waypoint와 매핑하기 위해 샘플링
    path_samples = []  # [(x, y, waypoint_index, distance_ratio), ...]
    
    # 재구성된 route_points와 실제 감지된 경로를 매칭
    for idx, (x, y) in enumerate(path_points_detected):
        # 가장 가까운 route_point 찾기
        min_dist = float('inf')
        closest_wp_idx = 0
        closest_ratio = 0.0
        
        for i in range(len(route_points) - 1):
            x1, y1 = route_points[i]
            x2, y2 = route_points[i + 1]
            
            # 선분에서 가장 가까운 점 찾기
            dx = x2 - x1
            dy = y2 - y1
            if dx == 0 and dy == 0:
                dist = np.sqrt((x - x1)**2 + (y - y1)**2)
                if dist < min_dist:
                    min_dist = dist
                    closest_wp_idx = i
                    closest_ratio = 0.0
            else:
                t = max(0, min(1, ((x - x1) * dx + (y - y1) * dy) / (dx*dx + dy*dy)))
                px = x1 + t * dx
                py = y1 + t * dy
                dist = np.sqrt((x - px)**2 + (y - py)**2)
                if dist < min_dist:
                    min_dist = dist
                    closest_wp_idx = i
                    closest_ratio = t
        
        if min_dist < 100:  # 100 픽셀 이내면 매핑
            pixel_color = tuple(img_array[y, x])
            # 경로 색상인지 확인
            is_path_color = False
            for path_rgb in path_colors:
                if is_similar_color(pixel_color, path_rgb, tolerance):
                    is_path_color = True
                    break
            if is_path_color:
                path_samples.append((x, y, closest_wp_idx, closest_ratio, pixel_color))
    
    print(f"    경로 색상 점 {len(path_samples)}개를 waypoint와 매핑")
    
    # 재구성된 경로 선을 따라 샘플링 (항상 사용 - 더 정확함)
    # 재구성된 route_points를 직접 사용하여 경로 선 생성
    # 성능을 위해 적절한 간격으로 샘플링
    path_samples_from_route = []
    for i in range(len(route_points) - 1):
        x1, y1 = route_points[i]
        x2, y2 = route_points[i + 1]
        # 거리에 따라 샘플링 간격 조정 (최대 50개 샘플)
        distance = np.sqrt((x2-x1)**2 + (y2-y1)**2)
        num_samples = min(max(int(distance / 10), 5), 50)  # 10픽셀당 1개, 최소 5개, 최대 50개
        for j in range(num_samples + 1):
            ratio = j / num_samples if num_samples > 0 else 0
            x = int(x1 + (x2 - x1) * ratio)
            y = int(y1 + (y2 - y1) * ratio)
            if 0 <= x < img_array.shape[1] and 0 <= y < img_array.shape[0]:
                pixel_color = tuple(img_array[y, x])
                path_samples_from_route.append((x, y, i, ratio, pixel_color))
    
    # 재구성된 경로를 항상 사용 (더 정확함)
    path_samples = path_samples_from_route
    print(f"    재구성된 경로에서 {len(path_samples)}개 점 샘플링 (사용)")
    
    # 경로를 따라가면서 색상 변화 감지
    result = {
        'light': [],
        'moderate': [],
        'severe': []
    }
    
    # 각 터뷸런스 타입별로 색상 변화 구간 찾기
    for turb_type in ['light', 'moderate', 'severe']:
        turb_color = TURBULENCE_COLORS[turb_type]
        turb_indices = []
        
        # JPG 압축을 고려하여 HSV 색공간 사용 (더 유연한 색상 매칭)
        # RGB를 HSV로 변환
        hsv_img = cv2.cvtColor(img_array, cv2.COLOR_RGB2HSV)
        
        # RGB 색상을 HSV로 변환
        turb_rgb = np.uint8([[turb_color]])
        turb_hsv = cv2.cvtColor(turb_rgb, cv2.COLOR_RGB2HSV)[0][0]
        
        # HSV에서 색상 범위 설정
        # H (Hue): 색상 - 넓은 범위 허용 (JPG 압축 고려)
        # S (Saturation): 채도 - 높은 채도만 (선명한 색상)
        # V (Value): 밝기 - 넓은 범위 허용
        
        if turb_type == 'light':  # Cyan
            # 실제 차트: H=90, S=185, V=242 (평균: H=89.9, S=197.5, V=248.3)
            # JPG 압축 고려하되 더 정확한 범위: H ±5, S ±60, V ±20
            hsv_lower = np.array([85, 140, 230])  # H: 85-95, S: 140-255, V: 230-255
            hsv_upper = np.array([95, 255, 255])
            turb_mask = cv2.inRange(hsv_img, hsv_lower, hsv_upper)
        elif turb_type == 'moderate':  # Yellow
            # 실제 차트: H=30, S=226, V=253 (평균: H=30.0, S=212.1, V=252.1)
            # JPG 압축 고려하되 더 정확한 범위: H ±5, S ±60, V ±20
            hsv_lower = np.array([25, 155, 235])  # H: 25-35, S: 155-255, V: 235-255
            hsv_upper = np.array([35, 255, 255])
            turb_mask = cv2.inRange(hsv_img, hsv_lower, hsv_upper)
        else:  # severe - Red
            # 실제 차트: H=1, S=195, V=224
            # Red: H 0-10 또는 170-180 (빨간색은 H 범위가 넓음)
            # JPG 압축 고려: H ±10, S ±50, V ±50
            hsv_lower1 = np.array([0, 145, 174])  # H: 0-11, S: 145-255, V: 174-255
            hsv_upper1 = np.array([11, 255, 255])
            hsv_lower2 = np.array([170, 145, 174])  # H: 170-180
            hsv_upper2 = np.array([180, 255, 255])
            
            # 두 범위를 합침
            mask1 = cv2.inRange(hsv_img, hsv_lower1, hsv_upper1)
            mask2 = cv2.inRange(hsv_img, hsv_lower2, hsv_upper2)
            turb_mask = cv2.bitwise_or(mask1, mask2)
        turb_pixel_count = np.sum(turb_mask > 0)
        
        # 디버깅: 마스크 생성 확인
        if turb_pixel_count == 0 and turb_type == 'light':
            # 샘플 픽셀 확인
            sample_y, sample_x = img_array.shape[0] // 2, img_array.shape[1] // 2
            sample_pixel_rgb = tuple(img_array[sample_y, sample_x])
            sample_pixel_hsv = tuple(hsv_img[sample_y, sample_x])
            print(f"      디버깅: 샘플 픽셀 (중앙) RGB: {sample_pixel_rgb}, HSV: {sample_pixel_hsv}")
            if turb_type == 'light':
                print(f"      디버깅: {turb_type} HSV 범위: {hsv_lower} ~ {hsv_upper}")
        
        # 경로 선을 따라가면서 turbulence 심볼이 근처에 있는지 확인
        # ASC 차트는 심볼 형태이므로 경로에서 30픽셀 이내에 turbulence 색상이 있으면 해당 구간으로 판단
        # 범위를 줄여서 더 정확한 감지
        path_nearby_range = 30
        
        # 경로 점을 순회하면서 주변 turbulence 확인
        # 성능을 위해 샘플링 간격 조정하되, 충분한 점 확인
        sample_step = max(1, len(path_samples) // 200)  # 최대 200개 점 확인
        
        checked_count = 0
        for idx in range(0, len(path_samples), sample_step):
            x, y, wp_idx, dist_ratio, path_pixel = path_samples[idx]
            checked_count += 1
            
            # 경로 점 주변 영역에서 turbulence 확인
            # 효율성을 위해 간격을 두고 확인하되, 충분히 확인
            check_step = 2  # 2픽셀 간격 (더 촘촘하게)
            found_turb = False
            
            for dy in range(-path_nearby_range, path_nearby_range + 1, check_step):
                for dx in range(-path_nearby_range, path_nearby_range + 1, check_step):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < img_array.shape[1] and 0 <= ny < img_array.shape[0]:
                        # turbulence 마스크 확인
                        if turb_mask[ny, nx] > 0:
                            # 해당 경로 점 인덱스 추가
                            if idx not in turb_indices:
                                turb_indices.append(idx)
                            found_turb = True
                            break
                if found_turb:
                    break
        
        print(f"      {turb_type} mask: {turb_pixel_count}개 픽셀, 경로 점 {checked_count}개 확인, {len(turb_indices)}개 지점 감지")
        
        print(f"    {turb_type} turbulence 색상 감지: {len(turb_indices)}개 지점")
        
        if not turb_indices:
            continue
        
        # 연속된 구간 찾기
        segments = []
        if turb_indices:
            current_segment_start = turb_indices[0]
            
            for i in range(1, len(turb_indices)):
                if turb_indices[i] - turb_indices[i-1] > 10:  # 10개 이상 떨어지면 새 구간
                    segments.append((current_segment_start, turb_indices[i-1]))
                    current_segment_start = turb_indices[i]
            
            # 마지막 구간 추가
            segments.append((current_segment_start, turb_indices[-1]))
        
        # 각 구간을 waypoint로 변환
        for seg_start_idx, seg_end_idx in segments:
            start_x, start_y, start_wp_idx, start_dist, _ = path_samples[seg_start_idx]
            end_x, end_y, end_wp_idx, end_dist, _ = path_samples[seg_end_idx]
            
            # 시작/종료 waypoint 찾기
            start_wp = waypoints[min(start_wp_idx, len(waypoints) - 1)]
            
            # 종료 waypoint는 다음 waypoint까지 고려
            if end_wp_idx < len(waypoints) - 1:
                if end_dist > 0.5:  # 중간 지점을 넘어섰으면
                    end_wp = waypoints[end_wp_idx + 1]
                else:
                    end_wp = waypoints[end_wp_idx]
            else:
                end_wp = waypoints[min(end_wp_idx, len(waypoints) - 1)]
            
            start_wp_name = start_wp['waypoint']
            end_wp_name = end_wp['waypoint']
            
            # 좌표 변환 (픽셀 -> 위경도)
            start_lat = georef['y_to_lat'](start_y)
            start_lon = georef['x_to_lon'](start_x)
            end_lat = georef['y_to_lat'](end_y)
            end_lon = georef['x_to_lon'](end_x)
            
            result[turb_type].append({
                'start_waypoint': start_wp_name,
                'end_waypoint': end_wp_name,
                'start_x': start_x,
                'end_x': end_x,
                'start_lat': start_lat,
                'end_lat': end_lat,
                'start_lon': start_lon,
                'end_lon': end_lon
            })
    
    return result


def analyze_chart_with_coordinates(pdf_path: str, chart_image: Image.Image) -> Dict:
    """
    Flight Plan 좌표를 사용하여 차트를 분석합니다.
    
    ⚠️ 주의: 현재 ASC 차트 분석은 오류가 많아 비활성화되어 있습니다.
    비행 분석 시에는 이 함수가 호출되지 않도록 주의하세요.
    
    Args:
        pdf_path: Flight Plan PDF 파일 경로
        chart_image: 차트 이미지 (PIL Image)
        
    Returns:
        {
            'waypoints': [...],
            'route_points': [(x, y), ...],
            'turbulence': {
                'light': [...],
                'moderate': [...],
                'severe': [...]
            }
        }
    """
    # ASC 차트 분석 비활성화 (오류가 많아서)
    print("⚠️ ASC 차트 분석이 비활성화되어 있습니다.")
    return {}
    
    # 아래 코드는 현재 실행되지 않음 (비활성화됨)
    print("=== Flight Plan 좌표 기반 차트 분석 ===")
    
    # 1. Flight Plan에서 좌표 추출
    print("\n1. Flight Plan에서 좌표 추출 중...")
    waypoints_with_coords = extract_coordinates_from_flight_plan(pdf_path)
    
    if not waypoints_with_coords:
        print("⚠️ 좌표를 추출할 수 없습니다.")
        return {}
    
    print(f"✅ {len(waypoints_with_coords)}개 waypoint 좌표 추출 완료")
    
    # 2. Georeferencing
    print("\n2. 차트 Georeferencing 중...")
    georef = georeference_chart(chart_image, waypoints_with_coords)
    
    if not georef:
        print("⚠️ Georeferencing 실패")
        return {}
    
    print("✅ Georeferencing 완료")
    
    # 3. 항로 재구성
    print("\n3. 항로 재구성 중...")
    route_points = reconstruct_route(chart_image, waypoints_with_coords, georef)
    print(f"✅ {len(route_points)}개 항로 점 생성 완료")
    
    # 4. Turbulence 분석 (구간 단위)
    print("\n4. Turbulence 구간 분석 중...")
    # ASC 차트는 경로 색상이 파란색일 수 있으므로 None으로 전달하여 자동 감지
    turbulence = analyze_turbulence_along_route(chart_image, route_points, georef, waypoints_with_coords, None)
    
    light_segments = len(turbulence['light'])
    moderate_segments = len(turbulence['moderate'])
    severe_segments = len(turbulence['severe'])
    
    print(f"✅ Turbulence 구간 감지: Light={light_segments}개 구간, Moderate={moderate_segments}개 구간, Severe={severe_segments}개 구간")
    
    return {
        'waypoints': waypoints_with_coords,
        'route_points': route_points,
        'turbulence': turbulence,
        'georef': georef
    }

