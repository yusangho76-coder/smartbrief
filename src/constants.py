"""
항공 용어 및 상수 설정 파일
참조: SmartNOTAMgemini_GCR/constants.py
"""

# 번역하지 않을 용어 목록
NO_TRANSLATE_TERMS = [
    # NOTAM 관련 용어
    "NOTAM", "NOTAMN", "NOTAMR", "NOTAMC", "TRIGGER NOTAM",
    "AIRAC", "AIP", "AIP SUP", "AIP AMDT",
    
    # # 공항 및 항공 관련 코드
    # "RKSS", "RKSI", "RKRR", "RKPC", "RKPK", "RKTU", "RKNY", "RKJJ",
    # "KLAX", "KSEA", "LFLN", "LFGN",
    
    # 항행 보조 시설
    "ILS", "VOR", "DME", "NDB", "ADF", "RNAV", "GPS", "RAIM",
    "LPV", "LOC", "S-LOC", "MDA", "DA", "HAT", "VDP",
    
    # 공항 시설
    "RWY", "TWY", "APRON", "TWR", "ATIS", "CTR", "FIR", "TMA",
    "STAND", "STANDS", "PARKING",
    
    # 단위 및 측정
    "UTC", "EST", "FT", "NM", "KM", "M", "MHZ", "KHZ",
    
    # 기타 전문 용어
    "ATC", "CNS", "MET", "VHF", "HF", "UHF", "RADAR", "TCAS",
    "GPWS", "EGPWS", "ACAS", "SID", "STAR", "IAP", "NPA",
    
    # 항공기 제조사 및 시스템
    "BOEING", "AIRBUS", "TERR", "OVRD", "OFF", "INHIB", "INHIBIT",
    "EGPWS", "TERR-INHIB", "TERR - OVRD", "TERR - OFF",
    
    # 날짜 및 시간 형식
    "SR", "SS", "SFC", "ASFC", "AMSL", "AGL",
    
    # 방향 및 위치
    # "N", "S", "E", "W", "NE", "NW", "SE", "SW",
    # "L", "R", "C", "LEFT", "RIGHT", "CENTER",
    
    # 상태 및 조건
    # "U/S", "AVBL", "ACT", "INOP",
    # "TEMP", "PERM", "EST",

]

# 기본 약어 사전
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
    "A/C": "aircraft"
}

# 색상 스타일 적용 용어 (위험/주의사항)
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

# 파란색 스타일 패턴 (항공시설/정보)
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
    r'\bS-LOC\b',
    r'\bMDA\b',
    r'\bCAT\b',
    r'\bVIS\b',
    r'\bRVR\b',
    r'\bHAT\b',
    r'\bRWY\s+(?:\d{2}[LRC]?(?:/\d{2}[LRC]?)?)\b',
    r'\bTWY\s+(?:[A-Z]|[A-Z]{2}|[A-Z]\d{1,2})\b',
    r'\bTWY\s+[A-Z]\b',
    r'\bTWY\s+[A-Z]{2}\b',
    r'\bTWY\s+[A-Z]\d{1,2}\b',
    r'\bVOR\b',
    r'\bDME\b',
    r'\bTWR\b',
    r'\bATIS\b',
    r'\bAPPROACH MINIMA\b',
    r'\bVDP\b',
    r'\bEST\b',
    r'\bEastern Standard Time\b',
    r'\bIAP\b',
    r'\bRNAV\b',
    r'\bGPS\s+(?:APPROACH|APP|APPROACHES)\b',
    r'\bLPV\b',
    r'\bDA\b',
    r'\b주기장\b',
    r'\b주기장\s+\d+\b',
    r'\b활주로\s+\d+[A-Z]?\b',
    r'\bP\d+\b',
    r'\bSTANDS?\s*(?:NR\.)?\s*(\d+)\b',
    r'\bSTANDS?\s*(\d+)\b',
]

# NOTAM 시작 패턴 (다양한 형식 지원)
NOTAM_START_PATTERN = r'(\d{2}[A-Z]{3}\d{2} \d{2}:\d{2} - (?:\d{2}[A-Z]{3}\d{2} \d{2}:\d{2}|UFN) [A-Z]{4} [A-Z0-9/ ]+)'

# 추가 NOTAM 패턴들 (다양한 형식 지원)
NOTAM_PATTERNS = [
    # 실제 발견된 패턴: 09JUL25 16:00 - 25SEP25 09:00 RKSI Z0582/25
    r'\d{2}[A-Z]{3}\d{2} \d{2}:\d{2} - (?:\d{2}[A-Z]{3}\d{2} \d{2}:\d{2}|UFN) [A-Z]{4} [A-Z0-9/]+',
    # 표준 NOTAM 형식: V0319/25 NOTAMN Q)...
    r'\b[A-Z]\d{4}/\d{2}\s+NOTAM[NRC]?\b',
    # FAA 형식: !LAX 03/235
    r'![A-Z]{3}\s+\d{2}/\d{3}',
    # FDC 형식: !FDC 1/1234
    r'!FDC\s+\d+/\d+',
    # 일반 NOTAM 형식: NOTAM 4/3193
    r'NOTAM\s+\d+/\d+'
]

# 대한항공 관련 키워드
KOREAN_AIR_KEYWORDS = [
    'KOREAN AIR NOTAM PACKAGE',
    'RKSI', 'RKSS', 'RKPC', 'RKPK', 'RKTU', 'RKNY', 'RKJJ',  # 한국 공항 코드
    'KOREA', 'SEOUL', 'INCHEON', 'GIMPO', 'BUSAN', 'JEJU',
    'KAL', 'KOREAN AIR', 'ASIANA', 'COMMENT'
]

# 한국 공항 코드 매핑
KOREAN_AIRPORTS = {
    'RKSI': '인천국제공항',
    'RKSS': '김포국제공항',
    'RKPC': '제주국제공항',
    'RKPK': '김해국제공항',
    'RKTU': '청주국제공항',
    'RKNY': '양양국제공항',
    'RKJJ': '광주공항'
}

# 우선순위 NOTAM 키워드 (중요도 높음)
PRIORITY_KEYWORDS = [
    'CLOSED', 'CLOSE', 'CLOSING',
    'BLOCKED', 'OBSTACLE', 'OBSTRUCTION',
    'EMERGENCY', 'CAUTION', 'RESTRICTED',
    'OUT OF SERVICE', 'UNSERVICEABLE',
    'GPS RAIM', 'SEVERE WEATHER'
]

# NOTAM 구분자 패턴들
NOTAM_SEPARATOR_PATTERNS = [
    # 기본 구분선 패턴
    r'^-{3,}$',  # 3개 이상의 하이픈
    r'^={3,}$',  # 3개 이상의 등호
    r'^_{3,}$',  # 3개 이상의 언더스코어
    r'^\*{3,}$',  # 3개 이상의 별표
    r'^#{3,}$',  # 3개 이상의 해시
    r'^\.{3,}$',  # 3개 이상의 점
    
    # 공백이 포함된 구분선 패턴
    r'^[\s\-]{5,}$',  # 하이픈과 공백 조합
    r'^[\s=]{5,}$',   # 등호와 공백 조합
    r'^[\s_]{5,}$',   # 언더스코어와 공백 조합
    r'^[\s\*]{5,}$',  # 별표와 공백 조합
    r'^[\s#]{5,}$',   # 해시와 공백 조합
    r'^[\s\.]{5,}$',  # 점과 공백 조합
    
    # 혼합 구분선 패턴
    r'^[\-\=\_\*\#\.]{3,}$',  # 다양한 구분자 조합
    
    # NOTAM 관련 구분자 텍스트
    r'^NOTAM\s+SEPARATOR$',
    r'^NOTAM\s+DIVIDER$',
    r'^NOTAM\s+BREAK$',
    r'^END\s+OF\s+NOTAM$',
    r'^NOTAM\s+END$',
    
    # 빈 줄이 아닌 구분자들 (공백만 있는 줄은 제외)
    r'^[^\s].*[^\s]$',  # 시작과 끝에 공백이 아닌 문자가 있는 줄
]

# 색상 스타일 적용 함수에서 사용할 HTML 태그
COLOR_STYLES = {
    'red': '<span style="color: red; font-weight: bold;">',
    'blue': '<span style="color: blue; font-weight: bold;">',
    'end': '</span>'
}