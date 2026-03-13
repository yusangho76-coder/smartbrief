#!/usr/bin/env python3
"""
SIGWX 차트 분석 개선 모듈
하이브리드 접근법: 이미지 처리 + 좌표 기반 매핑 + Gemini Vision
"""

import re
import logging
import math
from typing import List, Dict, Tuple, Optional
from PIL import Image
import io
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

# pdfplumber 사용
try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False
    pdfplumber = None


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    두 지점 간의 거리를 계산합니다 (Haversine formula, km 단위).
    """
    R = 6371  # 지구 반지름 (km)
    
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    
    return R * c


def point_in_polygon(point: Tuple[float, float], polygon: List[Dict]) -> bool:
    """
    점이 다각형 내부에 있는지 확인합니다 (Ray casting algorithm).
    
    Args:
        point: (latitude, longitude) 튜플
        polygon: [{"lat": float, "lon": float}, ...] 형식의 좌표 리스트
    
    Returns:
        True if point is inside polygon
    """
    if not polygon or len(polygon) < 3:
        return False
    
    lat, lon = point
    inside = False
    
    j = len(polygon) - 1
    for i in range(len(polygon)):
        pi = polygon[i]
        pj = polygon[j]
        
        if 'lat' in pi and 'lon' in pi:
            xi, yi = pi['lat'], pi['lon']
            xj, yj = pj['lat'], pj['lon']
        else:
            # coords 형식인 경우
            xi, yi = pi.get('lat', pi.get('y', 0)), pi.get('lon', pi.get('x', 0))
            xj, yj = pj.get('lat', pj.get('y', 0)), pj.get('lon', pj.get('x', 0))
        
        if ((yi > lon) != (yj > lon)) and (lat < (xj - xi) * (lon - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    
    return inside


def point_near_polygon(point: Tuple[float, float], polygon: List[Dict], threshold_km: float = 100) -> bool:
    """
    점이 다각형 근처에 있는지 확인합니다 (threshold 내).
    
    Args:
        point: (latitude, longitude) 튜플
        polygon: 좌표 리스트
        threshold_km: 임계 거리 (km)
    
    Returns:
        True if point is within threshold of polygon
    """
    if not polygon:
        return False
    
    lat, lon = point
    
    # 다각형의 모든 점과의 최소 거리 계산
    min_distance = float('inf')
    
    for coord in polygon:
        if 'lat' in coord and 'lon' in coord:
            coord_lat, coord_lon = coord['lat'], coord['lon']
        else:
            coord_lat = coord.get('lat', coord.get('y', 0))
            coord_lon = coord.get('lon', coord.get('x', 0))
        
        distance = haversine_distance(lat, lon, coord_lat, coord_lon)
        min_distance = min(min_distance, distance)
    
    return min_distance <= threshold_km


def match_sigmet_to_waypoints(sigmets: List[Dict], waypoints: List[Dict]) -> Dict[str, List[Dict]]:
    """
    SIGMET 데이터와 waypoint를 매칭합니다.
    
    Args:
        sigmets: SIGMET 데이터 리스트
        waypoints: [{"name": str, "lat": float, "lon": float, ...}, ...] 형식
    
    Returns:
        {waypoint_name: [matched_sigmet, ...]} 딕셔너리
    """
    matches = {}
    
    for waypoint in waypoints:
        wp_name = waypoint.get('name') or waypoint.get('waypoint', '')
        wp_lat = waypoint.get('lat')
        wp_lon = waypoint.get('lon')
        
        if wp_lat is None or wp_lon is None:
            continue
        
        matches[wp_name] = []
        
        for sigmet in sigmets:
            # SIGMET의 좌표 정보 추출
            coords = sigmet.get('coords', [])
            if not coords:
                continue
            
            # 다각형 내부 또는 근처에 있는지 확인
            is_inside = point_in_polygon((wp_lat, wp_lon), coords)
            is_near = point_near_polygon((wp_lat, wp_lon), coords, threshold_km=100)
            
            if is_inside or is_near:
                matches[wp_name].append({
                    'sigmet': sigmet,
                    'inside': is_inside,
                    'near': is_near and not is_inside
                })
    
    return matches


def find_sigwx_pages(pdf_path: str) -> List[int]:
    """
    PDF에서 SIGWX 차트가 있는 페이지 번호를 찾습니다.
    
    Args:
        pdf_path: PDF 파일 경로
        
    Returns:
        SIGWX 차트가 있는 페이지 번호 리스트 (0-based index)
    """
    sigwx_pages = []
    
    if not PDFPLUMBER_AVAILABLE:
        logger.warning("pdfplumber를 사용할 수 없습니다.")
        return sigwx_pages
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                page_text = page.extract_text()
                if page_text:
                    # SIGWX 키워드 찾기
                    if re.search(r'SIGWX', page_text, re.IGNORECASE):
                        sigwx_pages.append(i)
                        logger.info(f"Page {i+1}: SIGWX 차트 발견")
    except Exception as e:
        logger.warning(f"PDF 파일을 읽는 중 오류가 발생했습니다: {e}")
    
    return sigwx_pages

# OpenCV 사용 (정확한 색상 추출용)
try:
    import cv2
    import numpy as np
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False
    cv2 = None
    np = None

# pdf2image 사용
try:
    from pdf2image import convert_from_path
    PDF2IMAGE_AVAILABLE = True
except ImportError:
    PDF2IMAGE_AVAILABLE = False

# Gemini API 사용
try:
    import google.generativeai as genai
    from dotenv import load_dotenv
    import os
    load_dotenv()
    GEMINI_AVAILABLE = True
    
    api_key = os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
    if api_key:
        genai.configure(api_key=api_key)
        try:
            gemini_model = genai.GenerativeModel('gemini-2.5-flash-lite')
        except:
            try:
                gemini_model = genai.GenerativeModel('gemini-pro-vision')
            except:
                gemini_model = None
    else:
        GEMINI_AVAILABLE = False
        gemini_model = None
except ImportError:
    GEMINI_AVAILABLE = False
    genai = None
    gemini_model = None


def get_waypoint_coordinates_with_timing(flight_data: List[Dict]) -> List[Dict]:
    """
    Flight Plan 데이터에서 waypoint 좌표와 시간 정보를 추출
    
    Args:
        flight_data: extract_flight_data_from_pdf에서 추출한 Flight Plan 데이터
    
    Returns:
        [
            {
                'waypoint': 'KATCH',
                'lat': 37.5,
                'lon': 126.5,
                'estimated_time': '0332Z',
                'actm': '01.28',
                'fl': '350'
            },
            ...
        ]
    """
    try:
        from src.nav_data_loader import NavDataLoader
        
        nav_loader = NavDataLoader()
        nav_loader.load_nav_data()
        
        waypoints_with_coords = []
        for row in flight_data:
            wp_name = row.get('Waypoint', '')
            if wp_name and wp_name != 'N/A':
                coords = nav_loader.get_waypoint_coordinates(wp_name)
                if coords:
                    waypoints_with_coords.append({
                        'waypoint': wp_name,
                        'lat': coords[0],
                        'lon': coords[1],
                        'estimated_time': row.get('Estimated Time (Z)', 'N/A'),
                        'actm': row.get('ACTM (Accumulated Time)', 'N/A'),
                        'fl': row.get('FL (Flight Level)', 'N/A'),
                        'sr': row.get('SR (Shear Rate)', 'N/A')
                    })
                else:
                    # 좌표를 찾지 못한 경우도 추가 (나중에 처리)
                    waypoints_with_coords.append({
                        'waypoint': wp_name,
                        'lat': None,
                        'lon': None,
                        'estimated_time': row.get('Estimated Time (Z)', 'N/A'),
                        'actm': row.get('ACTM (Accumulated Time)', 'N/A'),
                        'fl': row.get('FL (Flight Level)', 'N/A'),
                        'sr': row.get('SR (Shear Rate)', 'N/A')
                    })
        
        return waypoints_with_coords
    except Exception as e:
        logger.error(f"Waypoint 좌표 추출 실패: {e}", exc_info=True)
        return []


def extract_page_as_image(pdf_path: str, page_num: int) -> Optional[Image.Image]:
    """
    PDF 페이지를 이미지로 추출합니다.
    
    Args:
        pdf_path: PDF 파일 경로
        page_num: 페이지 번호 (0-based)
    
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
        logger.warning(f"페이지 이미지 추출 중 오류: {e}")
        return None


def extract_flight_path_from_sigwx(image: Image.Image) -> List[Tuple[int, int]]:
    """
    SIGWX 차트 이미지에서 비행 경로(검은색 점선) 추출
    
    Args:
        image: PIL Image 객체
    
    Returns:
        경로상의 픽셀 좌표 리스트 [(x, y), ...]
    """
    if not OPENCV_AVAILABLE:
        return []
    
    try:
        img_array = np.array(image)
        
        # RGBA를 RGB로 변환
        if img_array.shape[2] == 4:
            img_array = cv2.cvtColor(img_array, cv2.COLOR_RGBA2RGB)
        
        # 검은색 점선 감지 (RGB 값이 낮고, 점선 패턴)
        # 검은색 범위: R, G, B 모두 0-50 사이
        black_lower = np.array([0, 0, 0])
        black_upper = np.array([50, 50, 50])
        
        black_mask = cv2.inRange(img_array, black_lower, black_upper)
        
        # 점선 패턴 감지 (연속된 선이 아닌 점선)
        # 모폴로지 연산으로 점선 연결
        kernel = np.ones((2, 2), np.uint8)
        black_mask = cv2.morphologyEx(black_mask, cv2.MORPH_CLOSE, kernel)
        
        # 경로 추출 (HoughLinesP 사용)
        edges = cv2.Canny(black_mask, 30, 100)
        lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=20, 
                                minLineLength=10, maxLineGap=5)
        
        path_points = []
        if lines is not None:
            for line in lines:
                x1, y1, x2, y2 = line[0]
                # 선상의 모든 점 추가
                num_points = max(abs(x2-x1), abs(y2-y1))
                for i in range(num_points + 1):
                    if num_points > 0:
                        x = int(x1 + (x2-x1) * i / num_points)
                        y = int(y1 + (y2-y1) * i / num_points)
                        path_points.append((x, y))
        
        return path_points
    except Exception as e:
        logger.warning(f"비행 경로 추출 중 오류: {e}")
        return []


def extract_weather_phenomena_from_sigwx(image: Image.Image) -> Dict[str, List[Tuple[int, int]]]:
    """
    SIGWX 차트에서 기상 현상을 색상별로 추출
    
    Args:
        image: PIL Image 객체
    
    Returns:
        {
            'mod_turbulence': [(x, y), ...],  # 핑크색 점선
            'sev_turbulence': [(x, y), ...],  # 빨간색 점선
            'cb_clouds': [(x, y), ...],       # 초록색 scalloped line
            'jet_streams': [(x, y), ...]      # 파란색 선
        }
    """
    if not OPENCV_AVAILABLE:
        return {
            'mod_turbulence': [],
            'sev_turbulence': [],
            'cb_clouds': [],
            'jet_streams': []
        }
    
    try:
        img_array = np.array(image)
        
        # RGBA를 RGB로 변환
        if img_array.shape[2] == 4:
            img_array = cv2.cvtColor(img_array, cv2.COLOR_RGBA2RGB)
        
        # 1. MOD Turbulence (핑크색/마젠타색 점선)
        # RGB 범위: R: 200-255, G: 0-100, B: 150-255
        pink_lower = np.array([200, 0, 150])
        pink_upper = np.array([255, 100, 255])
        pink_mask = cv2.inRange(img_array, pink_lower, pink_upper)
        
        # 2. SEV Turbulence (빨간색 점선)
        # RGB 범위: R: 200-255, G: 0-50, B: 0-50
        red_lower = np.array([200, 0, 0])
        red_upper = np.array([255, 50, 50])
        red_mask = cv2.inRange(img_array, red_lower, red_upper)
        
        # 3. CB Clouds (초록색 scalloped line)
        # RGB 범위: R: 0-100, G: 150-255, B: 0-100
        green_lower = np.array([0, 150, 0])
        green_upper = np.array([100, 255, 100])
        green_mask = cv2.inRange(img_array, green_lower, green_upper)
        
        # 4. Jet Streams (파란색 선)
        # RGB 범위: R: 0-100, G: 100-200, B: 200-255
        blue_lower = np.array([0, 100, 200])
        blue_upper = np.array([100, 200, 255])
        blue_mask = cv2.inRange(img_array, blue_lower, blue_upper)
        
        # 각 마스크에서 픽셀 좌표 추출
        def get_pixel_coordinates(mask):
            coords = []
            y_coords, x_coords = np.where(mask > 0)
            for x, y in zip(x_coords, y_coords):
                coords.append((x, y))
            return coords
        
        return {
            'mod_turbulence': get_pixel_coordinates(pink_mask),
            'sev_turbulence': get_pixel_coordinates(red_mask),
            'cb_clouds': get_pixel_coordinates(green_mask),
            'jet_streams': get_pixel_coordinates(blue_mask)
        }
    except Exception as e:
        logger.warning(f"기상 현상 추출 중 오류: {e}")
        return {
            'mod_turbulence': [],
            'sev_turbulence': [],
            'cb_clouds': [],
            'jet_streams': []
        }


def convert_geo_to_image_coords(
    lat: float, 
    lon: float, 
    image_bounds: Dict[str, float],
    image_size: Tuple[int, int]
) -> Tuple[int, int]:
    """
    지리적 좌표를 이미지 픽셀 좌표로 변환
    
    Args:
        lat, lon: 지리적 좌표
        image_bounds: {'min_lat': float, 'max_lat': float, 'min_lon': float, 'max_lon': float}
        image_size: (width, height)
    
    Returns:
        (x, y) 픽셀 좌표
    """
    width, height = image_size
    
    # 위도 변환 (Y 좌표) - 위도는 위에서 아래로 증가하므로 반전
    lat_range = image_bounds['max_lat'] - image_bounds['min_lat']
    if lat_range > 0:
        y = int(height * (1 - (lat - image_bounds['min_lat']) / lat_range))
    else:
        y = height // 2
    
    # 경도 변환 (X 좌표)
    lon_range = image_bounds['max_lon'] - image_bounds['min_lon']
    if lon_range > 0:
        x = int(width * (lon - image_bounds['min_lon']) / lon_range)
    else:
        x = width // 2
    
    return (x, y)


def extract_image_bounds_from_sigwx(page_text: str) -> Dict[str, float]:
    """
    SIGWX 차트 텍스트에서 지리적 범위 추출 (위도/경도 그리드에서)
    
    Args:
        page_text: PDF 페이지 텍스트
    
    Returns:
        {'min_lat': float, 'max_lat': float, 'min_lon': float, 'max_lon': float}
    """
    # 위도 추출 (N40, N20, S30 등)
    lat_pattern = r'([NS])(\d{2})'
    lats = re.findall(lat_pattern, page_text)
    
    # 경도 추출 (100E, 120E, 180E 등)
    lon_pattern = r'(\d{3})([EW])'
    lons = re.findall(lon_pattern, page_text)
    
    # 위도 범위 계산
    lat_values = []
    for direction, value in lats:
        lat_val = int(value)
        if direction == 'S':
            lat_val = -lat_val
        lat_values.append(lat_val)
    
    # 경도 범위 계산
    lon_values = []
    for value, direction in lons:
        lon_val = int(value)
        if direction == 'W':
            lon_val = -lon_val
        lon_values.append(lon_val)
    
    # 기본값 (Asia/Pacific 지역)
    result = {
        'min_lat': -40.0,
        'max_lat': 40.0,
        'min_lon': 100.0,
        'max_lon': 180.0
    }
    
    if lat_values:
        result['min_lat'] = min(lat_values)
        result['max_lat'] = max(lat_values)
    
    if lon_values:
        result['min_lon'] = min(lon_values)
        result['max_lon'] = max(lon_values)
    
    return result


def _sample_route_from_waypoint_coords(
    waypoint_image_coords: List[Dict],
    points_per_segment: int = 40,
) -> List[Tuple[int, int]]:
    """
    Waypoint 이미지 좌표를 이어 만든 경로를 구간당 N개 점으로 샘플링.
    Vision/이미지 경로 추출 실패 시 좌표 기반 경로로 대체할 때 사용.
    """
    path_points = []
    valid = [
        (int(w["image_coords"][0]), int(w["image_coords"][1]))
        for w in waypoint_image_coords
        if w.get("image_coords") and w["image_coords"][0] is not None and w["image_coords"][1] is not None
    ]
    for i in range(len(valid) - 1):
        x1, y1 = valid[i]
        x2, y2 = valid[i + 1]
        n = max(points_per_segment, abs(x2 - x1) // 5, abs(y2 - y1) // 5)
        for j in range(n + 1):
            t = j / n
            path_points.append((int(x1 + t * (x2 - x1)), int(y1 + t * (y2 - y1))))
    if valid:
        path_points.append(valid[-1])
    return path_points


def find_weather_intersections(
    flight_path_points: List[Tuple[int, int]],
    weather_phenomena: Dict[str, List[Tuple[int, int]]],
    waypoint_image_coords: List[Dict],
    threshold: int = 10
) -> Dict[str, List[Dict]]:
    """
    비행 경로와 기상 현상의 교차점을 찾아 waypoint와 매핑
    
    Args:
        flight_path_points: 비행 경로 픽셀 좌표
        weather_phenomena: 기상 현상 픽셀 좌표 딕셔너리
        waypoint_image_coords: Waypoint의 이미지 좌표 리스트
        threshold: 교차점 판단 거리 임계값 (픽셀)
    
    Returns:
        {
            'waypoint_name': [
                {
                    'phenomenon': 'mod_turbulence',
                    'distance': 5,  # 픽셀 거리
                    'waypoint': 'KATCH',
                    'estimated_time': '0332Z',
                    'actm': '01.28'
                },
                ...
            ]
        }
    """
    intersections = {}
    
    for wp_info in waypoint_image_coords:
        wp_name = wp_info['waypoint']
        wp_x, wp_y = wp_info.get('image_coords', (None, None))
        
        if wp_x is None or wp_y is None:
            continue
        
        wp_intersections = []
        
        # 각 기상 현상 타입별로 교차점 찾기
        for phenom_type, phenom_points in weather_phenomena.items():
            if not phenom_points:
                continue
            
            # Waypoint와 가장 가까운 기상 현상 점 찾기
            min_distance = float('inf')
            closest_point = None
            
            for px, py in phenom_points:
                distance = ((wp_x - px) ** 2 + (wp_y - py) ** 2) ** 0.5
                if distance < min_distance:
                    min_distance = distance
                    closest_point = (px, py)
            
            # 임계값 이내: 경로가 있으면 경로 근처일 때만, 없으면 waypoint 근처만으로 교차 인정 (좌표 기반 보조)
            if min_distance <= threshold:
                if flight_path_points:
                    path_distance = min([
                        ((path_x - closest_point[0]) ** 2 + (path_y - closest_point[1]) ** 2) ** 0.5
                        for path_x, path_y in flight_path_points
                    ])
                    if path_distance > threshold * 2:
                        continue
                wp_intersections.append({
                    'phenomenon': phenom_type,
                    'distance': int(min_distance),
                    'waypoint': wp_name,
                    'estimated_time': wp_info.get('estimated_time', 'N/A'),
                    'actm': wp_info.get('actm', 'N/A'),
                    'fl': wp_info.get('fl', 'N/A'),
                    'sr': wp_info.get('sr', 'N/A')
                })

        if wp_intersections:
            intersections[wp_name] = wp_intersections
    
    return intersections


def build_enhanced_sigwx_prompt(
    waypoints_with_coords: List[Dict],
    flight_path_info: str,
    image_bounds: Dict[str, float]
) -> str:
    """
    Waypoint 좌표 정보를 포함한 개선된 프롬프트 생성
    """
    waypoint_info = ""
    for wp in waypoints_with_coords[:50]:  # 처음 50개만
        if wp.get('lat') and wp.get('lon'):
            waypoint_info += f"- {wp['waypoint']}: 위도 {wp['lat']:.2f}°N, 경도 {wp['lon']:.2f}°E, 예상 시간: {wp.get('estimated_time', 'N/A')}, FL: {wp.get('fl', 'N/A')}\n"
        else:
            waypoint_info += f"- {wp['waypoint']}: 좌표 없음, 예상 시간: {wp.get('estimated_time', 'N/A')}, FL: {wp.get('fl', 'N/A')}\n"
    
    prompt = f"""
이것은 SIGWX (Significant Weather) 차트 이미지입니다.

**차트 지리적 범위:**
- 위도: {image_bounds['min_lat']}° ~ {image_bounds['max_lat']}°
- 경도: {image_bounds['min_lon']}° ~ {image_bounds['max_lon']}°

**비행 경로 Waypoint 정보 (지리적 좌표 포함):**
{waypoint_info}

**비행 경로 특징:**
{flight_path_info}

**매우 중요한 분석 지침:**

1. **비행 경로 식별:**
   - 차트에서 검은색 점선으로 표시된 비행 경로를 찾으세요
   - 위에 제공된 waypoint 좌표를 사용하여 경로상 waypoint 위치를 정확히 식별하세요
   - 경로는 위도/경도 그리드를 따라 이동합니다

2. **터뷸런스 구분 (색상 정확히 구분):**
   - **핑크색/마젠타색 점선**: MOD (Moderate) Turbulence
     - RGB 값: R: 200-255, G: 0-100, B: 150-255
     - 비행 경로와 교차하거나 경로 주변 10픽셀 이내에 있으면 해당 waypoint에 영향
   
   - **빨간색 점선**: SEV (Severe) Turbulence
     - RGB 값: R: 200-255, G: 0-50, B: 0-50
     - 핑크색보다 더 진한 빨간색입니다
     - 비행 경로와 교차하거나 경로 주변 10픽셀 이내에 있으면 해당 waypoint에 영향

3. **CB 구름 식별:**
   - **초록색 scalloped line (구름 모양 실선)**: Cumulonimbus Clouds
     - RGB 값: R: 0-100, G: 150-255, B: 0-100
     - "OCNL CB", "ISOL CB" 등의 텍스트와 함께 표시됨
     - 비행 경로와 교차하거나 경로 주변 20픽셀 이내에 있으면 해당 waypoint에 영향

4. **제트기류 식별:**
   - **파란색 선 (화살표 포함)**: Jet Streams
     - RGB 값: R: 0-100, G: 100-200, B: 200-255
     - 비행 경로와 교차하는 경우 해당 waypoint에 영향

**출력 형식 (JSON만 출력):**
{{
  "waypoint_name": {{
    "mod_turbulence": true/false,
    "sev_turbulence": true/false,
    "cb_clouds": [
      {{
        "type": "OCNL CB",
        "top_fl": "320",
        "base_fl": "XXX",
        "distance_from_path": 5
      }}
    ],
    "jet_streams": [
      {{
        "core_fl": "410",
        "wind_speed": "500",
        "distance_from_path": 3
      }}
    ],
    "estimated_time": "0332Z",
    "actm": "01.28"
  }}
}}

**중요:**
- 각 waypoint의 지리적 좌표를 사용하여 차트상 정확한 위치를 찾으세요
- 비행 경로(검은색 점선)를 따라가면서 각 waypoint 위치를 확인하세요
- 기상 현상이 경로와 교차하거나 경로 주변에 있으면 해당 waypoint에 영향이 있다고 판단하세요
- 색상을 정확히 구분하세요 (핑크색 ≠ 빨간색)
"""
    
    return prompt


def analyze_sigwx_chart_enhanced(
    pdf_path: str,
    flight_data: List[Dict],
    sigwx_page_num: int
) -> Dict[str, Dict]:
    """
    개선된 SIGWX 차트 분석 (하이브리드 접근)
    
    Args:
        pdf_path: PDF 파일 경로
        flight_data: Flight Plan 데이터
        sigwx_page_num: SIGWX 차트 페이지 번호 (0-based)
    
    Returns:
        {
            'waypoint_name': {
                'mod_turbulence': bool,
                'sev_turbulence': bool,
                'cb_clouds': List[Dict],
                'jet_streams': List[Dict],
                'estimated_time': str,
                'actm': str,
                'fl': str
            }
        }
    """
    result = {}
    
    try:
        # 1. Waypoint 좌표 추출
        waypoints_with_coords = get_waypoint_coordinates_with_timing(flight_data)
        if not waypoints_with_coords:
            logger.warning("Waypoint 좌표를 추출할 수 없습니다.")
            return result
        
        # 2. SIGWX 차트 이미지 추출
        page_image = extract_page_as_image(pdf_path, sigwx_page_num)
        if not page_image:
            logger.warning(f"SIGWX 차트 이미지를 추출할 수 없습니다 (페이지 {sigwx_page_num + 1})")
            return result
        
        # 3. 이미지 범위 추출
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            if sigwx_page_num >= len(pdf.pages):
                logger.warning(f"페이지 번호가 범위를 벗어났습니다: {sigwx_page_num + 1}")
                return result
            page_text = pdf.pages[sigwx_page_num].extract_text() or ""
        
        image_bounds = extract_image_bounds_from_sigwx(page_text)
        
        # 4. Waypoint를 이미지 좌표로 변환
        image_size = page_image.size
        for wp in waypoints_with_coords:
            if wp.get('lat') and wp.get('lon'):
                wp['image_coords'] = convert_geo_to_image_coords(
                    wp['lat'], wp['lon'], image_bounds, image_size
                )
            else:
                wp['image_coords'] = (None, None)
        
        # 5. 비행 경로: 이미지에서 추출 시도, 실패 시 waypoint 좌표로 선분 샘플링 (Vision 불필요)
        flight_path_points = extract_flight_path_from_sigwx(page_image)
        if len(flight_path_points) < 20:
            flight_path_points = _sample_route_from_waypoint_coords(waypoints_with_coords)
            flight_path_info = f"비행 경로는 waypoint 좌표 기반 {len(flight_path_points)}개 픽셀 (이미지 경로 미감지)."
        else:
            flight_path_info = f"비행 경로는 {len(flight_path_points)}개 픽셀로 추출되었습니다."

        # 6. 기상 현상 추출 (이미지 처리)
        weather_phenomena = extract_weather_phenomena_from_sigwx(page_image)
        
        # 7. 교차점 찾기 (이미지 처리 기반)
        intersections = find_weather_intersections(
            flight_path_points,
            weather_phenomena,
            waypoints_with_coords
        )
        
        # 8. Gemini Vision API로 검증 및 보완
        gemini_result = {}
        if GEMINI_AVAILABLE and gemini_model:
            try:
                prompt = build_enhanced_sigwx_prompt(
                    waypoints_with_coords,
                    flight_path_info,
                    image_bounds
                )
                
                response = gemini_model.generate_content([prompt, page_image])
                response_text = response.text
                
                # JSON 파싱 시도
                import json
                response_text = re.sub(r'```json\s*', '', response_text)
                response_text = re.sub(r'```\s*', '', response_text)
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    gemini_result = json.loads(json_match.group(0))
                    logger.info("Gemini Vision API로 SIGWX 차트 분석 완료")
            except Exception as e:
                logger.warning(f"Gemini Vision API 검증 실패: {e}")
        
        # 9. 최종 결과 포맷팅 (이미지 처리 결과 우선, Gemini 결과로 보완)
        for wp in waypoints_with_coords:
            wp_name = wp['waypoint']
            result[wp_name] = {
                'mod_turbulence': False,
                'sev_turbulence': False,
                'cb_clouds': [],
                'jet_streams': [],
                'estimated_time': wp.get('estimated_time', 'N/A'),
                'actm': wp.get('actm', 'N/A'),
                'fl': wp.get('fl', 'N/A'),
                'sr': wp.get('sr', 'N/A')
            }
            
            # 이미지 처리 결과 적용
            if wp_name in intersections:
                for intersection in intersections[wp_name]:
                    if intersection['phenomenon'] == 'mod_turbulence':
                        result[wp_name]['mod_turbulence'] = True
                    elif intersection['phenomenon'] == 'sev_turbulence':
                        result[wp_name]['sev_turbulence'] = True
                    elif intersection['phenomenon'] == 'cb_clouds':
                        result[wp_name]['cb_clouds'].append(intersection)
                    elif intersection['phenomenon'] == 'jet_streams':
                        result[wp_name]['jet_streams'].append(intersection)
            
            # Gemini 결과로 보완 (이미지 처리에서 발견하지 못한 경우)
            if wp_name in gemini_result:
                gemini_data = gemini_result[wp_name]
                if gemini_data.get('mod_turbulence') and not result[wp_name]['mod_turbulence']:
                    result[wp_name]['mod_turbulence'] = True
                if gemini_data.get('sev_turbulence') and not result[wp_name]['sev_turbulence']:
                    result[wp_name]['sev_turbulence'] = True
                if gemini_data.get('cb_clouds') and not result[wp_name]['cb_clouds']:
                    result[wp_name]['cb_clouds'] = gemini_data.get('cb_clouds', [])
                if gemini_data.get('jet_streams') and not result[wp_name]['jet_streams']:
                    result[wp_name]['jet_streams'] = gemini_data.get('jet_streams', [])
        
        logger.info(f"SIGWX 차트 분석 완료: {len(result)}개 waypoint 분석")
        
    except Exception as e:
        logger.error(f"SIGWX 차트 분석 중 오류: {e}", exc_info=True)
    
    return result


# ---------------------------------------------------------------------------
# ISIGMET 경로 매칭 (aviationweather.gov 실시간 API)
# ---------------------------------------------------------------------------

_HAZARD_KO: Dict[str, str] = {
    "TURB":  "터뷸런스",
    "TURBULENCE": "터뷸런스",
    "ICE":   "착빙",
    "ICING": "착빙",
    "CONV":  "대류/CB",
    "CONVECTIVE": "대류/CB",
    "MTW":   "산악파",
    "VA":    "화산재",
    "DS":    "모래폭풍",
    "SS":    "모래폭풍",
}

_QUALIFIER_KO: Dict[str, str] = {
    "MOD":  "Moderate",
    "SEV":  "Severe",
    "OCNL": "산발적",
    "ISOL": "고립",
    "FRQ":  "빈번",
    "LGT":  "Light",
    "HVY":  "Heavy",
}


def _parse_wp_datetime(time_str: str, base_date: datetime) -> Optional[datetime]:
    """'1040Z' 형식 → UTC datetime. 날짜선 통과로 자정 넘는 경우 +1일 처리."""
    if not time_str or len(time_str) < 4 or time_str == "N/A":
        return None
    try:
        hh = int(time_str[:2])
        mm = int(time_str[2:4])
        dt = base_date.replace(hour=hh, minute=mm, second=0, microsecond=0)
        # 이륙 시간보다 작으면 다음 날(날짜선 통과)
        if dt < base_date:
            dt += timedelta(days=1)
        return dt
    except Exception:
        return None


def _query_isigmet(lat_min: float, lon_min: float,
                   lat_max: float, lon_max: float,
                   timeout: int = 20) -> List[Dict]:
    """단일 bbox로 isigmet API 호출. 결과 리스트 반환."""
    try:
        import requests
        bbox = f"{lat_min:.1f},{lon_min:.1f},{lat_max:.1f},{lon_max:.1f}"
        url = f"https://aviationweather.gov/api/data/isigmet?format=json&bbox={bbox}"
        logger.debug(f"ISIGMET 조회: {url}")
        resp = requests.get(url, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            return data if isinstance(data, list) else []
        if resp.status_code == 204:
            return []
        logger.warning(f"ISIGMET API 응답 오류: {resp.status_code}")
    except Exception as e:
        logger.warning(f"ISIGMET API 호출 실패: {e}")
    return []


def fetch_and_match_sigmet_for_route(flight_data: List[Dict],
                                     ofp_date: Optional[datetime] = None) -> List[Dict]:
    """
    OFP flight_data(waypoint 좌표/FL/통과예상시각)를 기반으로
    aviationweather.gov ISIGMET + G-AIRMET API를 조회해 경로에 영향을 주는
    기상 현상을 분석합니다.

    필터 조건
    - 공간: waypoint가 SIGMET 다각형 내부 또는 150km 이내
    - 고도: 운항 FL이 SIGMET base~top ± 5000ft 범위
    - 시간: waypoint 통과 예상 시각이 SIGMET 유효 기간 ± 8h 내
             (시간 정보 없는 경우 시간 필터 생략)

    Args:
        flight_data: extract_flight_data_from_pdf() 반환값
        ofp_date:    OFP 출발 날짜 (UTC 자정 기준). None이면 오늘 날짜 사용.

    Returns:
        list of dicts. 날짜 불일치 경고인 경우 _warning_row=True 플래그.
    """
    import requests as _req

    # ── 1. waypoint 목록 정리 ──────────────────────────────────────────────
    wps: List[Dict] = []
    for row in flight_data:
        lat = row.get("lat")
        lon = row.get("lon")
        if lat is None or lon is None:
            continue
        fl_str = row.get("FL (Flight Level)", "N/A")
        time_str = row.get("Estimated Time (Z)", "N/A")
        actm = row.get("ACTM (Accumulated Time)", "N/A")
        wp_name = row.get("Waypoint", "")
        try:
            fl = int(fl_str) if fl_str not in ("N/A", "", None) else None
        except Exception:
            fl = None
        wps.append({"name": wp_name, "lat": lat, "lon": lon,
                     "fl": fl, "time_str": time_str, "actm": actm})

    if not wps:
        logger.info("SIGMET 분석: 좌표가 있는 waypoint 없음.")
        return []

    # 이륙 시각 기준 datetime
    # ofp_date가 주어지면 그것을 사용, 아니면 오늘 날짜
    today_utc = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    if ofp_date is not None:
        base_date = ofp_date
    else:
        base_date = today_utc

    # OFP 날짜와 오늘 날짜 차이 계산 (24h 이상이면 SIGMET 조회 불가 경고)
    date_diff_hours = abs((today_utc - base_date).total_seconds()) / 3600
    sigmet_stale = date_diff_hours > 28  # 28h 초과 시 과거 데이터 → 조회 불가

    # 각 WP에 dt 필드 추가
    for wp in wps:
        wp["dt"] = _parse_wp_datetime(wp["time_str"], base_date)

    # ── 1b. OFP 날짜가 너무 오래된 경우 경고 반환 ──────────────────────────
    if sigmet_stale:
        logger.warning(f"OFP 날짜({base_date.date()})와 오늘({today_utc.date()}) 차이 {date_diff_hours:.0f}h. SIGMET 실시간 조회 불가.")
        return [{
            "_warning_row": True,
            "warn_msg": (
                f"OFP 출발일({base_date.strftime('%Y-%m-%d')})과 현재 날짜({today_utc.strftime('%Y-%m-%d')}) 간격이 "
                f"{date_diff_hours:.0f}h입니다. SIGMET은 발행 후 최대 6h 유효하며, "
                f"이 OFP에 해당하는 과거 SIGMET은 API에서 더 이상 조회되지 않습니다. "
                f"WAFS SigWx 차트(aviationweather.gov/sigwx)를 직접 참조하세요."
            ),
        }]

    # ── 2. 경로 bbox 계산 (날짜선 통과 처리) ──────────────────────────────
    all_lats = [w["lat"] for w in wps]
    all_lons = [w["lon"] for w in wps]

    lat_min = min(all_lats) - 3.0
    lat_max = max(all_lats) + 3.0

    # 날짜선(antimeridian) 통과 여부 감지
    crosses_dateline = (max(all_lons) - min(all_lons)) > 180.0

    sigmets: List[Dict] = []
    if crosses_dateline:
        # 동쪽(E): 양수 경도 구간
        east_lons = [l for l in all_lons if l >= 0]
        west_lons = [l for l in all_lons if l < 0]
        if east_lons:
            sigmets += _query_isigmet(lat_min, min(east_lons) - 3.0,
                                      lat_max, 180.0)
        if west_lons:
            sigmets += _query_isigmet(lat_min, -180.0,
                                      lat_max, max(west_lons) + 3.0)
    else:
        lon_min = min(all_lons) - 3.0
        lon_max = max(all_lons) + 3.0
        sigmets = _query_isigmet(lat_min, lon_min, lat_max, lon_max)

    logger.info(f"ISIGMET 조회 결과: {len(sigmets)}개")

    # ── 2b. G-AIRMET TURB-HI 조회 (미국/캐나다 구간) ──────────────────────
    gairmets: List[Dict] = []
    try:
        ga_resp = _req.get(
            "https://aviationweather.gov/api/data/gairmet?format=json&hazard=turb-hi",
            timeout=20)
        if ga_resp.status_code == 200:
            ga_all = ga_resp.json() if isinstance(ga_resp.json(), list) else []
            # TURB-HI / TURB-LO 항목만 (고고도 영역 필터)
            gairmets = [g for g in ga_all
                        if g.get('hazard', '').upper() in ('TURB-HI', 'TURB-LO')]
            logger.info(f"G-AIRMET TURB 조회 결과: {len(gairmets)}개")
    except Exception as e:
        logger.warning(f"G-AIRMET 조회 실패: {e}")

    # G-AIRMET을 SIGMET 형식으로 변환하여 합산
    for ga in gairmets:
        raw_coords = ga.get('coords', [])
        if not raw_coords:
            continue
        # G-AIRMET coords: [{'lat': '48.99', 'lon': '-105.19'}, ...]
        # → float 변환
        poly = []
        for c in raw_coords:
            try:
                poly.append({'lat': float(c['lat']), 'lon': float(c['lon'])})
            except Exception:
                pass
        if len(poly) < 3:
            continue

        top_str = ga.get('top', '999')
        base_str = ga.get('base', '0')
        try:
            top_fl = int(str(top_str).replace('SFC','0').replace('UNL','999'))
        except Exception:
            top_fl = 999
        try:
            base_fl = int(str(base_str).replace('SFC','0'))
        except Exception:
            base_fl = 0

        expire_ts = ga.get('expireTime', 0) or 0
        valid_ts  = ga.get('validTime', '') or ''
        try:
            from datetime import datetime as _dt
            vfrom_dt_ga = _dt.fromisoformat(valid_ts.replace('Z','+00:00')) if valid_ts else today_utc
            vto_dt_ga   = datetime.fromtimestamp(expire_ts, tz=timezone.utc) if expire_ts else today_utc + timedelta(hours=6)
        except Exception:
            vfrom_dt_ga = today_utc
            vto_dt_ga   = today_utc + timedelta(hours=6)

        sigmets.append({
            '_gairmet': True,
            'hazard':   'TURB',
            'qualifier': ga.get('severity', 'MOD').upper(),
            'firName':  'G-AIRMET (US/CAN)',
            'base':     base_fl * 100,
            'top':      top_fl  * 100,
            'validTimeFrom': int(vfrom_dt_ga.timestamp()),
            'validTimeTo':   int(vto_dt_ga.timestamp()),
            'coords':   poly,
            'rawSigmet': f"G-AIRMET TURB-HI FL{base_fl}~FL{top_fl} MOD",
        })

    if not sigmets:
        logger.info("SIGMET 분석: 해당 구역에 활성 SIGMET/G-AIRMET 없음.")
        return []

    logger.info(f"SIGMET+G-AIRMET 합산: {len(sigmets)}개")

    # ── 3. SIGMET × waypoint 매칭 ──────────────────────────────────────────
    # 필터 통과 통계 (디버깅용)
    _filter_stats = {"alt_fail": 0, "time_fail": 0, "spatial_fail": 0, "matched": 0}

    # 출발/도착 구간 WP 인덱스 (앞 3개, 뒤 3개) — 상승/하강 중 SIGMET 포착
    _dep_idx = set(range(min(3, len(wps))))
    _arr_idx = set(range(max(0, len(wps) - 3), len(wps)))
    def _normalize_coords(raw_coords) -> List[List[Dict]]:
        """SIGMET coords를 폴리곤 리스트 형태로 정규화.
        API 응답에 따라 다음 두 가지 형태 처리:
          - [{"lat":x,"lon":y}, ...]           → 단일 폴리곤
          - [[{"lat":x,"lon":y}, ...], ...]    → 복수 폴리곤
        """
        if not raw_coords:
            return []
        if isinstance(raw_coords[0], dict):
            return [raw_coords]          # 단일 폴리곤
        if isinstance(raw_coords[0], list):
            return raw_coords            # 복수 폴리곤
        return []

    results: List[Dict] = []

    for sigmet in sigmets:
        raw_coords = sigmet.get("coords", [])
        polygons = _normalize_coords(raw_coords)
        if not polygons:
            continue

        # SIGMET 고도 (feet)
        base_ft = int(sigmet.get("base") or 0)
        top_ft  = int(sigmet.get("top")  or 99000)

        # SIGMET 유효 시간
        vfrom_ts = sigmet.get("validTimeFrom", 0) or 0
        vto_ts   = sigmet.get("validTimeTo",   0) or 0
        vfrom_dt = datetime.fromtimestamp(vfrom_ts, tz=timezone.utc)
        vto_dt   = datetime.fromtimestamp(vto_ts,   tz=timezone.utc)

        hazard_raw = (sigmet.get("hazard") or "").upper().strip()
        qualifier  = (sigmet.get("qualifier") or "").upper().strip()
        fir_name   = sigmet.get("firName") or sigmet.get("isigmetId") or "Unknown"
        raw_text   = (sigmet.get("rawAirSigmet") or
                      sigmet.get("rawText") or "")[:300]

        hazard_ko  = _HAZARD_KO.get(hazard_raw, hazard_raw)
        qual_ko    = _QUALIFIER_KO.get(qualifier, qualifier)

        base_fl_val = base_ft // 100
        top_fl_val  = top_ft  // 100

        # 각 waypoint에 대해 필터 적용
        affected: List[Dict] = []
        for wp_idx, wp in enumerate(wps):
            wp_lat, wp_lon = wp["lat"], wp["lon"]
            wp_fl  = wp["fl"]
            wp_dt  = wp["dt"]
            # 출발/도착 구간은 상승·하강 중이므로 고도 범위 확장 (±FL100)
            is_dep_arr = wp_idx in _dep_idx or wp_idx in _arr_idx
            alt_buffer = 10000 if is_dep_arr else 5000   # ft

            # ① 고도 필터: 운항 FL이 SIGMET FL ± alt_buffer ft 범위 내
            #    출발/도착 3개 WP는 ±FL100(10000ft), 순항 구간은 ±FL50(5000ft)
            if wp_fl is not None:
                wp_ft = wp_fl * 100
                # 출발/도착 구간: SIGMET이 SFC~top_ft 범위 안에 있으면 통과
                if is_dep_arr:
                    if top_ft < 3000:   # 지표 1000ft 미만 극저고도 SIGMET 제외
                        _filter_stats["alt_fail"] += 1
                        continue
                else:
                    if not (base_ft - alt_buffer <= wp_ft <= top_ft + alt_buffer):
                        _filter_stats["alt_fail"] += 1
                        continue
            else:
                # WP FL 정보 없음 → 저고도 SIGMET 제외 (FL200 미만 max FL은 건너뜀)
                if top_ft < 20000:
                    _filter_stats["alt_fail"] += 1
                    continue

            # ② 시간 필터: waypoint 통과 시각이 SIGMET 유효 기간 ± 8h 내
            #    (시간 정보 없는 WP는 시간 필터 생략)
            if wp_dt is not None:
                if not (vfrom_dt - timedelta(hours=8) <= wp_dt <=
                        vto_dt   + timedelta(hours=8)):
                    _filter_stats["time_fail"] += 1
                    continue

            # ③ 공간 필터: 임의의 폴리곤 내부 또는 200km 이내
            is_inside = any(point_in_polygon((wp_lat, wp_lon), poly)
                            for poly in polygons)
            is_near   = (not is_inside and
                         any(point_near_polygon((wp_lat, wp_lon), poly,
                                                threshold_km=200)
                             for poly in polygons))

            if is_inside or is_near:
                _filter_stats["matched"] += 1
                affected.append({
                    "name":     wp["name"],
                    "time_str": wp["time_str"],
                    "actm":     wp["actm"],
                    "inside":   is_inside,
                    "dep_arr":  is_dep_arr,
                })
            else:
                _filter_stats["spatial_fail"] += 1

        if not affected:
            continue

        # 순항 구간(dep/arr 아닌) WP 기준으로 affect_type 결정
        cruise_inside = any(w["inside"] and not w.get("dep_arr") for w in affected)
        cruise_near   = any(not w["inside"] and not w.get("dep_arr") for w in affected)
        dep_arr_only  = all(w.get("dep_arr") for w in affected)

        if cruise_inside:
            affect_type = "경로 내부"
        elif cruise_near:
            affect_type = "경로 근처(200km)"
        else:
            # 출발/도착 구간 전용: 상승/하강 중 통과 예상
            affect_type = "출발/도착 구간"
        first_wp     = affected[0]
        last_wp      = affected[-1]

        # 시간 포맷 정리 ("1040Z" → "10:40Z")
        def _fmt_t(s: str) -> str:
            if s and len(s) >= 4 and s[:4].isdigit():
                return f"{s[:2]}:{s[2:4]}Z"
            return s or "—"

        time_display = (f"{_fmt_t(first_wp['time_str'])} ~ "
                        f"{_fmt_t(last_wp['time_str'])}"
                        if first_wp["name"] != last_wp["name"]
                        else _fmt_t(first_wp["time_str"]))
        actm_display = (f"{first_wp['actm']} ~ {last_wp['actm']}"
                        if first_wp["name"] != last_wp["name"]
                        else first_wp["actm"])

        # 라벨 (TURB → SIGMET|G-AIRMET | MOD 터뷸런스 등)
        is_gairmet = sigmet.get('_gairmet', False)
        tag = "[G-AIRMET]" if is_gairmet else "[SIGMET]"
        label_parts = [tag]
        if qual_ko:
            label_parts.append(qual_ko)
        label_parts.append(hazard_ko)
        label = " ".join(label_parts)

        results.append({
            "fir":        fir_name,
            "hazard_en":  hazard_raw,
            "hazard_ko":  hazard_ko,
            "qualifier":  qualifier,
            "qual_ko":    qual_ko,
            "label":      label,
            "base_fl":    str(base_fl_val) if base_fl_val else "SFC",
            "top_fl":     str(top_fl_val)  if top_fl_val  else "—",
            "valid_from": vfrom_dt.strftime("%H:%MZ"),
            "valid_to":   vto_dt.strftime("%H:%MZ"),
            "affect_type": affect_type,
            "first_wp":   first_wp["name"],
            "last_wp":    last_wp["name"],
            "time_display": time_display,
            "actm_display": actm_display,
            "wp_count":   len(affected),
            "raw_text":   raw_text,
        })

    # 중복 제거: (fir + valid_from + valid_to + hazard_en + base_fl + top_fl) 기준
    seen_keys: set = set()
    deduped: List[Dict] = []
    for r in results:
        key = (r["fir"], r["valid_from"], r["valid_to"],
               r["hazard_en"], r["base_fl"], r["top_fl"])
        if key not in seen_keys:
            seen_keys.add(key)
            deduped.append(r)
    results = deduped

    # 시간 순 정렬
    results.sort(key=lambda r: r["valid_from"])

    logger.info(
        f"SIGMET 경로 영향 구간(중복제거 후): {len(results)}개 "
        f"[필터 통계: 고도제외={_filter_stats['alt_fail']} "
        f"시간제외={_filter_stats['time_fail']} "
        f"공간제외={_filter_stats['spatial_fail']} "
        f"매칭={_filter_stats['matched']}]"
    )
    return results

