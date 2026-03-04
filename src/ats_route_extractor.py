"""
Route 추출 및 비교 로직
PDF에서 OFP route와 ATS FPL route를 추출하고 정규화하여 비교합니다.
"""
import re
from typing import Optional, Tuple, Dict, List


# 좌표형 waypoint 정규화: 56N150W ↔ N56W150 동일 취급
_COORD_PREFIX = re.compile(r"^([NS])(\d{2,3})([EW])(\d{2,3})$")   # N56W150
_COORD_SUFFIX = re.compile(r"^(\d{2,3})([NS])(\d{2,3})([EW])$")   # 56N150W


def _normalize_coord_waypoint(token: str) -> Optional[str]:
    """좌표형 waypoint를 통일 형식(N+위도+E/W+경도)으로 반환. 인식 실패 시 None."""
    t = token.strip().upper().replace(" ", "")
    if not t:
        return None
    m = _COORD_PREFIX.match(t)
    if m:
        return f"{m.group(1)}{m.group(2)}{m.group(3)}{m.group(4)}"
    m = _COORD_SUFFIX.match(t)
    if m:
        return f"{m.group(2)}{m.group(1)}{m.group(4)}{m.group(3)}"
    return None


def normalize_route(route: str) -> str:
    """
    Route를 정규화합니다.
    - 시간 정보 제거 (RKSI0255 → RKSI)
    - TAS/고도 정보 제거 (N0495F320)
    - 속도/고도 제약 제거 (/K0917S0980)
    - DCT 제거
    - ..를 공백으로 변환
    - 같은 airway가 연속으로 나오면 하나로 처리 (예: W4 SEBLI/K0907S1040 W4 → W4 SEBLI W4)
    """
    if not route:
        return ""
    
    # ..를 공백으로 변환
    route = route.replace('..', ' ')
    
    # 시간 정보 제거 (예: RKSI0255 → RKSI, LOWW1225 → LOWW)
    route = re.sub(r'([A-Z]{4})\d{4}', r'\1', route)
    route = re.sub(r'-([A-Z]{4})\d{4}', r'-\1', route)
    
    # TAS/고도 정보 제거 (예: -N0495F320)
    route = re.sub(r'-[A-Z]\d+F\d+', '', route)
    
    # 속도/고도 제약 제거
    # /K숫자S숫자 형식 제거 (예: /K0895S1100 - 그라운드 스피드/미터 고도)
    route = re.sub(r'/[K]\d+S\d+', '', route)
    # /N숫자F숫자 형식 제거 (예: /N0485F360 - TAS/피트 고도)
    route = re.sub(r'/[N]\d+F\d+', '', route)
    # /M숫자F숫자 형식 제거 (예: /M085F380 - 마하 속도/피트 고도)
    route = re.sub(r'/[M]\d+F\d+', '', route)
    # waypoint/공항코드 뒤의 /K숫자S숫자, /N숫자F숫자, /M숫자F숫자 형식 제거 (예: BUVTA/K0895S1100 → BUVTA, RULAD/N0485F360 → RULAD, CJAYY/M085F380 → CJAYY)
    route = re.sub(r'([A-Z]{2,})/[KMN]\d+[SF]\d+', r'\1', route)
    # 기타 속도/고도 제약 제거 (예: /K0917S0980)
    route = re.sub(r'/[A-Z]\d+S\d+', '', route)
    
    # DCT 제거
    route = re.sub(r'\s+DCT\s+', ' ', route)
    route = re.sub(r'^DCT\s+', '', route)
    route = re.sub(r'\s+DCT$', '', route)
    
    # 여러 공백을 하나로 변환
    route = re.sub(r'\s+', ' ', route)
    
    # 같은 airway가 연속으로 나오면 하나로 처리
    # 예: "A326 SANKO A326" → "A326" (중간 waypoint 제거하고 airway 하나만 남김)
    # 패턴: airway + waypoint/공항코드 + 같은 airway
    # 여러 번 반복 실행하여 모든 중복 제거 (예: "A326 DOBGA A326 SANKO A326" → "A326")
    while True:
        new_route = re.sub(r'\b([A-Z]\d+)\s+[A-Z]{2,}\s+\1\b', r'\1', route)
        if new_route == route:
            break
        route = new_route
    # 연속된 같은 airway 제거 (예: "W4 W4" → "W4")
    while True:
        new_route = re.sub(r'\b([A-Z]\d+)\s+\1\b', r'\1', route)
        if new_route == route:
            break
        route = new_route
    
    # 앞뒤의 - 기호 제거 (예: "-RKSI" → "RKSI", "-LOWW" → "LOWW")
    route = re.sub(r'^-\s*', '', route)  # 앞의 - 제거
    route = re.sub(r'\s*-([A-Z]{4})$', r' \1', route)  # 뒤의 -공항코드 제거 (예: "-RKSI" → "RKSI")
    route = re.sub(r'-([A-Z]{4})$', r'\1', route)  # 뒤의 -공항코드 제거 (공백 없이 붙어있는 경우)
    route = re.sub(r'\s*-$', '', route)  # 뒤의 단독 - 제거
    
    # 앞뒤 공백 제거
    route = route.strip()
    
    return route


def extract_waypoints(route: str) -> List[str]:
    """
    Route에서 waypoint와 airway를 추출합니다.
    좌표형 waypoint(N56W150, 56N150W 등)는 통일 형식(N56W150)으로 넣어 OFP/ATS 비교가 맞도록 합니다.
    """
    if not route:
        return []
    
    # 공백으로 분리
    elements = route.split()
    
    waypoints = []
    for element in elements:
        element = element.strip()
        if not element:
            continue
        
        # 좌표형 waypoint (N56W150, 56N150W 등) → 통일 형식으로 추출
        coord = _normalize_coord_waypoint(element)
        if coord is not None:
            waypoints.append(coord)
            continue
        
        # 공항 코드 (4자리 대문자)
        if re.match(r'^[A-Z]{4}$', element):
            waypoints.append(element)
        # Airway (예: Y697, A591, W4, B339 등)
        elif re.match(r'^[A-Z]\d+$', element):
            waypoints.append(element)
        # SID/STAR (예: NAKH3A, BLECO8 - 출발/도착 절차). 좌표형(N56W150)은 위에서 처리됨
        elif re.match(r'^[A-Z][A-Z0-9]{4,7}$', element):
            waypoints.append(element)
        # Waypoint (예: NOPIK, AGAVO 등)
        elif re.match(r'^[A-Z]{2,}$', element):
            waypoints.append(element)
    
    return waypoints


def compare_routes(ofp_route: str, ats_route: str) -> Dict:
    """
    OFP route와 ATS FPL route를 비교합니다.
    
    Returns:
        {
            'ofp_normalized': 정규화된 OFP route,
            'ats_normalized': 정규화된 ATS route,
            'ofp_waypoints': OFP waypoint 리스트,
            'ats_waypoints': ATS waypoint 리스트,
            'only_in_ofp': OFP에만 있는 waypoint/airway,
            'only_in_ats': ATS에만 있는 waypoint/airway,
            'order_mismatch': 순서가 다른 부분,
            'match': 두 route가 일치하는지 여부
        }
    """
    ofp_normalized = normalize_route(ofp_route)
    ats_normalized = normalize_route(ats_route)
    
    ofp_waypoints = extract_waypoints(ofp_normalized)
    ats_waypoints = extract_waypoints(ats_normalized)
    
    only_in_ofp = [w for w in ofp_waypoints if w not in ats_waypoints]
    only_in_ats = [w for w in ats_waypoints if w not in ofp_waypoints]
    
    # 순서 불일치 확인
    order_mismatch = []
    if ofp_waypoints == ats_waypoints:
        order_mismatch = []
    else:
        # 공통 waypoint의 순서 비교
        common_waypoints = set(ofp_waypoints) & set(ats_waypoints)
        if common_waypoints:
            ofp_order = [w for w in ofp_waypoints if w in common_waypoints]
            ats_order = [w for w in ats_waypoints if w in common_waypoints]
            if ofp_order != ats_order:
                order_mismatch = {
                    'ofp_order': ofp_order,
                    'ats_order': ats_order
                }
    
    match = (only_in_ofp == [] and only_in_ats == [] and order_mismatch == [])
    
    return {
        'ofp_normalized': ofp_normalized,
        'ats_normalized': ats_normalized,
        'ofp_waypoints': ofp_waypoints,
        'ats_waypoints': ats_waypoints,
        'only_in_ofp': only_in_ofp,
        'only_in_ats': only_in_ats,
        'order_mismatch': order_mismatch,
        'match': match
    }


def extract_ofp_route_from_page(page_text: str) -> Optional[str]:
    """
    OFP 본경로를 추출합니다. (Aviator OFP는 본경로가 거의 항상 2페이지에 있음.)
    - "ROUTE TO ALTN"은 대체경로 섹션이므로 OFP가 아님 → 해당 구간은 제외하고 그 이전만 본경로로 사용.
    - Route는 "공항코드.." 형태로 "DIST LATITUDE" 직전까지. 페이지에 "DIST LATITUDE"가 있으면 그 직전 블록에서만 검색.
    예: "RKSI..NOPIK Y697 AGAVO A591 IKEKA W4 HCH W200 DOVIV W55 PAMRU W34 LADIX"
    """
    if not page_text:
        return None
    
    # "ROUTE TO ALTN" 등 섹션 헤더가 아닌 본경로만 허용
    def _reject_section_header(route: str) -> bool:
        return bool(route and route.upper().strip().startswith('ROUTE'))
    
    airport_pattern = r'[A-Z]{4}'
    waypoint_pattern = r'[A-Z]{2,}'
    airway_pattern = r'[A-Z]\d+'
    
    # 비행계획 테이블 페이지: "DIST LATITUDE" / "DIST. LATITUDE" 직전 블록에서만 검색 (테이블 본문 오탐 방지)
    # ROUTE TO ALTN은 대체경로 섹션이므로 OFP 본경로가 아님 → 그 이전까지만 사용
    search_text = page_text
    slice_start = 0
    dist_header = re.search(r'\bDIST\s*\.?\s*LATITUDE\b', page_text, re.IGNORECASE)
    if dist_header:
        dist_pos = dist_header.start()
        altn_pos = page_text.upper().find('ROUTE TO ALTN')
        if altn_pos != -1 and altn_pos < dist_pos:
            dist_pos = altn_pos  # 본경로는 ROUTE TO ALTN 이전에만 있음
        if dist_pos > 500:
            slice_start = max(0, dist_pos - 2500)
            search_text = page_text[slice_start:dist_pos]
        # 1순위: "2ND-$ 280 0972 07.45" 같은 줄 다음에 오는 본경로 블록에서 DEP.. ..DEST 검색
        second_line = re.search(r'(?m)^\s*2ND\s*(?:-\$)?\s*[\d\s.]{4,}\s*$', search_text, re.IGNORECASE)
        if second_line:
            block = search_text[second_line.end():second_line.end() + 900]
            stop = re.search(r'\bDIST\b|\bROUTE\s+TO\s+ALTN\b', block, re.IGNORECASE)
            if stop:
                block = block[:stop.start()]
            dep_dest = re.search(
                rf'(?:^|\s)({airport_pattern})\.\.\s*(.+?)\s*\.\.\s*({airport_pattern})\b',
                block,
                re.IGNORECASE | re.DOTALL,
            )
            if dep_dest and 'ROUTE TO ALTN' not in (dep_dest.group(2) or '').upper()[:80]:
                mid = ' '.join((dep_dest.group(2) or '').split())
                route_block = f"{dep_dest.group(1)}..{mid}..{dep_dest.group(3)}"
                if 20 <= len(route_block) <= 600 and re.search(airway_pattern, route_block):
                    return route_block
        # 2순위: DEP.. ... ..DEST 형식 (출발 4자.. 항로 ..도착 4자) — 레이아웃 독립, 멀티라인
        dep_dest = re.search(
            rf'(?:^|\s)({airport_pattern})\.\.\s*(.+?)\s*\.\.\s*({airport_pattern})\b',
            search_text,
            re.IGNORECASE | re.DOTALL,
        )
        if dep_dest and 'ROUTE TO ALTN' not in (dep_dest.group(2) or '').upper()[:80]:
            mid = ' '.join((dep_dest.group(2) or '').split())
            route_block = f"{dep_dest.group(1)}..{mid}..{dep_dest.group(3)}"
            if 20 <= len(route_block) <= 600 and re.search(airway_pattern, route_block):
                return route_block
        # 3순위: 이 블록에서 "공항코드 "로 시작하고 ".." 포함한 줄(본경로)을 찾음 (예: KSEA BANGR9 ARRIE..TOU..)
        for m in re.finditer(rf'(?m)^({airport_pattern})\s+[A-Z0-9\s\.]+\.\.[A-Z0-9\s\.]+', search_text):
            line_start = m.start()
            cand = search_text[line_start:].split('\n')[0]
            if _reject_section_header(cand):
                continue
            if len(cand) < 20 or 'ROUTE TO ALTN' in cand[:40]:
                continue
            # 이 줄부터 블록 끝까지가 경로 (여러 줄일 수 있음)
            route_block = search_text[line_start:].strip()
            route_block = ' '.join(route_block.split())
            if len(route_block) >= 20 and re.search(airway_pattern, route_block):
                return route_block
    
    # 4순위: 일반 페이지 "공항코드.." 또는 "공항코드 + 항로" 패턴 찾기
    start_match = re.search(rf'(?m)^{airport_pattern}\.\.\.?', search_text)
    if not start_match:
        start_match = re.search(rf'(?m)^{airport_pattern}(?!/)[^\n]*\.\.\s*{airport_pattern}\b', search_text)
    if not start_match:
        start_match = re.search(rf'(?m)^{airport_pattern}(?!/)[^\n]*\b[A-Z]\d{{1,4}}\b', search_text)
    if not start_match:
        # ".." 없이 공항코드 + 공백 + 항로 형태 (일부 OFP 형식)
        start_match = re.search(rf'(?m)^{airport_pattern}\s+[A-Z0-9\s\.]+', search_text)
    if not start_match:
        return None
    
    start_pos = start_match.start()
    if search_text is not page_text:
        start_pos_in_page = slice_start + start_pos
        remaining_in_page = page_text[start_pos_in_page:]
    else:
        remaining_in_page = page_text[start_pos:]
    
    dist_match = re.search(r'\bDIST\b', remaining_in_page, re.IGNORECASE)
    if not dist_match:
        end_match = re.search(rf'({airport_pattern})(?=\s|$|\n|DIST)', remaining_in_page)
        if end_match:
            end_pos_rel = end_match.end()
        else:
            end_pos_rel = min(1000, len(remaining_in_page))
    else:
        end_pos_rel = dist_match.start()
    
    route = remaining_in_page[:end_pos_rel].strip()
    route = ' '.join(route.split())
    
    if _reject_section_header(route):
        return None
    if len(route) < 20 or len(route) > 1000:
        return None
    if not (re.search(waypoint_pattern, route) or re.search(airway_pattern, route)):
        return None
    route_elements = re.findall(rf'{airport_pattern}|{waypoint_pattern}|{airway_pattern}', route)
    if len(route_elements) < 3:
        return None
    
    return route


def extract_ats_fpl_route_from_page(page_text: str) -> Optional[str]:
    """
    "COPY OF ATS FPL" 페이지에서 ATS Flight Plan route를 추출합니다.
    Route는 "-공항코드시간" 형식으로 시작하고 끝나며, waypoint와 airway가 포함됩니다.
    예: "-RKSI0255 -N0495F320 DCT NOPIK Y697 AGAVO/K0917S0980 A591 IKEKA W4 HCH"
    """
    if not page_text:
        return None
    
    # "(FPL-" (ICAO FPL) 형식도 ATS로 인정
    is_icao_fpl = '(FPL-' in page_text
    if not is_icao_fpl and 'COPY OF ATS FPL' not in page_text.upper() and 'ATS FPL' not in page_text.upper():
        return None
    
    # (FPL- 형식: -KSEA1920 ... -RKSI1147 구간 추출
    if is_icao_fpl:
        # -공항코드4자리 (예: -KSEA1920, -RKSI1147)
        dep_match = re.search(r'-([A-Z]{4})\d{4}\s', page_text)
        arr_match = re.search(r'-([A-Z]{4})\d{4}\s+(?:[A-Z]{2,}\s+)*[A-Z]{4}\s*', page_text)
        if dep_match:
            start = dep_match.start()
            # 다음 "-공항코드4자리" 전까지가 route (도착 -RKSI1147 RKSS 등)
            rest = page_text[start:]
            seg = re.search(r'-[A-Z]{4}\d{4}\s+[A-Z0-9\s\.\-/DCT]{20,}?-([A-Z]{4})\d{4}', rest, re.DOTALL)
            if seg:
                candidate = rest[:seg.end()].strip()
                candidate = ' '.join(candidate.split())
                if 30 <= len(candidate) <= 1000 and re.search(r'[A-Z]\d+', candidate):
                    return candidate
    
    # Route의 특징:
    # 1. "-공항코드시간" 형식으로 시작 (예: -RKSI0255)
    # 2. "-공항코드시간" 형식으로 끝남 (예: -LOWW1225)
    # 3. 중간에 waypoint, airway, DCT 등 포함
    # 4. TAS/고도 정보, 속도/고도 제약 등 포함 가능
    
    # 공항코드+시간 패턴 (예: -RKSI0255)
    airport_time_pattern = r'-[A-Z]{4}\d{4}'
    # Waypoint 패턴
    waypoint_pattern = r'[A-Z]{2,}'
    # Airway 패턴
    airway_pattern = r'[A-Z]\d+'
    
    # Route 후보 찾기: "-공항코드시간"으로 시작하고 끝나는 긴 텍스트 블록
    route_candidates = re.finditer(
        rf'({airport_time_pattern}[A-Z0-9\s\.\-/DCT]{{20,}}{airport_time_pattern})',
        page_text,
        re.MULTILINE | re.DOTALL
    )
    
    for match in route_candidates:
        candidate = match.group(1).strip()
        
        # Route 유효성 검사
        # 1. 길이 확인 (너무 짧거나 길면 제외)
        if len(candidate) < 20 or len(candidate) > 1000:
            continue
        
        # 2. "-공항코드시간" 형식으로 시작하고 끝나는지 확인
        if not (re.match(airport_time_pattern, candidate) and 
                re.search(rf'{airport_time_pattern}$', candidate)):
            continue
        
        # 3. Waypoint, Airway, 또는 DCT가 포함되어 있는지 확인
        has_waypoint = bool(re.search(waypoint_pattern, candidate))
        has_airway = bool(re.search(airway_pattern, candidate))
        has_dct = 'DCT' in candidate
        if not (has_waypoint or has_airway or has_dct):
            continue
        
        # 4. Route처럼 보이는지 확인 (공항코드+시간, waypoint, airway가 적절히 섞여있어야 함)
        # 최소 3개 이상의 route 요소가 있어야 함
        route_elements = re.findall(
            rf'{airport_time_pattern}|{waypoint_pattern}|{airway_pattern}|DCT',
            candidate
        )
        if len(route_elements) < 3:
            continue
        
        # 5. 테이블 헤더나 다른 구조화된 데이터가 아닌지 확인
        # 숫자만 있는 행이나 특수 문자 패턴이 많으면 제외
        lines = candidate.split('\n')
        numeric_lines = sum(1 for line in lines if re.match(r'^\s*[\d\s:/\-]+\s*$', line.strip()))
        if numeric_lines > len(lines) * 0.5:  # 50% 이상이 숫자만 있으면 제외
            continue
        
        return candidate
    
    return None


def is_valid_ofp_route(route: str) -> bool:
    """OFP 본경로로 유효한지 검사 (ROUTE TO ALTN 등 대체경로 제외)."""
    if not route or len(route) < 20:
        return False
    r = route.upper().strip()
    if r.startswith('ROUTE') or 'ROUTE TO ALTN' in r[:30]:
        return False
    return True


def extract_route_from_docpack(text: str) -> str:
    """
    전체 문서 텍스트(여러 페이지 합친 것)에서 OFP 본경로 후보를 추출.
    공항코드로 시작해 DIST 직전까지 구간을 route 후보로 사용하고, 유효하면 반환.
    """
    airport_pattern = r'[A-Z]{4}'
    patterns = [
        rf'(?m)^{airport_pattern}\.\.\.?',
        rf'(?m)^{airport_pattern}(?!/)[^\n]*\.\.\s*{airport_pattern}\b',
        rf'(?m)^{airport_pattern}(?!/)[^\n]*\b[A-Z]\d{{1,4}}\b',
    ]
    for pat in patterns:
        airport_match = re.search(pat, text, re.IGNORECASE)
        if not airport_match:
            continue
        start_pos = airport_match.start()
        remaining_text = text[start_pos:]
        dist_match = re.search(r'\bDIST\b', remaining_text, re.IGNORECASE | re.MULTILINE)
        if not dist_match:
            continue
        route = remaining_text[:dist_match.start()].strip()
        route = ' '.join(route.split())
        if 20 <= len(route) <= 500 and not re.search(r'[A-Z]\)\s+', route) and is_valid_ofp_route(route):
            return route
    return ''

