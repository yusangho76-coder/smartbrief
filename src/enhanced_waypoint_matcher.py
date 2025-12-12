"""
향상된 Waypoint 매칭 시스템
전세계 waypoint 데이터베이스 없이도 효과적인 매칭 수행
"""

import re
from typing import List, Dict, Any, Optional, Tuple
from .nav_data_loader import get_waypoint_coordinates, estimate_waypoint_fir

class EnhancedWaypointMatcher:
    """향상된 Waypoint 매칭 클래스"""
    
    def __init__(self):
        # 지역별 waypoint 패턴 매핑
        self.regional_patterns = {
            'RJJJ': {  # Fukuoka FIR (한국, 일본, 중국, 대만, 홍콩)
                'prefixes': ['EG', 'RK', 'VH', 'RC', 'RJ', 'RO'],
                'keywords': ['KOREA', 'JAPAN', 'CHINA', 'TAIWAN', 'HONGKONG']
            },
            'PAZA': {  # Anchorage Oceanic FIR (미국, 캐나다)
                'prefixes': ['K', 'P', 'C'],
                'keywords': ['USA', 'CANADA', 'ALASKA']
            },
            'KZAK': {  # Oakland Oceanic FIR (태평양 중앙)
                'prefixes': ['KZ'],
                'keywords': ['PACIFIC', 'OCEANIC']
            }
        }
        
        # 항로코드별 waypoint 매핑 (확장 가능)
        self.route_waypoint_mapping = {
            'Y697': ['EGOBA', 'LANAT'],
            'Y51': ['LANAT', 'SAMON'],
            'Y142': ['SAMON', 'GTC'],
            'Y512': ['GTC', 'ADNAP'],
            'R591': ['ADNAP', 'ADGOR'],
            'A1': ['EGOBA', 'BOPTA'],
            'G581': ['GTC', 'ADNAP'],
            'M503': ['ADNAP', 'ADGOR'],
        }
    
    def extract_waypoints_from_route(self, route_text: str) -> List[str]:
        """항로 텍스트에서 waypoint 추출"""
        waypoints = []
        
        # 1. 직접 waypoint 추출 (3-5글자 대문자)
        waypoint_pattern = r'\b[A-Z]{3,5}\b'
        found_waypoints = re.findall(waypoint_pattern, route_text)
        
        # 2. 항로코드에서 waypoint 추출
        route_codes = re.findall(r'[A-Z]\d{3}', route_text)
        for route_code in route_codes:
            route_waypoints = self.route_waypoint_mapping.get(route_code, [])
            waypoints.extend(route_waypoints)
        
        # 3. 공항코드 제외 (4글자)
        waypoints = [wp for wp in found_waypoints if len(wp) != 4]
        
        return list(set(waypoints))  # 중복 제거
    
    def estimate_waypoint_fir_by_pattern(self, waypoint: str) -> Optional[str]:
        """waypoint 이름 패턴으로 FIR 추정"""
        waypoint_upper = waypoint.upper()
        
        for fir_code, patterns in self.regional_patterns.items():
            # 접두사 패턴 확인
            for prefix in patterns['prefixes']:
                if waypoint_upper.startswith(prefix):
                    return fir_code
            
            # 키워드 패턴 확인 (waypoint 이름에 포함된 경우)
            for keyword in patterns['keywords']:
                if keyword in waypoint_upper:
                    return fir_code
        
        return None
    
    def match_notams_by_waypoints(self, waypoints: List[str], notams_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """waypoint 기반 NOTAM 매칭 (다단계 접근)"""
        matched_notams = []
        
        for notam in notams_data:
            description = notam.get('description', '').upper()
            text = notam.get('text', '').upper()
            full_text = f"{description} {text}"
            
            # 1단계: 직접 waypoint 매칭
            for waypoint in waypoints:
                if waypoint.upper() in full_text:
                    matched_notams.append(notam)
                    break
            
            # 2단계: waypoint FIR 기반 매칭
            if not any(wp.upper() in full_text for wp in waypoints):
                for waypoint in waypoints:
                    waypoint_fir = self.estimate_waypoint_fir_by_pattern(waypoint)
                    if waypoint_fir:
                        # NOTAM의 공항이 해당 FIR에 속하는지 확인
                        if self._is_notam_in_fir(notam, waypoint_fir):
                            matched_notams.append(notam)
                            break
            
            # 3단계: 좌표 기반 매칭 (waypoint 좌표가 있는 경우)
            if not any(wp.upper() in full_text for wp in waypoints):
                for waypoint in waypoints:
                    coords = get_waypoint_coordinates(waypoint)
                    if coords:
                        waypoint_fir = estimate_waypoint_fir(waypoint)
                        if waypoint_fir and self._is_notam_in_fir(notam, waypoint_fir):
                            matched_notams.append(notam)
                            break
        
        return matched_notams
    
    def _is_notam_in_fir(self, notam: Dict[str, Any], fir_code: str) -> bool:
        """NOTAM이 특정 FIR에 속하는지 확인"""
        # 공항코드에서 FIR 추정
        airports = notam.get('airports', [])
        if isinstance(airports, list):
            for airport in airports:
                if self._get_fir_from_airport_code(airport) == fir_code:
                    return True
        
        # airport_code 필드 확인
        airport_code = notam.get('airport_code', '')
        if self._get_fir_from_airport_code(airport_code) == fir_code:
            return True
        
        return False
    
    def _get_fir_from_airport_code(self, airport_code: str) -> Optional[str]:
        """공항코드로부터 FIR 추정"""
        if not airport_code or len(airport_code) != 4:
            return None
        
        # ICAO 코드 첫 2글자로 FIR 추정
        prefix = airport_code[:2]
        
        if prefix in ['RK', 'EG']:
            return 'RJJJ'  # Fukuoka FIR
        elif prefix in ['K', 'P']:
            return 'PAZA'  # Anchorage Oceanic FIR
        elif prefix == 'KZ':
            return 'KZAK'  # Oakland Oceanic FIR
        elif prefix in ['VH', 'RC']:
            return 'RJJJ'  # Fukuoka FIR
        
        return None
    
    def analyze_route_waypoints(self, route_text: str) -> Dict[str, Any]:
        """항로의 waypoint 분석"""
        waypoints = self.extract_waypoints_from_route(route_text)
        
        analysis = {
            'waypoints': waypoints,
            'waypoint_firs': {},
            'fir_coverage': set(),
            'unknown_waypoints': []
        }
        
        for waypoint in waypoints:
            # 1. 좌표 기반 FIR 추정
            coords = get_waypoint_coordinates(waypoint)
            if coords:
                fir = estimate_waypoint_fir(waypoint)
                if fir:
                    analysis['waypoint_firs'][waypoint] = fir
                    analysis['fir_coverage'].add(fir)
                    continue
            
            # 2. 패턴 기반 FIR 추정
            fir = self.estimate_waypoint_fir_by_pattern(waypoint)
            if fir:
                analysis['waypoint_firs'][waypoint] = fir
                analysis['fir_coverage'].add(fir)
            else:
                analysis['unknown_waypoints'].append(waypoint)
        
        analysis['fir_coverage'] = list(analysis['fir_coverage'])
        
        return analysis

# 전역 인스턴스
enhanced_waypoint_matcher = EnhancedWaypointMatcher()
