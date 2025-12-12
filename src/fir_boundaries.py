"""
FIR 경계 좌표 데이터베이스 및 좌표-다각형 내부 판별 시스템
"""

import re
from typing import List, Tuple, Dict, Optional

class FIRBoundaryDatabase:
    """FIR 경계 좌표 데이터베이스"""
    
    def __init__(self):
        self.fir_boundaries = self._load_fir_boundaries()
    
    def _load_fir_boundaries(self) -> Dict[str, List[Tuple[float, float]]]:
        """FIR 경계 좌표 로드"""
        return {
            'PAZA': self._parse_paza_boundary(),
            'KZAK': self._parse_kzak_boundary(), 
            'RJJJ': self._parse_rjjj_boundary(),  # Fukuoka FIR 추가
            'NZZO': self._parse_nzzo_boundary(),
            'AYPM': self._parse_aypm_boundary()
        }
    
    def _parse_coordinate_string(self, coord_str: str) -> Tuple[float, float]:
        """좌표 문자열을 (위도, 경도) 튜플로 변환"""
        # 544009N 1700000E 형식 파싱
        # 먼저 N/S와 E/W를 분리
        coord_str = coord_str.strip()
        
        # N/S 패턴 찾기
        lat_match = re.search(r'(\d{6})([NS])', coord_str)
        lon_match = re.search(r'(\d{7})([EW])', coord_str)
        
        if lat_match and lon_match:
            lat_val = lat_match.group(1)
            lat_dir = lat_match.group(2)
            lon_val = lon_match.group(1)
            lon_dir = lon_match.group(2)
            
            # 위도 파싱
            lat_deg = float(lat_val[:2])
            lat_min = float(lat_val[2:4])
            lat_sec = float(lat_val[4:6])
            lat = lat_deg + lat_min/60 + lat_sec/3600
            if lat_dir == 'S':
                lat = -lat
            
            # 경도 파싱
            lon_deg = float(lon_val[:3])
            lon_min = float(lon_val[3:5])
            lon_sec = float(lon_val[5:7])
            lon = lon_deg + lon_min/60 + lon_sec/3600
            if lon_dir == 'W':
                lon = -lon
            
            return (lat, lon)
        
        raise ValueError(f"좌표 파싱 실패: {coord_str}")
    
    def _parse_paza_boundary(self) -> List[Tuple[float, float]]:
        """PAZA (Anchorage Oceanic) FIR 경계 파싱 - 제공된 공식 좌표 사용"""
        boundary_text = """
        544009N 1700000E
        513000N 1700000E
        510500N 1734400E
        500800N 1763400W
        454200N 1625500E
        500500N 1590000E
        540000N 1690000E
        544009N 1700000E
        """
        import re
        cleaned = boundary_text
        coord_pairs = re.findall(r'\d{6}[NS]\s+\d{7}[EW]', cleaned)
        coordinates: List[Tuple[float, float]] = []
        for pair in coord_pairs:
            try:
                lat, lon = self._parse_coordinate_string(pair)
                coordinates.append((lat, lon))
            except ValueError as e:
                print(f"PAZA 좌표 파싱 오류: {pair} - {e}")
                continue
        return coordinates
    
    def _parse_kzak_boundary(self) -> List[Tuple[float, float]]:
        """KZAK (Oakland Oceanic) FIR 경계 파싱 - 제공된 공식 좌표 사용"""
        # 사용자가 제공한 KZAK 공식 경계 좌표를 그대로 사용합니다.
        # 일부 항목에 "N/S", "W/E"가 포함되어 있어 전처리로 각각 N, E로 치환합니다
        # (경계 다각형을 닫기 위한 일관된 방향 유지 목적).
        boundary_text = """
        524300N 1350000W
        510000N 1334500W
        482000N 1280000W
        450000N 1263000W
        405900N 1265400W
        405000N 1270000W
        373023N 1270000W
        362743N 1265600W
        353000N 1255000W
        360000N 1241200W
        343000N 1231500W
        304500N 1205000W
        300000N 1200000W
        033000N 1200000W
        033000N 1450000W
        050000S 1550000W
        050000S 1800000W/E
        033000N 1800000W/E
        033000N 1600000E
        000000N/S 1600000E
        000000N/S 1410000E
        033000N 1410000E
        033000N 1330000E
        070000N 1300000E
        210000N 1300000E
        210000N 1550000E
        270000N 1550000E
        270000N 1650000E
        430000N 1650000E
        454200N 1625500E
        500800N 1763400W
        512400N 1674900W
        533000N 1600000W
        560000N 1530000W 564542N 1514500W
        532203N 1370000W
        524300N 1350000W
        """
        
        # 전처리: N/S -> N, W/E -> E (다각형 연속성을 위해 단일 방향 선택)
        cleaned = boundary_text.replace('N/S', 'N').replace('W/E', 'E')
        
        # 행 내에 좌표쌍이 2개 있는 경우(예: "560000N 1530000W 564542N 1514500W")도 처리
        import re
        coord_pairs = re.findall(r'\d{6}[NS]\s+\d{7}[EW]', cleaned)
        coordinates: List[Tuple[float, float]] = []
        
        for pair in coord_pairs:
            try:
                lat, lon = self._parse_coordinate_string(pair)
                coordinates.append((lat, lon))
            except ValueError as e:
                print(f"KZAK 좌표 파싱 오류: {pair} - {e}")
                continue
        
        return coordinates
    
    def _parse_rjjj_boundary(self) -> List[Tuple[float, float]]:
        """RJJJ (Fukuoka) FIR 경계 파싱 - 제공된 공식 좌표 사용"""
        # 사용자가 제공한 RJJJ 공식 경계 좌표를 사용합니다
        boundary_text = """
        454200N 1625500E
        430000N 1650000E
        270000N 1650000E
        270000N 1550000E
        210000N 1550000E
        210000N 1213000E
        403000N 1333900E
        383800N 1333900E
        380000N 1330000E
        373000N 1330000E
        344000N 1291000E
        323000N 1281800E
        300000N 1252500E
        262500N 1230000E
        233000N 1230000E
        210000N 1213000E
        """
        
        import re
        coord_pairs = re.findall(r'\d{6}[NS]\s+\d{7}[EW]', boundary_text)
        coordinates: List[Tuple[float, float]] = []
        
        for pair in coord_pairs:
            try:
                lat, lon = self._parse_coordinate_string(pair)
                coordinates.append((lat, lon))
            except ValueError as e:
                print(f"RJJJ 좌표 파싱 오류: {pair} - {e}")
                continue
        
        return coordinates
    
    def _parse_nzzo_boundary(self) -> List[Tuple[float, float]]:
        """NZZO (Auckland Oceanic) FIR 경계 파싱"""
        boundary_text = """
        300000S 1310000W 900000S 0000000E 300000S 1630000E 280000S 1680000E 
        250000S 1712500E 250000S 1800000E 153245.1S 1754031.2W 050000S 1710000W 
        050000S 1570000W 300000S 1570000W 300000S 1310000W
        """
        
        coordinates = []
        coord_pairs = re.findall(r'\d{6}[NS]\s+\d{7}[EW]', boundary_text)
        
        for coord_pair in coord_pairs:
            try:
                lat, lon = self._parse_coordinate_string(coord_pair)
                coordinates.append((lat, lon))
            except ValueError as e:
                print(f"NZZO 좌표 파싱 오류: {coord_pair} - {e}")
        
        return coordinates
    
    def _parse_aypm_boundary(self) -> List[Tuple[float, float]]:
        """AYPM (Port Moresby) FIR 경계 파싱"""
        # AYPM 경계는 매우 복잡하므로 주요 좌표만 파싱
        boundary_text = """
        000000N 1600000E 045000S 1600000E 045000S 1590000E 120000S 1550000E 
        120000S 1440000E 000000N 1410000E 000000N 1600000E
        """
        
        coordinates = []
        coord_pairs = re.findall(r'\d{6}[NS]\s+\d{7}[EW]', boundary_text)
        
        for coord_pair in coord_pairs:
            try:
                lat, lon = self._parse_coordinate_string(coord_pair)
                coordinates.append((lat, lon))
            except ValueError as e:
                print(f"AYPM 좌표 파싱 오류: {coord_pair} - {e}")
        
        return coordinates

class PointInPolygonChecker:
    """점-다각형 내부 판별 알고리즘"""
    
    @staticmethod
    def is_point_in_polygon(point: Tuple[float, float], polygon: List[Tuple[float, float]]) -> bool:
        """
        Ray Casting 알고리즘을 사용하여 점이 다각형 내부에 있는지 판별
        
        Args:
            point: (위도, 경도) 튜플
            polygon: 다각형 꼭짓점들의 리스트 [(위도, 경도), ...]
            
        Returns:
            bool: 점이 다각형 내부에 있으면 True
        """
        x, y = point
        n = len(polygon)
        inside = False
        
        p1x, p1y = polygon[0]
        for i in range(1, n + 1):
            p2x, p2y = polygon[i % n]
            if y > min(p1y, p2y):
                if y <= max(p1y, p2y):
                    if x <= max(p1x, p2x):
                        if p1y != p2y:
                            xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                        if p1x == p2x or x <= xinters:
                            inside = not inside
            p1x, p1y = p2x, p2y
        
        return inside
    
    @staticmethod
    def is_point_in_polygon_simple(point: Tuple[float, float], polygon: List[Tuple[float, float]]) -> bool:
        """
        간단한 경계 박스 검사 + Ray Casting
        """
        x, y = point
        
        # 경계 박스 검사
        min_x = min(p[0] for p in polygon)
        max_x = max(p[0] for p in polygon)
        min_y = min(p[1] for p in polygon)
        max_y = max(p[1] for p in polygon)
        
        if x < min_x or x > max_x or y < min_y or y > max_y:
            return False
        
        # Ray Casting 알고리즘
        n = len(polygon)
        inside = False
        
        p1x, p1y = polygon[0]
        for i in range(1, n + 1):
            p2x, p2y = polygon[i % n]
            if y > min(p1y, p2y):
                if y <= max(p1y, p2y):
                    if x <= max(p1x, p2x):
                        if p1y != p2y:
                            xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                        if p1x == p2x or x <= xinters:
                            inside = not inside
            p1x, p1y = p2x, p2y
        
        return inside

class FIRIdentifier:
    """FIR 식별기"""
    
    def __init__(self):
        self.boundary_db = FIRBoundaryDatabase()
        self.polygon_checker = PointInPolygonChecker()
    
    def identify_fir_by_coordinate(self, lat: float, lon: float) -> Optional[str]:
        """
        좌표를 기반으로 FIR 식별 (경계 박스 기반)
        
        Args:
            lat: 위도
            lon: 경도
            
        Returns:
            str: FIR 코드 (예: 'PAZA', 'KZAK', 'NZZO', 'AYPM') 또는 None
        """
        for fir_code, boundary in self.boundary_db.fir_boundaries.items():
            # 경계 박스 검사 (날짜변경선 처리 포함)
            if self._is_point_in_fir_boundary_box((lat, lon), boundary):
                return fir_code
        
        return None
    
    def _is_point_in_fir_boundary_box(self, point: Tuple[float, float], boundary: List[Tuple[float, float]]) -> bool:
        """
        경계 박스 기반 점-다각형 내부 판별 (날짜변경선 처리)
        
        Args:
            point: (위도, 경도) 튜플
            boundary: 다각형 경계 좌표 리스트
            
        Returns:
            bool: 점이 경계 박스 내부에 있으면 True
        """
        lat, lon = point
        
        # 경계 박스 계산
        min_lat = min(p[0] for p in boundary)
        max_lat = max(p[0] for p in boundary)
        min_lon = min(p[1] for p in boundary)
        max_lon = max(p[1] for p in boundary)
        
        # 날짜변경선 처리
        if min_lon < 0 and max_lon > 0:  # 날짜변경선을 넘나드는 경우
            # 동경과 서경 모두 고려
            return (min_lat <= lat <= max_lat and 
                   (min_lon <= lon <= 180.0 or -180.0 <= lon <= max_lon))
        else:
            # 일반적인 경우
            return min_lat <= lat <= max_lat and min_lon <= lon <= max_lon
    
    def analyze_upr_route(self, upr_coordinates: List[Tuple[float, float]]) -> Dict:
        """
        UPR 좌표 구간을 분석하여 통과하는 FIR 식별
        
        Args:
            upr_coordinates: UPR 좌표 리스트 [(위도, 경도), ...]
            
        Returns:
            Dict: 분석 결과
        """
        result = {
            'coordinates': [],
            'traversed_firs': [],
            'fir_segments': {}
        }
        
        current_fir = None
        segment_start = 0
        
        for i, (lat, lon) in enumerate(upr_coordinates):
            fir = self.identify_fir_by_coordinate(lat, lon)
            
            coord_info = {
                'index': i,
                'lat': lat,
                'lon': lon,
                'fir': fir
            }
            result['coordinates'].append(coord_info)
            
            # FIR 변경 감지
            if fir != current_fir:
                if current_fir is not None:
                    # 이전 FIR 세그먼트 종료
                    if current_fir not in result['fir_segments']:
                        result['fir_segments'][current_fir] = []
                    result['fir_segments'][current_fir].append({
                        'start_index': segment_start,
                        'end_index': i - 1,
                        'coordinates': upr_coordinates[segment_start:i]
                    })
                
                # 새 FIR 세그먼트 시작
                current_fir = fir
                segment_start = i
                
                if fir and fir not in result['traversed_firs']:
                    result['traversed_firs'].append(fir)
        
        # 마지막 세그먼트 처리
        if current_fir is not None:
            if current_fir not in result['fir_segments']:
                result['fir_segments'][current_fir] = []
            result['fir_segments'][current_fir].append({
                'start_index': segment_start,
                'end_index': len(upr_coordinates) - 1,
                'coordinates': upr_coordinates[segment_start:]
            })
        
        return result

# 전역 인스턴스
fir_identifier = FIRIdentifier()

def identify_fir_by_coordinate(lat: float, lon: float) -> Optional[str]:
    """전역 함수: 좌표로 FIR 식별"""
    return fir_identifier.identify_fir_by_coordinate(lat, lon)

def analyze_upr_route(upr_coordinates: List[Tuple[float, float]]) -> Dict:
    """전역 함수: UPR 경로 분석"""
    return fir_identifier.analyze_upr_route(upr_coordinates)
