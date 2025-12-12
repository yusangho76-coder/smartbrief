"""
Route 추출 및 비교 로직
PDF에서 OFP route와 ATS FPL route를 추출하고 정규화하여 비교합니다.
"""
import re
from typing import Optional, Tuple, Dict, List


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
        
        # 공항 코드 (4자리 대문자)
        if re.match(r'^[A-Z]{4}$', element):
            waypoints.append(element)
        # Airway (예: Y697, A591, W4, B339 등)
        elif re.match(r'^[A-Z]\d+$', element):
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
    2페이지에서 OFP route를 추출합니다.
    Route는 "공항코드.."로 시작하고 "DIST" 이전까지 추출합니다.
    예: "RKSI..NOPIK Y697 AGAVO A591 IKEKA W4 HCH W200 DOVIV W55 PAMRU W34 LADIX"
    """
    if not page_text:
        return None
    
    # 공항코드 패턴
    airport_pattern = r'[A-Z]{4}'
    
    # "공항코드.."로 시작하는 패턴 찾기
    # 예: "RKSI..", "LOWW.." 등
    start_pattern = rf'({airport_pattern}\.\.)'
    
    # 시작 위치 찾기
    start_match = re.search(start_pattern, page_text)
    if not start_match:
        return None
    
    start_pos = start_match.start()
    
    # "DIST" 키워드 찾기 (대소문자 구분 없이)
    dist_match = re.search(r'\bDIST\b', page_text[start_pos:], re.IGNORECASE)
    if not dist_match:
        # DIST를 찾지 못하면 공항코드로 끝나는 패턴으로 대체
        # 공항코드로 끝나는 가장 긴 블록 찾기
        remaining_text = page_text[start_pos:]
        end_match = re.search(rf'({airport_pattern})(?=\s|$|\n|DIST)', remaining_text)
        if end_match:
            end_pos = start_pos + end_match.end()
        else:
            # 끝을 찾지 못하면 시작 위치부터 1000자까지
            end_pos = min(start_pos + 1000, len(page_text))
    else:
        # DIST 이전까지
        end_pos = start_pos + dist_match.start()
    
    # Route 추출
    route = page_text[start_pos:end_pos].strip()
    
    # 유효성 검사
    if len(route) < 20 or len(route) > 1000:
        return None
    
    # Waypoint나 Airway가 포함되어 있는지 확인
    waypoint_pattern = r'[A-Z]{2,}'
    airway_pattern = r'[A-Z]\d+'
    has_waypoint = bool(re.search(waypoint_pattern, route))
    has_airway = bool(re.search(airway_pattern, route))
    if not (has_waypoint or has_airway):
        return None
    
    # Route 요소 개수 확인
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
    
    # "COPY OF ATS FPL" 또는 "ATS FPL" 키워드 확인
    if 'COPY OF ATS FPL' not in page_text.upper() and 'ATS FPL' not in page_text.upper():
        return None
    
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

