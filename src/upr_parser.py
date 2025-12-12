"""
UPR (User Preferred Route) 좌표 파서
N44E160..N46E170..N49E180 형식의 좌표 구간을 파싱
"""

import re
from typing import List, Tuple, Optional, Dict

class UPRParser:
    """UPR 좌표 파서"""
    
    def __init__(self):
        self.coordinate_patterns = [
            # N44E160 형식
            r'([NS])(\d{2})([EW])(\d{3})',
            # N44.0E160.0 형식 (소수점 포함)
            r'([NS])(\d{2}(?:\.\d+)?)([EW])(\d{3}(?:\.\d+)?)',
            # 44N160E 형식
            r'(\d{2}(?:\.\d+)?)([NS])(\d{3}(?:\.\d+)?)([EW])',
        ]
    
    def parse_upr_route(self, route_text: str) -> List[Tuple[float, float]]:
        """
        UPR 경로 텍스트에서 좌표 추출
        
        Args:
            route_text: UPR 경로 텍스트 (예: "N44E160..N46E170..N49E180")
            
        Returns:
            List[Tuple[float, float]]: 파싱된 좌표 리스트 [(위도, 경도), ...]
        """
        coordinates = []
        
        # 좌표 구간 분리 (.. 또는 공백으로 구분)
        coord_segments = re.split(r'\.\.+|\s+', route_text.strip())
        
        for segment in coord_segments:
            segment = segment.strip()
            if not segment:
                continue
                
            coord = self._parse_single_coordinate(segment)
            if coord:
                coordinates.append(coord)
        
        return coordinates
    
    def _parse_single_coordinate(self, coord_str: str) -> Optional[Tuple[float, float]]:
        """
        단일 좌표 문자열 파싱
        
        Args:
            coord_str: 좌표 문자열 (예: "N44E160")
            
        Returns:
            Optional[Tuple[float, float]]: (위도, 경도) 또는 None
        """
        coord_str = coord_str.strip().upper()
        
        # 패턴 1: N44E160 형식
        match = re.match(r'([NS])(\d{2}(?:\.\d+)?)([EW])(\d{3}(?:\.\d+)?)', coord_str)
        if match:
            lat_dir, lat_val, lon_dir, lon_val = match.groups()
            lat = float(lat_val)
            lon = float(lon_val)
            
            if lat_dir == 'S':
                lat = -lat
            if lon_dir == 'W':
                lon = -lon
                
            return (lat, lon)
        
        # 패턴 2: 44N160E 형식
        match = re.match(r'(\d{2}(?:\.\d+)?)([NS])(\d{3}(?:\.\d+)?)([EW])', coord_str)
        if match:
            lat_val, lat_dir, lon_val, lon_dir = match.groups()
            lat = float(lat_val)
            lon = float(lon_val)
            
            if lat_dir == 'S':
                lat = -lat
            if lon_dir == 'W':
                lon = -lon
                
            return (lat, lon)
        
        return None
    
    def parse_route_with_waypoints(self, route_text: str) -> Dict:
        """
        waypoint와 좌표가 혼합된 경로 파싱 (향상된 waypoint 추출)
        
        Args:
            route_text: 경로 텍스트 (예: "RKSI..EGOBA Y697 LANAT Y51 SAMON Y142 GTC Y512 ADNAP R591 ADGOR..N44E160..N46E170..N49E180..N50W170..N52W160..N53W150..N52W140..ORNAI..TOU MARNR8 KSEA")
            
        Returns:
            Dict: 파싱 결과
        """
        result = {
            'waypoints': [],
            'coordinates': [],
            'route_codes': [],
            'full_route': [],
            'expanded_waypoints': []  # 항로코드에서 추출된 추가 waypoint
        }
        
        # 경로를 구분자로 분리
        segments = re.split(r'\.\.+|\s+', route_text.strip())
        
        for segment in segments:
            segment = segment.strip()
            if not segment:
                continue
            
            # 좌표 패턴 확인
            coord = self._parse_single_coordinate(segment)
            if coord:
                result['coordinates'].append(coord)
                result['full_route'].append({
                    'type': 'coordinate',
                    'value': segment,
                    'parsed': coord
                })
                continue
            
            # 항로 코드 패턴 확인 (Y697, R591 등)
            if re.match(r'^[A-Z]\d{3}$', segment):
                result['route_codes'].append(segment)
                result['full_route'].append({
                    'type': 'route_code',
                    'value': segment
                })
                # 항로코드에서 waypoint 추출
                route_waypoints = self._get_waypoints_from_route_code(segment)
                result['expanded_waypoints'].extend(route_waypoints)
                continue
            
            # waypoint 패턴 확인 (3-5글자 대문자)
            if re.match(r'^[A-Z]{3,5}$', segment):
                result['waypoints'].append(segment)
                result['full_route'].append({
                    'type': 'waypoint',
                    'value': segment
                })
                continue
            
            # 공항 코드 패턴 확인 (4글자 대문자)
            if re.match(r'^[A-Z]{4}$', segment):
                result['full_route'].append({
                    'type': 'airport',
                    'value': segment
                })
                continue
            
            # 기타 (SID, STAR 등)
            result['full_route'].append({
                'type': 'other',
                'value': segment
            })
        
        # 중복 제거
        result['expanded_waypoints'] = list(set(result['expanded_waypoints']))
        
        return result
    
    def _get_waypoints_from_route_code(self, route_code: str) -> List[str]:
        """항로코드에서 waypoint 추출"""
        from .nav_data_loader import nav_data_loader
        return nav_data_loader.get_route_waypoints(route_code)

# 전역 인스턴스
upr_parser = UPRParser()

def parse_upr_route(route_text: str) -> List[Tuple[float, float]]:
    """전역 함수: UPR 경로 파싱"""
    return upr_parser.parse_upr_route(route_text)

def parse_route_with_waypoints(route_text: str) -> Dict:
    """전역 함수: waypoint와 좌표가 혼합된 경로 파싱"""
    return upr_parser.parse_route_with_waypoints(route_text)
