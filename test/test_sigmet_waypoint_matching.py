#!/usr/bin/env python3
"""
SIGMET 데이터와 Waypoint 매칭 테스트
현재 시점의 SIGMET을 가져와서 waypoint와 비교
"""

import requests
from datetime import datetime
import json
import math
from typing import List, Dict, Tuple, Optional


def get_current_sigmet(hazard: str = 'turb', level: int = 34000) -> List[Dict]:
    """
    현재 시점의 SIGMET 데이터를 가져옵니다.
    
    Args:
        hazard: 위험 유형 ('turb', 'ice', 'conv', 'ifr')
        level: 고도 (feet)
        
    Returns:
        SIGMET 데이터 리스트
    """
    base_url = 'https://aviationweather.gov/api/data/isigmet'
    
    # 현재 시간
    current_time = datetime.now().strftime('%Y%m%d%H%M')
    
    params = {
        'format': 'json',
        'hazard': hazard,
        'level': level,
        'date': current_time
    }
    
    try:
        response = requests.get(base_url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list):
                return data
            elif isinstance(data, dict):
                return [data]
            return []
        elif response.status_code == 204:
            print(f"⚠️ 현재 시점({current_time})에 SIGMET 데이터가 없습니다. Skip합니다.")
            return []
        else:
            print(f"❌ SIGMET API 오류: {response.status_code}")
            return []
    except Exception as e:
        print(f"❌ SIGMET API 호출 실패: {e}")
        return []


def parse_waypoint_coordinates(waypoint_name: str) -> Optional[Tuple[float, float]]:
    """
    Waypoint 이름에서 좌표를 추출합니다.
    
    Args:
        waypoint_name: Waypoint 이름 (예: "57N60", "NOPIK", "CYVR")
        
    Returns:
        (latitude, longitude) 튜플 또는 None
    """
    # 좌표 형식: 57N60 (위도57도N, 경도60도)
    coord_pattern = r'(\d{2})N(\d{2,3})'
    import re
    match = re.match(coord_pattern, waypoint_name)
    if match:
        lat = float(match.group(1))
        lon = float(match.group(2))
        return (lat, lon)
    
    # 공항 코드는 나중에 처리 (airports.csv에서 조회 필요)
    return None


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


def get_waypoints_from_pdf(pdf_path: str) -> List[Dict]:
    """
    PDF에서 waypoint를 추출하고 좌표를 조회합니다.
    
    Args:
        pdf_path: PDF 파일 경로
        
    Returns:
        [{"name": str, "lat": float, "lon": float}, ...] 형식의 리스트
    """
    try:
        from flightplanextractor import extract_flight_data_from_pdf
        from src.nav_data_loader import NavDataLoader
        
        # Flight Plan에서 waypoint 추출
        flight_data = extract_flight_data_from_pdf(pdf_path, save_temp=False)
        if not flight_data:
            return []
        
        # NavDataLoader로 좌표 조회
        nav_loader = NavDataLoader()
        nav_loader.load_nav_data()
        
        waypoints = []
        for row in flight_data:
            wp_name = row.get('Waypoint', '')
            if wp_name and wp_name != 'N/A':
                coords = nav_loader.get_waypoint_coordinates(wp_name)
                if coords:
                    waypoints.append({
                        "name": wp_name,
                        "lat": coords[0],
                        "lon": coords[1]
                    })
                else:
                    # 좌표를 찾지 못한 경우도 추가 (나중에 처리)
                    waypoints.append({
                        "name": wp_name,
                        "lat": None,
                        "lon": None
                    })
        
        return waypoints
    except Exception as e:
        print(f"⚠️ PDF에서 waypoint 추출 실패: {e}")
        import traceback
        traceback.print_exc()
        return []


def match_sigmet_to_waypoints(sigmets: List[Dict], waypoints: List[Dict]) -> Dict[str, List[Dict]]:
    """
    SIGMET 데이터와 waypoint를 매칭합니다.
    
    Args:
        sigmets: SIGMET 데이터 리스트
        waypoints: [{"name": str, "lat": float, "lon": float}, ...] 형식
        
    Returns:
        {waypoint_name: [matched_sigmet, ...]} 딕셔너리
    """
    matches = {}
    
    for waypoint in waypoints:
        wp_name = waypoint.get('name', '')
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


def test_sigmet_waypoint_matching(pdf_path: Optional[str] = None):
    """테스트 함수"""
    print("=" * 80)
    print("SIGMET - Waypoint 매칭 테스트")
    print("=" * 80)
    print()
    
    # 1. 현재 SIGMET 데이터 가져오기
    print("[1단계] 현재 SIGMET 데이터 가져오기...")
    sigmets = get_current_sigmet(hazard='turb', level=34000)
    print(f"✅ 수신된 SIGMET 수: {len(sigmets)}")
    
    if not sigmets:
        print("⚠️ 현재 시점에 SIGMET 데이터가 없습니다. Skip합니다.")
        return
    
    # SIGMET 정보 출력
    print("\n수신된 SIGMET 목록:")
    for i, sigmet in enumerate(sigmets[:5], 1):  # 처음 5개만
        print(f"\n{i}. {sigmet.get('firName', 'Unknown')}")
        print(f"   Hazard: {sigmet.get('hazard', 'N/A')}")
        print(f"   Qualifier: {sigmet.get('qualifier', 'N/A')}")
        print(f"   Base: {sigmet.get('base', 'N/A')}ft, Top: {sigmet.get('top', 'N/A')}ft")
        print(f"   Valid: {datetime.fromtimestamp(sigmet.get('validTimeFrom', 0))} ~ {datetime.fromtimestamp(sigmet.get('validTimeTo', 0))}")
        coords = sigmet.get('coords', [])
        print(f"   좌표 수: {len(coords)}")
        if coords:
            print(f"   첫 좌표: lat={coords[0].get('lat', 'N/A')}, lon={coords[0].get('lon', 'N/A')}")
    
    # 2. Waypoint 추출
    print("\n" + "=" * 80)
    print("[2단계] Waypoint 좌표 추출...")
    
    if pdf_path:
        waypoints = get_waypoints_from_pdf(pdf_path)
        print(f"PDF에서 추출된 waypoint 수: {len(waypoints)}")
    else:
        # 테스트 waypoint (예시)
        waypoints = [
            {"name": "RKSI", "lat": 37.4692, "lon": 126.4510},  # 인천
            {"name": "NOPIK", "lat": 37.0, "lon": 130.0},  # 예시
            {"name": "57N60", "lat": 57.0, "lon": 60.0},  # 좌표 형식
            {"name": "CYVR", "lat": 49.1947, "lon": -123.1819},  # 밴쿠버
        ]
        print(f"테스트 waypoint 수: {len(waypoints)}")
    
    # 좌표가 있는 waypoint만 필터링
    valid_waypoints = [wp for wp in waypoints if wp.get('lat') is not None and wp.get('lon') is not None]
    print(f"좌표가 있는 waypoint 수: {len(valid_waypoints)}")
    
    if not valid_waypoints:
        print("⚠️ 좌표가 있는 waypoint가 없습니다.")
        return
    
    for wp in valid_waypoints[:10]:  # 처음 10개만 출력
        print(f"  - {wp['name']}: lat={wp['lat']:.4f}, lon={wp['lon']:.4f}")
    if len(valid_waypoints) > 10:
        print(f"  ... (총 {len(valid_waypoints)}개)")
    
    # 3. 매칭 수행
    print("\n" + "=" * 80)
    print("[3단계] SIGMET - Waypoint 매칭...")
    matches = match_sigmet_to_waypoints(sigmets, valid_waypoints)
    
    # 4. 결과 출력
    print("\n매칭 결과:")
    print("-" * 80)
    
    total_matches = 0
    for wp_name, matched_sigmets in matches.items():
        if matched_sigmets:
            total_matches += len(matched_sigmets)
            print(f"\n📍 {wp_name}: {len(matched_sigmets)}개 SIGMET 매칭")
            for match in matched_sigmets:
                sigmet = match['sigmet']
                location = "영역 내부" if match['inside'] else "영역 근처 (100km)"
                print(f"  - {sigmet.get('firName', 'Unknown')}")
                print(f"    {location} | {sigmet.get('qualifier', 'N/A')} {sigmet.get('hazard', 'N/A')}")
                print(f"    FL{sigmet.get('base', 0)//1000}-{sigmet.get('top', 0)//1000}")
        else:
            print(f"\n📍 {wp_name}: 매칭된 SIGMET 없음")
    
    print("\n" + "=" * 80)
    print(f"총 매칭 수: {total_matches}")
    print("=" * 80)


if __name__ == "__main__":
    import sys
    
    # PDF 파일 경로가 인자로 제공되면 사용
    pdf_path = None
    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]
        print(f"PDF 파일: {pdf_path}\n")
    
    test_sigmet_waypoint_matching(pdf_path)

