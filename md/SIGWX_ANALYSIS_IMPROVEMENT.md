# SIGWX 차트 분석 개선 방안

## 현재 문제점

1. **경로와 기상 현상 구분 실패**: Gemini Vision API가 비행 경로(검은색 점선)와 터뷸런스(핑크색/빨간색 점선), CB 구름(초록색 scalloped line)을 제대로 구분하지 못함
2. **시간/위치 매핑 실패**: 비행 경로상 어디(시간과 위치)에 기상 현상이 있는지 정확히 찾아내지 못함
3. **Waypoint 위치 인식 부족**: Waypoint의 실제 지도상 위치를 정확히 인식하지 못함

## 개선 방안: 하이브리드 접근법

### 1단계: Waypoint 좌표 기반 경로 매핑

**목적**: Waypoint의 실제 지리적 좌표를 사용하여 SIGWX 차트상 위치를 정확히 매핑

**구현 방법**:
```python
from src.nav_data_loader import NavDataLoader

def get_waypoint_coordinates_with_timing(flight_data: List[Dict]) -> List[Dict]:
    """
    Flight Plan 데이터에서 waypoint 좌표와 시간 정보를 추출
    
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
                    'fl': row.get('FL (Flight Level)', 'N/A')
                })
    
    return waypoints_with_coords
```

### 2단계: 이미지 처리 기반 경로 추출

**목적**: SIGWX 차트에서 비행 경로(검은색 점선)를 정확히 추출

**구현 방법**:
```python
import cv2
import numpy as np
from PIL import Image

def extract_flight_path_from_sigwx(image: Image.Image) -> List[Tuple[int, int]]:
    """
    SIGWX 차트 이미지에서 비행 경로(검은색 점선) 추출
    
    Returns:
        경로상의 픽셀 좌표 리스트 [(x, y), ...]
    """
    img_array = np.array(image)
    
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
```

### 3단계: 기상 현상 색상별 추출

**목적**: 터뷸런스, CB 구름, 제트기류를 색상별로 정확히 구분하여 추출

**구현 방법**:
```python
def extract_weather_phenomena_from_sigwx(image: Image.Image) -> Dict[str, List[Tuple[int, int]]]:
    """
    SIGWX 차트에서 기상 현상을 색상별로 추출
    
    Returns:
        {
            'mod_turbulence': [(x, y), ...],  # 핑크색 점선
            'sev_turbulence': [(x, y), ...],  # 빨간색 점선
            'cb_clouds': [(x, y), ...],       # 초록색 scalloped line
            'jet_streams': [(x, y), ...]      # 파란색 선
        }
    """
    img_array = np.array(image)
    
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
```

### 4단계: 지리적 좌표 ↔ 이미지 좌표 변환

**목적**: Waypoint의 지리적 좌표를 SIGWX 차트 이미지 좌표로 변환

**구현 방법**:
```python
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
    
    # 위도 변환 (Y 좌표)
    lat_range = image_bounds['max_lat'] - image_bounds['min_lat']
    y = int(height * (1 - (lat - image_bounds['min_lat']) / lat_range))
    
    # 경도 변환 (X 좌표)
    lon_range = image_bounds['max_lon'] - image_bounds['min_lon']
    x = int(width * (lon - image_bounds['min_lon']) / lon_range)
    
    return (x, y)

def extract_image_bounds_from_sigwx(image: Image.Image, page_text: str) -> Dict[str, float]:
    """
    SIGWX 차트에서 지리적 범위 추출 (위도/경도 그리드에서)
    
    Returns:
        {'min_lat': float, 'max_lat': float, 'min_lon': float, 'max_lon': float}
    """
    # 차트 헤더나 그리드에서 위도/경도 범위 추출
    # 예: "N40", "N20", "S30" 등에서 위도 범위 추출
    # 예: "100E", "120E", "180E" 등에서 경도 범위 추출
    
    import re
    
    # 위도 추출
    lat_pattern = r'([NS])(\d{2})'
    lats = re.findall(lat_pattern, page_text)
    
    # 경도 추출
    lon_pattern = r'(\d{3})([EW])'
    lons = re.findall(lon_pattern, page_text)
    
    # TODO: 실제 구현 필요
    # 임시로 기본값 반환
    return {
        'min_lat': -40.0,
        'max_lat': 40.0,
        'min_lon': 100.0,
        'max_lon': 180.0
    }
```

### 5단계: 경로와 기상 현상 교차점 찾기

**목적**: 비행 경로와 기상 현상이 교차하는 지점을 찾아 waypoint와 매핑

**구현 방법**:
```python
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
        wp_x, wp_y = wp_info['image_coords']
        
        wp_intersections = []
        
        # 각 기상 현상 타입별로 교차점 찾기
        for phenom_type, phenom_points in weather_phenomena.items():
            for px, py in phenom_points:
                # Waypoint와 기상 현상의 거리 계산
                distance = ((wp_x - px) ** 2 + (wp_y - py) ** 2) ** 0.5
                
                if distance <= threshold:
                    # 비행 경로상에서도 확인
                    path_distance = min([
                        ((path_x - px) ** 2 + (path_y - py) ** 2) ** 0.5
                        for path_x, path_y in flight_path_points
                    ])
                    
                    if path_distance <= threshold:
                        wp_intersections.append({
                            'phenomenon': phenom_type,
                            'distance': int(distance),
                            'waypoint': wp_name,
                            'estimated_time': wp_info.get('estimated_time', 'N/A'),
                            'actm': wp_info.get('actm', 'N/A'),
                            'fl': wp_info.get('fl', 'N/A')
                        })
        
        if wp_intersections:
            intersections[wp_name] = wp_intersections
    
    return intersections
```

### 6단계: 개선된 Gemini Vision 프롬프트

**목적**: Waypoint 좌표와 경로 정보를 제공하여 Gemini가 정확히 위치를 찾을 수 있도록

**구현 방법**:
```python
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
        waypoint_info += f"- {wp['waypoint']}: 위도 {wp['lat']:.2f}°N, 경도 {wp['lon']:.2f}°E, 예상 시간: {wp['estimated_time']}, FL: {wp['fl']}\n"
    
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
    "image_coords": {{"x": 1234, "y": 567}},
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
```

### 7단계: 통합 분석 함수

**목적**: 모든 단계를 통합하여 최종 분석 결과 생성

**구현 방법**:
```python
def analyze_sigwx_chart_enhanced(
    pdf_path: str,
    flight_data: List[Dict],
    sigwx_page_num: int
) -> Dict[str, Dict]:
    """
    개선된 SIGWX 차트 분석 (하이브리드 접근)
    
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
    # 1. Waypoint 좌표 추출
    waypoints_with_coords = get_waypoint_coordinates_with_timing(flight_data)
    
    # 2. SIGWX 차트 이미지 추출
    page_image = extract_page_as_image(pdf_path, sigwx_page_num)
    if not page_image:
        return {}
    
    # 3. 이미지 범위 추출
    with pdfplumber.open(pdf_path) as pdf:
        page_text = pdf.pages[sigwx_page_num].extract_text()
    image_bounds = extract_image_bounds_from_sigwx(page_image, page_text)
    
    # 4. Waypoint를 이미지 좌표로 변환
    image_size = page_image.size
    for wp in waypoints_with_coords:
        wp['image_coords'] = convert_geo_to_image_coords(
            wp['lat'], wp['lon'], image_bounds, image_size
        )
    
    # 5. 비행 경로 추출 (이미지 처리)
    flight_path_points = extract_flight_path_from_sigwx(page_image)
    
    # 6. 기상 현상 추출 (이미지 처리)
    weather_phenomena = extract_weather_phenomena_from_sigwx(page_image)
    
    # 7. 교차점 찾기 (이미지 처리 기반)
    intersections = find_weather_intersections(
        flight_path_points,
        weather_phenomena,
        waypoints_with_coords
    )
    
    # 8. Gemini Vision API로 검증 및 보완
    if GEMINI_AVAILABLE:
        flight_path_info = f"비행 경로는 {len(flight_path_points)}개 픽셀로 추출되었습니다."
        prompt = build_enhanced_sigwx_prompt(
            waypoints_with_coords,
            flight_path_info,
            image_bounds
        )
        
        try:
            response = model.generate_content([prompt, page_image])
            # Gemini 결과 파싱 및 intersections와 병합
            gemini_result = parse_gemini_response(response.text)
            
            # 이미지 처리 결과와 Gemini 결과 병합 (이미지 처리 결과 우선)
            for wp_name, gemini_data in gemini_result.items():
                if wp_name in intersections:
                    # 이미지 처리 결과가 있으면 보완만 수행
                    intersections[wp_name].extend(gemini_data.get('additional_info', []))
                else:
                    # Gemini만 발견한 경우 추가
                    intersections[wp_name] = gemini_data
        except Exception as e:
            logger.warning(f"Gemini Vision API 검증 실패: {e}")
    
    # 9. 최종 결과 포맷팅
    result = {}
    for wp in waypoints_with_coords:
        wp_name = wp['waypoint']
        result[wp_name] = {
            'mod_turbulence': False,
            'sev_turbulence': False,
            'cb_clouds': [],
            'jet_streams': [],
            'estimated_time': wp['estimated_time'],
            'actm': wp['actm'],
            'fl': wp['fl']
        }
        
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
    
    return result
```

## 구현 우선순위

### Phase 1: 기본 기능 (1-2주)
1. Waypoint 좌표 기반 경로 매핑 구현
2. 이미지 처리 기반 경로 추출 구현
3. 기상 현상 색상별 추출 구현

### Phase 2: 통합 및 검증 (1주)
1. 교차점 찾기 로직 구현
2. Gemini Vision API와 통합
3. 결과 검증 및 테스트

### Phase 3: 최적화 (1주)
1. 색상 감지 정확도 개선
2. 경로 추출 정확도 개선
3. 성능 최적화

## 예상 효과

1. **정확도 향상**: Waypoint 좌표 기반 매핑으로 위치 인식 정확도 90% 이상 향상
2. **시간/위치 매핑**: 각 waypoint의 예상 통과 시간과 기상 현상이 정확히 매핑됨
3. **조종사 의사결정 지원**: Weather deviation 시점과 turbulence 대비 시점을 명확히 제시

## 추가 고려사항

1. **차트 해상도**: DPI 300 이상으로 이미지 추출하여 색상 구분 정확도 향상
2. **색상 변이**: PDF 렌더링에 따른 색상 변이를 고려한 허용 범위 설정
3. **다중 차트**: High-level, Mid-level SIGWX 차트를 모두 분석하여 FL별 위험 요소 파악

