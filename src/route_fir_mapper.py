"""
항로 문자열을 NavData 및 FIR GeoJSON과 매칭하는 도우미

주요 기능:
- Navigraph NavData(waypoint/airway) 기반으로 항로 문자열을 실제 좌표 시퀀스로 확장
- FIR GeoJSON 데이터를 활용하여 항로가 통과하는 FIR 순서 계산
- 각 waypoint 별 FIR 소속 정보 제공
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from .nav_data_loader import nav_data_loader
from .fir_geo_reference import fir_geo_reference


@dataclass
class RoutePoint:
    ident: str
    lat: float
    lon: float
    source: str
    token: str
    inserted: bool = False
    airway: Optional[str] = None
    fir: Optional[str] = None


class RouteFIRMapper:
    """항로 문자열을 FIR 시퀀스로 매칭하는 유틸리티 클래스"""

    AIRWAY_PATTERN = re.compile(r"^[A-Z]{1,5}\d{1,4}$")

    def __init__(self, nav_loader=nav_data_loader, fir_reference=fir_geo_reference):
        self.nav_loader = nav_loader
        self.fir_reference = fir_reference

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------
    def analyze_route(self, route: str) -> Dict[str, object]:
        """
        항로 문자열을 분석하여 FIR 통과 순서를 계산.

        Returns:
            {
                'tokens': [...],
                'points': [RoutePoint dict...],
                'unresolved_tokens': [...],
                'warnings': [...],
                'fir_sequence': [...],
                'fir_segments': [...],
            }
        """
        tokens = self._tokenize_route(route)
        points, unresolved, warnings = self._build_point_sequence(tokens)

        fir_sequence: List[str] = []
        fir_segments: List[Dict[str, object]] = []

        if len(points) >= 2:
            coordinates = [(point.lat, point.lon) for point in points]
            if self.fir_reference:
                trace = self.fir_reference.trace_route(coordinates)
                fir_sequence = trace.get("fir_sequence", [])
                fir_segments = self._enrich_segments(trace.get("segments", []), points)
                waypoint_firs = trace.get("waypoint_firs", [])
                for idx, fir_code in enumerate(waypoint_firs):
                    if idx < len(points):
                        points[idx].fir = fir_code
            else:
                fir_sequence = self._fallback_fir_sequence(points)

        # fallback FIR 표기
        for point in points:
            if not point.fir:
                point.fir = self.nav_loader.estimate_waypoint_fir(point.ident)

        return {
            "tokens": tokens,
            "points": [point.__dict__ for point in points],
            "unresolved_tokens": unresolved,
            "warnings": warnings,
            "fir_sequence": fir_sequence,
            "fir_segments": fir_segments,
        }

    # ------------------------------------------------------------------
    # 내부 구현
    # ------------------------------------------------------------------
    def _tokenize_route(self, route: str) -> List[str]:
        sanitized = re.sub(r"[.\s]+", " ", route.strip().upper())
        tokens = [token for token in sanitized.split(" ") if token]
        return tokens

    def _build_point_sequence(
        self, tokens: Sequence[str]
    ) -> Tuple[List[RoutePoint], List[str], List[str]]:
        points: List[RoutePoint] = []
        unresolved: List[str] = []
        warnings: List[str] = []

        previous_ident: Optional[str] = None
        pending_airway: Optional[str] = None
        previous_coord: Optional[Tuple[float, float]] = None

        for token in tokens:
            if self._is_airway(token):
                pending_airway = token
                continue

            point = self._resolve_token(token, previous_coord)
            if not point:
                unresolved.append(token)
                pending_airway = None
                continue

            if pending_airway and previous_ident:
                inserted_points = self._expand_airway_segment(pending_airway, previous_ident, point.ident)
                if inserted_points is None:
                    warnings.append(
                        f"{pending_airway} 항로에서 {previous_ident}->{point.ident} 구간을 찾지 못했습니다."
                    )
                else:
                    for intermediate in inserted_points:
                        if intermediate in {previous_ident, point.ident}:
                            continue
                        coord = self.nav_loader.get_waypoint_coordinates(intermediate, previous_coord)
                        if not coord:
                            warnings.append(f"{pending_airway} 항로 중간 waypoint {intermediate} 좌표를 찾지 못했습니다.")
                            continue
                        source = self.nav_loader.get_coordinate_source(intermediate) or "awys"
                        intermediate_point = RoutePoint(
                            ident=intermediate,
                            lat=coord[0],
                            lon=coord[1],
                            source=source,
                            token=intermediate,
                            inserted=True,
                            airway=pending_airway,
                        )
                        points.append(intermediate_point)
                        previous_coord = (intermediate_point.lat, intermediate_point.lon)
            points.append(point)
            previous_ident = point.ident
            previous_coord = (point.lat, point.lon)
            pending_airway = None

        return points, unresolved, warnings

    def _resolve_token(
        self,
        token: str,
        reference: Optional[Tuple[float, float]],
    ) -> Optional[RoutePoint]:
        coord = self._parse_coordinate(token)
        if coord:
            return RoutePoint(
                ident=token,
                lat=coord[0],
                lon=coord[1],
                source="coordinate",
                token=token,
            )

        coords = self.nav_loader.get_waypoint_coordinates(token, reference)
        if not coords:
            return None

        source = self.nav_loader.get_coordinate_source(token) or "navdata"
        return RoutePoint(
            ident=token,
            lat=coords[0],
            lon=coords[1],
            source=source,
            token=token,
        )

    def _expand_airway_segment(
        self, airway: str, start_ident: str, end_ident: str
    ) -> Optional[List[str]]:
        waypoints = self.nav_loader.get_airway_waypoints(airway)
        if not waypoints:
            return None

        try:
            start_idx = waypoints.index(start_ident)
            end_idx = waypoints.index(end_ident)
        except ValueError:
            return None

        if start_idx < end_idx:
            return waypoints[start_idx : end_idx + 1]
        elif start_idx > end_idx:
            segment = list(reversed(waypoints[end_idx : start_idx + 1]))
            return segment
        else:
            return [start_ident]

    def _enrich_segments(
        self, segments: Sequence[Dict[str, object]], points: Sequence[RoutePoint]
    ) -> List[Dict[str, object]]:
        enriched: List[Dict[str, object]] = []
        for segment in segments:
            start_idx = int(segment.get("start_index", 0))
            end_idx = int(segment.get("end_index", start_idx))
            enriched.append(
                {
                    **segment,
                    "start_ident": points[start_idx].ident if 0 <= start_idx < len(points) else None,
                    "end_ident": points[end_idx].ident if 0 <= end_idx < len(points) else None,
                }
            )
        return enriched

    def _fallback_fir_sequence(self, points: Sequence[RoutePoint]) -> List[str]:
        sequence: List[str] = []
        for point in points:
            fir_code = self.nav_loader.estimate_waypoint_fir(point.ident)
            if fir_code and (not sequence or sequence[-1] != fir_code):
                sequence.append(fir_code)
        return sequence

    @classmethod
    def _is_airway(cls, token: str) -> bool:
        return bool(cls.AIRWAY_PATTERN.match(token))

    # ------------------------------------------------------------------
    # 좌표 파싱 로직
    # ------------------------------------------------------------------
    COORD_PATTERN_PREFIX = re.compile(
        r"^([NS])(\d{2,6}(?:\.\d+)?)([EW])(\d{3,7}(?:\.\d+)?)$"
    )
    COORD_PATTERN_SUFFIX = re.compile(
        r"^(\d{2,6}(?:\.\d+)?)([NS])(\d{3,7}(?:\.\d+)?)([EW])$"
    )

    def _parse_coordinate(self, token: str) -> Optional[Tuple[float, float]]:
        token = token.strip().upper()
        if not token:
            return None

        match = self.COORD_PATTERN_PREFIX.match(token)
        if match:
            lat_dir, lat_part, lon_dir, lon_part = match.groups()
            lat = self._decode_coordinate_component(lat_part, 2)
            lon = self._decode_coordinate_component(lon_part, 3)
            if lat is None or lon is None:
                return None
            if lat_dir == "S":
                lat = -lat
            if lon_dir == "W":
                lon = -lon
            return lat, lon

        match = self.COORD_PATTERN_SUFFIX.match(token)
        if match:
            lat_part, lat_dir, lon_part, lon_dir = match.groups()
            lat = self._decode_coordinate_component(lat_part, 2)
            lon = self._decode_coordinate_component(lon_part, 3)
            if lat is None or lon is None:
                return None
            if lat_dir == "S":
                lat = -lat
            if lon_dir == "W":
                lon = -lon
            return lat, lon

        return None

    @staticmethod
    def _decode_coordinate_component(value: str, degree_digits: int) -> Optional[float]:
        try:
            if "." in value:
                return float(value)

            if len(value) <= degree_digits:
                return float(value)

            if len(value) == degree_digits + 2:
                deg = int(value[:degree_digits])
                minutes = int(value[degree_digits:])
                return deg + minutes / 60

            if len(value) == degree_digits + 4:
                deg = int(value[:degree_digits])
                minutes = int(value[degree_digits : degree_digits + 2])
                seconds = int(value[degree_digits + 2 : degree_digits + 4])
                return deg + minutes / 60 + seconds / 3600

            return float(value[:degree_digits])
        except ValueError:
            return None


# 전역 헬퍼 인스턴스
route_fir_mapper = RouteFIRMapper()

