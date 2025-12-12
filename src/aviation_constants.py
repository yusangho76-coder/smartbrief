# SmartNOTAMgemini_GCR에서 가져온 항공 용어 설정
"""
항공 용어 설정 파일 (SmartNOTAMgemini_GCR에서 통합)
"""

"""
Aviation constants and abbreviations for NOTAM processing
"""
import re

# 번역하지 않을 항공 용어들 (대소문자 구분 없음)
NO_TRANSLATE_TERMS = [
    'NOTAM', 'AIRAC', 'AIP', 'SUP', 'AMDT', 'WEF', 'TIL', 'UTC',
    'GPS', 'RAIM', 'NPA', 'PBN', 'RNAV', 'RNP',
    'RWY', 'TWY', 'APRON', 'TAXI', 'SID', 'STAR', 'IAP',
    'SFC', 'AMSL', 'AGL', 'MSL',
    'PSN', 'RADIUS', 'HGT', 'HEIGHT',
    'TEMP', 'PERM', 'OBST', 'FIREWORKS'
]

# 빨간색 스타일 적용 용어 (위험/제한 관련)
RED_STYLE_TERMS = [
    'closed', 'close', 'closing', 'obstacle', 'obstacles', 'obstacle area', 
    'obstruction', 'obstructions', 'restricted', 'prohibited', 'severe', 
    'severe weather', 'volcanic ash', 'volcanic ash cloud', 'out of service', 
    'unserviceable', 'not available', 'not authorized', 'caution', 'cautious',
    'hazard', 'hazardous', 'hazardous weather', 'hazardous materials',
    'emergency', 'emergency landing', 'emergency landing procedure',
    '장애물', '장애물 구역', '장애물 설치', '장애물 설치됨',
    '사용 불가', '운용 중단', '제한됨', '폐쇄됨',
    '제한', '폐쇄', '중단', '불가능', '불가',
    '긴급', '긴급 착륙', '긴급 착륙 절차',
    '경보', '경보 발생', '경보 해제',
    '주의', '주의 요구', '주의 요구 사항',
    '크레인', 'crane', 'cranes',
    'GPS RAIM',  # GPS RAIM을 하나의 단어로 처리
    'Non-Precision Approach', 'non-precision approach',
    '포장 공사', 'pavement construction',
]

# 파란색 스타일 패턴 (시설/운영 관련)
BLUE_STYLE_PATTERNS = [
    r'\bDVOR\b',  # DVOR
    r'\bAPRON\b',  # APRON
    r'\bANTI-ICING\b',  # ANTI-ICING
    r'\bDE-ICING\b',  # DE-ICING
    r'\bDE/ANTI-ICING\b',  # DE/ANTI-ICING
    r'\bDE/ANTI-ICING\s+FLUID\b',  # DE/ANTI-ICING FLUID
    r'\bDE-ICING\s+FLUID\b',  # DE-ICING FLUID
    r'\bANTI-ICING\s+FLUID\b',  # ANTI-ICING FLUID
    r'\bSTAND\s+NUMBER\s+\d+\b',  # STAND NUMBER + 숫자
    r'\bSTAND\s+\d+\b',  # STAND + 숫자
    r'\bSTAND\b',  # STAND
    r'\bILS\b',  # ILS
    r'\bLOC\b',  # LOC
    r'\bS-LOC\b',  # S-LOC
    r'\bMDA\b',  # MDA
    r'\bCAT\b',  # CAT
    r'\bVIS\b',  # VIS
    r'\bRVR\b',  # RVR
    r'\bHAT\b',  # HAT
    r'\bRWY\s+(?:\d{2}[LRC]?(?:/\d{2}[LRC]?)?)\b',  # RWY + 숫자 + L/R/C
    r'\bTWY\s+(?:[A-Z]|[A-Z]{2}|[A-Z]\d{1,2})\b',  # TWY + 알파벳/숫자
    r'\bTWY\s+[A-Z]\b',  # TWY + 한 자리 알파벳
    r'\bTWY\s+[A-Z]{2}\b',  # TWY + 두 자리 알파벳
    r'\bTWY\s+[A-Z]\d{1,2}\b',  # TWY + 알파벳+숫자
    r'\bVOR\b',  # VOR
    r'\bDME\b',  # DME
    r'\bTWR\b',  # TWR
    r'\bATIS\b',  # ATIS
    r'\bAPPROACH MINIMA\b',  # APPROACH MINIMA
    r'\bVDP\b',  # VDP
    r'\bEST\b',  # EST
    r'\bEastern Standard Time\b',  # Eastern Standard Time
    r'\bIAP\b',  # IAP
    r'\bRNAV\b',  # RNAV
    r'\bGPS\s+(?:APPROACH|APP|APPROACHES)\b',  # GPS APPROACH
    r'\bLPV\b',  # LPV
    r'\bDA\b',  # DA
    r'\b주기장\b',  # 주기장
    r'\b주기장\s+\d+\b',  # 주기장 + 숫자
    r'\b활주로\s+\d+[A-Z]?\b',  # 활주로 + 숫자 + 알파벳
    r'\bP\d+\b',  # P + 숫자
    r'\bSTANDS?\s*(?:NR\.)?\s*(\d+)\b',  # STANDS NR. 711
    r'\bSTANDS?\s*(\d+)\b',  # STANDS 711
]

def apply_color_styles(text):
    """텍스트에 색상 스타일을 적용합니다."""
    if not text:
        return text
    
    # HTML 태그가 이미 있는지 확인하고 제거
    text = re.sub(r'<span[^>]*>', '', text)
    text = re.sub(r'</span>', '', text)
    
    # Runway를 RWY로 변환
    text = re.sub(r'\bRunway\s+', 'RWY ', text, flags=re.IGNORECASE)
    text = re.sub(r'\brunway\s+', 'RWY ', text, flags=re.IGNORECASE)
    
    # GPS RAIM을 하나의 단어로 처리
    text = re.sub(
        r'\bGPS\s+RAIM\b',
        r'<span style="color: red; font-weight: bold;">GPS RAIM</span>',
        text
    )
    
    # 빨간색 스타일 적용 (GPS RAIM 제외)
    for term in [t for t in RED_STYLE_TERMS if t != 'GPS RAIM']:
        if term.lower() in text.lower():
            text = re.sub(
                re.escape(term),
                lambda m: f'<span style="color: red; font-weight: bold;">{m.group()}</span>',
                text,
                flags=re.IGNORECASE
            )
    
    # 활주로 및 유도로 패턴 처리
    rwy_twy_patterns = [
        (r'(?:^|\s)(RWY\s*\d{2}[LRC]?(?:/\d{2}[LRC]?)?)', 'blue'),  # RWY 15L/33R
        (r'(?:^|\s)(TWY\s*[A-Z](?:\s+AND\s+[A-Z])*)', 'blue'),  # TWY D, TWY D AND E
        (r'(?:^|\s)(TWY\s*[A-Z]\d+)', 'blue'),  # TWY D1
    ]
    
    for pattern, color in rwy_twy_patterns:
        text = re.sub(
            pattern,
            lambda m: f' <span style="color: {color}; font-weight: bold;">{m.group(1).strip()}</span>',
            text
        )
    
    # 파란색 스타일 적용 (RWY, TWY 제외)
    for pattern in [p for p in BLUE_STYLE_PATTERNS if not (p.startswith(r'\bRWY') or p.startswith(r'\bTWY'))]:
        text = re.sub(
            pattern,
            lambda m: f'<span style="color: blue; font-weight: bold;">{m.group(0)}</span>',
            text,
            flags=re.IGNORECASE
        )
    
    # HTML 태그 중복 방지
    text = re.sub(r'(<span[^>]*>)+', r'\1', text)
    text = re.sub(r'(</span>)+', r'\1', text)
    text = re.sub(r'\s+', ' ', text)  # 중복 공백 제거
    
    return text.strip()

# 기본 약어 사전 - 번역 품질 향상을 위한 전처리용
DEFAULT_ABBR_DICT = {
    "OBST": "obstacle",
    "HGT": "height", 
    "TEMP": "temporary",
    "FLW": "following",
    "ASML": "above mean sea level",
    "CLSD": "closed",
    "DUE": "due to",
    "WIP": "work in progress",
    "ACFT": "aircraft",
    "TWY": "taxiway",
    "RWY": "runway",
    "APCH": "approach",
    "AVBL": "available",
    "BTN": "between",
    "COND": "condition",
    "COORD": "coordinate",
    "DEP": "departure",
    "EST": "estimated",
    "EXC": "except",
    "FM": "from",
    "INFO": "information",
    "MAINT": "maintenance",
    "OPR": "operational",
    "REF": "reference",
    "SKED": "scheduled",
    "SVC": "service",
    "THR": "threshold",
    "TIL": "until",
    "UFN": "until further notice",
    "AMSL": "above mean sea level",
    "PROC": "procedure",
    "ELEV": "elevation",
    "FRNG": "firing",
    "AREA": "area",
    "FREQ": "frequency",
    "EMRG": "emergency",
    "CTRL": "control",
    "ADVS": "advise",
    "WARN": "warning"
}

# 색상 스타일 적용 용어 (기존 구현 유지)
RED_STYLE_TERMS = [
    'closed', 'close', 'closing', 'obstacle', 'obstacles', 'obstacle area',
    'obstruction', 'obstructions', 'restricted', 'prohibited', 'severe',
    'severe weather', 'volcanic ash', 'volcanic ash cloud', 'out of service',
    'unserviceable', 'not available', 'not authorized', 'caution', 'cautious',
    'hazard', 'hazardous', 'hazardous weather', 'hazardous materials',
    'emergency', 'emergency landing', 'emergency landing procedure',
    '장애물', '장애물 구역', '장애물 설치', '장애물 설치됨',
    '사용 불가', '운용 중단', '제한됨', '폐쇄됨', '제한', '폐쇄', '중단',
    '불가능', '불가', '긴급', '긴급 착륙', '긴급 착륙 절차',
    '경보', '경보 발생', '경보 해제', '주의', '주의 요구', '주의 요구 사항',
    '크레인', 'crane', 'cranes', 'GPS RAIM', 'Non-Precision Approach',
    'non-precision approach', '포장 공사', 'pavement construction',
    'AIRAC AIP SUP', 'UTC'
]

BLUE_STYLE_PATTERNS = [
    r'\bDVOR\b',
    r'\bAPRON\b', 
    r'\bANTI-ICING\b',
    r'\bDE-ICING\b',
    r'\bSTAND\s+NUMBER\s+\d+\b',
    r'\bSTAND\s+\d+\b',
    r'\bSTAND\b',
    r'\bILS\b',
    r'\bLOC\b',
    r'\bS-LOC\b'
]