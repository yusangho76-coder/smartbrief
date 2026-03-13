"""
FIR 기반 NOTAM 필터링 시스템
좌표 구간이 속한 FIR의 NOTAM만 선별
"""

import math
from typing import List, Dict, Any, Optional, Tuple
from .fir_boundaries import identify_fir_by_coordinate, analyze_upr_route
from .upr_parser import parse_route_with_waypoints
from .nav_data_loader import get_waypoint_coordinates, estimate_waypoint_fir

class FIRNotamFilter:
    """FIR 기반 NOTAM 필터링 클래스"""
    
    def __init__(self):
        # FIR별 공항 코드 매핑 (ICAO 코드 첫 2글자 기준)
        self.fir_airport_mapping = {
            'PAZA': ['PA', 'KZ'],  # Anchorage Oceanic FIR (알래스카 + 미국 서부)
            'KZAK': ['KZ'],        # Oakland Oceanic FIR  
            'NZZO': ['NZ'],        # Auckland Oceanic FIR
            'AYPM': ['AY'],        # Port Moresby FIR
            'RJJJ': ['RJ', 'RK'],  # Fukuoka FIR (일본 + 한국)
        }
        
        # 추가 공항 코드 매핑 (특정 공항별)
        self.specific_airport_mapping = {
            'RKSI': 'RJJJ',  # 인천 -> Fukuoka FIR
            'KSEA': 'PAZA',  # 시애틀 -> Anchorage Oceanic FIR
            'KPDX': 'PAZA',  # 포틀랜드 -> Anchorage Oceanic FIR
        }
    
    def filter_notams_by_fir(self, notams_data: List[Dict[str, Any]], fir_codes: List[str]) -> List[Dict[str, Any]]:
        """
        FIR 코드 목록에 해당하는 NOTAM만 필터링
        
        Args:
            notams_data: NOTAM 데이터 리스트
            fir_codes: FIR 코드 리스트 (예: ['PAZA', 'KZAK'])
            
        Returns:
            List[Dict[str, Any]]: 필터링된 NOTAM 리스트
        """
        filtered_notams = []
        
        for notam in notams_data:
            if self._is_notam_relevant_to_firs(notam, fir_codes):
                filtered_notams.append(notam)
        
        return filtered_notams
    
    def _is_notam_relevant_to_firs(self, notam: Dict[str, Any], fir_codes: List[str]) -> bool:
        """
        NOTAM이 지정된 FIR들과 관련이 있는지 확인
        
        Args:
            notam: NOTAM 데이터
            fir_codes: FIR 코드 리스트
            
        Returns:
            bool: 관련이 있으면 True
        """
        # NOTAM에서 공항 코드 추출
        airport_codes = self._extract_airport_codes_from_notam(notam)
        
        # 각 공항 코드가 해당 FIR에 속하는지 확인
        for airport_code in airport_codes:
            airport_fir = self._get_fir_from_airport_code(airport_code)
            if airport_fir in fir_codes:
                return True
        
        return False
    
    def _extract_airport_codes_from_notam(self, notam: Dict[str, Any]) -> List[str]:
        """
        NOTAM에서 공항 코드 추출 (웹 인터페이스 데이터 구조 지원)
        
        Args:
            notam: NOTAM 데이터
            
        Returns:
            List[str]: 공항 코드 리스트
        """
        airport_codes = []
        
        # 1. airports 필드에서 추출 (웹 인터페이스 데이터)
        if 'airports' in notam and isinstance(notam['airports'], list):
            airport_codes.extend(notam['airports'])
        
        # 2. airport_code 필드에서 추출 (기존 데이터)
        if 'airport_code' in notam and notam['airport_code']:
            airport_codes.append(notam['airport_code'])
        
        # 3. text/description 필드에서 4글자 대문자 패턴 추출
        text_field = notam.get('text', '') or notam.get('description', '')
        if text_field:
            import re
            codes = re.findall(r'\b[A-Z]{4}\b', text_field)
            airport_codes.extend(codes)
        
        # 중복 제거 및 빈 문자열 제거
        airport_codes = [code for code in airport_codes if code and len(code) == 4]
        return list(set(airport_codes))
    
    def _get_fir_from_airport_code(self, airport_code: str) -> Optional[str]:
        """
        공항 코드로부터 FIR 코드 추출
        
        Args:
            airport_code: 공항 코드 (예: 'KSEA', 'RJTT')
            
        Returns:
            Optional[str]: FIR 코드 또는 None
        """
        if len(airport_code) < 2:
            return None
        
        # 1. 특정 공항 매핑 확인 (우선순위)
        if airport_code in self.specific_airport_mapping:
            return self.specific_airport_mapping[airport_code]
        
        # 2. 일반적인 FIR 매핑 확인
        airport_prefix = airport_code[:2]
        for fir_code, prefixes in self.fir_airport_mapping.items():
            if airport_prefix in prefixes:
                return fir_code
        
        return None
    
    def analyze_route_with_fir_notams(self, route_text: str, notams_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        경로를 분석하여 FIR별 NOTAM 필터링
        
        Args:
            route_text: 경로 텍스트
            notams_data: NOTAM 데이터 리스트
            
        Returns:
            Dict[str, Any]: 분석 결과
        """
        # 1. 경로 파싱
        parsed_route = parse_route_with_waypoints(route_text)
        
        # 2. 좌표 구간에서 FIR 분석
        coordinates: List[Tuple[float, float]] = parsed_route.get('coordinates', [])
        fir_analysis = analyze_upr_route(coordinates) if coordinates else {}
        
        # 3. FIR별 NOTAM 필터링 (중복 제거)
        traversed_firs = fir_analysis.get('traversed_firs', [])
        fir_notams = {}
        
        for fir_code in traversed_firs:
            filtered_notams = self.filter_notams_by_fir(notams_data, [fir_code])
            # 중복 제거: notam_number + airports 조합으로 고유 ID 생성
            unique_notams = {}
            for notam in filtered_notams:
                notam_id = notam.get('notam_number', '') + str(notam.get('airports', []))
                if notam_id not in unique_notams:
                    unique_notams[notam_id] = notam
            fir_notams[fir_code] = list(unique_notams.values())
        
        # 4. waypoint 기반 NOTAM 필터링 (확장된 waypoint 포함 + 거리 기반 150NM 필터링)
        all_waypoints = parsed_route.get('waypoints', []) + parsed_route.get('expanded_waypoints', [])
        waypoint_notams = self._filter_notams_by_waypoints(
            all_waypoints, 
            notams_data,
            route_coordinates=coordinates
        )
        
        # 5. waypoint FIR 분석 (새로운 기능)
        waypoint_fir_analysis = self._analyze_waypoint_firs(parsed_route.get('waypoints', []))
        
        return {
            'parsed_route': parsed_route,
            'fir_analysis': fir_analysis,
            'fir_notams': fir_notams,
            'waypoint_notams': waypoint_notams,
            'waypoint_fir_analysis': waypoint_fir_analysis,
            'traversed_firs': traversed_firs,
            'total_relevant_notams': self._count_total_relevant_notams(fir_notams, waypoint_notams)
        }
    
    def _filter_notams_by_waypoints(
        self,
        waypoints: List[str],
        notams_data: List[Dict[str, Any]],
        route_coordinates: Optional[List[Tuple[float, float]]] = None,
        max_distance_nm: float = 150.0,
    ) -> List[Dict[str, Any]]:
        """
        waypoint 기반 NOTAM 필터링 (다단계 매칭 시스템)
        
        Args:
            waypoints: waypoint 리스트
            notams_data: NOTAM 데이터 리스트
            
        Returns:
            List[Dict[str, Any]]: 필터링된 NOTAM 리스트
        """
        filtered_notams: List[Dict[str, Any]] = []
        upper_waypoints = [wp.upper() for wp in waypoints]

        for notam in notams_data:
            description = (notam.get('description', '') or '').upper()
            text = (notam.get('text', '') or '').upper()
            full_text = f"{description} {text}"

            is_candidate = False

            # 1단계: 직접 waypoint 매칭 (가장 정확)
            if any(wp in full_text for wp in upper_waypoints):
                is_candidate = True
            else:
                # 2단계: waypoint FIR 기반 매칭 (패턴 + 좌표 기반)
                for waypoint in upper_waypoints:
                    waypoint_fir = estimate_waypoint_fir(waypoint)
                    if waypoint_fir and self._is_notam_in_fir(notam, waypoint_fir):
                        is_candidate = True
                        break

            # 3단계: 항로코드 기반 waypoint 확장 매칭
            if not is_candidate:
                expanded_waypoints = self._expand_waypoints_from_route_codes(upper_waypoints)
                if any(wp in full_text for wp in expanded_waypoints):
                    is_candidate = True

            # 4단계: 거리 기반 필터링 (Haversine, 150NM 이내만 유지)
            if is_candidate and route_coordinates:
                notam_coord = notam.get('coordinates')
                if isinstance(notam_coord, dict):
                    lat = notam_coord.get('latitude')
                    lon = notam_coord.get('longitude')
                    if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
                        min_dist = self._min_distance_to_route(lat, lon, route_coordinates)
                        # 150NM보다 먼 좌표만 언급하는 NOTAM은 제외
                        if min_dist is None or min_dist > max_distance_nm:
                            continue

            if is_candidate:
                filtered_notams.append(notam)

        return filtered_notams
    
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
    
    def _expand_waypoints_from_route_codes(self, waypoints: List[str]) -> List[str]:
        """항로코드에서 추가 waypoint 추출"""
        from .nav_data_loader import nav_data_loader
        
        expanded_waypoints = []
        
        # 항로코드 패턴 찾기 (Y697, R591 등)
        import re
        route_codes = re.findall(r'[A-Z]\d{3}', ' '.join(waypoints))
        
        for route_code in route_codes:
            route_waypoints = nav_data_loader.get_route_waypoints(route_code)
            expanded_waypoints.extend(route_waypoints)
        
        return expanded_waypoints
    
    def _analyze_waypoint_firs(self, waypoints: List[str]) -> Dict[str, Any]:
        """
        waypoint들의 FIR 분석
        
        Args:
            waypoints: waypoint 리스트
            
        Returns:
            Dict[str, Any]: waypoint FIR 분석 결과
        """
        result = {
            'waypoint_firs': {},
            'fir_waypoints': {},
            'unknown_waypoints': []
        }
        
        for waypoint in waypoints:
            # waypoint 좌표 조회
            coords = get_waypoint_coordinates(waypoint)
            if coords:
                lat, lon = coords
                # 좌표 기반 FIR 식별
                fir = identify_fir_by_coordinate(lat, lon)
                if fir:
                    result['waypoint_firs'][waypoint] = {
                        'fir': fir,
                        'coordinates': coords
                    }
                    
                    # FIR별 waypoint 그룹화
                    if fir not in result['fir_waypoints']:
                        result['fir_waypoints'][fir] = []
                    result['fir_waypoints'][fir].append(waypoint)
                else:
                    result['unknown_waypoints'].append(waypoint)
            else:
                # 좌표가 없는 경우 FIR 추정
                estimated_fir = estimate_waypoint_fir(waypoint)
                if estimated_fir:
                    result['waypoint_firs'][waypoint] = {
                        'fir': estimated_fir,
                        'coordinates': None,
                        'estimated': True
                    }
                    
                    if estimated_fir not in result['fir_waypoints']:
                        result['fir_waypoints'][estimated_fir] = []
                    result['fir_waypoints'][estimated_fir].append(waypoint)
                else:
                    result['unknown_waypoints'].append(waypoint)
        
        return result

    # ------------------------------------------------------------------
    # 거리 기반 필터링 유틸리티 (Haversine, NM 단위)
    # ------------------------------------------------------------------
    def _haversine_nm(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """두 지점 간 대권거리를 해리 단위로 계산 (Haversine)."""
        # 지구 반경 (NM)
        R_nm = 3440.065

        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)

        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R_nm * c

    def _min_distance_to_route(
        self,
        lat: float,
        lon: float,
        route_coordinates: List[Tuple[float, float]],
    ) -> Optional[float]:
        """NOTAM 좌표와 항로 좌표 시퀀스 간 최소 거리(NM)를 계산."""
        if not route_coordinates:
            return None

        min_dist = None
        for rlat, rlon in route_coordinates:
            try:
                d = self._haversine_nm(lat, lon, rlat, rlon)
            except Exception:
                continue
            if min_dist is None or d < min_dist:
                min_dist = d
        return min_dist
    
    def _count_total_relevant_notams(self, fir_notams: Dict[str, List], waypoint_notams: List) -> int:
        """
        전체 관련 NOTAM 수 계산 (중복 제거)
        
        Args:
            fir_notams: FIR별 NOTAM 딕셔너리
            waypoint_notams: waypoint 기반 NOTAM 리스트
            
        Returns:
            int: 전체 관련 NOTAM 수
        """
        all_notams = set()
        
        # FIR 기반 NOTAM 추가
        for fir_code, notams in fir_notams.items():
            for notam in notams:
                # 웹 인터페이스 데이터 구조 지원
                notam_id = notam.get('notam_number', '') + str(notam.get('airports', []))
                all_notams.add(notam_id)
        
        # waypoint 기반 NOTAM 추가 (중복 제거)
        for notam in waypoint_notams:
            # 웹 인터페이스 데이터 구조 지원
            notam_id = notam.get('notam_number', '') + str(notam.get('airports', []))
            all_notams.add(notam_id)
        
        return len(all_notams)
    
    def generate_fir_analysis_report(self, analysis_result: Dict[str, Any]) -> str:
        """
        FIR 분석 결과를 보고서 형태로 생성
        
        Args:
            analysis_result: analyze_route_with_fir_notams 결과
            
        Returns:
            str: 분석 보고서
        """
        report = []
        report.append("## FIR 기반 NOTAM 분석 보고서\n")
        
        # 경로 정보
        parsed_route = analysis_result.get('parsed_route', {})
        report.append(f"**분석 경로:** {len(parsed_route.get('coordinates', []))}개 좌표, {len(parsed_route.get('waypoints', []))}개 waypoint")
        report.append("")
        
        # FIR 통과 정보
        fir_analysis = analysis_result.get('fir_analysis', {})
        traversed_firs = analysis_result.get('traversed_firs', [])
        
        if traversed_firs:
            report.append("### 통과하는 FIR")
            for fir_code in traversed_firs:
                fir_segments = fir_analysis.get('fir_segments', {}).get(fir_code, [])
                report.append(f"- **{fir_code}**: {len(fir_segments)}개 구간")
            report.append("")
        
        # FIR별 NOTAM 분석
        fir_notams = analysis_result.get('fir_notams', {})
        if fir_notams:
            report.append("### FIR별 관련 NOTAM")
            for fir_code, notams in fir_notams.items():
                report.append(f"#### {fir_code} FIR ({len(notams)}개 NOTAM)")
                for notam in notams[:5]:  # 최대 5개만 표시
                    airport = notam.get('airport_code', 'N/A')
                    notam_num = notam.get('notam_number', 'N/A')
                    report.append(f"- {airport} {notam_num}")
                if len(notams) > 5:
                    report.append(f"- ... 외 {len(notams) - 5}개")
                report.append("")
        
        # waypoint 기반 NOTAM
        waypoint_notams = analysis_result.get('waypoint_notams', [])
        if waypoint_notams:
            report.append(f"### Waypoint 기반 NOTAM ({len(waypoint_notams)}개)")
            for notam in waypoint_notams[:5]:  # 최대 5개만 표시
                airport = notam.get('airport_code', 'N/A')
                notam_num = notam.get('notam_number', 'N/A')
                report.append(f"- {airport} {notam_num}")
            if len(waypoint_notams) > 5:
                report.append(f"- ... 외 {len(waypoint_notams) - 5}개")
            report.append("")
        
        # 요약
        total_notams = analysis_result.get('total_relevant_notams', 0)
        report.append(f"### 요약")
        report.append(f"- **총 관련 NOTAM 수**: {total_notams}개")
        report.append(f"- **통과 FIR 수**: {len(traversed_firs)}개")
        report.append(f"- **분석된 좌표 수**: {len(parsed_route.get('coordinates', []))}개")
        
        return "\n".join(report)

# 전역 인스턴스
fir_notam_filter = FIRNotamFilter()

def filter_notams_by_fir(notams_data: List[Dict[str, Any]], fir_codes: List[str]) -> List[Dict[str, Any]]:
    """전역 함수: FIR 기반 NOTAM 필터링"""
    return fir_notam_filter.filter_notams_by_fir(notams_data, fir_codes)

def analyze_route_with_fir_notams(route_text: str, notams_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """전역 함수: 경로 FIR 분석"""
    return fir_notam_filter.analyze_route_with_fir_notams(route_text, notams_data)
