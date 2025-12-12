"""
Navigraph 품질윙 787 NAV DATA 로더

- ints.txt, navs.txt, apts.txt, awys.txt 등을 파싱하여 좌표 인덱스를 구성
- 항로(E.g. Y697) 구성 waypoint 시퀀스 조회
- waypoint / 공항 / 항법시설 좌표 조회 지원
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class NavDataLoader:
    """Navigraph 품질윙 787 NavData 파서"""

    def __init__(self, navdata_root: Optional[Path] = None) -> None:
        self.navdata_root = Path(navdata_root) if navdata_root else self._resolve_default_root()
        self._coordinate_index: Dict[str, List[Tuple[float, float]]] = {}
        self._coordinate_source: Dict[str, List[str]] = {}
        self._airways: Dict[str, List[str]] = {}
        self._initialized = False
        self.load_nav_data()

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------
    def load_nav_data(self) -> None:
        """NavData 디렉터리에서 waypoint/항공로 데이터를 로드한다."""
        if self._initialized:
            return

        if not self.navdata_root.exists():
            logger.warning("NavData 디렉터리를 찾을 수 없습니다: %s", self.navdata_root)
            return

        try:
            self._load_intersections()
            self._load_navaids()
            self._load_airports()
            self._load_airways()
            self._initialized = True
            logger.info(
                "Navigraph NAV 데이터 로드 완료: %d 포인트, %d 항로",
                len(self._coordinate_index),
                len(self._airways),
            )
        except Exception as exc:  # pragma: no cover - 로깅 목적
            logger.exception("NavData 로딩 중 오류 발생: %s", exc)

    def get_waypoint_coordinates(
        self,
        ident: str,
        reference: Optional[Tuple[float, float]] = None,
    ) -> Optional[Tuple[float, float]]:
        """식별자(waypoint/공항/항법시설)의 좌표를 반환한다."""
        if not ident:
            return None
        coords_list = self._coordinate_index.get(ident.upper())
        if not coords_list:
            return None
        if reference is None or len(coords_list) == 1:
            return coords_list[0]
        return min(coords_list, key=lambda coord: self._distance(coord, reference))

    def get_airway_waypoints(self, airway_code: str) -> List[str]:
        """항로 코드에 해당하는 waypoint 시퀀스를 반환한다."""
        if not airway_code:
            return []
        return self._airways.get(airway_code.upper(), [])

    def get_coordinate_source(self, ident: str) -> Optional[str]:
        """좌표가 어떤 데이터 파일에서 왔는지 반환한다."""
        if not ident:
            return None
        sources = self._coordinate_source.get(ident.upper())
        if not sources:
            return None
        return sources[0]

    def estimate_waypoint_fir(self, waypoint: str) -> Optional[str]:
        """
        FIR 추정을 위한 헬퍼.
        - fir_geo_reference 모듈(GeoJSON 기반)이 준비되어 있으면 그 결과 사용
        - 그렇지 않으면 간단한 패턴 기반 추정으로 fallback
        """
        coords = self.get_waypoint_coordinates(waypoint)
        if coords:
            try:
                from .fir_geo_reference import fir_geo_reference
            except Exception:  # pragma: no cover - optional dependency
                fir_geo_reference = None

            if fir_geo_reference:
                fir_code = fir_geo_reference.locate_fir_by_point(coords[0], coords[1])
                if fir_code:
                    return fir_code

        return self._estimate_fir_by_pattern(waypoint)

    # ------------------------------------------------------------------
    # 내부 구현
    # ------------------------------------------------------------------
    def _resolve_default_root(self) -> Path:
        project_root = Path(__file__).resolve().parent.parent
        return project_root / "NavData"

    def _store_coordinate(self, ident: str, lat: float, lon: float, source: str) -> None:
        ident = ident.upper()
        coords = self._coordinate_index.setdefault(ident, [])
        sources = self._coordinate_source.setdefault(ident, [])

        for existing in coords:
            if abs(existing[0] - lat) < 1e-6 and abs(existing[1] - lon) < 1e-6:
                return

        coords.append((lat, lon))
        sources.append(source)

    def _load_intersections(self) -> None:
        """ints.txt 파싱 (교차점 waypoint)"""
        path = self.navdata_root / "ints.txt"
        if not path.exists():
            logger.warning("ints.txt 미존재: %s", path)
            return

        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line or line.startswith(";"):
                    continue
                parts = line.split()
                # 예: "KARDE     KARIOI_AERODROME  -39.474917   175.556861    SPA"
                #     ident   name              lat          lon           region
                if len(parts) < 5:
                    continue
                ident = parts[0].upper()
                region = parts[-1].upper()

                # KARDE는 동일한 식별자로 NZ(SPA)와 TR(MES)에 중복 정의되어 있음.
                # 우리 운항 구간에서는 MES(터키) 쪽 좌표만 사용하는 것이 맞으므로
                # SPA 레코드는 무시하고 MES 레코드만 사용한다.
                if ident == "KARDE" and region == "SPA":
                    continue

                try:
                    lat = float(parts[-3])
                    lon = float(parts[-2])
                except ValueError:
                    continue
                self._store_coordinate(ident, lat, lon, "ints")

    def _load_navaids(self) -> None:
        """navs.txt 파싱 (VOR/NDB 등)"""
        path = self.navdata_root / "navs.txt"
        if not path.exists():
            logger.warning("navs.txt 미존재: %s", path)
            return

        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line or line.startswith(";"):
                    continue
                parts = line.split()
                if len(parts) < 5:
                    continue
                ident = parts[0].upper()
                try:
                    lat = float(parts[-4])
                    lon = float(parts[-3])
                except ValueError:
                    continue
                self._store_coordinate(ident, lat, lon, "navs")

    def _load_airports(self) -> None:
        """apts.txt 파싱 (공항 좌표)"""
        path = self.navdata_root / "apts.txt"
        if not path.exists():
            logger.warning("apts.txt 미존재: %s", path)
            return

        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line or line.startswith(";"):
                    continue
                ident = line[0:4].strip().upper()
                if len(ident) != 4:
                    continue
                parts = line.split()
                if len(parts) < 5:
                    continue
                try:
                    lat = float(parts[3])
                    lon = float(parts[4])
                except ValueError:
                    continue
                self._store_coordinate(ident, lat, lon, "apts")

    def _load_airways(self) -> None:
        """awys.txt 파싱 (항로 구성 waypoint 시퀀스)"""
        path = self.navdata_root / "awys.txt"
        if not path.exists():
            logger.warning("awys.txt 미존재: %s", path)
            return

        airway_points: Dict[str, List[Tuple[int, str]]] = {}

        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line or line.startswith(";"):
                    continue
                parts = line.split()
                if len(parts) < 6:
                    continue
                airway = parts[0].upper()
                seq_str = parts[1]
                ident = parts[2].upper()
                try:
                    seq = int(seq_str)
                    lat = float(parts[3])
                    lon = float(parts[4])
                except ValueError:
                    continue
                self._store_coordinate(ident, lat, lon, "awys")
                airway_points.setdefault(airway, []).append((seq, ident))

        for airway, seq_points in airway_points.items():
            ordered = []
            seen = set()
            for _, ident in sorted(seq_points, key=lambda item: item[0]):
                if ident not in seen:
                    ordered.append(ident)
                    seen.add(ident)
            self._airways[airway] = ordered

    @staticmethod
    def _distance(a: Tuple[float, float], b: Tuple[float, float]) -> float:
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    def _estimate_fir_by_pattern(self, waypoint: str) -> Optional[str]:
        """간단한 패턴 기반 FIR 추정 (fallback)"""
        if not waypoint:
            return None
        waypoint_upper = waypoint.upper()

        regional_patterns = {
            "RJJJ": {
                "prefixes": ["EG", "RK", "VH", "RC", "RJ", "RO"],
                "keywords": ["KOREA", "JAPAN", "CHINA", "TAIWAN", "HONGKONG"],
            },
            "PAZA": {
                "prefixes": ["K", "P", "C"],
                "keywords": ["USA", "CANADA", "ALASKA"],
            },
            "KZAK": {
                "prefixes": ["KZ"],
                "keywords": ["PACIFIC", "OCEANIC", "HAWAII"],
            },
        }

        for fir_code, patterns in regional_patterns.items():
            if any(waypoint_upper.startswith(prefix) for prefix in patterns["prefixes"]):
                return fir_code
            if any(keyword in waypoint_upper for keyword in patterns["keywords"]):
                return fir_code
        return None


# 전역 인스턴스 (Lazy initialization)
_nav_data_loader_instance = None

def get_nav_data_loader():
    """Lazy initialization: 필요할 때만 NavDataLoader 인스턴스 생성"""
    global _nav_data_loader_instance
    if _nav_data_loader_instance is None:
        try:
            _nav_data_loader_instance = NavDataLoader()
            logger.info("NavData 로더 초기화 완료")
        except Exception as exc:
            logger.warning("NavData 로더 초기화 실패: %s", exc)
            _nav_data_loader_instance = None
    return _nav_data_loader_instance

# 하위 호환성을 위한 전역 변수 (lazy getter로 동작)
class _LazyNavDataLoader:
    """Lazy initialization wrapper for nav_data_loader"""
    def __getattr__(self, name):
        instance = get_nav_data_loader()
        if instance is None:
            raise AttributeError(f"NavDataLoader가 초기화되지 않았습니다: {name}")
        return getattr(instance, name)
    
    def __bool__(self):
        return get_nav_data_loader() is not None

nav_data_loader = _LazyNavDataLoader()


def get_waypoint_coordinates(waypoint: str) -> Optional[Tuple[float, float]]:
    """전역 함수: 식별자 좌표 조회"""
    return nav_data_loader.get_waypoint_coordinates(waypoint)


def estimate_waypoint_fir(waypoint: str) -> Optional[str]:
    """전역 함수: waypoint FIR 추정"""
    return nav_data_loader.estimate_waypoint_fir(waypoint)
