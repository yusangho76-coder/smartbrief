from __future__ import annotations

import glob
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple


# 좌표 형식 지원:
# - DDMMSSN DDDMMSSW (초 포함)
# - DDMMN DDDMMW (초 미포함)
COORD_REGEX_STR = (
    r"(?:[NS]\d{6}[EW]\d{7})|(?:\d{6}[NS]\d{7}[EW])|"
    r"(?:[NS]\d{4}[EW]\d{5})|(?:\d{4}[NS]\d{5}[EW])"
)
COORD_PATTERN = re.compile(COORD_REGEX_STR)
CIRCLE_PATTERN = re.compile(
    rf"(?:A\s+)?CIRCLE\s+RADIUS\s+(\d+(?:\.\d+)?)\s*(NM|KM)\s+CENTERED\s+ON\s+({COORD_REGEX_STR})",
    re.IGNORECASE,
)
# 좌표에 공백이 있을 수 있는 경우를 위한 추가 패턴
CIRCLE_PATTERN_WITH_SPACES = re.compile(
    rf"(?:A\s+)?CIRCLE\s+RADIUS\s+(\d+(?:\.\d+)?)\s*(NM|KM)\s+CENTERED\s+ON\s+(\d{{6}})\s*([NS])\s*(\d{{7}})\s*([EW])",
    re.IGNORECASE,
)
# Package 3 / ICAO 형식: "WI A RADIUS OF 25NM OF 311414N1442648E" (RJJJ P0439 등)
CIRCLE_PATTERN_RADIUS_OF = re.compile(
    rf"(?:WI\s+A\s+)?RADIUS\s+OF\s+(\d+(?:\.\d+)?)\s*(NM|KM)\s+OF\s+({COORD_REGEX_STR})",
    re.IGNORECASE,
)
BUFFER_PATTERN = re.compile(r"BUFFER[^0-9]*?(\d+(?:\.\d+)?)\s*(NM|KM)", re.IGNORECASE)
# NOTAM 블록 패턴: "SEE NOTAM:" 같은 참조는 무시
# 날짜 형식이 있는 줄의 NOTAM 번호만 다음 NOTAM으로 인식
# 예: "27NOV25 07:00 - 02DEC25 14:00 LTAA A5306/25"
NOTAM_BLOCK_PATTERN = re.compile(
    r"([A-Z]\d{4}/\d{2})(.*?)(?=\n\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s+-\s+.*?\s+[A-Z]{4}\s+[A-Z]\d{4}/\d{2}|\Z)", 
    re.DOTALL | re.MULTILINE
)

# VOR/NDB/VORTAC out of service 패턴
NAVAID_OUT_OF_SERVICE_PATTERNS = [
    # 패턴 1: "VOR ABCDE OUT OF SERVICE" 또는 "VOR ABCDE U/S"
    re.compile(r"\b(VOR|NDB|DME|ILS|TACAN|VORTAC)\s+([A-Z0-9]{2,5})\s+(?:IS\s+)?(?:OUT\s+OF\s+SERVICE|U/S|UNSERVICEABLE|NOT\s+AVAILABLE|UNAVAILABLE|UNAVBL)", re.IGNORECASE),
    # 패턴 2: "ABCDE VOR OUT OF SERVICE"
    re.compile(r"\b([A-Z0-9]{2,5})\s+(VOR|NDB|DME|ILS|TACAN|VORTAC)\s+(?:IS\s+)?(?:OUT\s+OF\s+SERVICE|U/S|UNSERVICEABLE|NOT\s+AVAILABLE|UNAVAILABLE|UNAVBL)", re.IGNORECASE),
    # 패턴 3: "VOR ABCDE WILL BE OUT OF SERVICE" / "VORTAC(SOT) WILL BE UNSERVICEABLE" (RKRR Z0475 등)
    re.compile(r"\b(VOR|NDB|DME|ILS|TACAN|VORTAC)\s*\(?([A-Z0-9]{2,5})\)?\s*(?:WILL\s+BE\s+)?(?:OUT\s+OF\s+SERVICE|U/S|UNSERVICEABLE)", re.IGNORECASE),
    # 패턴 4: "ABCDE VOR U/S" (간단한 형태)
    re.compile(r"\b([A-Z0-9]{2,5})\s+(VOR|NDB|DME|ILS|TACAN|VORTAC)\s+U/S\b", re.IGNORECASE),
]


@dataclass
class Package3Area:
    notam_id: str
    geometry: str  # "polygon" | "circle"
    coordinates: List[Tuple[float, float]]
    raw_coordinates: List[str] = field(default_factory=list)
    description: str = ""
    altitude_text: Optional[str] = None
    restriction: Optional[str] = None
    radius_nm: Optional[float] = None
    is_buffer: bool = False
    raw_notam_text: str = ""
    affected_routes: List[str] = field(default_factory=list)  # COMMENT에서 추출한 영향받는 항로 목록


@dataclass
class Package3Segment:
    airway: str
    points: List[str]
    raw: str


@dataclass
class Package3AltitudeConstraint:
    notam_id: str
    altitude_text: Optional[str]
    airways: List[str]
    segments: List[Package3Segment]
    waypoints: List[str]
    description: str
    raw_notam_text: str = ""


@dataclass
class Package3Navaid:
    notam_id: str
    navaid_ident: str  # VOR/NDB 식별자
    navaid_type: str  # "VOR", "NDB", "DME", "ILS" 등
    coordinates: Optional[Tuple[float, float]] = None  # NavData에서 조회한 좌표
    description: str = ""
    raw_notam_text: str = ""


@dataclass
class Package3AirwayClosure:
    notam_id: str
    airway: str  # 항로 코드 (예: UN644, UM859)
    start_waypoint: str  # 시작 waypoint (예: INB, OSDIP)
    end_waypoint: str  # 종료 waypoint (예: KARDE)
    coordinates: List[Tuple[float, float]] = field(default_factory=list)  # 항로 구간 좌표
    description: str = ""
    raw_notam_text: str = ""


@dataclass
class Package3ParseResult:
    areas: List[Package3Area] = field(default_factory=list)
    altitude_constraints: List[Package3AltitudeConstraint] = field(default_factory=list)
    navaids: List[Package3Navaid] = field(default_factory=list)  # VOR/NDB out of service 정보
    airway_closures: List[Package3AirwayClosure] = field(default_factory=list)  # 항로 폐쇄 정보


def _dms_to_decimal(coord: str) -> Tuple[float, float]:
    coord = coord.strip().upper()
    # 1) NS DDMMSS EW DDDMMSS
    match = re.match(r"([NS])(\d{2})(\d{2})(\d{2})([EW])(\d{3})(\d{2})(\d{2})", coord)
    if match:
        lat_dir, lat_deg, lat_min, lat_sec, lon_dir, lon_deg, lon_min, lon_sec = match.groups()
    else:
        # 2) DDMMSSN DDDMMSSW
        match_alt = re.match(r"(\d{2})(\d{2})(\d{2})([NS])(\d{3})(\d{2})(\d{2})([EW])", coord)
        if match_alt:
            lat_deg, lat_min, lat_sec, lat_dir, lon_deg, lon_min, lon_sec, lon_dir = match_alt.groups()
        else:
            # 3) NS DDMM EW DDDMM (초 미포함)
            match_no_sec = re.match(r"([NS])(\d{2})(\d{2})([EW])(\d{3})(\d{2})", coord)
            if match_no_sec:
                lat_dir, lat_deg, lat_min, lon_dir, lon_deg, lon_min = match_no_sec.groups()
                lat_sec = "00"
                lon_sec = "00"
            else:
                # 4) DDMMN DDDMMW (초 미포함)
                match_no_sec_alt = re.match(r"(\d{2})(\d{2})([NS])(\d{3})(\d{2})([EW])", coord)
                if not match_no_sec_alt:
                    raise ValueError(f"Invalid coordinate format: {coord}")
                lat_deg, lat_min, lat_dir, lon_deg, lon_min, lon_dir = match_no_sec_alt.groups()
                lat_sec = "00"
                lon_sec = "00"
    lat = int(lat_deg) + int(lat_min) / 60 + int(lat_sec) / 3600
    lon = int(lon_deg) + int(lon_min) / 60 + int(lon_sec) / 3600
    if lat_dir == "S":
        lat = -lat
    if lon_dir == "W":
        lon = -lon
    return lat, lon


def _find_latest_split_file(temp_dir: Path) -> Optional[Path]:
    pattern = str(temp_dir / "*_split.txt")
    files = glob.glob(pattern)
    if not files:
        return None
    latest = max(files, key=os.path.getmtime)
    return Path(latest)


def _extract_package3_text(full_text: str) -> str:
    marker_start = "KOREAN AIR NOTAM PACKAGE 3"
    marker_end = "END OF KOREAN AIR NOTAM PACKAGE 3"
    start_idx = full_text.find(marker_start)
    if start_idx == -1:
        return ""
    end_idx = full_text.find(marker_end, start_idx)
    if end_idx == -1:
        return full_text[start_idx:]
    end_idx += len(marker_end)
    return full_text[start_idx:end_idx]


def _clean_text(value: str) -> str:
    value = value.replace("\r", "").strip()
    value = re.sub(r"\s+", " ", value)
    return value


def _normalize_altitude_value(value: str) -> str:
    value = _clean_text(value)
    for token in (" G)", " F)"):
        upper = value.upper()
        idx = upper.find(token)
        if idx != -1:
            value = value[:idx]
    value = value.replace("F)", "").replace("G)", "")
    return value.strip(" -")


def _extract_altitude_text(block: str) -> Optional[str]:
    f_match = re.search(r"F\)\s*([^\n\r]+)", block, re.IGNORECASE)
    g_match = re.search(r"G\)\s*([^\n\r]+)", block, re.IGNORECASE)
    parts: List[str] = []
    if f_match:
        value = _normalize_altitude_value(f_match.group(1))
        if value:
            parts.append(value)
    if g_match:
        value = _normalize_altitude_value(g_match.group(1))
        if value:
            parts.append(value)
    if parts:
        if len(parts) == 2:
            return f"{parts[0]} - {parts[1]}"
        return parts[0]
    alt_match = re.search(r"ALT[:：]\s*([^\n\r]+)", block, re.IGNORECASE)
    if alt_match:
        return _clean_text(alt_match.group(1))
    range_match = re.search(
        r"\b(SFC|FL\d{2,3}|[0-9,]+(?:\.\d+)?\s*(?:FT|M))\s*[-–]\s*(SFC|FL\d{2,3}|[0-9,]+(?:\.\d+)?\s*(?:FT|M))(?:\s*(?:AGL|AMSL|MSL))?",
        block,
        re.IGNORECASE,
    )
    if range_match:
        lower = _clean_text(range_match.group(1))
        upper = _clean_text(range_match.group(2))
        return f"{lower} - {upper}"
    explicit_sfc = re.search(r"\bSFC\s*[-–]\s*(FL\d{2,3}|[0-9,]+(?:\.\d+)?\s*(?:FT|M))", block, re.IGNORECASE)
    if explicit_sfc:
        return f"SFC - {_clean_text(explicit_sfc.group(1))}"
    return None


def _extract_restriction_type(block: str) -> Optional[str]:
    match = re.search(r"(?:TEMPO|TEMPORARY)\s+([A-Z ]*?)\s+AREA", block, re.IGNORECASE)
    if match:
        return _clean_text(match.group(1)).upper()
    return None


def _extract_affected_routes(block: str) -> List[str]:
    """
    COMMENT 필드에서 "AFFECTED RTE" 정보를 추출합니다.
    예: "AFFECTED RTE AS FLW : ICN/DXB(P01) DXB/ICN(X01)"
    -> ["ICN/DXB", "DXB/ICN"]
    """
    affected_routes = []
    
    # COMMENT 필드에서 AFFECTED RTE 패턴 찾기
    # 패턴: "AFFECTED RTE AS FLW : ICN/DXB(P01) DXB/ICN(X01)"
    # 또는 "AFFECTED RTE: ICN/DXB DXB/ICN"
    comment_patterns = [
        r"COMMENT\)\s*AFFECTED\s+RTE\s+(?:AS\s+FLW\s*:?|:)\s*([^\n]+)",
        r"AFFECTED\s+RTE\s+(?:AS\s+FLW\s*:?|:)\s*([^\n]+)",
    ]
    
    for pattern in comment_patterns:
        matches = re.finditer(pattern, block, re.IGNORECASE)
        for match in matches:
            route_text = match.group(1).strip()
            # 항로 추출: "ICN/DXB(P01) DXB/ICN(X01)" -> ["ICN/DXB", "DXB/ICN"]
            # 또는 "ICN/DXB DXB/ICN" -> ["ICN/DXB", "DXB/ICN"]
            # 공항 코드 패턴: 3-4자 대문자 코드
            route_matches = re.findall(r"([A-Z]{3,4})/([A-Z]{3,4})", route_text)
            for dep, dest in route_matches:
                route_pair = f"{dep}/{dest}"
                if route_pair not in affected_routes:
                    affected_routes.append(route_pair)
                # 역방향도 추가 (예: DXB/ICN도 있으면 ICN/DXB와 매칭)
                reverse_pair = f"{dest}/{dep}"
                if reverse_pair not in affected_routes:
                    affected_routes.append(reverse_pair)
    
    return affected_routes


def _collect_description(block: str) -> str:
    lines: List[str] = []
    for raw_line in block.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if COORD_PATTERN.search(line.replace(" ", "")):
            continue
        if line.startswith("F)") or line.startswith("G)"):
            continue
        lines.append(line)
    return " ".join(lines)


def _parse_circle_areas(
    notam_id: str,
    block: str,
    altitude_text: Optional[str],
    restriction: Optional[str],
    description: str,
    raw_notam_text: str,
    affected_routes: List[str] = None,
) -> List[Package3Area]:
    if affected_routes is None:
        affected_routes = []
    areas: List[Package3Area] = []
    processed_coords = set()  # 중복 처리 방지

    # Package 3 / ICAO 형식: "WI A RADIUS OF 25NM OF 311414N1442648E" (RJJJ P0439 등)
    for match in CIRCLE_PATTERN_RADIUS_OF.finditer(block):
        radius_value, unit, coord = match.groups()
        coord_normalized = coord.replace(" ", "").upper()
        if coord_normalized in processed_coords:
            continue
        processed_coords.add(coord_normalized)
        try:
            radius_nm = float(radius_value)
        except ValueError:
            continue
        unit = (unit or "NM").upper()
        if unit == "KM":
            radius_nm = radius_nm / 1.852
        try:
            center = _dms_to_decimal(coord_normalized)
        except ValueError:
            continue
        areas.append(
            Package3Area(
                notam_id=notam_id,
                geometry="circle",
                coordinates=[center],
                raw_coordinates=[coord_normalized],
                radius_nm=radius_nm,
                altitude_text=altitude_text,
                restriction=restriction,
                description=description,
                is_buffer=False,
                raw_notam_text=raw_notam_text,
                affected_routes=affected_routes,
            )
        )

    # 첫 번째 패턴 시도 (공백 없는 좌표)
    for match in CIRCLE_PATTERN.finditer(block):
        radius_value, unit, coord = match.groups()
        coord_normalized = coord.replace(" ", "").upper()
        if coord_normalized in processed_coords:
            continue
        processed_coords.add(coord_normalized)
        
        try:
            radius_nm = float(radius_value)
        except ValueError:
            continue
        unit = unit.upper()
        if unit == "KM":
            radius_nm = radius_nm / 1.852
        try:
            center = _dms_to_decimal(coord_normalized)
        except ValueError:
            continue
        
        areas.append(
            Package3Area(
                notam_id=notam_id,
                geometry="circle",
                coordinates=[center],
                raw_coordinates=[coord],
                radius_nm=radius_nm,
                altitude_text=altitude_text,
                restriction=restriction,
                description=description,
                is_buffer=False,
                raw_notam_text=raw_notam_text,
                affected_routes=affected_routes,
            )
        )

        buffer_added = set()
        for buffer_match in BUFFER_PATTERN.finditer(block):
            buffer_value, buffer_unit = buffer_match.groups()
            try:
                buffer_nm = float(buffer_value)
            except ValueError:
                continue
            buffer_unit = (buffer_unit or "NM").upper()
            if buffer_unit == "KM":
                buffer_nm = buffer_nm / 1.852
            if buffer_nm <= radius_nm or buffer_nm in buffer_added:
                continue
            buffer_added.add(buffer_nm)
            areas.append(
                Package3Area(
                    notam_id=notam_id,
                    geometry="circle",
                    coordinates=[center],
                    raw_coordinates=[coord],
                    radius_nm=buffer_nm,
                    altitude_text=altitude_text,
                    restriction=restriction,
                    description=description,
                    is_buffer=True,
                    raw_notam_text=raw_notam_text,
                    affected_routes=affected_routes,
                )
            )
    
    # 두 번째 패턴 시도 (공백이 있는 좌표)
    for match in CIRCLE_PATTERN_WITH_SPACES.finditer(block):
        radius_value, unit, lat_digits, lat_dir, lon_digits, lon_dir = match.groups()
        coord_normalized = f"{lat_digits}{lat_dir}{lon_digits}{lon_dir}"
        if coord_normalized in processed_coords:
            continue
        processed_coords.add(coord_normalized)
        
        try:
            radius_nm = float(radius_value)
        except ValueError:
            continue
        unit = unit.upper()
        if unit == "KM":
            radius_nm = radius_nm / 1.852
        try:
            center = _dms_to_decimal(coord_normalized)
        except ValueError:
            continue
        
        areas.append(
            Package3Area(
                notam_id=notam_id,
                geometry="circle",
                coordinates=[center],
                raw_coordinates=[coord_normalized],
                radius_nm=radius_nm,
                altitude_text=altitude_text,
                restriction=restriction,
                description=description,
                is_buffer=False,
                raw_notam_text=raw_notam_text,
                affected_routes=affected_routes,
            )
        )

        buffer_added = set()
        for buffer_match in BUFFER_PATTERN.finditer(block):
            buffer_value, buffer_unit = buffer_match.groups()
            try:
                buffer_nm = float(buffer_value)
            except ValueError:
                continue
            buffer_unit = (buffer_unit or "NM").upper()
            if buffer_unit == "KM":
                buffer_nm = buffer_nm / 1.852
            if buffer_nm <= radius_nm or buffer_nm in buffer_added:
                continue
            buffer_added.add(buffer_nm)
            areas.append(
                Package3Area(
                    notam_id=notam_id,
                    geometry="circle",
                    coordinates=[center],
                    raw_coordinates=[coord_normalized],
                    radius_nm=buffer_nm,
                    altitude_text=altitude_text,
                    restriction=restriction,
                    description=description,
                    is_buffer=True,
                    raw_notam_text=raw_notam_text,
                    affected_routes=affected_routes,
                )
            )
    
    return areas


def _parse_polygon_areas(
    notam_id: str,
    block: str,
    altitude_text: Optional[str],
    restriction: Optional[str],
    description: str,
    raw_notam_text: str,
    affected_routes: List[str] = None,
) -> List[Package3Area]:
    if affected_routes is None:
        affected_routes = []
    # 공백 제거 후 좌표 찾기
    block_no_spaces = block.replace(" ", "")
    coords = COORD_PATTERN.findall(block_no_spaces)
    
    # 디버깅: 좌표를 찾지 못한 경우 로그 출력
    if len(coords) < 3:
        # "FORBIDDEN", "PROHIBITED", "BOUNDED BY" 등의 키워드가 있는데 좌표를 찾지 못한 경우
        if any(keyword in block.upper() for keyword in ["FORBIDDEN", "PROHIBITED", "BOUNDED BY", "AREA"]):
            # 하이픈이나 콜론으로 구분된 좌표 문자열에서 직접 추출 시도
            # 예: "N401336E0861826-N374507E0855421-N374319E0874013-N401336E0875009"
            hyphen_separated = re.split(r'[-–—]', block_no_spaces)
            for segment in hyphen_separated:
                found_coords = COORD_PATTERN.findall(segment)
                if found_coords:
                    coords.extend(found_coords)
            # 중복 제거
            coords = list(dict.fromkeys(coords))  # 순서 유지하면서 중복 제거
    
    if len(coords) < 3:
        return []
    try:
        path = [_dms_to_decimal(coord) for coord in coords]
    except ValueError as e:
        # 좌표 변환 실패 시 로그 출력 (디버깅용)
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"좌표 변환 실패 (NOTAM {notam_id}): {e}, 좌표: {coords}")
        return []
    return [
        Package3Area(
            notam_id=notam_id,
            geometry="polygon",
            coordinates=path,
            raw_coordinates=coords,
            altitude_text=altitude_text,
            restriction=restriction,
            description=description,
            raw_notam_text=raw_notam_text,
            affected_routes=affected_routes,
        )
    ]


def _parse_route_constraints(
    notam_id: str,
    block: str,
    altitude_text: Optional[str],
    description: str,
    raw_notam_text: str,
) -> Optional[Package3AltitudeConstraint]:
    segments: List[Package3Segment] = []
    airways: List[str] = []
    waypoint_set = set()

    for route_match in re.finditer(r"\b([A-Z][A-Z0-9]{1,5})\(([^\)]+)\)", block):
        airway = route_match.group(1).strip().upper()
        segment_raw = route_match.group(2).strip()
        if "-" not in segment_raw:
            continue
        if not re.search(r"\d", airway):
            continue
        airways.append(airway)
        for part in re.split(r"[;,]", segment_raw):
            part = part.strip()
            if not part:
                continue
            tokens = [
                token.strip().upper().replace(".", "")
                for token in part.replace("..", "-").split("-")
                if token.strip()
            ]
            if not tokens:
                continue
            segments.append(Package3Segment(airway=airway, points=tokens, raw=part))
            for token in tokens:
                waypoint_set.add(token)

    if not segments:
        return None

    unique_airways = sorted(set(airways))
    waypoints = sorted(waypoint_set, key=lambda x: (len(x), x))

    return Package3AltitudeConstraint(
        notam_id=notam_id,
        altitude_text=altitude_text,
        airways=unique_airways,
        segments=segments,
        waypoints=waypoints,
        description=description,
        raw_notam_text=raw_notam_text,
    )


def _parse_airway_closures(
    notam_id: str,
    block: str,
    description: str,
    raw_notam_text: str,
) -> List[Package3AirwayClosure]:
    """항로 폐쇄 정보 파싱 (예: AWY N/UN644 INB-KARDE SEGMENT CLSD)"""
    import logging
    logger = logging.getLogger(__name__)
    
    closures = []
    
    # 패턴 1: AWY N/UN644 INB-KARDE SEGMENT CLSD (N/ 형식, SEGMENT 포함)
    # "AWY N/UN644 INB-KARDE SEGMENT CLSD." 형식 매칭
    # [A-Z]/?(UN644) - N/UN644에서 UN644만 캡처
    # 주의: [A-Z]/?는 반드시 슬래시가 있어야 함 (N/UN644) - 슬래시 없으면 매칭 안 됨
    pattern1 = re.compile(
        r'\bAWY\s+[A-Z]/([A-Z0-9]{2,5})\s+([A-Z0-9]{2,5})\s*[-–]\s*([A-Z0-9]{2,5})\s+SEGMENT\s+(?:CLSD|CLOSED|RESTRICTED|PROHIBITED)',
        re.IGNORECASE
    )
    
    # 패턴 2: AWY UN644 INB-KARDE SEGMENT CLSD (N/ 없이, SEGMENT 포함)
    pattern2 = re.compile(
        r'\bAWY\s+([A-Z0-9]{2,5})\s+([A-Z0-9]{2,5})\s*[-–]\s*([A-Z0-9]{2,5})\s+SEGMENT\s+(?:CLSD|CLOSED|RESTRICTED|PROHIBITED)',
        re.IGNORECASE
    )
    
    # 패턴 3: AWY N/UN644 INB-KARDE CLSD (N/ 형식, SEGMENT 없이)
    pattern3 = re.compile(
        r'\bAWY\s+[A-Z]/([A-Z0-9]{2,5})\s+([A-Z0-9]{2,5})\s*[-–]\s*([A-Z0-9]{2,5})\s+(?:SEGMENT\s+)?(?:CLSD|CLOSED|RESTRICTED|PROHIBITED)',
        re.IGNORECASE
    )
    
    # 패턴 4: AWY UM860 KUGOS-CRM CLSD (N/ 없이, SEGMENT 없이)
    pattern4 = re.compile(
        r'\bAWY\s+([A-Z0-9]{2,5})\s+([A-Z0-9]{2,5})\s*[-–]\s*([A-Z0-9]{2,5})\s+(?:SEGMENT\s+)?(?:CLSD|CLOSED|RESTRICTED|PROHIBITED)',
        re.IGNORECASE
    )
    
    seen_pairs = set()
    
    # 패턴 순서 중요: 더 구체적인 패턴(N/ 형식)을 먼저 시도
    for pattern_idx, pattern in enumerate([pattern1, pattern2, pattern3, pattern4], 1):
        for match in pattern.finditer(block):
            airway = match.group(1).strip().upper()
            start_wpt = match.group(2).strip().upper()
            end_wpt = match.group(3).strip().upper()
            
            if not airway or not start_wpt or not end_wpt:
                continue
            
            # 중복 제거
            pair_key = (airway, start_wpt, end_wpt)
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)
            
            logger.debug(f"항로 폐쇄 파싱 (NOTAM {notam_id}): {airway} {start_wpt}-{end_wpt} (패턴{pattern_idx})")
            
            closures.append(
                Package3AirwayClosure(
                    notam_id=notam_id,
                    airway=airway,
                    start_waypoint=start_wpt,
                    end_waypoint=end_wpt,
                    description=description,
                    raw_notam_text=raw_notam_text,
                )
            )
    
    if closures:
        logger.info(f"항로 폐쇄 {len(closures)}개 파싱됨 (NOTAM {notam_id}): {[f'{c.airway} {c.start_waypoint}-{c.end_waypoint}' for c in closures]}")
    
    return closures


def _parse_navaid_out_of_service(
    notam_id: str,
    block: str,
    description: str,
    raw_notam_text: str,
) -> List[Package3Navaid]:
    """VOR/NDB out of service 정보 추출"""
    navaids: List[Package3Navaid] = []
    seen_pairs = set()  # (notam_id, navaid_ident) 쌍으로 중복 제거
    
    # 각 패턴으로 검색
    for pattern in NAVAID_OUT_OF_SERVICE_PATTERNS:
        for match in pattern.finditer(block):
            navaid_type = None
            navaid_ident = None
            
            groups = match.groups()
            if len(groups) >= 2:
                # 패턴 1: "VOR ABCDE OUT OF SERVICE" / "VORTAC(SOT) WILL BE UNSERVICEABLE" (첫 번째 그룹이 타입, 두 번째가 식별자)
                if groups[0].upper() in ('VOR', 'NDB', 'DME', 'ILS', 'TACAN', 'VORTAC'):
                    navaid_type = groups[0].upper()
                    navaid_ident = groups[1].upper()
                # 패턴 2: "ABCDE VOR OUT OF SERVICE" (첫 번째 그룹이 식별자, 두 번째가 타입)
                elif groups[1].upper() in ('VOR', 'NDB', 'DME', 'ILS', 'TACAN', 'VORTAC'):
                    navaid_ident = groups[0].upper()
                    navaid_type = groups[1].upper()
            
            if not navaid_ident or len(navaid_ident) < 2 or len(navaid_ident) > 5:
                continue
            
            # 중복 제거 (같은 NOTAM에서 같은 식별자)
            pair_key = (notam_id, navaid_ident)
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)
            
            navaids.append(
                Package3Navaid(
                    notam_id=notam_id,
                    navaid_ident=navaid_ident,
                    navaid_type=navaid_type or "UNKNOWN",
                    description=description,
                    raw_notam_text=raw_notam_text,
                )
            )
    
    return navaids


def _parse_package3_data(text: str) -> Package3ParseResult:
    result = Package3ParseResult()
    if not text:
        return result

    normalized = text.replace("\r", "")
    processed_ids = set()

    for match in NOTAM_BLOCK_PATTERN.finditer(normalized):
        notam_id = match.group(1)
        if notam_id in processed_ids:
            continue
        processed_ids.add(notam_id)

        block = match.group(2)
        altitude_text = _extract_altitude_text(block)
        restriction = _extract_restriction_type(block)
        description = _collect_description(block)
        affected_routes = _extract_affected_routes(block)
        raw_notam_text = f"{notam_id}\n{block}".strip()

        circle_areas = _parse_circle_areas(
            notam_id, block, altitude_text, restriction, description, raw_notam_text, affected_routes
        )
        polygon_areas = _parse_polygon_areas(
            notam_id, block, altitude_text, restriction, description, raw_notam_text, affected_routes
        )

        result.areas.extend(circle_areas)
        result.areas.extend(polygon_areas)

        constraint = _parse_route_constraints(
            notam_id, block, altitude_text, description, raw_notam_text
        )
        if constraint:
            result.altitude_constraints.append(constraint)
        
        # VOR/NDB out of service 정보 추출
        navaids = _parse_navaid_out_of_service(
            notam_id, block, description, raw_notam_text
        )
        result.navaids.extend(navaids)
        
        # 항로 폐쇄 정보 추출
        closures = _parse_airway_closures(
            notam_id, block, description, raw_notam_text
        )
        result.airway_closures.extend(closures)

    return result


def get_package3_data(temp_dir: Path = None, package3_text: str = None) -> Package3ParseResult:
    """
    Package 3 데이터를 파싱하여 반환
    
    Args:
        temp_dir: temp 폴더 경로 (파일에서 읽을 때 사용)
        package3_text: Package 3 텍스트 (직접 제공 시 우선 사용, Cloud Run 호환성)
    
    Returns:
        Package3ParseResult: 파싱된 Package 3 데이터
    """
    # 텍스트가 직접 제공되면 우선 사용 (캐시 우선)
    if package3_text:
        result = _parse_package3_data(package3_text)
    else:
        # 파일에서 읽기
        temp_dir = temp_dir or Path("temp")
        temp_dir = Path(temp_dir)
        latest_file = _find_latest_split_file(temp_dir)
        if not latest_file or not latest_file.exists():
            return Package3ParseResult()
        try:
            full_text = latest_file.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return Package3ParseResult()
        
        package3_text = _extract_package3_text(full_text)
        result = _parse_package3_data(package3_text)
    
    # NavData에서 VOR/NDB 좌표 조회
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        from src.nav_data_loader import get_nav_data_loader
        navdata_loader = get_nav_data_loader()
        if navdata_loader:
            for navaid in result.navaids:
                if not navaid.coordinates:
                    coords = navdata_loader.get_waypoint_coordinates(navaid.navaid_ident)
                    if coords:
                        navaid.coordinates = coords
            
            # 항로 폐쇄 구간 좌표 계산
            logger.info(f"항로 폐쇄 {len(result.airway_closures)}개의 좌표 계산 시작...")
            for closure in result.airway_closures:
                try:
                    closure.coordinates = _calculate_airway_segment_coordinates(
                        navdata_loader, closure.airway, closure.start_waypoint, closure.end_waypoint
                    )
                    if not closure.coordinates:
                        logger.warning(f"항로 폐쇄 좌표 계산 실패: {closure.airway} {closure.start_waypoint}-{closure.end_waypoint}")
                except Exception as e:
                    logger.error(f"항로 폐쇄 좌표 계산 오류 ({closure.airway} {closure.start_waypoint}-{closure.end_waypoint}): {e}", exc_info=True)
    except Exception as e:
        logger.error(f"NavData 로더 오류: {e}", exc_info=True)
        # NavData가 없어도 계속 진행
    
    return result


def _calculate_airway_segment_coordinates(
    navdata_loader,
    airway: str,
    start_waypoint: str,
    end_waypoint: str,
) -> List[Tuple[float, float]]:
    """항로 구간의 좌표를 계산합니다."""
    import logging
    logger = logging.getLogger(__name__)
    
    coordinates = []
    
    try:
        # 항로의 전체 waypoint 시퀀스 가져오기
        waypoints = navdata_loader.get_airway_waypoints(airway)
        if not waypoints:
            logger.debug(f"항로 {airway}의 waypoint 목록이 비어있음")
            # 항로 목록이 없어도 waypoint 좌표는 사용 가능
            start_coord = navdata_loader.get_waypoint_coordinates(start_waypoint)
            end_coord = navdata_loader.get_waypoint_coordinates(end_waypoint)
            if start_coord and end_coord:
                return [start_coord, end_coord]
            return coordinates
        
        # 시작/종료 waypoint 인덱스 찾기
        start_idx = None
        end_idx = None
        
        for i, wpt in enumerate(waypoints):
            if wpt.upper() == start_waypoint.upper():
                start_idx = i
            if wpt.upper() == end_waypoint.upper():
                end_idx = i
        
        # 시작/종료 waypoint를 찾지 못한 경우, 직접 좌표 조회
        if start_idx is None or end_idx is None:
            logger.debug(f"항로 {airway}에서 waypoint를 찾지 못함: start={start_waypoint} (idx={start_idx}), end={end_waypoint} (idx={end_idx})")
            # 시작 waypoint 좌표 조회
            start_coord = navdata_loader.get_waypoint_coordinates(start_waypoint)
            if start_coord:
                # 종료 waypoint는 시작 좌표를 reference로 사용하여 가장 가까운 것 선택
                end_coord = navdata_loader.get_waypoint_coordinates(end_waypoint, reference=start_coord)
            else:
                end_coord = navdata_loader.get_waypoint_coordinates(end_waypoint)
            
            if start_coord and end_coord:
                logger.debug(f"직접 좌표 사용: {start_waypoint} {start_coord}, {end_waypoint} {end_coord}")
                return [start_coord, end_coord]
            logger.warning(f"waypoint 좌표를 찾을 수 없음: {start_waypoint} {start_coord}, {end_waypoint} {end_coord}")
            return coordinates
        
        # 구간 내의 모든 waypoint 좌표 수집
        # 이전 waypoint 좌표를 reference로 사용하여 가장 가까운 좌표 선택
        logger.debug(f"항로 {airway} 구간 {start_waypoint}({start_idx})-{end_waypoint}({end_idx}) 좌표 계산 중...")
        
        # 시작 인덱스가 종료 인덱스보다 크면 역순으로 처리
        if start_idx > end_idx:
            # 역순: start_idx부터 end_idx까지 역순으로 순회 (OSDIP -> ... -> KARDE)
            prev_coord = None
            for i in range(start_idx, end_idx - 1, -1):  # 역순으로 순회
                wpt = waypoints[i]
                coord = navdata_loader.get_waypoint_coordinates(wpt, reference=prev_coord)
                if coord:
                    coordinates.append(coord)
                    prev_coord = coord
                else:
                    logger.warning(f"waypoint {wpt} 좌표를 찾을 수 없음")
            # 마지막 waypoint (end_waypoint) 추가
            end_wpt = waypoints[end_idx]
            end_coord = navdata_loader.get_waypoint_coordinates(end_wpt, reference=prev_coord)
            if end_coord:
                coordinates.append(end_coord)
        else:
            # 정순: start_idx부터 end_idx까지
            prev_coord = None
            for i in range(start_idx, end_idx + 1):
                wpt = waypoints[i]
                coord = navdata_loader.get_waypoint_coordinates(wpt, reference=prev_coord)
                if coord:
                    coordinates.append(coord)
                    prev_coord = coord
                else:
                    logger.warning(f"waypoint {wpt} 좌표를 찾을 수 없음")
        
        logger.info(f"항로 {airway} 구간 {start_waypoint}-{end_waypoint}: {len(coordinates)}개 좌표 계산됨")
    
    except Exception as e:
        logger.error(f"항로 구간 좌표 계산 오류 ({airway} {start_waypoint}-{end_waypoint}): {e}", exc_info=True)
        # 오류 발생 시 시작/종료 waypoint 좌표만 반환
        try:
            start_coord = navdata_loader.get_waypoint_coordinates(start_waypoint)
            if start_coord:
                # 종료 waypoint는 시작 좌표를 reference로 사용
                end_coord = navdata_loader.get_waypoint_coordinates(end_waypoint, reference=start_coord)
            else:
                end_coord = navdata_loader.get_waypoint_coordinates(end_waypoint)
            
            if start_coord:
                coordinates.append(start_coord)
            if end_coord:
                coordinates.append(end_coord)
            if coordinates:
                logger.info(f"fallback: 항로 {airway} 구간 {start_waypoint}-{end_waypoint}: {len(coordinates)}개 좌표 (시작/종료만)")
        except Exception as e2:
            logger.error(f"fallback 좌표 조회도 실패: {e2}")
    
    return coordinates


def get_package3_polygons(temp_dir: Path) -> List[Package3Area]:
    return get_package3_data(temp_dir).areas

