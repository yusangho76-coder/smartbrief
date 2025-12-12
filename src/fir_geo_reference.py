"""
GeoJSON 기반 FIR 경계 참조 모듈 (Shapely 없이 동작)

- NavData/fir.geojson을 로드하여 FIR 폴리곤 보관
- 좌표(Point) → FIR 코드 조회 (Ray-casting)
- 항로 좌표 시퀀스를 기준으로 FIR 통과 순서 추정
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from math import atan2, cos, radians, sin, sqrt
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

EARTH_RADIUS_NM = 3440.065  # 해리 단위 지구 반경


@dataclass
class FIRFeature:
    code: str
    name: str
    is_oceanic: bool
    polygons: List[List[Tuple[float, float]]]  # 각 폴리곤 외곽선 (lat, lon)


class FIRGeoReference:
    """fir.geojson을 이용한 FIR 공간 조회 클래스"""

    def __init__(self, geojson_path: Optional[Path] = None) -> None:
        self.geojson_path = geojson_path or self._resolve_default_path()
        self._features: List[FIRFeature] = []
        self._load_geojson()

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------
    def locate_firs_for_point(self, lat: float, lon: float) -> List[str]:
        """위치가 속하는 FIR 코드를 모두 반환 (복수 가능)."""
        fir_codes: List[str] = []
        for feature in self._features:
            if self._is_point_inside_feature(lat, lon, feature):
                fir_codes.append(feature.code)
        return fir_codes

    def locate_fir_by_point(self, lat: float, lon: float) -> Optional[str]:
        """좌표가 속한 첫 번째 FIR 코드를 반환."""
        firs = self.locate_firs_for_point(lat, lon)
        return firs[0] if firs else None

    def trace_route(self, coordinates: Sequence[Tuple[float, float]]) -> dict:
        """
        좌표 시퀀스를 따라 통과하는 FIR 순서를 계산한다.

        Returns:
            {
                'fir_sequence': [...],
                'segments': [...],
                'waypoint_firs': [...]
            }
        """
        coords = [(float(lat), float(lon)) for lat, lon in coordinates if _is_valid_coord(lat, lon)]
        if len(coords) < 2:
            return {"fir_sequence": [], "segments": [], "waypoint_firs": []}

        total_distance, cumulative_nm = _cumulative_distance_nm(coords)
        waypoint_firs = [self.locate_fir_by_point(lat, lon) for lat, lon in coords]

        segments = self._build_segments(coords, waypoint_firs, cumulative_nm, total_distance)
        fir_sequence: List[str] = []
        for segment in segments:
            fir = segment.get("fir")
            if not fir:
                continue
            if not fir_sequence or fir_sequence[-1] != fir:
                fir_sequence.append(fir)

        return {
            "fir_sequence": fir_sequence,
            "segments": segments,
            "waypoint_firs": waypoint_firs,
        }

    # ------------------------------------------------------------------
    # 내부 구현
    # ------------------------------------------------------------------
    def _resolve_default_path(self) -> Path:
        project_root = Path(__file__).resolve().parent.parent
        return project_root / "NavData" / "fir.geojson"

    def _load_geojson(self) -> None:
        if not self.geojson_path.exists():
            logger.warning("fir.geojson 파일을 찾을 수 없습니다: %s", self.geojson_path)
            return

        with self.geojson_path.open(encoding="utf-8") as handle:
            data = json.load(handle)

        features = data.get("features", [])
        for feature in features:
            properties = feature.get("properties", {})
            geometry = feature.get("geometry", {})

            code = (properties.get("ICAO") or "").strip().upper()
            if not code:
                continue

            polygons = _extract_polygons(geometry)
            if not polygons:
                continue

            fir_feature = FIRFeature(
                code=code,
                name=str(properties.get("name") or properties.get("FIR_NAME") or code),
                is_oceanic=str(properties.get("IsOceanic", "0")) == "1",
                polygons=polygons,
            )
            self._features.append(fir_feature)

        logger.info("FIR GeoJSON 로드 완료: %d개 경계", len(self._features))

    def _is_point_inside_feature(self, lat: float, lon: float, feature: FIRFeature) -> bool:
        for polygon in feature.polygons:
            if _point_in_polygon(lat, lon, polygon):
                return True
        return False

    def _build_segments(
        self,
        coords: Sequence[Tuple[float, float]],
        waypoint_firs: Sequence[Optional[str]],
        cumulative_nm: Sequence[float],
        total_distance: float,
    ) -> List[dict]:
        segments: List[dict] = []

        current_fir = waypoint_firs[0] or "UNKNOWN"
        current_start_idx = 0
        current_start_distance = 0.0

        for idx in range(len(coords) - 1):
            start = coords[idx]
            end = coords[idx + 1]
            start_fir = waypoint_firs[idx]
            end_fir = waypoint_firs[idx + 1]

            samples = self._segment_samples(start, end, start_fir, end_fir)
            segment_distance = cumulative_nm[idx + 1] - cumulative_nm[idx]

            for frac, fir_code in samples[1:]:
                fir_code = fir_code or "UNKNOWN"
                prev_fir = current_fir or "UNKNOWN"
                if fir_code != prev_fir:
                    boundary_distance = cumulative_nm[idx] + segment_distance * frac
                    end_index = min(len(coords) - 1, max(idx, int(round(idx + frac))))
                    segments.append(
                        self._make_segment(prev_fir, current_start_idx, end_index, current_start_distance, boundary_distance)
                    )
                    current_fir = fir_code
                    current_start_idx = end_index
                    current_start_distance = boundary_distance

        segments.append(
            self._make_segment(
                current_fir or "UNKNOWN",
                current_start_idx,
                len(coords) - 1,
                current_start_distance,
                total_distance,
            )
        )

        filtered = [
            segment
            for segment in segments
            if segment["length_nm"] > 1e-3 or (segment["start_index"] == segment["end_index"])
        ]
        return filtered

    def _segment_samples(
        self,
        start: Tuple[float, float],
        end: Tuple[float, float],
        start_fir: Optional[str],
        end_fir: Optional[str],
    ) -> List[Tuple[float, Optional[str]]]:
        fractions = [0.0, 0.25, 0.5, 0.75, 1.0]
        samples: List[Tuple[float, Optional[str]]] = []

        for frac in fractions:
            lat = start[0] + (end[0] - start[0]) * frac
            lon = _interpolate_longitude(start[1], end[1], frac)

            if frac == 0.0:
                fir_code = start_fir or self.locate_fir_by_point(lat, lon)
            elif frac == 1.0:
                fir_code = end_fir or self.locate_fir_by_point(lat, lon)
            else:
                fir_code = self.locate_fir_by_point(lat, lon)

            samples.append((frac, fir_code))

        return samples

    def _make_segment(
        self,
        fir_code: str,
        start_idx: int,
        end_idx: int,
        start_distance: float,
        end_distance: float,
    ) -> dict:
        fir = None if fir_code == "UNKNOWN" else fir_code
        return {
            "fir": fir,
            "name": self._fir_name(fir),
            "start_index": start_idx,
            "end_index": end_idx,
            "start_distance_nm": start_distance,
            "end_distance_nm": end_distance,
            "length_nm": max(end_distance - start_distance, 0.0),
            "is_oceanic": self._is_oceanic(fir),
        }

    def _fir_name(self, fir_code: Optional[str]) -> Optional[str]:
        if not fir_code:
            return None
        for feature in self._features:
            if feature.code == fir_code:
                return feature.name
        return fir_code

    def _is_oceanic(self, fir_code: Optional[str]) -> bool:
        if not fir_code:
            return False
        for feature in self._features:
            if feature.code == fir_code:
                return feature.is_oceanic
        return False


def _extract_polygons(geometry: dict) -> List[List[Tuple[float, float]]]:
    geom_type = geometry.get("type")
    coordinates = geometry.get("coordinates", [])

    polygons: List[List[Tuple[float, float]]] = []
    if geom_type == "Polygon":
        if coordinates:
            polygons.append(_convert_ring(coordinates[0]))
    elif geom_type == "MultiPolygon":
        for polygon in coordinates:
            if polygon:
                polygons.append(_convert_ring(polygon[0]))
    return polygons


def _convert_ring(ring: List[Sequence[float]]) -> List[Tuple[float, float]]:  # type: ignore[name-defined]
    converted: List[Tuple[float, float]] = []
    for point in ring:
        if len(point) >= 2:
            lon, lat = point[0], point[1]
            converted.append((lat, lon))
    return converted


def _point_in_polygon(lat: float, lon: float, polygon: Sequence[Tuple[float, float]]) -> bool:
    """Ray casting 알고리즘"""
    x = lon
    y = lat
    inside = False

    if len(polygon) < 3:
        return False

    p1x, p1y = polygon[0][1], polygon[0][0]
    for i in range(1, len(polygon) + 1):
        p2x, p2y = polygon[i % len(polygon)][1], polygon[i % len(polygon)][0]
        if ((p1y > y) != (p2y > y)) and (x <= (p2x - p1x) * (y - p1y) / ((p2y - p1y) or 1e-12) + p1x):
            inside = not inside
        p1x, p1y = p2x, p2y
    return inside


def _interpolate_longitude(lon1: float, lon2: float, frac: float) -> float:
    delta = lon2 - lon1
    if abs(delta) <= 180:
        return lon1 + delta * frac
    if delta > 0:
        delta -= 360
    else:
        delta += 360
    interpolated = lon1 + delta * frac
    if interpolated > 180:
        interpolated -= 360
    elif interpolated < -180:
        interpolated += 360
    return interpolated


def _is_valid_coord(lat: float, lon: float) -> bool:
    try:
        lat_f = float(lat)
        lon_f = float(lon)
    except (TypeError, ValueError):
        return False
    return -90.0 <= lat_f <= 90.0 and -180.0 <= lon_f <= 180.0


def _cumulative_distance_nm(coords: Sequence[Tuple[float, float]]) -> Tuple[float, List[float]]:
    cumulative: List[float] = [0.0]
    total = 0.0
    for (lat1, lon1), (lat2, lon2) in zip(coords, coords[1:]):
        distance = _haversine_nm(lat1, lon1, lat2, lon2)
        total += distance
        cumulative.append(total)
    return total, cumulative


def _haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1_rad, lon1_rad = radians(lat1), radians(lon1)
    lat2_rad, lon2_rad = radians(lat2), radians(lon2)

    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad

    a = sin(dlat / 2) ** 2 + cos(lat1_rad) * cos(lat2_rad) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return EARTH_RADIUS_NM * c


# 전역 인스턴스 (Lazy initialization - 모듈 레벨 변수는 None으로 시작)
_fir_geo_reference_instance = None

def get_fir_geo_reference():
    """Lazy initialization: 필요할 때만 FIRGeoReference 인스턴스 생성"""
    global _fir_geo_reference_instance
    if _fir_geo_reference_instance is None:
        try:
            _fir_geo_reference_instance = FIRGeoReference()
            logger.info("FIR GeoJSON 레퍼런스 초기화 완료")
        except Exception as exc:
            logger.warning("FIR GeoJSON 레퍼런스 초기화 실패: %s", exc)
            _fir_geo_reference_instance = None
    return _fir_geo_reference_instance

# 하위 호환성을 위한 전역 변수 (lazy getter로 동작)
class _LazyFIRGeoReference:
    """Lazy initialization wrapper for fir_geo_reference"""
    def __getattr__(self, name):
        instance = get_fir_geo_reference()
        if instance is None:
            raise AttributeError(f"FIRGeoReference가 초기화되지 않았습니다: {name}")
        return getattr(instance, name)
    
    def __bool__(self):
        return get_fir_geo_reference() is not None

fir_geo_reference = _LazyFIRGeoReference()

