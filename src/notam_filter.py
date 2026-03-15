import os
import google.generativeai as genai
from dotenv import load_dotenv
import re
from datetime import datetime, timedelta
from src.timezone_api import _timezone_api
import json
import csv
import logging
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from constants import NO_TRANSLATE_TERMS, DEFAULT_ABBR_DICT
from typing import Dict, List, Optional

# 환경 변수 로드
load_dotenv()

# Google API 키 설정 (선택사항) - 클래스 내부에서 초기화
GOOGLE_API_KEY = None
GEMINI_AVAILABLE = False
model = None

# NOTAM 카테고리 매핑 (아이콘과 색깔 포함)
NOTAM_CATEGORIES = {
    'RUNWAY': {
        'keywords': ['runway', 'rw', '활주로', '착륙', '이륙', 'landing', 'takeoff'],
        'q_codes': ['Q) RW', 'Q) RWY'],
        'icon': '🛬',
        'color': '#dc3545',  # 빨간색 (위험/중요)
        'bg_color': '#f8d7da'
    },
    'TAXIWAY': {
        'keywords': ['taxiway', 'tw', 'twy', '택시웨이', '유도로', 'movement area'],
        'q_codes': ['Q) TW', 'Q) TWY'],
        'icon': '🛣️',
        'color': '#fd7e14',  # 주황색
        'bg_color': '#fff3cd'
    },
    'APRON': {
        'keywords': ['apron', 'ramp', 'gate', 'docking', 'mars', '계류장', '게이트', '접현', '도킹', 'lead-in line', 'vdgs'],
        'q_codes': ['Q) APRON', 'Q) RAMP'],
        'icon': '🅿️',
        'color': '#6f42c1',  # 보라색
        'bg_color': '#e2d9f3'
    },
    'LIGHT': {
        'keywords': ['light', 'lighting', 'lgt', '조명', '등화', 'beacon', 'approach light', 'runway light'],
        'q_codes': ['Q) LGT', 'Q) LIGHT'],
        'icon': '💡',
        'color': '#ffc107',  # 노란색
        'bg_color': '#fff3cd'
    },
    'APPROACH': {
        'keywords': [
            'approach procedure', 'approach minima', 'instrument approach', 'precision approach',
            'gps approach', 'ils', 'vor approach', 'ndb approach', '접근 절차', '정밀 접근'
        ],
        'q_codes': ['Q) APP', 'Q) ILS', 'Q) VOR', 'Q) NDB'],
        'icon': '📡',
        'color': '#20c997',  # 청록색
        'bg_color': '#d1ecf1'
    },
    'DEPARTURE': {
        'keywords': ['departure procedure', 'dep procedure', 'sid', 'standard instrument departure', '출발 절차', '이륙 절차'],
        'q_codes': ['Q) DEP', 'Q) SID'],
        'icon': '✈️',
        'color': '#0dcaf0',  # 하늘색
        'bg_color': '#cff4fc'
    },
    'GPS': {
        'keywords': ['gps', 'gnss', 'raim', 'gps approach', 'gps outage', 'gps unavailable'],
        'q_codes': ['Q) GPS', 'Q) GNSS', 'Q) RAIM'],
        'icon': '🛰️',
        'color': '#198754',  # 녹색
        'bg_color': '#d1e7dd'
    },
    'OBSTRUCTION': {
        'keywords': ['obstacle', 'obstruction', 'obstacles', 'obstructions', '장애물', '장애물 구역'],
        'q_codes': ['Q) OBST', 'Q) OBSTRUCTION'],
        'icon': '⚠️',
        'color': '#dc3545',  # 빨간색 (위험)
        'bg_color': '#f8d7da'
    },
    'NAVAID': {
        'keywords': ['navaid', 'navigation aid', 'vor', 'ndb', 'ils', 'dme', 'tacan', '항행보조시설'],
        'q_codes': ['Q) NAVAID', 'Q) VOR', 'Q) NDB', 'Q) ILS', 'Q) DME'],
        'icon': '📶',
        'color': '#6c757d',  # 회색
        'bg_color': '#e9ecef'
    },
    'COMMUNICATION': {
        'keywords': ['communication', 'comm', 'radio', 'frequency', '통신', '주파수', 'frequency change'],
        'q_codes': ['Q) COMM', 'Q) FREQ'],
        'icon': '📻',
        'color': '#0d6efd',  # 파란색
        'bg_color': '#cfe2ff'
    },
    'AIRWAY': {
        'keywords': [
            'airway', 'air route', 'ats route', 'ats rte', 'temporary route', 'route closure',
            'route closed', 'segment closed', '항로', '항공로', '항로 폐쇄', 'enroute', 'rte',
            'flight route adjustment', 'route adjustment'
        ],
        'q_codes': ['Q) AWY', 'Q) AIRWAY'],
        'icon': '🗺️',
        'color': '#fd7e14',  # 주황색
        'bg_color': '#fff3cd'
    },
    'FLOW_CONTROL': {
        'keywords': [
            'flow control', 'flow ctl', 'traffic flow', 'traffic flow management',
            'slot', 'slot regulation', 'slot allocation', 'ctot', 'regulation',
            'flow restriction', 'airspace flow program'
        ],
        'q_codes': ['QPF', 'QPFCA'],
        'icon': '📊',
        'color': '#17a2b8',  # 청록색
        'bg_color': '#d1ecf1'
    },
    'AIRSPACE': {
        'keywords': ['airspace', 'air space', 'controlled airspace', 'airspace restriction', '공역', '제한공역'],
        'q_codes': ['Q) AIRSPACE'],
        'icon': '🌐',
        'color': '#6f42c1',  # 보라색
        'bg_color': '#e2d9f3'
    },
    'AIP': {
        'keywords': ['aip', 'aeronautical information publication', '항공정보간행물'],
        'q_codes': ['Q) AIP'],
        'icon': '📋',
        'color': '#6c757d',  # 회색
        'bg_color': '#e9ecef'
    }
}

def analyze_notam_category(notam_text, q_code=None):
    """NOTAM 텍스트와 Q-code를 분석하여 카테고리 결정"""
    if not notam_text:
        return 'OTHER'
    
    # 텍스트를 소문자로 변환하여 분석
    text_lower = notam_text.lower()
    
    # Q-code가 있으면 우선적으로 사용
    if q_code:
        q_code_upper = q_code.upper()
        for category, data in NOTAM_CATEGORIES.items():
            for q_pattern in data['q_codes']:
                if q_pattern.upper() in q_code_upper:
                    return category
    
    # 키워드 기반 분석 (가중치 적용)
    category_scores = {}
    for category, data in NOTAM_CATEGORIES.items():
        score = 0
        for keyword in data['keywords']:
            keyword_lower = keyword.lower()
            # 정확한 단어 매칭 (단어 경계 고려)
            if re.search(r'\b' + re.escape(keyword_lower) + r'\b', text_lower):
                # 중요한 키워드는 더 높은 가중치
                if keyword_lower in ['gate', 'docking', 'mars', 'apron', 'ramp', 'vdgs']:
                    score += 3
                elif keyword_lower in ['runway', 'taxiway', 'approach', 'departure']:
                    score += 2
                else:
                    score += 1
        category_scores[category] = score
    
    # 가장 높은 점수의 카테고리 반환
    if category_scores:
        best_category = max(category_scores.items(), key=lambda x: x[1])[0]
        if category_scores[best_category] > 0:
            return best_category
    
    return 'OTHER'

# 색상 패턴 정의
RED_STYLE_TERMS = [
    'closed', 'close', 'closing','obstacle','obstacles','obstacle area','obstruction','obstructions',
    'restricted','prohibited','severe','severe weather','volcanic ash','volcanic ash cloud',
    'out of service', 'unserviceable', 'not available','not authorized',
    'caution','cautious','cautionary',
    'hazard','hazardous','hazardous weather','hazardous materials',
    'emergency','emergency landing','emergency landing procedure',
    '장애물', '장애물 구역', '장애물 설치', '장애물 설치됨',
    '사용 불가', '운용 중단', '제한됨', '폐쇄됨',
    '제한', '폐쇄', '중단', '불가능', '불가',
    '긴급', '긴급 착륙', '긴급 착륙 절차',
    '경보', '경보 발생', '경보 해제', '오경보',
    '주의', '주의 요구', '주의 요구 사항',
    '크레인', 'crane', 'cranes',
    'GPS RAIM',  # GPS RAIM을 하나의 단어로 처리
    'Non-Precision Approach', 'non-precision approach',
    '포장 공사', 'pavement construction',
]

BLUE_STYLE_PATTERNS = [
    r'\bDVOR\b',  # DVOR
    r'\bAPRON\b',  # APRON
    r'\bANTI-ICING\b',  # ANTI-ICING
    r'\bPAINTING\b',  # PAINTING
    r'\bDE-ICING\b',  # DE-ICING
    r'\bSTAND\s+NUMBER\s+\d+\b',  # STAND NUMBER + 숫자 (예: STAND NUMBER 711)
    r'\bSTAND\s+\d+\b',  # STAND + 숫자 (예: STAND 711)
    r'\bSTAND\b',  # STAND
    r'\bILS\b',  # ILS
    r'\bLOC\b',  # LOC
    r'\bS-LOC\b',  # S-LOC
    r'\bMDA\b',  # MDA
    r'\bCAT\b',  # CAT
    r'\bVIS\b',  # VIS
    r'\bRVR\b',  # RVR
    r'\bHAT\b',  # HAT
    r'\bRWY\s+(?:\d{2}[LRC]?(?:/\d{2}[LRC]?)?)\b',  # RWY + 숫자 + 선택적 L/R/C (예: RWY 15L/33R)
    r'\bTWY\s+(?:[A-Z]|[A-Z]{2}|[A-Z]\d{1,2})\b',  # TWY + 알파벳(1-2자리) 또는 알파벳+숫자(1-2자리)
    r'\bTWY\s+[A-Z]\b',  # TWY + 한 자리 알파벳 (예: TWY D)
    r'\bTWY\s+[A-Z]{2}\b',  # TWY + 두 자리 알파벳 (예: TWY DD)
    r'\bTWY\s+[A-Z]\d{1,2}\b',  # TWY + 알파벳+숫자(1-2자리) (예: TWY D1, TWY D12)
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
    r'\bGPS\s+(?:APPROACH|APP|APPROACHES)\b',  # GPS APPROACH, GPS APP 등
    r'\bLPV\b',  # LPV
    r'\bDA\b',  # DA
    r'\b주기장\b',  # 주기장
    r'\b주기장\s+\d+\b',  # 주기장 + 숫자
    r'\b활주로\s+\d+[A-Z]?\b',  # 활주로 + 숫자 + 선택적 알파벳
    r'\bP\d+\b',  # P + 숫자
    r'\bSTANDS?\s*(?:NR\.)?\s*(\d+)\b',  # STANDS NR. 711 형식
    r'\bSTANDS?\s*(\d+)\b',  # STANDS 711 형식
]

def apply_color_styles(text):
    """텍스트에 색상 스타일을 적용합니다."""
    
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
        (r'\b(RWY\s*\d{2}[LRC]?(?:/\d{2}[LRC]?)?)\b', 'blue'),  # RWY 15L/33R
        (r'\b(RWY\s*\|)\b', 'blue'),  # RWY |
        (r'\b(RWY)\b', 'blue'),  # RWY 단독
        (r'\b(TWY\s*[A-Z](?:\s+AND\s+[A-Z])*)\b', 'blue'),  # TWY D, TWY D AND E
        (r'\b(TWY\s*[A-Z]\d+)\b', 'blue'),  # TWY D1
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

# 모듈 레벨에서 정리 패턴 사전 컴파일 (성능 최적화 - 모든 호출에서 재사용)
_E_SECTION_CLEANUP_PATTERNS = {
    'no_current': re.compile(r'\*{8}\s*NO CURRENT NOTAMS FOUND\s*\*{8}.*$', re.DOTALL | re.IGNORECASE),
    'created': re.compile(r'CREATED:.*$', re.DOTALL),
    'source': re.compile(r'SOURCE:.*$', re.DOTALL),
    # 카테고리 마커 제거 패턴 개선: ◼ 또는 ■ 뒤에 오는 모든 텍스트(특수문자 포함) 제거
    # 예: ◼ RUNWAY, ■ TAXIWAY, ◼ COMPANY MINIMA FOR CAT II/III 등
    'category_marker': re.compile(r'[◼■]\s*[^\n]*(?:\n|$)', re.MULTILINE)
}

_SECURITY_FOOTER_PATTERNS = [
    re.compile(r'^SECY\s*/\s*SECURITY INFORMATION', re.IGNORECASE),
    re.compile(r'^SECY\s+COAD\d+/\d+', re.IGNORECASE),
    re.compile(r'^SECY\s*$', re.IGNORECASE),
    re.compile(r'^COMPANY\s+ADVISORY', re.IGNORECASE),
    re.compile(r'^\d+\.\s+\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*-\s*\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s+SECY', re.IGNORECASE),
]


def truncate_at_package_end(text: str) -> str:
    """
    NOTAM 원문에서 'END OF KOREAN AIR NOTAM PACKAGE' 이후(CFP, REFILE, 경로표 등)를 제거합니다.
    같은 줄에 붙어 있거나 줄바꿈 누락으로 패키지 종료 문구 이후가 섞였을 때 원문이 길어지는 것을 방지합니다.
    """
    if not text:
        return text
    idx = re.search(r'\bEND\s+OF\s+KOREAN\s+AIR\s+NOTAM\s+PACKAGE\b', text, re.IGNORECASE)
    if idx:
        return text[:idx.start()].rstrip()
    return text


def strip_security_footer(text: str) -> str:
    """
    SECY / SECURITY INFORMATION 및 COMPANY ADVISORY 등 보안 부속 정보를 제거합니다.
    해당 문구가 등장하면 이후 내용은 모두 무시합니다.
    """
    if not text:
        return text
    cleaned_lines = []
    for line in text.splitlines():
        line_stripped = line.strip()
        if not line_stripped:
            cleaned_lines.append(line)
            continue
        if any(pattern.search(line_stripped) for pattern in _SECURITY_FOOTER_PATTERNS):
            break
        cleaned_lines.append(line)
    return '\n'.join(cleaned_lines).strip()

def extract_e_section(notam_text, compiled_patterns=None):
    """
    NOTAM 텍스트에서 E 섹션만 추출합니다.
    여러 줄에 걸친 NOTAM도 완전히 추출합니다.
    
    Args:
        notam_text: NOTAM 텍스트
        compiled_patterns: 사전 컴파일된 패턴 리스트 (선택사항, 성능 최적화용)
    """
    # 사전 컴파일된 패턴이 제공되면 사용 (성능 최적화)
    if compiled_patterns:
        patterns = compiled_patterns
    else:
        # 패턴이 제공되지 않으면 런타임에 컴파일 (하위 호환성)
        # 하지만 한 번만 컴파일하고 재사용 (모듈 레벨 캐싱)
        # 모듈 레벨 변수로 관리 (함수 속성 대신)
        global _E_SECTION_FALLBACK_PATTERNS
        if '_E_SECTION_FALLBACK_PATTERNS' not in globals():
            _E_SECTION_FALLBACK_PATTERNS = [
                re.compile(r'E\)\s*(.+?)(?=(?:\n|^)\s*={20,}\s*$)', re.DOTALL | re.MULTILINE),
                re.compile(
                    r'E\)\s*(.+?)(?=(?:\n|^)\s*\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*-\s*(?:\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}|UFN|PERM)\s+[A-Z]{4})',
                    re.DOTALL | re.MULTILINE
                ),
                re.compile(r'E\)\s*(.+?)(?=(?:\n|^)\s*[A-Z]\)\s*[A-Z])', re.DOTALL | re.MULTILINE),
                re.compile(r'E\)\s*(.+?)$', re.DOTALL)
            ]
        patterns = _E_SECTION_FALLBACK_PATTERNS
    
    # 우선순위 순서로 패턴 시도 (조기 종료 최적화)
    for pattern in patterns:
        match = pattern.search(notam_text)
        if match:
            e_section = match.group(1).strip()
            # 정리 작업 (모듈 레벨 사전 컴파일된 패턴 사용)
            e_section = _E_SECTION_CLEANUP_PATTERNS['no_current'].sub('', e_section).strip()
            e_section = _E_SECTION_CLEANUP_PATTERNS['created'].sub('', e_section).strip()
            e_section = _E_SECTION_CLEANUP_PATTERNS['source'].sub('', e_section).strip()
            e_section = _E_SECTION_CLEANUP_PATTERNS['category_marker'].sub('', e_section).strip()  # 카테고리 마커 제거
            e_section = strip_security_footer(e_section)
            if e_section:
                return e_section  # 조기 종료
    return ""  # E 섹션을 찾지 못하면 빈 문자열 반환

# 사용되지 않는 번역 함수 제거됨 (integrated_translator에서 처리)

def identify_notam_type(notam_number):
    """NOTAM 번호를 기반으로 NOTAM 타입을 식별합니다."""
    prefix = notam_number[0].upper()
    
    notam_types = {
        'A': "AERODROME NOTAM",
        'B': "BEACON NOTAM",
        'C': "COMMUNICATION NOTAM",
        'D': "DANGER AREA NOTAM",
        'E': "ENROUTE NOTAM",
        'F': "FLIGHT INFORMATION NOTAM",
        'G': "GENERAL NOTAM",
        'H': "HELIPORT NOTAM",
        'I': "INSTRUMENT APPROACH NOTAM",
        'L': "LIGHTING NOTAM",
        'M': "MILITARY NOTAM",
        'N': "NEW NOTAM",
        'O': "OBSTACLE NOTAM",
        'P': "PROHIBITED AREA NOTAM",
        'R': "RESTRICTED AREA NOTAM",
        'S': "SNOWTAM",
        'T': "TERMINAL NOTAM",
        'U': "UNMANNED AIRCRAFT NOTAM",
        'V': "VOLCANIC ACTIVITY NOTAM",
        'W': "WARNING NOTAM",
        'X': "OTHER NOTAM",
        'Z': "TRIGGER NOTAM"
    }
    
    return notam_types.get(prefix, "GENERAL NOTAM")

__all__ = ['apply_color_styles', 'RED_STYLE_TERMS', 'BLUE_STYLE_PATTERNS', 'NOTAMFilter']


class NOTAMFilter:
    """NOTAM 필터링 및 파싱 클래스"""
    
    def __init__(self):
        """NOTAMFilter 초기화"""
        # 로거 설정
        self.logger = logging.getLogger(__name__)
        
        # GEMINI API 초기화
        self.GEMINI_AVAILABLE = False
        self.model = None
        self._init_gemini()
        
        # 패키지별 공항 순서 정의
        self.package_airport_order = {
            'package1': ['RKSI', 'VVDN', 'VVTS', 'VVCR', 'SECY'],
            'package2': ['RKSI', 'RKPC', 'ROAH', 'RJFF', 'RORS', 'RCTP', 'VHHH', 'ZJSY', 'VVNB', 'VVDN', 'VVTS'],
            'package3': ['RKRR', 'RJJJ', 'RCAA', 'VHHK', 'ZJSA', 'VVHN', 'VVHM']
        }
        
        # 로거 레벨만 설정 (핸들러는 app.py에서 이미 설정됨)
        self.logger.setLevel(logging.INFO)
            
        # 공항 데이터 로드
        self.airports_data = self._load_airports_data()
        
        # 시간대 캐시 (성능 최적화)
        self.timezone_cache = {}
        
        # 정규식 패턴 사전 컴파일 (성능 최적화 - 전략 1)
        self._compile_regex_patterns()

    def warmup_airport_timezones(self, airports, sample_times_utc: Optional[List[str]] = None):
        """패키지에 포함된 공항들의 타임존 ID/오프셋을 미리 해석해 캐시에 적재

        - 공항당 1회만 IANA 타임존 ID를 해석(필요 시 원격 허용: TIMEZONE_FALLBACK_ENABLED)
        - 이후 개별 NOTAM 시간 변환 시에는 zoneinfo만 사용하므로 네트워크 호출이 발생하지 않음

        Args:
            airports: 공항 코드(ICAO)들의 이터러블
            sample_times_utc: 선택. 'YYYY-MM-DDTHH:MM:SSZ' 형식의 UTC 시각 문자열 리스트.
                              제공 시 각 공항-시각 쌍에 대해 오프셋을 미리 계산(로컬 zoneinfo)
        Returns:
            dict: { ICAO: timezone_id or None }
        """
        from datetime import datetime
        # 원격 폴백 허용 여부는 환경 변수로 제어(기본 False)
        allow_remote = os.getenv('TIMEZONE_FALLBACK_ENABLED', '0').lower() in ('1', 'true', 'yes')
        results = {}
        unique_airports = { (a or '').strip().upper() for a in airports if a }
        if not unique_airports:
            return results

        self.logger.debug(f"타임존 워밍업 시작: {len(unique_airports)}개 공항, 원격허용={allow_remote}")
        for icao in unique_airports:
            try:
                tzid = _timezone_api.get_timezone_id_by_icao(icao, allow_remote=allow_remote)
                results[icao] = tzid
                if tzid:
                    self.logger.debug(f"워밍업: {icao} -> {tzid}")
                    # 선택적으로 표본 시각에 대한 오프셋도 미리 계산(네트워크 없이 zoneinfo만)
                    if sample_times_utc:
                        for s in sample_times_utc:
                            try:
                                dt = datetime.fromisoformat(s.replace('Z', '+00:00'))
                                _ = _timezone_api.get_offset_for_datetime(icao, dt, allow_remote=False)
                            except Exception:
                                continue
                else:
                    self.logger.warning(f"워밍업: {icao} 타임존 ID 해석 실패")
            except Exception as e:
                self.logger.error(f"워밍업 중 오류({icao}): {e}")
                results[icao] = None
        self.logger.debug("타임존 워밍업 완료")
        return results
    
    def _compile_regex_patterns(self):
        """정규식 패턴을 사전 컴파일하여 성능 최적화"""
        import re
        
        # additional_info_patterns 컴파일
        self.compiled_additional_info_patterns = [
            re.compile(pattern, re.IGNORECASE) for pattern in [
                r'^\d+\.\s*COMPANY\s+RADIO\s*:',
                r'^\d+\.\s*COMPANY\s+ADVISORY\s*:',
                r'^\d+\.\s*RADIO\s*:',
                r'^\d+\.\s*ADVISORY\s*:',
                r'^\d+\.\s*[A-Z\s]+\s*:',
                r'^\[PAX\]',
                r'^\[JINAIR\]',
                r'^CTC\s+TWR',
                r'^NIL\s*$',
                r'^COMMENT\)\s*$',
                r'^\d+\.\s+\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*-\s*(?:UFN|PERM)\s+[A-Z]{4}\s+(?!COAD)[A-Z]+\d+/\d+',
                r'â—C¼O\s*MPANY',
                r'â—C¼O\s*COMPANY',
                r'â—A¼R\s*RIVAL',
                r'â—O¼B\s*STRUCTION',
                r'â—G¼P\s*S',
                r'â—R¼U\s*NWAY',
                r'â—A¼PP\s*ROACH',
                r'â—T¼A\s*XIWAY',
                r'â—N¼A\s*VAID',
                r'â—D¼E\s*PARTURE',
                r'â—R¼U\s*NWAY\s*LIGHT',
                r'â—A¼IP',
                r'â—O¼T\s*HER',
                r'//REQUIRED WEATHER MINIMA IN VIETNAM//',
                r'// SPEED LIMIT WHEN USING VDGS //',
                r'CAAV\(CIVIL AVIATION AUTHORITY OF VIETNAM\)',
                r'CARGO FLIGHTS ARE NOT ALLOWED TO LAND EARLIER',
                r'PLZ DEPART TO HAN AFTER ETD ON FPL',
                r'ANY QUESTIONS ABOUT ETD OF FLT',
                r'CONTACT KOREANAIR DISPATCH BY CO-RADIO',
                r'// SIMILAR CALLSIGN //',
                r'KE\d+ AND KE\d+ MAY OPERATE ON SAME FREQ',
                r'PLZ PAY MORE ATTENTION TO ATC COMMUNICATION',
                r'CEILING IS ALWAYS SHOWN IN SMALLER SIZE',
                r'MUST NOT EXCEED \d+KTS FROM STARTING POINT',
                r'REDUCE SPEED TO STOP AT THE DESIGNATED STOP LINE',
                r'^\d+\.\s+ANY REVISION TO RWY CLOSURE',
                r'^\d+\.\s+IN THE EVENT THAT THE OPERATIONAL RWY',
                r'DEPENDENT ON THE WORK BEING CARRIED OUT',
                r'IT MAY TAKE UP TO \d+ HRS FOR A CLOSED RWY',
            ]
        ]
        
        # airport_info_patterns 컴파일
        self.compiled_airport_info_patterns = [
            re.compile(pattern, re.IGNORECASE) for pattern in [
                r'^\d+\. RUNWAY',
                r'^\d+\. COMPANY RADIO',
                r'TAKEOFF PERFORMANCE INFORMATION',
                r'NOTAM A\d{4}/\d{2}.*NO IMPACT',
                r'CHECK RWY ID FOR TODC REQUEST',
                r'COMPANY MINIMA FOR CAT II/III',
                r'131\.500.*KOREAN AIR INCHEON',
                r'129\.35.*ASIANA INCHEON'
            ]
        ]

        # Takeoff Performance Information 패턴
        self.takeoff_header_pattern = re.compile(r'^\s*TAKEOFF\s+PERFORMANCE\s+INFORMATION\s*$', re.IGNORECASE)
        self.takeoff_line_patterns = [
            re.compile(r'^\s*\d+\.\s*NOTAM\s+[A-Z0-9]+/\d{2}.*$', re.IGNORECASE),
            re.compile(r'^\s*NOTAM\s+[A-Z0-9]+/\d{2}.*$', re.IGNORECASE),
            re.compile(r'^\s*[A-Z0-9/\-]+(?:\s+[A-Z0-9/\-]+)*\s+TAKEOFF\b.*$', re.IGNORECASE),
            re.compile(r'^\s*-\s+.+$', re.IGNORECASE),
            re.compile(r'^\s*\*.+$', re.IGNORECASE)
        ]
        
        # NOTAM 번호 확인 패턴 (접미사 포함)
        self.compiled_has_notam_number = re.compile(
            r'\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*-\s*(?:\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}|UFN|PERM)\s+[A-Z]{4}\s+[A-Z0-9]+/\d{2}[A-Z0-9]*'
        )
        
        # 공항 코드 추출 패턴들
        self.compiled_airport_patterns = {
            'main': re.compile(
                r'(?:\d+\.\s+)?\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*-\s*(?:\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}|UFN|PERM)\s+([A-Z]{4})(?:\s+(?:AIP\s+SUP|AIP\s+AD|CHINA\s+SUP|COAD))?\s+[A-Z0-9]+/\d{2}[A-Z0-9]*'
            ),
            'aip_ad': re.compile(r'([A-Z]{4})\s+AIP\s+AD\s+\d+\.\d+'),
            'fallback': re.compile(
                r'\b([A-Z]{4})(?:\s+(?:AIP\s+SUP|AIP\s+AD|CHINA\s+SUP|COAD))?\s+[A-Z0-9]+/\d{2}[A-Z0-9]*'
            ),
            'coad': re.compile(r'([A-Z]{4})\s+COAD\d{2}/\d{2}'),
            'has_time': re.compile(
                r'\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*-\s*(?:\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}|UFN)'
            )
        }
        
        # NOTAM 번호 추출 패턴들
        self.compiled_notam_number_patterns = {
            'main': re.compile(
                r'(?:\d+\.\s+)?\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*-\s*(?:\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}|UFN|PERM)\s+[A-Z]{4}(?:\s+(?:AIP\s+SUP|AIP\s+AD|CHINA\s+SUP|COAD))?\s+([A-Z0-9]+/\d{2}[A-Z0-9]*)'
            ),
            'aip_sup': re.compile(
                r'(?:\d+\.\s+)?\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*-\s*(?:\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}|UFN|PERM)\s+[A-Z]{4}\s+(AIP\s+SUP|AIP\s+AD|CHINA\s+SUP|COAD)\s+([A-Z0-9]+/\d{2}[A-Z0-9]*)'
            ),
            'fallback': re.compile(r'(AIP\s+SUP|AIP\s+AD|CHINA\s+SUP|COAD)\s+([A-Z0-9]+/\d{2}[A-Z0-9]*)'),
            'aip_ad': re.compile(r'([A-Z]{4})\s+AIP\s+AD\s+(\d+\.\d+)'),
            'coad': re.compile(r'([A-Z]{4})\s+COAD(\d{2}/\d{2})'),
            'fallback2': re.compile(r'\b([A-Z]\d{4}/\d{2}[A-Z0-9]*)\b')
        }
        
        # E 필드 추출 패턴들
        self.compiled_e_field_patterns = {
            'separator': re.compile(r'E\)\s*(.+)(?=\n\s*={20,}\s*$)', re.DOTALL | re.MULTILINE),
            'next_notam': re.compile(
                r'E\)\s*(.+)(?=\n\s*\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*-\s*(?:\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}|UFN|PERM)\s+[A-Z]{4})',
                re.DOTALL | re.MULTILINE
            ),
            'next_section': re.compile(r'E\)\s*(.+)(?=\n\s*[A-Z]\)\s*[A-Z])', re.DOTALL | re.MULTILINE),
            'end': re.compile(r'E\)\s*(.+)$', re.DOTALL)
        }
        
        # E 필드 정리 패턴들
        self.compiled_e_field_cleanup_patterns = {
            'no_current': re.compile(r'\*{8}\s*NO CURRENT NOTAMS FOUND\s*\*{8}.*$', re.DOTALL | re.IGNORECASE),
            'created': re.compile(r'CREATED:.*$', re.DOTALL),
            'source': re.compile(r'SOURCE:.*$', re.DOTALL),
            # 카테고리 마커 제거 패턴 개선: ◼ 또는 ■ 뒤에 오는 모든 텍스트(특수문자 포함) 제거
            # 예: ◼ RUNWAY, ■ TAXIWAY, ◼ COMPANY MINIMA FOR CAT II/III 등
            'category_marker': re.compile(r'[◼■]\s*[^\n]*(?:\n|$)', re.MULTILINE)
        }
        
        # extract_e_section을 위한 패턴들 (전역 함수용 - 사전 컴파일)
        self.compiled_extract_e_section_patterns = [
            re.compile(r'E\)\s*(.+?)(?=(?:\n|^)\s*={20,}\s*$)', re.DOTALL | re.MULTILINE),
            re.compile(
                r'E\)\s*(.+?)(?=(?:\n|^)\s*\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*-\s*(?:\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}|UFN|PERM)\s+[A-Z]{4})',
                re.DOTALL | re.MULTILINE
            ),
            re.compile(r'E\)\s*(.+?)(?=(?:\n|^)\s*[A-Z]\)\s*[A-Z])', re.DOTALL | re.MULTILINE),
            re.compile(r'E\)\s*(.+?)$', re.DOTALL)
        ]
        
        # 시간 정보 패턴들
        self.compiled_time_patterns = {
            'ufn': re.compile(
                r'(?:\d+\.\s+)?(\d{2}[A-Z]{3}\d{2}) (\d{2}:\d{2}) - UFN(?:\s+[A-Z]{4}(?:\s+[A-Z\s]+/\d{2})?)?'
            ),
            'perm': re.compile(
                r'(?:\d+\.\s+)?(\d{2}[A-Z]{3}\d{2}) (\d{2}:\d{2}) - PERM(?:\s+[A-Z]{4}(?:\s+[A-Z\s]+/\d{2})?)?'
            ),
            'wef_til': re.compile(
                r'(?:\d+\.\s+)?(\d{2}[A-Z]{3}\d{2}) (\d{2}:\d{2}) - (\d{2}[A-Z]{3}\d{2}) (\d{2}:\d{2})(?:\s+[A-Z]{4}(?:\s+[A-Z0-9]+/\d{2})?)?'
            ),
            'b_field': re.compile(r'B\)\s*(\d{10})'),
            'c_field': re.compile(r'C\)\s*(\d{10})')
        }

    def _find_nearest_airport_for_takeoff(self, lines, header_index, search_window=40):
        """Takeoff Performance 섹션 기준으로 인근 공항 코드를 추출"""
        import re

        total_lines = len(lines)
        airports_data = getattr(self, 'airports_data', {}) or {}
        invalid_tokens = {
            'FAIL', 'PASS', 'NIL', 'INFO', 'NOTE', 'ONLY', 'TIME', 'DATE',
            'THIS', 'THAT', 'FROM', 'WITH', 'WHEN', 'WORK', 'ITEM', 'NONE',
            'NEAR', 'MODE', 'TEST', 'CALL', 'GOOD'
        }

        def extract_candidate_from_line(line_text, allow_fallback=False):
            line_upper = line_text.strip().upper()
            if not line_upper:
                return None
            matches = re.findall(r'\b([A-Z]{4})\b', line_upper)
            # 1차: 공항 데이터에 존재하는 코드만 반환
            for match in matches:
                if match in airports_data:
                    return match
            if not allow_fallback:
                return None
            # 2차: 알려진 무효 토큰 제외 후 첫 번째 후보 반환
            for match in matches:
                if match not in invalid_tokens:
                    return match
            return None

        # 후방 검색
        for offset in range(1, search_window + 1):
            idx = header_index - offset
            if idx < 0:
                break
            candidate = extract_candidate_from_line(lines[idx])
            if candidate:
                return candidate

        # 전방 검색
        for offset in range(1, search_window + 1):
            idx = header_index + offset
            if idx >= total_lines:
                break
            candidate = extract_candidate_from_line(lines[idx])
            if candidate:
                return candidate

        # 폴백: 무효 토큰을 제외한 첫 후보 (후방 → 전방 순)
        for offset in range(1, search_window + 1):
            idx = header_index - offset
            if idx < 0:
                break
            candidate = extract_candidate_from_line(lines[idx], allow_fallback=True)
            if candidate:
                return candidate

        for offset in range(1, search_window + 1):
            idx = header_index + offset
            if idx >= total_lines:
                break
            candidate = extract_candidate_from_line(lines[idx], allow_fallback=True)
            if candidate:
                return candidate

        return None

    def _is_takeoff_info_line(self, line):
        """Takeoff Performance 섹션의 하위 라인 여부 확인"""
        stripped = line.strip()
        if not stripped:
            return False
        for pattern in getattr(self, 'takeoff_line_patterns', []) or []:
            if pattern.match(stripped):
                return True
        return False

    def extract_takeoff_performance_info(self, text):
        """텍스트에서 Takeoff Performance Information 블록을 추출"""
        if not text:
            return []

        lines = text.splitlines()
        total_lines = len(lines)
        header_pattern = getattr(self, 'takeoff_header_pattern', None)
        results = []
        idx = 0

        while idx < total_lines:
            line = lines[idx]
            if header_pattern and header_pattern.match(line.strip()):
                airport_code = self._find_nearest_airport_for_takeoff(lines, idx)
                content_lines = []
                j = idx + 1

                while j < total_lines and self._is_takeoff_info_line(lines[j]):
                    content_lines.append(lines[j].strip())
                    j += 1

                if content_lines:
                    styled_lines = [apply_color_styles(l) for l in content_lines]
                    content_html = '<br>'.join(styled_lines)
                    airport_display = (airport_code or 'UNKNOWN').upper()
                    results.append({
                        'id': f"takeoff_{airport_display}_{len(results) + 1}",
                        'airport_code': airport_code,
                        'title': 'TAKEOFF PERFORMANCE INFORMATION',
                        'content_lines': content_lines,
                        'content_text': '\n'.join(content_lines),
                        'content_html': content_html,
                        'source_line': idx + 1
                    })

                idx = j
            else:
                idx += 1

        return results
    
    def _init_gemini(self):
        """GEMINI API 초기화"""
        try:
            api_key = os.getenv('GOOGLE_API_KEY') or os.getenv('GEMINI_API_KEY')
            if api_key:
                genai.configure(api_key=api_key)
                self.model = genai.GenerativeModel('gemini-2.5-flash-lite')
                self.GEMINI_AVAILABLE = True
                self.logger.debug("GEMINI API 초기화 성공")
            else:
                self.logger.warning("GEMINI API 키가 설정되지 않음")
        except Exception as e:
            self.logger.error(f"GEMINI API 초기화 실패: {e}")
            self.GEMINI_AVAILABLE = False
            self.model = None
    
    def _translate_with_gemini(self, text, target_lang="ko"):
        """GEMINI를 사용하여 NOTAM 번역"""
        if not self.GEMINI_AVAILABLE or not self.model:
            return "번역 준비 중..."
        
        try:
            if target_lang == "ko":
                prompt = f"""다음 NOTAM을 한국어로 번역하세요. 항공 전문 용어는 정확하게 번역하고, 공항 코드, 활주로 번호, 좌표 등은 그대로 유지하세요.

NOTAM: {text}

번역 규칙:
1. NOTAM, AIRAC, AIP, SUP, AMDT, WEF, TIL, UTC 등은 그대로 유지
2. RWY, TWY, APRON, SID, STAR, IAP 등 항공 용어는 정확한 한국어로 번역
3. 공항 코드, 활주로 번호, 좌표는 그대로 유지
4. 날짜와 시간은 원래 형식 유지
5. 괄호와 그 내용은 그대로 유지
6. 번호가 매겨진 항목은 그대로 유지 (1., 2., 3. 등)

번역 결과만 제공하세요:"""
            else:
                prompt = f"""Translate the following NOTAM to clear, professional English while maintaining technical accuracy:

NOTAM: {text}

Translation rules:
1. Keep technical terms like NOTAM, AIRAC, AIP, SUP, AMDT, WEF, TIL, UTC as is
2. Translate aviation terms accurately (RWY=Runway, TWY=Taxiway, etc.)
3. Keep airport codes, runway numbers, coordinates unchanged
4. Maintain original date and time format
5. Keep parentheses and their contents intact
6. Preserve numbered items (1., 2., 3., etc.)

Provide only the translation:"""
            
            response = self.model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            self.logger.error(f"GEMINI 번역 실패: {e}")
            return "번역 실패"
    
# 사용되지 않는 배치 번역 메서드 제거됨 (integrated_translator에서 처리)
    
    def _detect_package_type(self, text):
        """텍스트에서 패키지 타입을 감지"""
        if 'KOREAN AIR NOTAM PACKAGE 1' in text:
            return 'package1'
        elif 'KOREAN AIR NOTAM PACKAGE 2' in text:
            return 'package2'
        elif 'KOREAN AIR NOTAM PACKAGE 3' in text:
            return 'package3'
        return None
        
    def _get_airport_priority(self, airport_code, package_type):
        """공항 코드의 우선순위를 반환"""
        if package_type and package_type in self.package_airport_order:
            order_list = self.package_airport_order[package_type]
            try:
                return order_list.index(airport_code)
            except ValueError:
                return 999  # 순서에 없는 공항은 마지막에
        return 999
        
    def _load_airports_data(self):
        """공항 데이터 로드"""
        airports_data = {}
        try:
            # src 폴더의 공항 데이터 사용
            csv_path = os.path.join(os.path.dirname(__file__), 'airports_timezones.csv')
            
            if os.path.exists(csv_path):
                with open(csv_path, 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        icao_code = row.get('ident')  # CSV 파일의 실제 컬럼명
                        if icao_code:
                            time_zone = row.get('time_zone', 'UTC')
                            # UTC+8 -> +08:00 형식으로 변환
                            if time_zone.startswith('UTC+'):
                                utc_offset = '+' + time_zone[4:].zfill(2) + ':00'
                            elif time_zone.startswith('UTC-'):
                                utc_offset = '-' + time_zone[4:].zfill(2) + ':00'
                            else:
                                utc_offset = '+00:00'
                                
                            airports_data[icao_code] = {
                                'name': row.get('code', ''),
                                'country': '',
                                'timezone': time_zone,
                                'utc_offset': utc_offset
                            }
            else:
                print(f"Airport data file not found: {csv_path}")
                
        except Exception as e:
            print(f"Error loading airport data: {e}")
            
        return airports_data
    
    def get_timezone(self, airport_code, at_utc: str | None = None, use_api: bool = False):
        """공항 코드에 따른 타임존 정보 반환 (캐싱 적용)

        Args:
            airport_code: ICAO 코드
            at_utc: 'YYYY-MM-DDTHH:MM:SSZ' 형식의 UTC 시각 문자열. 제공되면 해당 시점 기준 오프셋을 zoneinfo로 계산 시도
            use_api: True면 timezone_api 보조 경로 사용 허용
        """
        # 캐시 확인
        if airport_code in self.timezone_cache:
            return self.timezone_cache[airport_code]
        
        # 날짜 지정 시 zoneinfo로 먼저 시도
        if at_utc:
            try:
                from datetime import datetime
                from src.timezone_api import _timezone_api
                dt = datetime.fromisoformat(at_utc.replace('Z', '+00:00'))
                off = _timezone_api.get_offset_for_datetime(airport_code, dt, allow_remote=use_api)
                if off:
                    # 날짜별 오프셋은 공항코드 단일 키로 캐시하지 않음(계절 변화 때문)
                    return off
            except Exception:
                pass

        timezone_result = self._calculate_timezone(airport_code)
        
        # 캐시에 저장
        self.timezone_cache[airport_code] = timezone_result
        
        return timezone_result
    
    def _calculate_timezone(self, airport_code):
        """실제 시간대 계산 (캐싱 없이)"""
        
        # FIR 코드 처리 (공항 코드가 아닌 경우)
        if self._is_fir_code(airport_code):
            return self._get_fir_timezone(airport_code)
        
        # 1단계: CSV 데이터에서 정확한 시간대 조회
        if airport_code in self.airports_data:
            csv_timezone = self.airports_data[airport_code].get('utc_offset', '+00:00')
            # DST 적용 여부 확인
            return self._apply_dst_if_needed(airport_code, csv_timezone)
        
        # 2단계: 고급 시간대 시스템 사용 시도 (API 비활성화로 성능 향상)
        try:
            from src.icao import get_utc_offset
            advanced_timezone = get_utc_offset(airport_code, use_api=False)  # API 비활성화
            if advanced_timezone and advanced_timezone != "UTC+0":
                # "UTC+9" 또는 "UTC+09:30" 등의 형식을 '+HH:MM'으로 정규화
                if advanced_timezone.startswith('UTC+') or advanced_timezone.startswith('UTC-'):
                    sign = '+' if advanced_timezone[3] == '+' else '-'
                    raw = advanced_timezone[4:]
                    if ':' in raw:
                        hours_part, minutes_part = raw.split(':', 1)
                    elif '.' in raw:
                        # 예: '5.5' -> 시간과 분으로 변환
                        hours_float = float(raw)
                        hours_part = int(hours_float)
                        minutes_part = int(round((hours_float - hours_part) * 60))
                        hours_part = str(hours_part)
                        minutes_part = f"{minutes_part:02d}"
                    else:
                        hours_part = raw
                        minutes_part = '00'

                    # 숫자 문자열 보정
                    hours_part = hours_part.zfill(2)
                    minutes_part = minutes_part.zfill(2)
                    return f"{sign}{hours_part}:{minutes_part}"
        except Exception as e:
            # 인코딩 오류 방지를 위해 영어 메시지 사용
            print(f"Advanced timezone system failed: {str(e)}")
        
        # 3단계: 기본 타임존 설정 (ICAO 코드 첫 글자 기준)
        if airport_code.startswith('RK'):  # 한국
            return '+09:00'
        elif airport_code.startswith('RJ'):  # 일본
            return '+09:00'
        elif airport_code.startswith('ZB') or airport_code.startswith('ZG'):  # 중국
            return '+08:00'
        elif airport_code.startswith('VV'):  # 베트남
            return '+07:00'
        elif airport_code.startswith('K'):  # 미국 공항들
            # 미국 시간대별 기본 설정 (DST 고려하지 않고 표준 시간 사용)
            if airport_code.startswith('KS'):  # 서부 (시애틀, 샌프란시스코)
                return '-08:00'  # PST
            elif airport_code.startswith('KL'):  # 서부 (로스앤젤레스)
                return '-08:00'  # PST
            elif airport_code.startswith('KD'):  # 중부 (덴버)
                return '-07:00'  # MST
            elif airport_code.startswith('KM'):  # 중부 (시카고)
                return '-06:00'  # CST
            elif airport_code.startswith('KE'):  # 동부 (뉴욕)
                return '-05:00'  # EST
            else:
                return '-06:00'  # 기본 중부 시간대
        else:
            return '+00:00'  # UTC
    
    def _is_fir_code(self, code):
        """FIR 코드인지 확인"""
        # FIR 코드 패턴: 국가 코드를 두 번 반복하는 형태
        # 예: RKRR (한국), RJJJ (일본), KZSE (미국), CZVR (캐나다)
        if len(code) != 4:
            return False
        
        # 일반적인 FIR 코드 패턴들 (Wikipedia FIR 목록 기반)
        fir_patterns = [
            # 한국
            'RKRR',  # 인천 (Incheon)
            
            # 일본
            'RJJJ',  # 후쿠오카 (Fukuoka)
            'RJBE',  # 고베 (Kobe)
            'RJCG',  # 삿포로 (Sapporo)
            'RJFF',  # 후쿠오카 (Fukuoka)
            'RJTG',  # 도쿄 (Tokyo)
            
            # 미국
            'KZAB',  # 앨버커키 (Albuquerque)
            'KZAK',  # 오클랜드 해양 (Oakland Oceanic)
            'KZAU',  # 시카고 (Chicago)
            'KZBW',  # 보스턴 (Boston)
            'KZDC',  # 워싱턴 (Washington)
            'KZDV',  # 덴버 (Denver)
            'KZFW',  # 포트워스 (Fort Worth)
            'KZHU',  # 휴스턴 (Houston)
            'KZID',  # 인디애나폴리스 (Indianapolis)
            'KZJX',  # 잭슨빌 (Jacksonville)
            'KZKC',  # 캔자스시티 (Kansas City)
            'KZLA',  # 로스앤젤레스 (Los Angeles)
            'KZLC',  # 솔트레이크 (Salt Lake)
            'KZMA',  # 마이애미 (Miami)
            'KZME',  # 멤피스 (Memphis)
            'KZMP',  # 미니애폴리스 (Minneapolis)
            'KZNY',  # 뉴욕 (New York)
            'KZOA',  # 오클랜드 (Oakland)
            'KZOB',  # 클리블랜드 (Cleveland)
            'KZSE',  # 시애틀 (Seattle)
            'KZTL',  # 애틀랜타 (Atlanta)
            'KZWY',  # 뉴욕 해양 (New York Oceanic)
            'PAZA',  # 앵커리지 대륙 (Anchorage Continental)
            'PAZN',  # 앵커리지 해양 (Anchorage Oceanic)
            'PHZH',  # 호놀룰루 (Honolulu)
            
            # 캐나다
            'CZEG',  # 에드먼턴 (Edmonton)
            'CZQM',  # 몽크톤 (Moncton)
            'CZQX',  # 간더 (Gander)
            'CZUL',  # 몬트리올 (Montreal)
            'CZVR',  # 밴쿠버 (Vancouver)
            'CZWG',  # 위니펙 (Winnipeg)
            'CZYZ',  # 토론토 (Toronto)
            
            # 유럽
            'EGTT',  # 런던 (London)
            'EGGX',  # 센윅 해양 (Shanwick Oceanic)
            'EGPX',  # 스코틀랜드 (Scottish)
            'EGQQ',  # 스코틀랜드 군사 (Scottish Military)
            'EBBU',  # 브뤼셀 (Brussels)
            'EDGG',  # 랑겐 (Langen)
            'EDMM',  # 뮌헨 (Munich)
            'EDUU',  # 라인 UIR (Rhein UIR)
            'EDWW',  # 브레멘 (Bremen)
            'EDYY',  # 마스트리흐트 (Maastricht)
            'EETT',  # 탈린 (Tallinn)
            'EFIN',  # 핀란드 (Finland)
            'EHAA',  # 암스테르담 (Amsterdam)
            'EISN',  # 섀넌 (Shannon)
            'EKDK',  # 코펜하겐 (Copenhagen)
            'ENOB',  # 보도 (Bodo)
            'ENOR',  # 노르웨이 (Norway)
            'EPWW',  # 바르샤바 (Warszawa)
            'ESAA',  # 스웨덴 (Sweden)
            'ESMM',  # 말뫼 (Malmo)
            'EVRR',  # 리가 (Riga)
            'EYVL',  # 빌뉴스 (Vilnius)
            'LFBB',  # 보르도 (Bordeaux)
            'LFEE',  # 랭스 (Reims)
            'LFFF',  # 파리 (Paris)
            'LFMM',  # 마르세유 (Marseille)
            'LFRR',  # 브레스트 (Brest)
            'LGGG',  # 아테네 (Athens)
            'LHCC',  # 부다페스트 (Budapest)
            'LIBB',  # 브린디시 (Brindisi)
            'LIMM',  # 밀라노 (Milano)
            'LIPP',  # 파도바 (Padova)
            'LIRR',  # 로마 (Roma)
            'LJLA',  # 류블랴나 (Ljubljana)
            'LKAA',  # 프라하 (Praha)
            'LLLL',  # 텔아비브 (Tel-Aviv)
            'LMMM',  # 몰타 (Malta)
            'LOVV',  # 비엔나 (Wien)
            'LPPC',  # 리스본 (Lisboa)
            'LPPO',  # 산타마리아 (Santa Maria)
            'LQSB',  # 사라예보 (Sarajevo)
            'LRBB',  # 부쿠레슈티 (Bucuresti)
            'LSAG',  # 제네바 (Geneve)
            'LSAS',  # 스위스 (Switzerland)
            'LSAZ',  # 취리히 (Zurich)
            'LTAA',  # 앙카라 (Ankara)
            'LTBB',  # 이스탄불 (Istanbul)
            'LUUU',  # 키시나우 (Chisinau)
            'LWSS',  # 스코페 (Skopje)
            'LYBA',  # 베오그라드 (Beograd)
            'LZBB',  # 브라티슬라바 (Bratislava)
            
            # 러시아
            'UUEE',  # 야쿠츠크 (Yakutsk)
            'UEEE',  # 야쿠츠크 (Yakutsk)
            'UHHH',  # 하바롭스크 (Khabarovsk)
            'UHMM',  # 마가단 (Magadan)
            'UHPP',  # 페트로파블롭스크 (Petropavlovsk-Kamchatsky)
            'UIII',  # 이르쿠츠크 (Irkutsk)
            'ULLL',  # 상트페테르부르크 (Sankt-Peterburg)
            'UMKK',  # 칼리닌그라드 (Kaliningrad)
            'UNKL',  # 크라스노야르스크 (Krasnoyarsk)
            'UNNT',  # 노보시비르스크 (Novosibirsk)
            'URRV',  # 로스토프나도누 (Rostov-Na-Donu)
            'USSV',  # 예카테린부르크 (Yekaterinburg)
            'USTV',  # 튜멘 (Tyumen)
            'UUWV',  # 모스크바 (Moscow)
            'UWWW',  # 사마라 (Samara)
            
            # 아시아
            'ZBPE',  # 베이징 (Beijing)
            'ZGZU',  # 광저우 (Guangzhou)
            'ZHWH',  # 우한 (Wuhan)
            'ZJSA',  # 싼야 (Sanya)
            'ZKKP',  # 평양 (Pyongyang)
            'ZLHW',  # 란저우 (Lanzhou)
            'ZMUB',  # 울란바토르 (Ulan Bator)
            'ZPKM',  # 쿤밍 (Kunming)
            'ZSHA',  # 상하이 (Shanghai)
            'ZWUQ',  # 우루무치 (Urumqi)
            'ZYSH',  # 선양 (Shenyang)
            'VHHK',  # 홍콩 (Hong Kong)
            'VTBB',  # 방콕 (Bangkok)
            'VTSM',  # 방콕 (Bangkok)
            'WIIF',  # 자카르타 (Jakarta)
            'WAAF',  # 우중판당 (Ujung Pandang)
            'WBFC',  # 코타키나발루 (Kota Kinabalu)
            'WMFC',  # 쿠알라룸푸르 (Kuala Lumpur)
            'WSJC',  # 싱가포르 (Singapore)
            'RPHI',  # 마닐라 (Manila)
            'VABF',  # 뭄바이 (Mumbai)
            'VCCC',  # 콜롬보 (Colombo)
            'VDPF',  # 프놈펜 (Phnom Penh)
            'VECF',  # 콜카타 (Kolkata)
            'VGFR',  # 다카 (Dhaka)
            'VIDF',  # 델리 (Delhi)
            'VLVT',  # 비엔티안 (Vientiane)
            'VNSM',  # 카트만두 (Kathmandu)
            'VOMF',  # 첸나이 (Chennai)
            'VRMF',  # 말레 (Male)
            'VVHM',  # 호치민 (Ho Chi Minh)
            'VVHN',  # 하노이 (Hanoi)
            'VYYF',  # 양곤 (Yangon)
            
            # 호주/오세아니아
            'YBBB',  # 브리즈번 (Brisbane)
            'YMMM',  # 멜버른 (Melbourne)
            'NZZC',  # 뉴질랜드 (New Zealand)
            'NZZO',  # 오클랜드 해양 (Auckland Oceanic)
            'NFFF',  # 피지 (Fiji)
            'NTTT',  # 타히티 (Tahiti)
            
            # 기타 주요 FIR들
            'OAKX',  # 카불 (Kabul)
            'OBBB',  # 바레인 (Bahrain)
            'OEJD',  # 제다 (Jeddah)
            'OIIX',  # 테헤란 (Tehran)
            'OJAC',  # 암만 (Amman)
            'OKAC',  # 쿠웨이트 (Kuwait)
            'OLBB',  # 베이루트 (Beirut)
            'OMAE',  # 에미레이트 (Emirates)
            'OOMM',  # 무스카트 (Muscat)
            'OPKR',  # 카라치 (Karachi)
            'OPLR',  # 라호르 (Lahore)
            'ORBB',  # 바그다드 (Baghdad)
            'OSTT',  # 다마스쿠스 (Damascus)
            'OYSC',  # 사나 (Sanaa)
        ]
        
        return code in fir_patterns
    
    def _get_fir_timezone(self, fir_code):
        """FIR 코드에 따른 시간대 반환 (Wikipedia FIR 목록 기반)"""
        fir_timezones = {
            # 한국
            'RKRR': '+09:00',  # 인천 (KST)
            
            # 일본
            'RJJJ': '+09:00',  # 후쿠오카 (JST)
            'RJBE': '+09:00',  # 고베 (JST)
            'RJCG': '+09:00',  # 삿포로 (JST)
            'RJFF': '+09:00',  # 후쿠오카 (JST)
            'RJTG': '+09:00',  # 도쿄 (JST)
            
            # 미국 (주요 시간대별)
            'KZAB': '-07:00',  # 앨버커키 (MST)
            'KZAK': '-08:00',  # 오클랜드 해양 (PST)
            'KZAU': '-06:00',  # 시카고 (CST)
            'KZBW': '-05:00',  # 보스턴 (EST)
            'KZDC': '-05:00',  # 워싱턴 (EST)
            'KZDV': '-07:00',  # 덴버 (MST)
            'KZFW': '-06:00',  # 포트워스 (CST)
            'KZHU': '-06:00',  # 휴스턴 (CST)
            'KZID': '-05:00',  # 인디애나폴리스 (EST)
            'KZJX': '-05:00',  # 잭슨빌 (EST)
            'KZKC': '-06:00',  # 캔자스시티 (CST)
            'KZLA': '-08:00',  # 로스앤젤레스 (PST)
            'KZLC': '-07:00',  # 솔트레이크 (MST)
            'KZMA': '-05:00',  # 마이애미 (EST)
            'KZME': '-06:00',  # 멤피스 (CST)
            'KZMP': '-06:00',  # 미니애폴리스 (CST)
            'KZNY': '-05:00',  # 뉴욕 (EST)
            'KZOA': '-08:00',  # 오클랜드 (PST)
            'KZOB': '-05:00',  # 클리블랜드 (EST)
            'KZSE': '-08:00',  # 시애틀 (PST)
            'KZTL': '-05:00',  # 애틀랜타 (EST)
            'KZWY': '-05:00',  # 뉴욕 해양 (EST)
            'PAZA': '-09:00',  # 앵커리지 대륙 (AKST)
            'PAZN': '-09:00',  # 앵커리지 해양 (AKST)
            'PHZH': '-10:00',  # 호놀룰루 (HST)
            
            # 캐나다
            'CZEG': '-07:00',  # 에드먼턴 (MST)
            'CZQM': '-04:00',  # 몽크톤 (AST)
            'CZQX': '-03:30',  # 간더 (NST)
            'CZUL': '-05:00',  # 몬트리올 (EST)
            'CZVR': '-08:00',  # 밴쿠버 (PST)
            'CZWG': '-06:00',  # 위니펙 (CST)
            'CZYZ': '-05:00',  # 토론토 (EST)
            
            # 유럽 (주요 시간대별)
            'EGTT': '+00:00',  # 런던 (GMT)
            'EGGX': '+00:00',  # 센윅 해양 (GMT)
            'EGPX': '+00:00',  # 스코틀랜드 (GMT)
            'EGQQ': '+00:00',  # 스코틀랜드 군사 (GMT)
            'EBBU': '+01:00',  # 브뤼셀 (CET)
            'EDGG': '+01:00',  # 랑겐 (CET)
            'EDMM': '+01:00',  # 뮌헨 (CET)
            'EDUU': '+01:00',  # 라인 UIR (CET)
            'EDWW': '+01:00',  # 브레멘 (CET)
            'EDYY': '+01:00',  # 마스트리흐트 (CET)
            'EETT': '+02:00',  # 탈린 (EET)
            'EFIN': '+02:00',  # 핀란드 (EET)
            'EHAA': '+01:00',  # 암스테르담 (CET)
            'EISN': '+00:00',  # 섀넌 (GMT)
            'EKDK': '+01:00',  # 코펜하겐 (CET)
            'ENOB': '+01:00',  # 보도 (CET)
            'ENOR': '+01:00',  # 노르웨이 (CET)
            'EPWW': '+01:00',  # 바르샤바 (CET)
            'ESAA': '+01:00',  # 스웨덴 (CET)
            'ESMM': '+01:00',  # 말뫼 (CET)
            'EVRR': '+02:00',  # 리가 (EET)
            'EYVL': '+02:00',  # 빌뉴스 (EET)
            'LFBB': '+01:00',  # 보르도 (CET)
            'LFEE': '+01:00',  # 랭스 (CET)
            'LFFF': '+01:00',  # 파리 (CET)
            'LFMM': '+01:00',  # 마르세유 (CET)
            'LFRR': '+01:00',  # 브레스트 (CET)
            'LGGG': '+02:00',  # 아테네 (EET)
            'LHCC': '+01:00',  # 부다페스트 (CET)
            'LIBB': '+01:00',  # 브린디시 (CET)
            'LIMM': '+01:00',  # 밀라노 (CET)
            'LIPP': '+01:00',  # 파도바 (CET)
            'LIRR': '+01:00',  # 로마 (CET)
            'LJLA': '+01:00',  # 류블랴나 (CET)
            'LKAA': '+01:00',  # 프라하 (CET)
            'LLLL': '+02:00',  # 텔아비브 (IST)
            'LMMM': '+01:00',  # 몰타 (CET)
            'LOVV': '+01:00',  # 비엔나 (CET)
            'LPPC': '+00:00',  # 리스본 (WET)
            'LPPO': '-01:00',  # 산타마리아 (AZOT)
            'LQSB': '+01:00',  # 사라예보 (CET)
            'LRBB': '+02:00',  # 부쿠레슈티 (EET)
            'LSAG': '+01:00',  # 제네바 (CET)
            'LSAS': '+01:00',  # 스위스 (CET)
            'LSAZ': '+01:00',  # 취리히 (CET)
            'LTAA': '+03:00',  # 앙카라 (TRT)
            'LTBB': '+03:00',  # 이스탄불 (TRT)
            'LUUU': '+02:00',  # 키시나우 (EET)
            'LWSS': '+01:00',  # 스코페 (CET)
            'LYBA': '+01:00',  # 베오그라드 (CET)
            'LZBB': '+01:00',  # 브라티슬라바 (CET)
            
            # 러시아 (여러 시간대)
            'UUEE': '+09:00',  # 야쿠츠크 (YAKT)
            'UEEE': '+09:00',  # 야쿠츠크 (YAKT)
            'UHHH': '+10:00',  # 하바롭스크 (VLAT)
            'UHMM': '+11:00',  # 마가단 (MAGT)
            'UHPP': '+12:00',  # 페트로파블롭스크 (PETT)
            'UIII': '+08:00',  # 이르쿠츠크 (IRKT)
            'ULLL': '+03:00',  # 상트페테르부르크 (MSK)
            'UMKK': '+02:00',  # 칼리닌그라드 (EET)
            'UNKL': '+07:00',  # 크라스노야르스크 (KRAT)
            'UNNT': '+07:00',  # 노보시비르스크 (NOVT)
            'URRV': '+03:00',  # 로스토프나도누 (MSK)
            'USSV': '+05:00',  # 예카테린부르크 (YEKT)
            'USTV': '+05:00',  # 튜멘 (YEKT)
            'UUWV': '+03:00',  # 모스크바 (MSK)
            'UWWW': '+04:00',  # 사마라 (SAMT)
            
            # 아시아
            'ZBPE': '+08:00',  # 베이징 (CST)
            'ZGZU': '+08:00',  # 광저우 (CST)
            'ZHWH': '+08:00',  # 우한 (CST)
            'ZJSA': '+08:00',  # 싼야 (CST)
            'ZKKP': '+09:00',  # 평양 (KST)
            'ZLHW': '+08:00',  # 란저우 (CST)
            'ZMUB': '+08:00',  # 울란바토르 (ULAT)
            'ZPKM': '+08:00',  # 쿤밍 (CST)
            'ZSHA': '+08:00',  # 상하이 (CST)
            'ZWUQ': '+06:00',  # 우루무치 (XJT)
            'ZYSH': '+08:00',  # 선양 (CST)
            'VHHK': '+08:00',  # 홍콩 (HKT)
            'VTBB': '+07:00',  # 방콕 (ICT)
            'VTSM': '+07:00',  # 방콕 (ICT)
            'WIIF': '+07:00',  # 자카르타 (WIB)
            'WAAF': '+08:00',  # 우중판당 (WITA)
            'WBFC': '+08:00',  # 코타키나발루 (MYT)
            'WMFC': '+08:00',  # 쿠알라룸푸르 (MYT)
            'WSJC': '+08:00',  # 싱가포르 (SGT)
            'RPHI': '+08:00',  # 마닐라 (PHT)
            'VABF': '+05:30',  # 뭄바이 (IST)
            'VCCC': '+05:30',  # 콜롬보 (IST)
            'VDPF': '+07:00',  # 프놈펜 (ICT)
            'VECF': '+05:30',  # 콜카타 (IST)
            'VGFR': '+06:00',  # 다카 (BST)
            'VIDF': '+05:30',  # 델리 (IST)
            'VLVT': '+07:00',  # 비엔티안 (ICT)
            'VNSM': '+05:45',  # 카트만두 (NPT)
            'VOMF': '+05:30',  # 첸나이 (IST)
            'VRMF': '+05:00',  # 말레 (MVT)
            'VVHM': '+07:00',  # 호치민 (ICT)
            'VVHN': '+07:00',  # 하노이 (ICT)
            'VYYF': '+06:30',  # 양곤 (MMT)
            
            # 호주/오세아니아
            'YBBB': '+10:00',  # 브리즈번 (AEST)
            'YMMM': '+10:00',  # 멜버른 (AEST)
            'NZZC': '+12:00',  # 뉴질랜드 (NZST)
            'NZZO': '+12:00',  # 오클랜드 해양 (NZST)
            'NFFF': '+12:00',  # 피지 (FJT)
            'NTTT': '-10:00',  # 타히티 (TAHT)
            
            # 중동/서아시아
            'OAKX': '+04:30',  # 카불 (AFT)
            'OBBB': '+03:00',  # 바레인 (AST)
            'OEJD': '+03:00',  # 제다 (AST)
            'OIIX': '+03:30',  # 테헤란 (IRST)
            'OJAC': '+02:00',  # 암만 (EET)
            'OKAC': '+03:00',  # 쿠웨이트 (AST)
            'OLBB': '+02:00',  # 베이루트 (EET)
            'OMAE': '+04:00',  # 에미레이트 (GST)
            'OOMM': '+04:00',  # 무스카트 (GST)
            'OPKR': '+05:00',  # 카라치 (PKT)
            'OPLR': '+05:00',  # 라호르 (PKT)
            'ORBB': '+03:00',  # 바그다드 (AST)
            'OSTT': '+02:00',  # 다마스쿠스 (EET)
            'OYSC': '+03:00',  # 사나 (AST)
        }
        
        return fir_timezones.get(fir_code, '+00:00')  # 기본값: UTC
    
    def _apply_dst_if_needed(self, airport_code, timezone_offset):
        """DST가 필요한 공항에 대해 서머타임 적용"""
        # 입력 형식은 "+HH:MM" 또는 "-HH:MM" 가정
        def parse_offset(offset_str):
            sign = 1 if offset_str.startswith('+') else -1
            hours = int(offset_str[1:3])
            minutes = int(offset_str[4:6])
            return sign, hours, minutes

        def format_offset(sign, hours, minutes):
            s = '+' if sign >= 0 else '-'
            return f"{s}{hours:02d}:{minutes:02d}"

        try:
            region = airport_code[0]

            # 유럽(E*, L*)은 실제 규칙 적용: 3월 마지막 일요일 01:00 UTC ~ 10월 마지막 일요일 01:00 UTC
            if region in ('E', 'L'):
                from datetime import datetime, timedelta
                import calendar

                now_utc = datetime.utcnow()
                year = now_utc.year

                # 특정 월의 마지막 일요일 날짜 반환
                def last_sunday(year, month):
                    last_day = calendar.monthrange(year, month)[1]
                    d = datetime(year, month, last_day)
                    # weekday(): 월=0 ... 일=6, 마지막 일요일까지 뒤로 이동
                    return d - timedelta(days=(d.weekday() + 1) % 7)

                start = last_sunday(year, 3).replace(hour=1, minute=0, second=0, microsecond=0)  # 01:00 UTC
                end = last_sunday(year, 10).replace(hour=1, minute=0, second=0, microsecond=0)    # 01:00 UTC

                sign, base_h, base_m = parse_offset(timezone_offset)

                if start <= now_utc < end:
                    # DST 활성: 유럽은 표준 오프셋에서 +1h
                    if sign >= 0:
                        adj_h = base_h + 1
                        return format_offset(+1, adj_h, base_m)
                    else:
                        # 음수 오프셋 지역은 유럽에 드묾. 일반화: 절대값 1시간 감소(즉, UTC에 1시간 가까워짐)
                        adj_h = max(0, base_h - 1)
                        return format_offset(-1, adj_h, base_m)
                else:
                    # 표준시: 그대로 반환
                    return timezone_offset

            # 북미(K*, C*)는 간단 규칙 유지(근사치): 3월~10월을 DST로 간주
            if region in ('K', 'C'):
                from datetime import datetime
                month = datetime.utcnow().month
                dst_active = 3 <= month <= 10
                sign, base_h, base_m = parse_offset(timezone_offset)
                if dst_active:
                    if sign >= 0:
                        return format_offset(+1, base_h + 1, base_m)
                    else:
                        return format_offset(-1, max(0, base_h - 1), base_m)
                else:
                    return timezone_offset

            # 기타 지역: 원본 유지
            return timezone_offset

        except Exception as e:
            print(f"DST application error: {e}")
            return timezone_offset
    
    def _clean_additional_info(self, notam_text):
        """NOTAM에서 추가 정보 제거 (조기 종료 최적화)"""
        lines = notam_text.split('\n')
        cleaned_lines = []
        
        for line in lines:
            line_stripped = line.strip()
            # 추가 정보 패턴에 매치되면 제거 (조기 종료 최적화)
            # any()는 첫 번째 True에서 종료되지만, 명시적으로 조기 종료 로직 적용
            should_skip = False
            for pattern in self.compiled_additional_info_patterns:
                if pattern.search(line_stripped):
                    should_skip = True
                    break  # 첫 번째 매칭 발견 시 즉시 종료
            if should_skip:
                continue
            cleaned_lines.append(line)
        
        return '\n'.join(cleaned_lines).strip()
    
    def _parse_notam_section(self, notam_text):
        """NOTAM 텍스트를 파싱하여 정보 추출"""
        # 추가 정보 제거
        cleaned_text = self._clean_additional_info(notam_text)
        
        # upper(), lower(), strip() 결과 캐싱 (재사용 최적화)
        cleaned_text_upper = cleaned_text.upper()
        cleaned_text_lower = cleaned_text.lower()
        cleaned_text_stripped = cleaned_text.strip()
        
        parsed_notam = {}
        
        # NOTAM이 아닌 비정보 섹션 체크 (COMPANY ADVISORY 등) - upper() 결과 재사용 및 조기 종료 최적화
        skip_phrases = ['COMPANY ADVISORY', 'OTHER INFORMATION', 'DEP:', 'DEST:', 'ALTN:', 'SECY']
        skip_phrase_found = False
        for phrase in skip_phrases:
            if phrase in cleaned_text_upper:
                skip_phrase_found = True
                break  # 첫 번째 매칭 발견 시 즉시 종료
        if skip_phrase_found:
            # 길이가 긴 경우 더 엄격한 체크
            if len(cleaned_text) > 400:
                self.logger.debug(f"긴 비NOTAM 섹션 감지하여 건너뛰기: {cleaned_text[:100]}...")
                return {}
        
        # 공항 정보 섹션 체크 (사전 컴파일된 패턴 사용) - 조기 종료 최적화
        airport_info_found = False
        for pattern in self.compiled_airport_info_patterns:
            if pattern.search(cleaned_text):
                airport_info_found = True
                break  # 첫 번째 매칭 발견 시 즉시 종료
        if airport_info_found:
            if len(cleaned_text) > 500:  # 매우 긴 공항 정보 섹션
                self.logger.debug(f"긴 공항 정보 섹션 감지하여 건너뛰기: {cleaned_text[:100]}...")
                return {}
        
        # 추가 체크: 공항 정보로 보이는 특별한 패턴들
        # 단, NOTAM 번호가 있는 경우에는 진짜 NOTAM일 가능성이 높으므로 관대하게 처리
        has_notam_number = self.compiled_has_notam_number.search(cleaned_text)
        if cleaned_text.count('RWY') > 3 or cleaned_text.count('CAT') > 2:
            if len(cleaned_text) > 800:  # 매우 긴 경로 정보나 성능 정보
                # NOTAM 번호가 있는 경우에는 건너뛰지 않음
                if not has_notam_number:
                    self.logger.debug(f"매우 긴 공항 성능 정보 감지하여 건너뛰기: {cleaned_text[:100]}...")
                    return {}
                else:
                    self.logger.debug(f"NOTAM 번호가 있으므로 길이 제한 예외 적용: {cleaned_text[:100]}...")

        # ICAO 공항 코드 추출 (통합 패턴 및 조기 종료 최적화)
        # 우선순위 기반 통합 패턴으로 단일 검색으로 여러 패턴을 한 번에 시도
        airport_code = None
        
        # 우선순위 1: 메인 패턴 (가장 일반적이고 빠름)
        airport_match = self.compiled_airport_patterns['main'].search(cleaned_text)
        if airport_match:
            airport_code = airport_match.group(1)
        # 우선순위 2: AIP AD 패턴
        elif (airport_match := self.compiled_airport_patterns['aip_ad'].search(cleaned_text)):
            airport_code = airport_match.group(1)
        # 우선순위 3: Fallback 패턴
        elif (airport_match := self.compiled_airport_patterns['fallback'].search(cleaned_text)):
            airport_code = airport_match.group(1)
        # 우선순위 4: COAD 패턴
        elif (airport_match := self.compiled_airport_patterns['coad'].search(cleaned_text)):
            airport_code = airport_match.group(1)
        
        # 공항 코드 추출 성공 시 즉시 설정 (조기 종료)
        if airport_code:
            parsed_notam['airport_code'] = airport_code
        else:
            # 실제 COAD NOTAM인지 확인 (시간 정보가 있는지 체크)
            has_time_pattern = self.compiled_airport_patterns['has_time'].search(cleaned_text)
            # COAD가 포함되어 있지만 시간 정보가 없는 경우는 fake일 가능성이 높음
            # 하지만 너무 엄격하지 않게 수정 (길이 제한을 더 크게)
            # lower() 결과 재사용 (이미 위에서 계산됨)
            if 'coad' in cleaned_text_lower and not has_time_pattern and len(cleaned_text) > 800:
                self.logger.debug(f"시간 정보 없는 매우 긴 COAD 섹션 건너뛰기: {cleaned_text[:100]}...")
                return {}
            # E) 형식 NOTAM (공항 이름에서 추출) - upper() 결과 재사용 (이미 위에서 계산됨)
            if cleaned_text_stripped.startswith('E)'):
                # upper() 결과 재사용 (이미 위에서 계산됨)
                if 'HONG KONG' in cleaned_text_upper:
                    parsed_notam['airport_code'] = 'VHHH'
                elif 'INCHEON' in cleaned_text_upper:
                    parsed_notam['airport_code'] = 'RKSI'
                elif 'GIMPO' in cleaned_text_upper:
                    parsed_notam['airport_code'] = 'RKSS'
                else:
                    # 기본값 설정
                    parsed_notam['airport_code'] = 'UNKNOWN'
            else:
                # 모든 패턴 실패 시
                parsed_notam['airport_code'] = None
        
        # NOTAM 번호 추출 (우선순위 기반 조기 종료 최적화)
        notam_number = None
        
        # 우선순위 1: 메인 패턴에서 AIP SUP/AD/CHINA SUP/COAD가 있는지 확인
        notam_number_match = self.compiled_notam_number_patterns['main'].search(cleaned_text)
        if notam_number_match:
            # AIP SUP, AIP AD, CHINA SUP가 있으면 전체를 붙여서 사용
            aip_sup_match = self.compiled_notam_number_patterns['aip_sup'].search(cleaned_text)
            if aip_sup_match:
                notam_number = f"{aip_sup_match.group(1)} {aip_sup_match.group(2)}"
            else:
                notam_number = notam_number_match.group(1)
        
        # 메인 패턴 실패 시 순차적으로 시도 (조기 종료 적용)
        if not notam_number:
            # 우선순위 2: Fallback 패턴
            if (notam_fallback := self.compiled_notam_number_patterns['fallback'].search(cleaned_text)):
                notam_number = f"{notam_fallback.group(1)} {notam_fallback.group(2)}"
            # 우선순위 3: AIP AD 패턴
            elif (aip_ad_match := self.compiled_notam_number_patterns['aip_ad'].search(cleaned_text)):
                notam_number = f"AIP AD {aip_ad_match.group(2)}"
            # 우선순위 4: COAD 패턴
            elif (coad_match := self.compiled_notam_number_patterns['coad'].search(cleaned_text)):
                notam_number = f"COAD{coad_match.group(2)}"
            # 우선순위 5: Fallback2 패턴
            elif (notam_fallback2 := self.compiled_notam_number_patterns['fallback2'].search(cleaned_text)):
                notam_number = notam_fallback2.group(1)
        
        if notam_number:
            parsed_notam['notam_number'] = notam_number
        
        # 시간 정보 파싱
        self._parse_time_info(cleaned_text, parsed_notam)
        
        # D) 필드 추출 (시간대 정보) - 원본 텍스트에서 추출
        lines = cleaned_text.split('\n')
        for i, line in enumerate(lines):
            if line.strip().startswith('D)'):
                d_content = []
                # D) 다음 줄들도 포함
                for j in range(i, len(lines)):
                    if j == i:
                        d_content.append(lines[j].strip()[2:].strip())  # D) 제거
                    elif lines[j].strip() and not lines[j].strip().startswith(('E)', 'F)', 'G)')):
                        d_content.append(lines[j].strip())
                    else:
                        break
                if d_content:
                    parsed_notam['d_field'] = '\n'.join(d_content)
                break
        
        
        # E) 필드 추출 (사전 컴파일된 패턴 사용)
        e_field_match = self.compiled_e_field_patterns['separator'].search(cleaned_text)
        if not e_field_match:
            e_field_match = self.compiled_e_field_patterns['next_notam'].search(cleaned_text)
        if not e_field_match:
            e_field_match = self.compiled_e_field_patterns['next_section'].search(cleaned_text)
        if not e_field_match:
            e_field_match = self.compiled_e_field_patterns['end'].search(cleaned_text)
        
        if e_field_match:
            e_field = e_field_match.group(1).strip()
            # NO CURRENT NOTAMS FOUND 이후의 내용 제거 (사전 컴파일된 패턴 사용)
            e_field = self.compiled_e_field_cleanup_patterns['no_current'].sub('', e_field).strip()
            # CREATED: 이후의 텍스트 제거
            e_field = self.compiled_e_field_cleanup_patterns['created'].sub('', e_field).strip()
            # SOURCE: 이후의 텍스트 제거
            e_field = self.compiled_e_field_cleanup_patterns['source'].sub('', e_field).strip()
            # 카테고리 마커 제거 (예: ◼ APPROACH LIGHT, ◼ OBSTRUCTION)
            e_field = self.compiled_e_field_cleanup_patterns['category_marker'].sub('', e_field).strip()
            # 마크다운 스타일도 제거 (예: **■ TAXIWAY**)
            e_field = re.sub(r'\*+\s*[◼■]\s*[^\n*]+\*+', '', e_field, flags=re.MULTILINE).strip()
            
            # E) 필드에 색상 스타일 적용
            e_field = apply_color_styles(e_field)
            # HTML 태그 내부에 있을 수 있는 카테고리 마커도 제거
            e_field = re.sub(r'<[^>]*>[◼■]\s*[^<]*</[^>]*>', '', e_field, flags=re.MULTILINE).strip()
            
            parsed_notam['e_field'] = e_field
        
        # F) 필드 추출 (고도 하한)
        # F)와 G)가 같은 줄에 있을 수 있으므로, G) 또는 줄바꿈+다음 필드까지 매칭
        f_field_match = re.search(r'F\)\s*(.+?)(?=\s+G\)|(?:\n\s*[A-Z]\))|$)', cleaned_text, re.IGNORECASE | re.DOTALL)
        if f_field_match:
            f_field = f_field_match.group(1).strip()
            # G)가 같은 줄에 있으면 제거
            f_field = re.split(r'\s+G\)', f_field)[0].strip()
            # 다음 필드(E), G) 등) 시작 전까지만 추출
            f_field = re.split(r'\n\s*[A-Z]\)', f_field)[0].strip()
            parsed_notam['f_field'] = f_field
        
        # G) 필드 추출 (고도 상한)
        # G)는 F) 다음에 같은 줄에 있거나, 별도 줄에 있을 수 있음
        g_field_match = re.search(r'G\)\s*(.+?)(?=(?:\n\s*[A-Z]\))|$)', cleaned_text, re.IGNORECASE | re.DOTALL)
        if g_field_match:
            g_field = g_field_match.group(1).strip()
            # 다음 필드(H), COMMENT) 등) 시작 전까지만 추출
            g_field = re.split(r'\n\s*[A-Z]\)', g_field)[0].strip()
            parsed_notam['g_field'] = g_field
        
        # COMMENT) 필드 추출
        comment_field_match = re.search(r'COMMENT\)\s*(.+?)(?=\n\s*[A-Z]\)|$)', cleaned_text, re.IGNORECASE | re.DOTALL)
        if comment_field_match:
            comment_field = comment_field_match.group(1).strip()
            # 다음 필드 시작 전까지만 추출
            comment_field = re.split(r'\n\s*[A-Z]\)', comment_field)[0].strip()
            parsed_notam['comment_field'] = comment_field
        
        return parsed_notam
    
    def _parse_time_info(self, notam_text, parsed_notam):
        """시간 정보 파싱 (UFN 지원 포함)"""
        
        # 1. UFN (Until Further Notice) 패턴 먼저 확인 (번호 포함) - Package 3 NOTAM 형식 지원 (사전 컴파일된 패턴 사용)
        ufn_match = self.compiled_time_patterns['ufn'].search(notam_text)
        
        if ufn_match:
            start_date, start_time = ufn_match.groups()
            try:
                # 시작 시간 파싱
                day = int(start_date[:2])
                month_str = start_date[2:5]
                year = int('20' + start_date[5:7])
                
                month_map = {
                    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
                    'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12
                }
                month = month_map[month_str]
                
                hour, minute = map(int, start_time.split(':'))
                start_dt = datetime(year, month, day, hour, minute)
                
                parsed_notam['effective_time'] = start_dt.strftime('%Y-%m-%dT%H:%M:%SZ')
                parsed_notam['expiry_time'] = 'UFN'
                
                return
                
            except Exception as e:
                print(f"UFN 시간 파싱 오류: {e}")
        
        # 1.5. PERM (Permanent) 패턴 추가 (사전 컴파일된 패턴 사용)
        perm_match = self.compiled_time_patterns['perm'].search(notam_text)
        
        if perm_match:
            start_date, start_time = perm_match.groups()
            try:
                # 시작 시간 파싱
                day = int(start_date[:2])
                month_str = start_date[2:5]
                year = int('20' + start_date[5:7])
                
                month_map = {
                    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
                    'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12
                }
                month = month_map[month_str]
                
                hour, minute = map(int, start_time.split(':'))
                start_dt = datetime(year, month, day, hour, minute)
                
                parsed_notam['effective_time'] = start_dt.strftime('%Y-%m-%dT%H:%M:%SZ')
                parsed_notam['expiry_time'] = 'PERM'
                
                return
                
            except Exception as e:
                print(f"PERM 시간 파싱 오류: {e}")
        
        # 2. WEF/TIL 패턴 (번호 포함) - Package 3 NOTAM 형식 지원 (사전 컴파일된 패턴 사용)
        wef_til_match = self.compiled_time_patterns['wef_til'].search(notam_text)
        
        if wef_til_match:
            start_date, start_time, end_date, end_time = wef_til_match.groups()
            try:
                # 시작 시간 파싱
                start_dt = self._parse_datetime_string(start_date, start_time)
                end_dt = self._parse_datetime_string(end_date, end_time)
                
                parsed_notam['effective_time'] = start_dt.strftime('%Y-%m-%dT%H:%M:%SZ')
                parsed_notam['expiry_time'] = end_dt.strftime('%Y-%m-%dT%H:%M:%SZ')
                
                return
                
            except Exception as e:
                print(f"WEF/TIL 시간 파싱 오류: {e}")
        
        # 3. B) C) 필드 패턴 (사전 컴파일된 패턴 사용)
        b_field_match = self.compiled_time_patterns['b_field'].search(notam_text)
        c_field_match = self.compiled_time_patterns['c_field'].search(notam_text)
        
        if b_field_match:
            b_time = b_field_match.group(1)
            try:
                start_dt = self._parse_b_c_time(b_time)
                parsed_notam['effective_time'] = start_dt.strftime('%Y-%m-%dT%H:%M:%SZ')
            except Exception as e:
                print(f"B) 필드 시간 파싱 오류: {e}")
        
        if c_field_match:
            c_time = c_field_match.group(1)
            try:
                end_dt = self._parse_b_c_time(c_time)
                parsed_notam['expiry_time'] = end_dt.strftime('%Y-%m-%dT%H:%M:%SZ')
            except Exception as e:
                print(f"C) 필드 시간 파싱 오류: {e}")
    
    def _parse_datetime_string(self, date_str, time_str):
        """날짜 문자열 파싱 (30MAY24 01:15 형식)"""
        day = int(date_str[:2])
        month_str = date_str[2:5]
        year = int('20' + date_str[5:7])
        
        month_map = {
            'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
            'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12
        }
        month = month_map[month_str]
        
        hour, minute = map(int, time_str.split(':'))
        return datetime(year, month, day, hour, minute)
    
    def _parse_b_c_time(self, time_str):
        """B), C) 필드 시간 파싱 (2503200606 형식)"""
        year = int('20' + time_str[:2])
        month = int(time_str[2:4])
        day = int(time_str[4:6])
        hour = int(time_str[6:8])
        minute = int(time_str[8:10])
        
        return datetime(year, month, day, hour, minute)
    
    def _generate_local_time_display(self, parsed_notam):
        """로컬 시간 표시 생성"""
        if not parsed_notam.get('effective_time'):
            return None, []
        
        airport_code = parsed_notam.get('airport_code', '')
        # 기본 오프셋(폴백): 기존 계산
        fallback_offset = self.get_timezone(airport_code)
        
        try:
            # UTC 시간을 datetime 객체로 변환
            effective_dt = datetime.fromisoformat(parsed_notam['effective_time'].replace('Z', '+00:00'))
            # 날짜별 정확 오프셋(zoneinfo) 시도, 실패 시 폴백 사용
            import os
            allow_remote = os.getenv('TIMEZONE_FALLBACK_ENABLED', '0').lower() in ('1','true','yes')
            tz_for_display = _timezone_api.get_offset_for_datetime(airport_code, effective_dt, allow_remote=allow_remote)
            timezone_offset = tz_for_display or fallback_offset
            # 타임존 오프셋 파싱 (+HH:MM 형식)
            offset_sign = 1 if timezone_offset.startswith('+') else -1
            offset_hours = int(timezone_offset[1:3])
            offset_minutes = int(timezone_offset[4:6])
            offset_delta = timedelta(hours=offset_hours * offset_sign, minutes=offset_minutes * offset_sign)
            
            # 로컬 시간 계산
            local_start = effective_dt + offset_delta
            
            # 만료 시간 처리
            if parsed_notam.get('expiry_time') == 'UFN':
                # UFN인 경우
                local_time_str = f"{local_start.strftime('%y/%m/%d %H:%M')} - UFN ({timezone_offset})"
            elif parsed_notam.get('expiry_time') == 'PERM':
                # PERM인 경우
                local_time_str = f"{local_start.strftime('%y/%m/%d %H:%M')} - PERM ({timezone_offset})"
            elif parsed_notam.get('expiry_time'):
                # 일반적인 만료 시간이 있는 경우
                expiry_dt = datetime.fromisoformat(parsed_notam['expiry_time'].replace('Z', '+00:00'))
                local_end = expiry_dt + offset_delta
                local_time_str = f"{local_start.strftime('%y/%m/%d %H:%M')} - {local_end.strftime('%y/%m/%d %H:%M')} ({timezone_offset})"
            else:
                # 만료 시간이 없는 경우
                local_time_str = f"{local_start.strftime('%y/%m/%d %H:%M')} ({timezone_offset})"
            
            # D) 필드가 있으면 시간대 정보 추가
            local_time_ranges = []
            if parsed_notam and parsed_notam.get('d_field'):
                d_field = parsed_notam['d_field'].strip()
                # D) 필드의 시간 정보를 로컬 시간으로 변환
                local_d_field, local_d_ranges = self._convert_d_field_to_local_time(
                    d_field,
                    timezone_offset,
                    reference_dt=effective_dt
                )
                local_time_str += f" / 시간대: {local_d_field}({timezone_offset})"
                if local_d_ranges:
                    for rng in local_d_ranges:
                        rng_copy = rng.copy()
                        rng_copy['timezone_offset'] = timezone_offset
                        local_time_ranges.append(rng_copy)
            
            return local_time_str, local_time_ranges
            
        except Exception as e:
            print(f"로컬 시간 변환 오류: {e}")
            return None, []
    
    def format_notam_time_with_local(self, effective_time, expiry_time, airport_code, parsed_notam=None):
        """NOTAM 시간을 로컬 시간으로 포맷팅"""
        if not effective_time:
            return None
        # 폴백 오프셋
        fallback_offset = self.get_timezone(airport_code)
        timezone_offset = fallback_offset
        
        try:
            # UTC 시간을 datetime 객체로 변환
            effective_dt = datetime.fromisoformat(effective_time.replace('Z', '+00:00'))
            # 날짜별 정확 오프셋(zoneinfo) 시도
            import os
            allow_remote = os.getenv('TIMEZONE_FALLBACK_ENABLED', '0').lower() in ('1','true','yes')
            tz_for_display = _timezone_api.get_offset_for_datetime(airport_code, effective_dt, allow_remote=allow_remote)
            timezone_offset = tz_for_display or fallback_offset
            # 타임존 오프셋 파싱 (+HH:MM 형식)
            offset_sign = 1 if timezone_offset.startswith('+') else -1
            offset_hours = int(timezone_offset[1:3])
            offset_minutes = int(timezone_offset[4:6])
            offset_delta = timedelta(hours=offset_hours * offset_sign, minutes=offset_minutes * offset_sign)
            
            # 로컬 시간 계산
            local_start = effective_dt + offset_delta
            
            # 만료 시간 처리
            if expiry_time == 'UFN':
                # UFN인 경우
                local_time_str = f"{local_start.strftime('%y/%m/%d %H:%M')} - UFN ({timezone_offset})"
            elif expiry_time == 'PERM':
                # PERM인 경우
                local_time_str = f"{local_start.strftime('%y/%m/%d %H:%M')} - PERM ({timezone_offset})"
            elif expiry_time:
                # 일반적인 만료 시간이 있는 경우
                expiry_dt = datetime.fromisoformat(expiry_time.replace('Z', '+00:00'))
                local_end = expiry_dt + offset_delta
                local_time_str = f"{local_start.strftime('%y/%m/%d %H:%M')} - {local_end.strftime('%y/%m/%d %H:%M')} ({timezone_offset})"
            else:
                # 만료 시간이 없는 경우
                local_time_str = f"{local_start.strftime('%y/%m/%d %H:%M')} ({timezone_offset})"
            
            # D) 필드가 있으면 시간대 정보 추가
            if parsed_notam and parsed_notam.get('d_field'):
                d_field = parsed_notam['d_field'].strip()
                # D) 필드의 시간 정보를 로컬 시간으로 변환
                local_d_field, _ = self._convert_d_field_to_local_time(
                    d_field,
                    timezone_offset,
                    reference_dt=effective_dt
                )
                local_time_str += f" / 시간대: {local_d_field}({timezone_offset})"
            
            return local_time_str
            
        except Exception as e:
            print(f"시간 포맷팅 오류: {e}")
            print(f"  effective_time: {effective_time}")
            print(f"  expiry_time: {expiry_time}")
            print(f"  airport_code: {airport_code}")
            print(f"  timezone_offset: {timezone_offset}")
            return None
    
    def _convert_d_field_to_local_time(self, d_field, timezone_offset, reference_dt=None):
        """D) 필드의 시간을 로컬 시간으로 변환"""
        try:
            import re
            from datetime import datetime, timedelta
            from calendar import monthrange
            
            # 타임존 오프셋 파싱 (+07:00 형식)
            offset_sign = 1 if timezone_offset.startswith('+') else -1
            offset_hours = int(timezone_offset[1:3])
            offset_minutes = int(timezone_offset[4:6])
            offset_delta = timedelta(hours=offset_hours * offset_sign, minutes=offset_minutes * offset_sign)
            
            lines = d_field.split('\n')
            converted_lines = []
            range_entries = []
            # 기준 날짜 설정 (effectivet_time 기반, 없으면 현재 날짜 사용)
            if reference_dt:
                base_dt = reference_dt
            else:
                base_dt = datetime.utcnow()
            base_date = base_dt.date()

            def resolve_date(day, base_dt):
                """기준일 기준으로 날짜 계산 (월 경계 보정)"""
                year = base_dt.year
                month = base_dt.month
                base_day = base_dt.day

                if day < 1:
                    day = 1

                # 기준일보다 훨씬 작은 경우 다음 달로 간주
                if day < base_day - 30:
                    month += 1
                    if month > 12:
                        month = 1
                        year += 1
                # 기준일보다 훨씬 큰 경우 이전 달로 간주
                elif day > base_day + 30:
                    month -= 1
                    if month < 1:
                        month = 12
                        year -= 1

                # 월 말 초과 보정
                last_day = monthrange(year, month)[1]
                if day > last_day:
                    day = last_day

                return datetime(year, month, day)
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # 날짜와 시간 패턴 매칭 (예: "05 1900-1930", "06-29 1900-2300")
                # 단일 날짜 패턴: DD HHMM-HHMM
                single_date_match = re.match(r'^(\d{1,2})\s+(\d{4})-(\d{4})$', line)
                if single_date_match:
                    day = int(single_date_match.group(1))
                    start_time = single_date_match.group(2)
                    end_time = single_date_match.group(3)
                    
                    # UTC 시간을 datetime으로 변환 (reference_dt 기준)
                    base_start = resolve_date(day, base_dt)
                    utc_start = datetime(base_start.year, base_start.month, base_start.day,
                                         int(start_time[:2]), int(start_time[2:]))
                    utc_end = datetime(base_start.year, base_start.month, base_start.day,
                                       int(end_time[:2]), int(end_time[2:]))
                    
                    # 로컬 시간으로 변환
                    local_start = utc_start + offset_delta
                    local_end = utc_end + offset_delta
                    
                    day_str = f"{local_start.day:02d}"
                    converted_line = f"{day_str} {local_start.strftime('%H%M')}-{local_end.strftime('%H%M')}"
                    converted_lines.append(converted_line)
                    range_entries.append({
                        'start_utc': utc_start.strftime('%Y-%m-%dT%H:%M:%SZ'),
                        'end_utc': utc_end.strftime('%Y-%m-%dT%H:%M:%SZ')
                    })
                    continue
                # 날짜 목록 + 시간 패턴 (예: "03-07 11-14 1430/2020")
                complex_range_match = re.match(r'^((?:\d{1,2}(?:-\d{1,2})?\s+)+)(\d{4})/(\d{4})$', line)
                if complex_range_match:
                    day_tokens = complex_range_match.group(1).split()
                    start_time = complex_range_match.group(2)
                    end_time = complex_range_match.group(3)
                    for token in day_tokens:
                        if '-' in token:
                            d_start, d_end = token.split('-')
                            d_start = int(d_start)
                            d_end = int(d_end)
                            for day in range(d_start, d_end + 1):
                                base_day = resolve_date(day, base_dt)
                                utc_start = datetime(base_day.year, base_day.month, base_day.day,
                                                     int(start_time[:2]), int(start_time[2:]))
                                utc_end = datetime(base_day.year, base_day.month, base_day.day,
                                                   int(end_time[:2]), int(end_time[2:]))
                                if utc_end < utc_start:
                                    utc_end += timedelta(days=1)
                                local_start = utc_start + offset_delta
                                local_end = utc_end + offset_delta
                                converted_lines.append(
                                    f"{day:02d} {local_start.strftime('%H%M')}-{local_end.strftime('%H%M')}"
                                )
                                range_entries.append({
                                    'day_token': f"{day:02d}",
                                    'start_utc': utc_start.strftime('%Y-%m-%dT%H:%M:%SZ'),
                                    'end_utc': utc_end.strftime('%Y-%m-%dT%H:%M:%SZ')
                                })
                        else:
                            d = int(token)
                            base_day_dt = resolve_date(d, base_dt)
                            utc_start = datetime(base_day_dt.year, base_day_dt.month, base_day_dt.day,
                                                 int(start_time[:2]), int(start_time[2:]))
                            utc_end = datetime(base_day_dt.year, base_day_dt.month, base_day_dt.day,
                                               int(end_time[:2]), int(end_time[2:]))
                            if utc_end < utc_start:
                                utc_end += timedelta(days=1)
                            local_start = utc_start + offset_delta
                            local_end = utc_end + offset_delta
                            converted_lines.append(
                                f"{d:02d} {local_start.strftime('%H%M')}-{local_end.strftime('%H%M')}"
                            )
                            range_entries.append({
                                'day_token': f"{d:02d}",
                                'start_utc': utc_start.strftime('%Y-%m-%dT%H:%M:%SZ'),
                                'end_utc': utc_end.strftime('%Y-%m-%dT%H:%M:%SZ')
                            })
                    continue

                # 시간만 있는 패턴: HHMM/HHMM 또는 HHMM-HHMM
                time_only_match = re.match(r'^(\d{4})/(\d{4})$', line)
                time_only_dash_match = re.match(r'^(\d{4})-(\d{4})$', line) if not time_only_match else None
                if time_only_match:
                    start_time = time_only_match.group(1)
                    end_time = time_only_match.group(2)
                elif time_only_dash_match:
                    start_time = time_only_dash_match.group(1)
                    end_time = time_only_dash_match.group(2)
                else:
                    start_time = end_time = None

                if start_time and end_time:
                    # 기준 날짜 사용
                    utc_start = datetime(
                        base_date.year, base_date.month, base_date.day,
                        int(start_time[:2]), int(start_time[2:])
                    )
                    utc_end = datetime(
                        base_date.year, base_date.month, base_date.day,
                        int(end_time[:2]), int(end_time[2:])
                    )
                    # 종료 시간이 시작보다 빠르면 다음날로 간주
                    if utc_end < utc_start:
                        utc_end += timedelta(days=1)
                    # 로컬 시간 변환
                    local_start = utc_start + offset_delta
                    local_end = utc_end + offset_delta
                    start_str = local_start.strftime('%H%M')
                    end_str = local_end.strftime('%H%M')
                    converted_lines.append(f"{start_str}-{end_str}")
                    range_entries.append({
                        'start_utc': utc_start.strftime('%Y-%m-%dT%H:%M:%SZ'),
                        'end_utc': utc_end.strftime('%Y-%m-%dT%H:%M:%SZ')
                    })
                    continue
                
                # 날짜 범위 패턴: DD-DD HHMM-HHMM
                date_range_match = re.match(r'^(\d{1,2})-(\d{1,2})\s+(\d{4})-(\d{4})$', line)
                if date_range_match:
                    start_day = int(date_range_match.group(1))
                    end_day = int(date_range_match.group(2))
                    start_time = date_range_match.group(3)
                    end_time = date_range_match.group(4)
                    
                    for day in range(start_day, end_day + 1):
                        base_day = resolve_date(day, base_dt)
                        utc_start = datetime(base_day.year, base_day.month, base_day.day,
                                             int(start_time[:2]), int(start_time[2:]))
                        utc_end = datetime(base_day.year, base_day.month, base_day.day,
                                           int(end_time[:2]), int(end_time[2:]))
                        if utc_end < utc_start:
                            utc_end += timedelta(days=1)
                        local_start = utc_start + offset_delta
                        local_end = utc_end + offset_delta
                        converted_lines.append(
                            f"{day:02d} {local_start.strftime('%H%M')}-{local_end.strftime('%H%M')}"
                        )
                        range_entries.append({
                            'day_token': f"{day:02d}",
                            'start_utc': utc_start.strftime('%Y-%m-%dT%H:%M:%SZ'),
                            'end_utc': utc_end.strftime('%Y-%m-%dT%H:%M:%SZ')
                        })
                    continue
                
                # 변환할 수 없는 패턴은 그대로 유지
                converted_lines.append(line)
            
            # 동일 시간대(예: "02 0010-0530")를 압축 표현
            from collections import OrderedDict
            grouped_times = OrderedDict()
            retained_lines = []
            for line in converted_lines:
                single_match = re.match(r'^(\d{2}) (\d{4}-\d{4})$', line)
                if single_match:
                    day = single_match.group(1)
                    time_range = single_match.group(2)
                    if time_range not in grouped_times:
                        grouped_times[time_range] = []
                    grouped_times[time_range].append(day)
                else:
                    retained_lines.append(line)

            condensed_lines = []
            for time_range, days in grouped_times.items():
                condensed_lines.append(f"{' '.join(days)} {time_range}")
            condensed_lines.extend(retained_lines)

            return '\n'.join(condensed_lines), range_entries
            
        except Exception as e:
            print(f"D) 필드 시간 변환 오류: {e}")
            return d_field, []  # 오류 시 원본 반환

    def _detect_notam_type(self, text):
        """텍스트에서 NOTAM 유형을 감지 (package or airport)"""
        # upper() 결과 캐싱 (성능 최적화)
        text_upper = text.upper()
        if 'KOREAN AIR NOTAM PACKAGE' in text_upper:
            return 'package'
        return 'airport'

    def filter_korean_air_notams(self, text):
        """한국 항공사 노선 관련 모든 공항 NOTAM 처리 (패키지/개별 공항 자동 감지)"""
        import re
        
        # NOTAM 유형 감지
        notam_type = self._detect_notam_type(text)
        self.logger.debug(f"NOTAM 유형 감지: {notam_type}")
        
        if notam_type == 'package':
            return self._filter_package_notams(text)
        else:
            return self._filter_airport_notams(text)

    def _filter_airport_notams(self, text):
        """공항 NOTAM 필터링 (기존 로직)"""
        import re
        
        # 더 유연한 NOTAM 시작 패턴 (다양한 형식 지원, SECY 제외, 번호 포함)
        notam_start_patterns = [
            r'^(?:\d+\.\s+)?\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*-\s*(?:\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}|UFN|PERM)\s+[A-Z]{4}(?!\s+SECY)',  # 번호 포함 패턴 (SECY 제외)
            r'^\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*-\s*(?:\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}|UFN|PERM)\s+[A-Z]{4}(?!\s+SECY)',  # 기존 패턴 (SECY 제외)
            r'^(?:\d+\.\s+)?\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*-\s*(?:\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}|UFN|PERM)\s+[A-Z]{4}\s+(?!SECY)[A-Z0-9]+/\d{2}[A-Z0-9]*',  # 번호 포함 NOTAM 번호 패턴 (SECY 제외, 접미사 포함)
            r'^\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*-\s*(?:\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}|UFN|PERM)\s+[A-Z]{4}\s+(?!SECY)[A-Z0-9]+/\d{2}[A-Z0-9]*',  # NOTAM 번호 포함 (SECY 제외, 접미사 포함)
            r'^(?:\d+\.\s+)?\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*-\s*(?:\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}|UFN|PERM)\s+[A-Z]{4}\s+AIP\s+SUP\s+\d{2}/\d{2}',  # 번호 포함 AIP SUP 형식
            r'^\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*-\s*(?:\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}|UFN|PERM)\s+[A-Z]{4}\s+AIP\s+SUP\s+\d{2}/\d{2}',  # AIP SUP 형식
            r'^(?:\d+\.\s+)?\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*-\s*(?:\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}|UFN|PERM)\s+[A-Z]{4}\s+AIP\s+AD\s+\d+\.\d+',  # AIP AD 형식 (예: VVDN AIP AD 2.9)
            r'^\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*-\s*(?:\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}|UFN|PERM)\s+[A-Z]{4}\s+AIP\s+AD\s+\d+\.\d+',  # AIP AD 형식 (예: VVDN AIP AD 2.9)
            r'^[A-Z]{4}\s+COAD\d{2}/\d{2}$',  # VVCR COAD01/25 형식
        ]
        section_end_patterns = [
            r'^\[ALTN\]', r'^\[DEST\]', r'^\[ENRT\]', r'^\[ETC\]', r'^\[INFO\]', r'^\[ROUTE\]', r'^\[WX\]',
            r'^\[FIR\]',  # FIR 섹션 종료 패턴 추가
            r'^COAD',
            r'^[A-Z]{4} COAD\d{2}/\d{2}',
            r'^[A-Z]{4}\s*$',  # 공항코드만 단독 등장
            r'^1\.\s+RUNWAY\s*:',  # "1. RUNWAY :" 패턴 추가
            r'^={4,}$',  # 4개 이상의 등호로만 구성된 줄 (NOTAM 구분선)
            r'^\[REFILE\]'  # [REFILE]로 시작하는 줄도 NOTAM 종료로 인식
        ]
        
        # 기존 공항 NOTAM 필터링 로직
        lines = text.split('\n')
        notam_sections = []
        current_notam = []
        found_first_notam = False
        skip_mode = False
        
        for line in lines:
            # skip_mode가 True일 때는 새로운 NOTAM 시작 패턴만 처리하고 나머지는 모두 건너뛰기
            if skip_mode:
                # 여러 패턴 시도 (조기 종료 최적화)
                notam_start_in_skip = False
                for pattern in notam_start_patterns:
                    if re.match(pattern, line):
                        notam_start_in_skip = True
                        break  # 첫 번째 매칭 발견 시 즉시 종료
                if notam_start_in_skip:
                    found_first_notam = True
                    skip_mode = False
                    if current_notam:
                        notam_sections.append('\n'.join(current_notam).strip())
                        current_notam = []
                    current_notam.append(line)
                    self.logger.debug(f"새로운 NOTAM 시작으로 skip_mode 해제: {line.strip()[:50]}...")
                # skip_mode가 True면 어떤 줄도 current_notam에 추가하지 않음
                continue
            
            # END OF KOREAN AIR NOTAM PACKAGE 처리 - 현재 NOTAM을 종료하고 END OF KOREAN AIR NOTAM PACKAGE 이후 모든 내용 건너뛰기
            if re.search(r'END OF KOREAN AIR NOTAM PACKAGE', line.strip(), re.IGNORECASE):
                if current_notam:
                    notam_sections.append('\n'.join(current_notam).strip())
                    self.logger.debug(f"END OF KOREAN AIR NOTAM PACKAGE로 NOTAM 종료: {len(current_notam)}줄")
                    current_notam = []
                # END OF KOREAN AIR NOTAM PACKAGE 이후 모든 내용을 건너뛰기 위해 skip_mode 활성화
                skip_mode = True
                self.logger.debug(f"END OF KOREAN AIR NOTAM PACKAGE 이후 건너뛰기 시작")
                # END OF KOREAN AIR NOTAM PACKAGE 라인 자체도 current_notam에 추가하지 않음
                continue
                
            # NO CURRENT NOTAMS FOUND 처리 - 현재 NOTAM을 종료하고 이후 모든 내용 건너뛰기
            if re.search(r'\*{8}\s*NO CURRENT NOTAMS FOUND\s*\*{8}', line.strip(), re.IGNORECASE):
                if current_notam:
                    notam_sections.append('\n'.join(current_notam).strip())
                    self.logger.debug(f"NO CURRENT NOTAMS FOUND로 NOTAM 종료: {len(current_notam)}줄")
                    current_notam = []
                # NO CURRENT NOTAMS FOUND 이후 모든 내용을 건너뛰기 위해 skip_mode 활성화
                skip_mode = True
                self.logger.debug(f"NO CURRENT NOTAMS FOUND 이후 건너뛰기 시작")
                # NO CURRENT NOTAMS FOUND 라인 자체도 current_notam에 추가하지 않음
                continue
                
            # SECY 관련 패턴 완전 제외
            if (re.search(r'SECY\s*/\s*SECURITY INFORMATION', line.strip(), re.IGNORECASE) or
                re.search(r'SECY\s+COAD\d+/\d+', line.strip(), re.IGNORECASE) or
                re.search(r'\d+\.\s+\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*-\s*\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s+SECY', line.strip(), re.IGNORECASE)):
                # SECY 섹션 전체를 건너뛰기 위해 skip_mode 활성화
                skip_mode = True
                self.logger.debug(f"SECY 관련 패턴 건너뛰기 시작: {line.strip()}")
                continue
                
            # COMPANY ADVISORY 섹션 완전 제외 - 모든 COMPANY ADVISORY 관련 내용 건너뛰기
            if re.search(r'COMPANY ADVISORY|MPANY ADVISORY', line.strip(), re.IGNORECASE):
                # COMPANY ADVISORY 섹션 전체를 건너뛰기 위해 skip_mode 활성화
                skip_mode = True
                self.logger.debug(f"COMPANY ADVISORY 섹션 건너뛰기 시작: {line.strip()}")
                continue
                
            # SECY 섹션 내 개별 항목들도 건너뛰기 (1., 2., 3. 등)
            if re.search(r'^\d+\.\s+\d{2}[A-Z]{3}\d{2}', line.strip()) and skip_mode:
                self.logger.debug(f"SECY/COMPANY ADVISORY 항목 건너뛰기: {line.strip()[:50]}...")
                continue
                
            # COMPANY ADVISORY 항목 종료 패턴에서 skip_mode 해제
            if re.search(r'--\s+BY\s+[A-Z]+--', line.strip()) and skip_mode:
                self.logger.debug(f"COMPANY ADVISORY 섹션 건너뛰기 종료")
                skip_mode = False
                continue
                
            # COMPANY ADVISORY 섹션에서 새로운 NOTAM이 시작되면 skip_mode 해제
            # 여러 패턴 시도하여 NOTAM 시작 확인 (조기 종료 최적화)
            notam_start_found = False
            for pattern in notam_start_patterns:
                if re.match(pattern, line):
                    notam_start_found = True
                    break  # 첫 번째 매칭 발견 시 즉시 종료
            
            if notam_start_found and skip_mode:
                self.logger.debug(f"새로운 NOTAM 시작으로 COMPANY ADVISORY skip_mode 해제")
                skip_mode = False
                found_first_notam = True
                if current_notam:
                    notam_sections.append('\n'.join(current_notam).strip())
                    current_notam = []
                current_notam.append(line)
                continue
                
            if notam_start_found:
                found_first_notam = True
                skip_mode = False
                if current_notam:
                    notam_sections.append('\n'.join(current_notam).strip())
                    self.logger.debug(f"새 NOTAM 시작으로 이전 NOTAM 종료: {len(current_notam)}줄")
                    current_notam = []
                current_notam.append(line)
                self.logger.debug(f"새 NOTAM 시작: {line.strip()[:50]}...")
            else:
                # section_end_patterns 체크 (조기 종료 최적화)
                section_end_found = False
                for pat in section_end_patterns:
                    if re.match(pat, line):
                        section_end_found = True
                        break  # 첫 번째 매칭 발견 시 즉시 종료
                
                if section_end_found:
                    if current_notam:
                        notam_sections.append('\n'.join(current_notam).strip())
                        current_notam = []
                    skip_mode = True

                elif line.startswith('[REFILE]'):
                    if current_notam:
                        notam_sections.append('\n'.join(current_notam).strip())
                        current_notam = []
                    skip_mode = True

                elif found_first_notam:
                    current_notam.append(line)
                
        if current_notam:
            notam_sections.append('\n'.join(current_notam).strip())

        filtered_notams = []
        self.logger.debug(f"총 {len(notam_sections)}개의 NOTAM 섹션으로 분할됨")
        

        for i, section in enumerate(notam_sections):
            # strip() 결과 캐싱 (성능 최적화 - 반복 호출 방지)
            section_stripped = section.strip()
            if not section_stripped:
                continue
            
            # NOTAM 파싱 (캐싱된 strip() 결과 사용)
            parsed_notam = self._parse_notam_section(section_stripped)

            self.logger.debug(f"섹션 {i+1}: 공항코드={parsed_notam.get('airport_code')}, NOTAM번호={parsed_notam.get('notam_number')}")

            # 공항 코드가 있는 모든 NOTAM 처리 (한국 공항이 아니어도 포함)
            airport_code = parsed_notam.get('airport_code')
            if airport_code:
                # 기본 정보 설정
                # COAD NOTAM의 경우 E) 필드가 짧게 추출될 수 있으므로 원문 전체를 보존
                # strip() 결과 재사용 (이미 위에서 계산됨)
                description = parsed_notam.get('e_field') or section_stripped
                description = strip_security_footer(description)
                # 카테고리 마커 제거 (예: ◼ APPROACH LIGHT, ◼ OBSTRUCTION)
                description = self.compiled_e_field_cleanup_patterns['category_marker'].sub('', description).strip()
                
                # E 섹션만 원문으로 사용 (D 섹션 제외)
                # _parse_notam_section에서 이미 추출한 e_field를 우선 사용
                e_field_content = parsed_notam.get('e_field', '')
                
                # e_field가 충분한 길이(100자 이상)이면 extract_e_section 재호출하지 않음 (캐싱 효과)
                if not e_field_content or len(e_field_content) < 100:
                    # e_field가 없거나 너무 짧으면 extract_e_section으로 재시도 (사전 컴파일된 패턴 사용)
                    # strip() 결과 재사용 (이미 위에서 계산됨)
                    e_field_from_section = extract_e_section(section_stripped, self.compiled_extract_e_section_patterns)
                    if e_field_from_section and len(e_field_from_section) > len(e_field_content):
                        e_field_content = e_field_from_section
                    if not e_field_content:
                        e_field_content = description  # 그래도 없으면 description 사용
                
                e_field_content = strip_security_footer(e_field_content)
                # 카테고리 마커 제거 (예: ◼ APPROACH LIGHT, ◼ OBSTRUCTION)
                e_field_content = self.compiled_e_field_cleanup_patterns['category_marker'].sub('', e_field_content).strip()

                # COAD NOTAM 보정: e_field가 매우 짧으면 본문 전체를 사용
                notam_number_value = parsed_notam.get('notam_number') or ''
                if 'COAD' in notam_number_value:
                    section_lines = section_stripped.split('\n')
                    coad_body = '\n'.join(section_lines[1:]).strip() or section_stripped
                    if not e_field_content or len(e_field_content.strip()) < 40:
                        e_field_content = coad_body
                    if not description or len(description.strip()) < 40:
                        description = coad_body
                    # COAD 본문에서도 카테고리 마커 제거
                    e_field_content = self.compiled_e_field_cleanup_patterns['category_marker'].sub('', e_field_content).strip()
                    description = self.compiled_e_field_cleanup_patterns['category_marker'].sub('', description).strip()
                
                # 원문은 D) 필드부터 시작하는 내용만 포함 (시간 정보와 NOTAM 번호 제외)
                # COAD NOTAM의 경우 E) 필드가 없으므로 시간 정보와 NOTAM 번호 다음부터 가져옴
                notam_number_value = parsed_notam.get('notam_number') or ''
                is_coad = 'COAD' in notam_number_value
                
                if is_coad:
                    # COAD NOTAM: 시간 정보와 NOTAM 번호 패턴 찾기
                    # 패턴: DDMMMYY HH:MM - (UFN|PERM|DDMMMYY HH:MM) RKSI COAD##/YY
                    coad_header_pattern = re.compile(
                        r'\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*-\s*(?:UFN|PERM|\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2})\s+[A-Z]{4}\s+COAD\d{2}/\d{2}',
                        re.IGNORECASE
                    )
                    coad_match = coad_header_pattern.search(section_stripped)
                    if coad_match:
                        # 시간 정보와 NOTAM 번호 다음부터 모든 내용 추출
                        full_original_text = section_stripped[coad_match.end():].strip()
                    else:
                        # 패턴을 찾지 못하면 첫 줄 제거 시도 (시간 정보가 첫 줄에 있을 가능성)
                        lines = section_stripped.split('\n')
                        if len(lines) > 1:
                            full_original_text = '\n'.join(lines[1:]).strip()
                        else:
                            full_original_text = section_stripped
                else:
                    # 일반 NOTAM: D) 필드의 시작 위치를 찾아서 그 이후의 모든 내용 추출
                    # D) 필드가 없으면 E) 필드부터 시작
                    # D) 필드는 줄의 시작 부분에 있어야 함 (단어 경계 고려)
                    d_field_start = re.search(r'^D\)\s*', section_stripped, re.IGNORECASE | re.MULTILINE)
                    if not d_field_start:
                        # 줄 시작이 아닌 경우도 확인 (공백이나 탭 후 D))
                        d_field_start = re.search(r'(?:^|\n)\s*D\)\s*', section_stripped, re.IGNORECASE)
                    
                    if d_field_start:
                        # D) 필드부터 시작하는 모든 내용 추출
                        full_original_text = section_stripped[d_field_start.start():].strip()
                    else:
                        # D) 필드가 없으면 E) 필드부터 시작
                        # E) 필드는 줄의 시작 부분에 있어야 함
                        e_field_start = re.search(r'^E\)\s*', section_stripped, re.IGNORECASE | re.MULTILINE)
                        if not e_field_start:
                            # 줄 시작이 아닌 경우도 확인 (공백이나 탭 후 E))
                            e_field_start = re.search(r'(?:^|\n)\s*E\)\s*', section_stripped, re.IGNORECASE)
                        
                        if e_field_start:
                            # E) 필드부터 시작하는 모든 내용 추출
                            full_original_text = section_stripped[e_field_start.start():].strip()
                            
                            # E) 필드 앞에 시간 정보와 NOTAM 번호 헤더가 있는지 확인하고 제거
                            if e_field_start.start() > 0:
                                before_e_field = section_stripped[:e_field_start.start()]
                                general_header_pattern = re.compile(
                                    r'\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*-\s*(?:UFN|PERM|\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2})\s+[A-Z]{4}\s+[A-Z0-9]+/\d{2}[A-Z0-9]*',
                                    re.IGNORECASE
                                )
                                header_match = general_header_pattern.search(before_e_field)
                                if header_match:
                                    # 시간 정보와 NOTAM 번호 다음부터 E) 필드까지 추출
                                    full_original_text = section_stripped[header_match.end():].strip()
                        else:
                            # D), E) 필드가 모두 없으면 시간 정보와 NOTAM 번호 헤더 제거 후 전체 섹션 사용
                            # 시간 정보와 NOTAM 번호 패턴 찾기 (일반 NOTAM용, 접미사 포함)
                            general_header_pattern = re.compile(
                                r'\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*-\s*(?:UFN|PERM|\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2})\s+[A-Z]{4}\s+[A-Z0-9]+/\d{2}[A-Z0-9]*',
                                re.IGNORECASE
                            )
                            header_match = general_header_pattern.search(section_stripped)
                            if header_match:
                                # 시간 정보와 NOTAM 번호 다음부터 모든 내용 추출
                                full_original_text = section_stripped[header_match.end():].strip()
                            else:
                                # 패턴을 찾지 못하면 전체 섹션 사용 (fallback)
                                full_original_text = section_stripped
                
                # Package 종료 문구 이후(CFP, REFILE, 경로표 등) 제거 — 원문이 한 줄에 붙었을 때 길게 나오는 현상 방지
                full_original_text = truncate_at_package_end(full_original_text)

                # full_original_text가 비어있거나 "D)"만 있으면 e_field_content 사용
                if not full_original_text or full_original_text.strip() == 'D)' or len(full_original_text.strip()) < 5:
                    if e_field_content:
                        # e_field_content에서 시간 정보와 NOTAM 번호 헤더 제거
                        e_field_clean = e_field_content
                        # 시간 정보와 NOTAM 번호 패턴 찾기 (접미사 포함)
                        general_header_pattern = re.compile(
                            r'\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*-\s*(?:UFN|PERM|\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2})\s+[A-Z]{4}\s+[A-Z0-9]+/\d{2}[A-Z0-9]*',
                            re.IGNORECASE
                        )
                        # E) 필드 앞에 시간 정보가 있으면 제거
                        e_field_match = re.search(r'E\)\s*', e_field_clean, re.IGNORECASE)
                        if e_field_match and e_field_match.start() > 0:
                            before_e = e_field_clean[:e_field_match.start()]
                            header_match = general_header_pattern.search(before_e)
                            if header_match:
                                e_field_clean = e_field_clean[header_match.end():].strip()
                        # E) 필드가 없으면 추가
                        if not e_field_clean.strip().startswith('E)'):
                            e_field_clean = 'E) ' + e_field_clean.strip()
                        full_original_text = e_field_clean
                
                # 카테고리 마커 제거 (예: ◼ APPROACH LIGHT, ◼ OBSTRUCTION)
                full_original_text = self.compiled_e_field_cleanup_patterns['category_marker'].sub('', full_original_text).strip()
                # 원문에도 색상 스타일 적용 (전체 원문에 적용)
                styled_section = apply_color_styles(full_original_text)
                # styled_section에서도 카테고리 마커 제거 (HTML 태그, 마크다운 스타일 등 모든 경우 처리)
                # 더 강력한 패턴: ◼ 또는 ■ 뒤에 오는 모든 문자(HTML 태그, 마크다운 포함) 제거
                styled_section = re.sub(r'[◼■]\s*[^\n]*(?:\n|$)', '', styled_section, flags=re.MULTILINE)
                # HTML 태그 내부에 있을 수 있는 경우도 처리 (예: <span>■ TAXIWAY</span>)
                styled_section = re.sub(r'<[^>]*>[◼■]\s*[^<]*</[^>]*>', '', styled_section, flags=re.MULTILINE)
                # 마크다운 스타일 제거 (예: **■ TAXIWAY**)
                styled_section = re.sub(r'\*+\s*[◼■]\s*[^\n*]+\*+', '', styled_section, flags=re.MULTILINE)
                styled_section = styled_section.strip()
                
                # NOTAM 카테고리 분석
                category = analyze_notam_category(e_field_content, parsed_notam.get('q_code'))
                category_info = NOTAM_CATEGORIES.get(category, {
                    'icon': '📄',
                    'color': '#6c757d',
                    'bg_color': '#e9ecef'
                })
                
                raw_notam_number = parsed_notam.get('notam_number', 'Unknown')
                display_notam_number = raw_notam_number
                if airport_code and raw_notam_number:
                    airport_code_upper = airport_code.upper()
                    if not raw_notam_number.upper().startswith(airport_code_upper):
                        display_notam_number = f"{airport_code_upper} {raw_notam_number}"
                
                notam_dict = {
                    'id': raw_notam_number or display_notam_number,
                    'notam_number': raw_notam_number,
                    'notam_number_display': display_notam_number,
                    'notam_number_raw': raw_notam_number,
                    'airport_code': parsed_notam.get('airport_code'),
                    'effective_time': parsed_notam.get('effective_time', ''),
                    'expiry_time': parsed_notam.get('expiry_time', ''),
                    'description': description,
                    'original_text': styled_section,
                    'd_field': parsed_notam.get('d_field', ''),
                    'e_field': e_field_content,
                    'category': category,
                    'category_icon': category_info['icon'],
                    'category_color': category_info['color'],
                    'category_bg_color': category_info['bg_color'],
                    'local_time_ranges': []
                }
                
                # UFN을 포함한 모든 시간 정보에 대해 local_time_display 생성
                if parsed_notam.get('effective_time') and (parsed_notam.get('expiry_time') or parsed_notam.get('expiry_time') == 'UFN'):
                    local_time_display, local_time_ranges = self._generate_local_time_display(parsed_notam)
                    if local_time_display:
                        notam_dict['local_time_display'] = local_time_display
                        if local_time_ranges:
                            notam_dict['local_time_ranges'] = local_time_ranges
                        # 원본 텍스트에는 로컬 시간 추가하지 않음 (별도 필드로 관리)

                filtered_notams.append(notam_dict)
            else:
                self.logger.debug(f"섹션 {i+1}: 공항 코드를 찾을 수 없음 (섹션 시작: {section[:100]}...)")

        self.logger.debug(f"최종 {len(filtered_notams)}개의 NOTAM 추출 완료")
        return filtered_notams
    
    def _extract_content_after_notam_number(self, text, notam_number):
        """NOTAM 번호 이후의 내용만 추출합니다."""
        self.logger.debug(f"🔍 원문 추출 시작 - NOTAM: {notam_number}")
        self.logger.debug(f"📝 원본 텍스트 길이: {len(text)}")
        
        if not notam_number:
            self.logger.debug("⚠️ NOTAM 번호가 없어서 원본 텍스트 반환")
            return text
        
        # NOTAM 번호를 찾아서 그 이후의 내용을 추출
        # 다양한 패턴으로 NOTAM 번호를 찾습니다
        patterns = [
            # COAD 패턴: RKSI COAD01/25
            rf'([A-Z]{{4}}\s+)?{re.escape(notam_number)}',
            # AIP SUP 패턴: AIP SUP 20/25
            rf'(AIP\s+SUP\s+)?{re.escape(notam_number)}',
            # 일반 패턴: A1234/25
            rf'\b{re.escape(notam_number)}\b'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                # NOTAM 번호 이후의 내용 추출
                after_notam = text[match.end():].strip()
                
                # // 로 시작하는 경우 // 제거
                if after_notam.startswith('//'):
                    after_notam = after_notam[2:].strip()
                
                # -- BY로 끝나는 경우 그 이후 제거
                by_match = re.search(r'--\s*BY\s+[A-Z]+--', after_notam)
                if by_match:
                    after_notam = after_notam[:by_match.start()].strip()
                
                self.logger.debug(f"✅ 첫 번째 패턴으로 추출 성공: {len(after_notam)}자")
                return after_notam
        
        # 패턴을 찾지 못한 경우, 더 간단한 방법으로 시도
        # NOTAM 번호만으로 직접 찾기
        simple_patterns = [
            rf'{re.escape(notam_number)}\s*//',  # COAD01/25 //
            rf'{re.escape(notam_number)}\s+//',  # COAD01/25 //
            rf'{re.escape(notam_number)}\s*$',   # 줄 끝에 있는 경우
        ]
        
        for pattern in simple_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                after_notam = text[match.end():].strip()
                if after_notam.startswith('//'):
                    after_notam = after_notam[2:].strip()
                
                by_match = re.search(r'--\s*BY\s+[A-Z]+--', after_notam)
                if by_match:
                    after_notam = after_notam[:by_match.start()].strip()
                
                self.logger.debug(f"✅ 간단한 패턴으로 추출 성공: {len(after_notam)}자")
                return after_notam
        
        # 모든 패턴을 찾지 못한 경우 원본 텍스트 반환
        self.logger.warning(f"❌ 패턴을 찾지 못해서 원본 텍스트 반환")
        
        return text

    def _filter_package_notams(self, text):
        """패키지 NOTAM 필터링 (pdf_to_txt_test_package.py 기반)"""
        import re
        
        # 패키지 NOTAM의 복잡한 구조를 처리하기 위한 로직
        # 먼저 라인 병합 처리
        merged_text = self._merge_package_notam_lines(text)
        
        # NOTAM 분리
        notam_sections = self._split_package_notams(merged_text)
        
        filtered_notams = []
        # 중복 제거를 위한 set: "공항코드 NOTAM번호" 형식의 키를 저장
        # 예: "RKSS G1935/25", "RKSI COAD12/25" 등
        seen_notam_keys = set()
        self.logger.debug(f"패키지 NOTAM 총 {len(notam_sections)}개의 섹션으로 분할됨")
        

        for i, section in enumerate(notam_sections):
            # strip() 결과 캐싱 (성능 최적화 - 반복 호출 방지)
            section_stripped = section.strip()
            if not section_stripped:
                continue
            
            # NOTAM 파싱 (캐싱된 strip() 결과 사용)
            parsed_notam = self._parse_notam_section(section_stripped)

            self.logger.debug(f"패키지 섹션 {i+1}: 공항코드={parsed_notam.get('airport_code')}, NOTAM번호={parsed_notam.get('notam_number')}")

                # 공항 코드가 있는 모든 NOTAM 처리
            airport_code = parsed_notam.get('airport_code')
            if airport_code:
                # 중복 제거: "공항코드 NOTAM번호" 형식의 키 생성
                raw_notam_number = parsed_notam.get('notam_number', '')
                if raw_notam_number:
                    # NOTAM 번호에서 공항 코드 제거 (이미 포함되어 있을 수 있음)
                    notam_number_clean = raw_notam_number.strip()
                    airport_code_upper = airport_code.upper()
                    
                    # NOTAM 번호가 공항 코드로 시작하면 제거
                    if notam_number_clean.upper().startswith(airport_code_upper):
                        # 공항 코드와 공백 제거
                        notam_number_clean = notam_number_clean[len(airport_code_upper):].strip()
                    
                    # 중복 체크용 키 생성: "공항코드 NOTAM번호" (대소문자 무시)
                    notam_key = f"{airport_code_upper} {notam_number_clean}".upper()
                    
                    # 이미 처리된 NOTAM인지 확인
                    if notam_key in seen_notam_keys:
                        self.logger.debug(f"중복 NOTAM 건너뛰기: {notam_key} (섹션 {i+1})")
                        continue
                    
                    # 처리된 NOTAM 키에 추가
                    seen_notam_keys.add(notam_key)
                    self.logger.debug(f"새 NOTAM 추가: {notam_key} (섹션 {i+1})")
                # 기본 정보 설정
                # E 필드가 있으면 우선 사용, 없으면 NOTAM 번호 이후의 내용 추출
                e_field_content = parsed_notam.get('e_field', '')
                notam_num = parsed_notam.get('notam_number', '')
                
                # e_field가 충분한 길이(100자 이상)이면 extract_e_section 재호출하지 않음 (캐싱 효과)
                if not e_field_content or len(e_field_content) < 100:
                    # E 필드가 없거나 너무 짧으면 extract_e_section으로 재시도 (사전 컴파일된 패턴 사용)
                    # strip() 결과 재사용 (이미 위에서 계산됨)
                    e_field_from_section = extract_e_section(section_stripped, self.compiled_extract_e_section_patterns)
                    if e_field_from_section and len(e_field_from_section) > len(e_field_content):
                        e_field_content = e_field_from_section
                
                # 원문은 D) 필드부터 시작하는 내용만 포함 (시간 정보와 NOTAM 번호 제외)
                # COAD NOTAM의 경우 E) 필드가 없으므로 시간 정보와 NOTAM 번호 다음부터 가져옴
                notam_number_value = parsed_notam.get('notam_number') or ''
                is_coad = 'COAD' in notam_number_value
                
                if is_coad:
                    # COAD NOTAM: 시간 정보와 NOTAM 번호 패턴 찾기
                    # 패턴: DDMMMYY HH:MM - (UFN|PERM|DDMMMYY HH:MM) RKSI COAD##/YY
                    coad_header_pattern = re.compile(
                        r'\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*-\s*(?:UFN|PERM|\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2})\s+[A-Z]{4}\s+COAD\d{2}/\d{2}',
                        re.IGNORECASE
                    )
                    coad_match = coad_header_pattern.search(section_stripped)
                    if coad_match:
                        # 시간 정보와 NOTAM 번호 다음부터 모든 내용 추출
                        original_content = section_stripped[coad_match.end():].strip()
                    else:
                        # 패턴을 찾지 못하면 첫 줄 제거 시도 (시간 정보가 첫 줄에 있을 가능성)
                        lines = section_stripped.split('\n')
                        if len(lines) > 1:
                            original_content = '\n'.join(lines[1:]).strip()
                        else:
                            original_content = section_stripped
                else:
                    # 일반 NOTAM: D) 필드의 시작 위치를 찾아서 그 이후의 모든 내용 추출
                    # D) 필드가 없으면 E) 필드부터 시작
                    # D) 필드는 줄의 시작 부분에 있어야 함 (단어 경계 고려)
                    d_field_start = re.search(r'^D\)\s*', section_stripped, re.IGNORECASE | re.MULTILINE)
                    if not d_field_start:
                        # 줄 시작이 아닌 경우도 확인 (공백이나 탭 후 D))
                        d_field_start = re.search(r'(?:^|\n)\s*D\)\s*', section_stripped, re.IGNORECASE)
                    
                    if d_field_start:
                        # D) 필드부터 시작하는 모든 내용 추출
                        original_content = section_stripped[d_field_start.start():].strip()
                    else:
                        # D) 필드가 없으면 E) 필드부터 시작
                        # E) 필드는 줄의 시작 부분에 있어야 함
                        e_field_start = re.search(r'^E\)\s*', section_stripped, re.IGNORECASE | re.MULTILINE)
                        if not e_field_start:
                            # 줄 시작이 아닌 경우도 확인 (공백이나 탭 후 E))
                            e_field_start = re.search(r'(?:^|\n)\s*E\)\s*', section_stripped, re.IGNORECASE)
                        
                        if e_field_start:
                            # E) 필드부터 시작하는 모든 내용 추출
                            original_content = section_stripped[e_field_start.start():].strip()
                            
                            # E) 필드 앞에 시간 정보와 NOTAM 번호 헤더가 있는지 확인하고 제거
                            if e_field_start.start() > 0:
                                before_e_field = section_stripped[:e_field_start.start()]
                                general_header_pattern = re.compile(
                                    r'\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*-\s*(?:UFN|PERM|\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2})\s+[A-Z]{4}\s+[A-Z0-9]+/\d{2}[A-Z0-9]*',
                                    re.IGNORECASE
                                )
                                header_match = general_header_pattern.search(before_e_field)
                                if header_match:
                                    # 시간 정보와 NOTAM 번호 다음부터 E) 필드까지 추출
                                    original_content = section_stripped[header_match.end():].strip()
                        else:
                            # D), E) 필드가 모두 없으면 시간 정보와 NOTAM 번호 헤더 제거 후 전체 섹션 사용
                            # 시간 정보와 NOTAM 번호 패턴 찾기 (일반 NOTAM용, 접미사 포함)
                            general_header_pattern = re.compile(
                                r'\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*-\s*(?:UFN|PERM|\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2})\s+[A-Z]{4}\s+[A-Z0-9]+/\d{2}[A-Z0-9]*',
                                re.IGNORECASE
                            )
                            header_match = general_header_pattern.search(section_stripped)
                            if header_match:
                                # 시간 정보와 NOTAM 번호 다음부터 모든 내용 추출
                                original_content = section_stripped[header_match.end():].strip()
                            else:
                                # 패턴을 찾지 못하면 전체 섹션 사용 (fallback)
                                original_content = section_stripped
                
                # COAD NOTAM 보정: 본문이 매우 짧게 추출되는 경우 전체 본문 사용
                if 'COAD' in (parsed_notam.get('notam_number') or ''):
                    section_lines = section_stripped.split('\n')
                    coad_body = '\n'.join(section_lines[1:]).strip() or section_stripped
                    if not e_field_content or len(e_field_content.strip()) < 40:
                        e_field_content = coad_body
                
                # Package 종료 문구 이후(CFP, REFILE, 경로표 등) 제거 — 원문이 한 줄에 붙었을 때 길게 나오는 현상 방지
                original_content = truncate_at_package_end(original_content)

                # original_content가 비어있거나 "D)"만 있으면 e_field_content 사용
                if not original_content or original_content.strip() == 'D)' or len(original_content.strip()) < 5:
                    if e_field_content:
                        # e_field_content에서 시간 정보와 NOTAM 번호 헤더 제거
                        e_field_clean = e_field_content
                        # 시간 정보와 NOTAM 번호 패턴 찾기 (접미사 포함)
                        general_header_pattern = re.compile(
                            r'\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*-\s*(?:UFN|PERM|\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2})\s+[A-Z]{4}\s+[A-Z0-9]+/\d{2}[A-Z0-9]*',
                            re.IGNORECASE
                        )
                        # E) 필드 앞에 시간 정보가 있으면 제거
                        e_field_match = re.search(r'E\)\s*', e_field_clean, re.IGNORECASE)
                        if e_field_match and e_field_match.start() > 0:
                            before_e = e_field_clean[:e_field_match.start()]
                            header_match = general_header_pattern.search(before_e)
                            if header_match:
                                e_field_clean = e_field_clean[header_match.end():].strip()
                        # E) 필드가 없으면 추가
                        if not e_field_clean.strip().startswith('E)'):
                            e_field_clean = 'E) ' + e_field_clean.strip()
                        original_content = e_field_clean
                
                # 카테고리 마커 제거 (예: ◼ APPROACH LIGHT, ◼ OBSTRUCTION)
                original_content = self.compiled_e_field_cleanup_patterns['category_marker'].sub('', original_content).strip()
                e_field_content = self.compiled_e_field_cleanup_patterns['category_marker'].sub('', e_field_content).strip()
                
                self.logger.debug(f"원문 추출 - NOTAM: {parsed_notam.get('notam_number')}, 원본 길이: {len(section)}, 추출된 길이: {len(original_content)}")
                styled_original = apply_color_styles(original_content)
                # styled_original에서도 카테고리 마커 제거 (HTML 태그, 마크다운 스타일 등 모든 경우 처리)
                # 더 강력한 패턴: ◼ 또는 ■ 뒤에 오는 모든 문자(HTML 태그, 마크다운 포함) 제거
                styled_original = re.sub(r'[◼■]\s*[^\n]*(?:\n|$)', '', styled_original, flags=re.MULTILINE)
                # HTML 태그 내부에 있을 수 있는 경우도 처리 (예: <span>■ TAXIWAY</span>)
                styled_original = re.sub(r'<[^>]*>[◼■]\s*[^<]*</[^>]*>', '', styled_original, flags=re.MULTILINE)
                # 마크다운 스타일 제거 (예: **■ TAXIWAY**)
                styled_original = re.sub(r'\*+\s*[◼■]\s*[^\n*]+\*+', '', styled_original, flags=re.MULTILINE)
                styled_original = styled_original.strip()
                
                description_content = e_field_content if e_field_content else original_content
                styled_description = apply_color_styles(description_content)
                # styled_description에서도 카테고리 마커 제거
                styled_description = re.sub(r'[◼■]\s*[^\n]*(?:\n|$)', '', styled_description, flags=re.MULTILINE)
                styled_description = re.sub(r'<[^>]*>[◼■]\s*[^<]*</[^>]*>', '', styled_description, flags=re.MULTILINE)
                styled_description = re.sub(r'\*+\s*[◼■]\s*[^\n*]+\*+', '', styled_description, flags=re.MULTILINE)
                styled_description = styled_description.strip()
                
                # NOTAM 카테고리 분석
                category = analyze_notam_category(original_content, parsed_notam.get('q_code'))
                category_info = NOTAM_CATEGORIES.get(category, {
                    'icon': '📄',
                    'color': '#6c757d',
                    'bg_color': '#e9ecef'
                })
                
                # 번역은 나중에 배치로 처리 (성능 최적화)
                korean_translation = "번역 준비 중..."
                english_translation = "Translation pending..."
                
                raw_notam_number = parsed_notam.get('notam_number', 'Unknown')
                display_notam_number = raw_notam_number
                if airport_code and raw_notam_number:
                    airport_code_upper = airport_code.upper()
                    if not raw_notam_number.upper().startswith(airport_code_upper):
                        display_notam_number = f"{airport_code_upper} {raw_notam_number}"

                notam_dict = {
                    'id': parsed_notam.get('notam_number', 'Unknown'),
                    'notam_number': raw_notam_number,
                    'notam_number_display': display_notam_number,
                    'notam_number_raw': raw_notam_number,
                    'airport_code': parsed_notam.get('airport_code'),
                    'effective_time': parsed_notam.get('effective_time', ''),
                    'expiry_time': parsed_notam.get('expiry_time', ''),
                    'description': styled_description,
                    'original_text': styled_original,
                    'd_field': parsed_notam.get('d_field', ''),
                    'e_field': description_content,  # e_field 추가
                    'f_field': parsed_notam.get('f_field', ''),  # F) 필드 (고도 하한)
                    'g_field': parsed_notam.get('g_field', ''),  # G) 필드 (고도 상한)
                    'comment_field': parsed_notam.get('comment_field', ''),  # COMMENT) 필드
                    'category': category,
                    'category_icon': category_info['icon'],
                    'category_color': category_info['color'],
                    'category_bg_color': category_info['bg_color'],
                    'korean_translation': korean_translation,
                    'english_translation': english_translation,
                    'local_time_ranges': []
                }
                
                # UFN을 포함한 모든 시간 정보에 대해 local_time_display 생성
                if parsed_notam.get('effective_time') and (parsed_notam.get('expiry_time') or parsed_notam.get('expiry_time') == 'UFN'):
                    local_time_display, local_time_ranges = self._generate_local_time_display(parsed_notam)
                    if local_time_display:
                        notam_dict['local_time_display'] = local_time_display
                        if local_time_ranges:
                            notam_dict['local_time_ranges'] = local_time_ranges
                        # 원본 텍스트에는 로컬 시간 추가하지 않음 (별도 필드로 관리)

                filtered_notams.append(notam_dict)
            else:
                self.logger.debug(f"패키지 섹션 {i+1}: 공항 코드를 찾을 수 없음 (섹션 시작: {section[:100]}...)")

        # 패키지 타입 감지 및 공항 순서 정렬
        package_type = self._detect_package_type(text)
        if package_type:
            self.logger.debug(f"패키지 타입 감지: {package_type}")
            # 공항 순서에 따라 정렬
            filtered_notams.sort(key=lambda x: self._get_airport_priority(x.get('airport_code', ''), package_type))
            self.logger.debug(f"패키지별 공항 순서로 정렬 완료: {package_type}")
            
            # 정렬 후 순서 로깅 (DEBUG 레벨로)
            self.logger.debug("=== 패키지별 공항 순서로 정렬된 NOTAM ===")
            for i, notam in enumerate(filtered_notams[:10], 1):  # 첫 10개만 로깅
                airport = notam.get('airport_code', 'N/A')
                notam_num = notam.get('notam_number', 'N/A')
                priority = self._get_airport_priority(airport, package_type)
                self.logger.debug(f"정렬 후 {i}: {airport} {notam_num} (우선순위: {priority})")
        else:
            self.logger.debug("패키지 타입을 감지할 수 없음 - 원본 순서 유지")
        
        self.logger.debug(f"패키지 NOTAM 최종 {len(filtered_notams)}개의 NOTAM 추출 완료")
        return filtered_notams

    def extract_package_airports(self, text, all_airports):
        """PDF 텍스트에서 Package별 공항 정보를 추출하고 순서를 동적으로 설정"""
        import re
        
        package_airports = {}
        
        # Package 1 정보 추출 - DEP, DEST, ALTN 라인에서 공항 코드 추출
        package1_airports = []
        
        # DEP/DEST/ALTN이 한 줄에 있을 수 있으므로 더 유연한 패턴 사용
        # 예: "DEP: RKSI DEST: LPPT ALTN: LPFR SECY"
        dep_dest_altn_line = re.search(r'DEP:\s*([A-Z]{4}).*?DEST:\s*([A-Z]{4}).*?ALTN:\s*([A-Z\s]+?)(?=\s+SECY|\s+ERA|\n|$)', text, re.DOTALL)
        
        if dep_dest_altn_line:
            # 한 줄에 모두 있는 경우
            dep_code = dep_dest_altn_line.group(1)
            dest_code = dep_dest_altn_line.group(2)
            altn_text = dep_dest_altn_line.group(3)
            package1_airports.append(dep_code)
            package1_airports.append(dest_code)
            altn_airports = re.findall(r'[A-Z]{4}', altn_text)
            package1_airports.extend(altn_airports)
        else:
            # 개별적으로 찾기
            # DEP 라인에서 공항 코드 추출
            dep_match = re.search(r'DEP:\s*([A-Z]{4})', text)
            if dep_match:
                package1_airports.append(dep_match.group(1))
            
            # DEST 라인에서 공항 코드 추출
            dest_match = re.search(r'DEST:\s*([A-Z]{4})', text)
            if dest_match:
                package1_airports.append(dest_match.group(1))
            
            # ALTN 라인에서 공항 코드 추출 (여러 개 가능)
            # SECY, ERA 등 다른 키워드가 올 수 있으므로 더 넓은 패턴 사용
            altn_match = re.search(r'ALTN:\s*([A-Z\s]+?)(?=\s+SECY|\s+ERA|\n[A-Z]{2,}:\s*|\n|$)', text)
            if altn_match:
                altn_airports = re.findall(r'[A-Z]{4}', altn_match.group(1))
                package1_airports.extend(altn_airports)
        
        # 실제 존재하는 공항만 필터링 (추출한 순서 유지)
        existing_package1 = [airport for airport in package1_airports if airport in all_airports]
        
        # Package 1 정의상 포함되어야 하는 공항들 중 누락된 것 추가 (순서 유지)
        expected_package1 = ['RKSI', 'VVDN', 'VVCR']
        for airport in expected_package1:
            if airport in package1_airports and airport not in existing_package1:
                existing_package1.append(airport)
                
        if existing_package1:
            package_airports['package1'] = existing_package1
            # 동적으로 추출된 순서로 package_airport_order 업데이트
            self.package_airport_order['package1'] = existing_package1
        
        # Package 2 정보 추출 - 다양한 ERA 패턴에서 공항 코드 추출
        package2_airports = []
        
        # 다양한 ERA 패턴들 처리 (3% ERA, 5% ERA, ERA 등)
        era_patterns = [
            r'\d+%\s*ERA:\s*([A-Z\s]+?)(?=\n[A-Z]{2,}:\s*|\n=+|\n\[|$)',  # 3% ERA, 5% ERA 등
            r'ERA:\s*([A-Z\s]+?)(?=\n[A-Z]{2,}:\s*|\n=+|\n\[|$)'  # 일반 ERA
        ]
        
        for pattern in era_patterns:
            era_matches = re.findall(pattern, text, re.DOTALL)
            for era_match in era_matches:
                era_airports = re.findall(r'[A-Z]{4}', era_match)
                package2_airports.extend(era_airports)
        
        # REFILE 라인에서 공항 코드 추출 (있는 경우)
        refile_match = re.search(r'REFILE:\s*([A-Z\s]+?)(?=\n[A-Z]{2,}:\s*|\n=+|\n\[|$)', text, re.DOTALL)
        if refile_match:
            refile_airports = re.findall(r'[A-Z]{4}', refile_match.group(1))
            package2_airports.extend(refile_airports)
        
        # EDTO 라인에서 공항 코드 추출 (있는 경우)
        edto_match = re.search(r'EDTO:\s*([A-Z\s]+?)(?=\n[A-Z]{2,}:\s*|\n=+|\n\[|$)', text, re.DOTALL)
        if edto_match:
            edto_airports = re.findall(r'[A-Z]{4}', edto_match.group(1))
            package2_airports.extend(edto_airports)
        
        # 중복 제거 및 실제 존재하는 공항만 필터링 (추출한 순서 유지)
        package2_airports = list(set(package2_airports))
        existing_package2 = [airport for airport in package2_airports if airport in all_airports]
        if existing_package2:
            package_airports['package2'] = existing_package2
            # 동적으로 추출된 순서로 package_airport_order 업데이트
            self.package_airport_order['package2'] = existing_package2
        
        # Package 3 정보 추출 - FIR 라인에서 공항 코드 추출
        package3_airports = []
        
        # FIR 라인에서 공항 코드 추출
        fir_match = re.search(r'FIR:\s*([A-Z\s]+?)(?=\n[A-Z]{2,}:\s*|\n=+|\n\[|$)', text, re.DOTALL)
        if fir_match:
            fir_airports = re.findall(r'[A-Z]{4}', fir_match.group(1))
            package3_airports.extend(fir_airports)
        
        # 실제 존재하는 공항만 필터링 (추출한 순서 유지)
        existing_package3 = [airport for airport in package3_airports if airport in all_airports]
        if existing_package3:
            package_airports['package3'] = existing_package3
            # 동적으로 추출된 순서로 package_airport_order 업데이트
            self.package_airport_order['package3'] = existing_package3
        
        self.logger.debug(f"추출된 Package별 공항 (동적 순서): {package_airports}")
        self.logger.debug(f"업데이트된 package_airport_order: {self.package_airport_order}")
        return package_airports

    def _merge_package_notam_lines(self, text):
        """패키지 NOTAM 라인 병합 (pdf_to_txt_test_package.py 기반)"""
        lines = text.split('\n')
        
        # 삭제할 키워드 목록 (OCR 오류 패턴 포함)
        unwanted_keywords = [
            'â—R¼A MP', 'â—O¼B STRUCTION', 'â—G¼P S', 'â—R¼U NWAY', 'â—A¼PP ROACH', 'â—T¼A XIWAY',
            'â—N¼A VAID', 'â—D¼E PARTURE', 'â—R¼U NWAY LIGHT', 'â—A¼IP', 'â—O¼T HER'
        ]
        
        # 불필요한 키워드가 포함된 줄 삭제 (조기 종료 최적화)
        filtered_lines = []
        for line in lines:
            # 조기 종료를 위해 명시적 루프 사용
            should_filter = False
            for keyword in unwanted_keywords:
                if keyword in line:
                    should_filter = True
                    break  # 첫 번째 매칭 발견 시 즉시 종료
            if not should_filter:
                filtered_lines.append(line)
        
        merged_lines = []
        i = 0
        last_date_index = None
        pending_id_line = None
        
        # 더 정확한 패턴들
        notam_id_pattern = r'^[A-Z]{4}(?:\s+[A-Z]+(?:\s+[A-Z]+)*)?\s+\d{1,4}/\d{2}$|^[A-Z]{4}\s+[A-Z]?\d{4}/\d{2}$'
        coad_pattern = r'^[A-Z]{4}\s+COAD\d{2}/\d{2}$'  # COAD 패턴 추가
        date_line_pattern = r'^(?:\d+\.\s+)?\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*-'  # "3. " 패턴 포함
        
        while i < len(filtered_lines):
            raw_line = filtered_lines[i]
            line = raw_line.replace('\f', '').strip()

            # COAD NOTAM ID 패턴 체크
            if re.match(coad_pattern, line):
                # 다음 줄이 날짜 패턴이면 합침
                if i + 1 < len(filtered_lines) and re.match(date_line_pattern, filtered_lines[i+1].strip()):
                    next_line = filtered_lines[i+1].strip()
                    # "3. " 같은 번호 접두사 제거
                    cleaned_date_line = re.sub(r'^\d+\.\s+', '', next_line)
                    merged_lines.append(f"{cleaned_date_line} {line}")
                    last_date_index = len(merged_lines) - 1
                    i += 2
                    continue
                pending_id_line = line
                i += 1
                continue
            
            # 일반 NOTAM ID 패턴 체크
            elif re.match(notam_id_pattern, line):
                # 다음 줄이 날짜 패턴이면 합침
                if i + 1 < len(filtered_lines) and re.match(date_line_pattern, filtered_lines[i+1].strip()):
                    next_line = filtered_lines[i+1].strip()
                    # "3. " 같은 번호 접두사 제거
                    cleaned_date_line = re.sub(r'^\d+\.\s+', '', next_line)
                    merged_lines.append(f"{cleaned_date_line} {line}")
                    last_date_index = len(merged_lines) - 1
                    i += 2
                    continue
                # 직전 날짜 라인이 이미 ID를 포함하고 있다면 새 NOTAM으로 간주
                if last_date_index is not None and '/' in merged_lines[last_date_index]:
                    pending_id_line = line
                    i += 1
                    continue
                # 이전에 기록한 날짜 라인과 결합 (PDF에서 ID가 아래로 내려온 경우)
                if last_date_index is not None and 0 <= last_date_index < len(merged_lines):
                    merged_lines[last_date_index] = f"{merged_lines[last_date_index].strip()} {line}"
                    i += 1
                    continue
                pending_id_line = line
                i += 1
                continue
            
            merged_lines.append(line)
            if re.match(date_line_pattern, line):
                cleaned_line = re.sub(r'^\d+\.\s+', '', line)
                merged_lines[-1] = cleaned_line
                last_date_index = len(merged_lines) - 1
                # 대기 중인 ID가 있으면 현재 날짜 라인에 결합
                if pending_id_line:
                    merged_lines[-1] = f"{merged_lines[-1]} {pending_id_line}"
                    pending_id_line = None
            i += 1

        if pending_id_line:
            merged_lines.append(pending_id_line)
        
        merged_text = '\n'.join(merged_lines)
        return self._restore_missing_notam_letters(merged_text)

    def _split_package_notams(self, text):
        """패키지 NOTAM들을 원본 텍스트 파일의 줄 순서로 분할"""
        # 줄번호와 함께 관리하여 원본 ORDER 유지
        lines_with_index = []
        for i, line in enumerate(text.split('\n'), 1):
            if line.strip():  # 빈 줄이 아닌 경우만
                lines_with_index.append((i, line.strip()))
        
        # 패턴 정의 - 더 정확한 NOTAM 시작 패턴들
        notam_start_pattern = r'^(?:\d+\.\s+)?\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*-'
        section_start_pattern = r'^\[.*\]'
        notam_id_pattern = r'^[A-Z]{4}(?:\s+(?!COAD)[A-Z]+)?\s*\d{1,4}/\d{2}$|^[A-Z]{4}\s+[A-Z]?\d{4}/\d{2}$'
        coad_pattern = r'^[A-Z]{4}\s+COAD\d{2}/\d{2}$'  # COAD NOTAM 패턴 추가
        aip_ad_pattern = r'^\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*-\s*(?:UFN|PERM)\s+[A-Z]{4}\s+AIP\s+AD\s+\d+\.\d+'  # AIP AD 패턴 추가
        
        # 새로운 NOTAM 시작을 감지하는 더 정확한 패턴들
        new_notam_patterns = [
            # COAD 패턴들 - 숫자 접두사가 있는 형식
            r'^\d+\.\s*\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*-\s*UFN\s+[A-Z]{4}\s+COAD\d{2}/\d{2}',  # UFN 형식
            r'^\d+\.\s*\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*-\s*PERM\s+[A-Z]{4}\s+COAD\d{2}/\d{2}',  # PERM 형식  
            r'^\d+\.\s*\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*-\s*\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s+[A-Z]{4}\s+COAD\d{2}/\d{2}',  # 온전한 날짜 형식
            # 일반 NOTAM 패턴들
            r'^\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*-\s*(?:\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}|UFN|PERM)\s+[A-Z]{4}\s+[A-Z]\d{4}/\d{2}',  # 일반 NOTAM - UFN/PERM 추가
            r'^\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*-\s*(?:\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}|UFN|PERM)\s+[A-Z]{4}\s+AIP\s+SUP\s+\d+/\d{2}',  # AIP SUP
            r'^\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*-\s*(?:\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}|UFN|PERM)\s+[A-Z]{4}\s+AIP\s+AD\s+\d+\.\d+',  # AIP AD (예: AIP AD 2.9)
            r'^\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*-\s*(?:\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}|UFN|PERM)\s+[A-Z]{4}\s+Z\d{4}/\d{2}',  # Z NOTAM
            r'^\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*-\s*(?:\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}|UFN|PERM)\s+[A-Z]{4}\s+COAD\d{2}/\d{2}',  # COAD
            r'^\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*-\s*UFN\s+[A-Z]{4}\s+CHINA\s+SUP\s+\d+/\d{2}',  # CHINA SUP 패턴 추가
            r'^\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*-\s*(?:[A-Z]{3}\d{2}|UFN|PERM)\s+[A-Z]{4}\s+[A-Z]+\d+/\d{2}',  # 더 일반적인 패턴 추가
            r'^\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*-\s*\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s+[A-Z]{4}\s+[A-Z]\d{4}/\d{2}',  # 연속 날짜 패턴
        ]
        
        end_phrase_pattern = r'ANY CHANGE WILL BE NOTIFIED BY NOTAM\.'
        
        # 섹션 종료 패턴들 (더 구체적인 패턴을 먼저 배치)
        section_end_patterns = [
            r'^\[ALTN\]', r'^\[DEST\]', r'^\[EDTO\]', 
            r'^\[\d+%?\s*ERA\]',  # [3% ERA], [10% ERA] 등의 숫자가 포함된 ERA 패턴 (먼저 체크)
            r'^\[ERA\]',  # 일반 [ERA] 패턴
            r'^\[ENRT\]', r'^\[ETC\]', r'^\[INFO\]', r'^\[ROUTE\]', r'^\[WX\]',
            r'^\[FIR\]',  # FIR 섹션 종료 패턴 추가
            r'^COAD',
            r'^[A-Z]{4} COAD\d{2}/\d{2}',
            r'^[A-Z]{4}\s*$',  # 공항코드만 단독 등장
            r'^1\.\s+RUNWAY\s*:',  # "1. RUNWAY :" 패턴 추가
            r'^={4,}$'  # 4개 이상의 등호로만 구성된 줄 (NOTAM 구분선)
        ]

        notams_with_index = []
        current_notam_lines = []
        
        for line_num, line in lines_with_index:
            line = line.replace('\f', '').strip()
            if not line:
                continue
            if line.startswith('â—'):
                if current_notam_lines:
                    notam_text_to_save = '\n'.join([l[1] for l in current_notam_lines]).strip()
                    notams_with_index.append((current_notam_lines[0][0], notam_text_to_save))
                    current_notam_lines = []
                continue
            # 구분선 감지 (먼저 체크) - = 구분선만 사용
            if re.match(r'^={20,}$', line):
                if current_notam_lines:
                    notam_text = '\n'.join([l[1] for l in current_notam_lines]).strip()
                    notams_with_index.append((current_notam_lines[0][0], notam_text))
                    current_notam_lines = []
                continue  # 구분선 라인은 다음 NOTAM에 포함하지 않음
            
            # strip() 결과 캐싱 (성능 최적화)
            line_stripped = line.strip()
            
            # E 섹션 내 여부 확인 (E)로 시작하는 줄 이후의 내용은 E 섹션)
            is_in_e_section = False
            for prev_line_num, prev_line in current_notam_lines:
                if re.match(r'^E\)', prev_line):
                    is_in_e_section = True
                    break
            
            # 섹션 종료 패턴 감지 ([ALTN], "1. RUNWAY :" 등) - 조기 종료 최적화
            section_end_found = False
            for pattern in section_end_patterns:
                if re.match(pattern, line_stripped):
                    # E 섹션 내에서는 4자 대문자 단독 패턴을 무시 (MAKE, STOP 등 일반 단어)
                    if pattern == r'^[A-Z]{4}\s*$' and is_in_e_section:
                        continue  # E 섹션 내에서는 무시
                    section_end_found = True
                    break  # 첫 번째 매칭 발견 시 즉시 종료
            
            if section_end_found:
                if current_notam_lines:
                    notam_text_to_save = '\n'.join([l[1] for l in current_notam_lines]).strip()
                    notams_with_index.append((current_notam_lines[0][0], notam_text_to_save))
                    current_notam_lines = []
                continue  # 섹션 종료 라인은 다음 NOTAM에 포함하지 않음
            
            # 새로운 NOTAM 시작 감지 (더 정확한 패턴 사용) - 조기 종료 최적화
            is_new_notam = False
            for pattern in new_notam_patterns:
                if re.match(pattern, line_stripped):
                    is_new_notam = True
                    break  # 첫 번째 매칭 발견 시 즉시 종료
            
            # AIP AD 패턴도 체크 (strip() 결과 재사용)
            if not is_new_notam and re.match(aip_ad_pattern, line_stripped):
                is_new_notam = True
            
            if is_new_notam:
                # 현재 NOTAM이 있으면 저장하고 새로 시작
                if current_notam_lines:
                    notam_text_to_save = '\n'.join([l[1] for l in current_notam_lines]).strip()
                    notams_with_index.append((current_notam_lines[0][0], notam_text_to_save))
                current_notam_lines = [(line_num, line)]
            else:
                current_notam_lines.append((line_num, line))
                
            # 끝 문구 등장 시 강제 끊기
            if re.search(end_phrase_pattern, line):
                if current_notam_lines:
                    notams_with_index.append((current_notam_lines[0][0], '\n'.join([l[1] for l in current_notam_lines]).strip()))
                    current_notam_lines = []
                
        if current_notam_lines:
            notam_text_final = '\n'.join([l[1] for l in current_notam_lines]).strip()
            notams_with_index.append((current_notam_lines[0][0], notam_text_final))
        
        # 줄번호 순으로 정렬하여 원본 텍스트 순서 엄격히 유지
        notams_with_index.sort(key=lambda x: x[0])
        
        # 로깅으로 순서 확인 (디버깅용)
        self.logger.debug("=== 원본 텍스트 파일 순서로 NOTAM 정렬 ===")
        for i, (line_num, notam_text) in enumerate(notams_with_index[:10], 1):  # 첫 10개만 로깅
            if i <= 10:
                coad_match = re.search(r'COAD\d+/\d+', notam_text)
                coad_number = coad_match.group(0) if coad_match else "N/A"
                notam_type = "RKSI" if "RKSI" in notam_text else ""
                self.logger.debug(f"줄 {line_num}: NOTAM {i} -> {notam_type} {coad_number}")
            
        normalized_notams = []
        for _, notam_text in notams_with_index:
            normalized_notams.append(self._restore_missing_notam_letters(notam_text))
        return normalized_notams

    def _restore_missing_notam_letters(self, text):
        """PDF 추출 과정에서 누락된 NOTAM 식별 문자(A 등)를 복원"""
        import re

        def replacer(match):
            airport = match.group(1)
            number = match.group(2)
            if number and number[0].isalpha():
                return match.group(0)
            # 기본값: A (Aerodrome). 필요 시 규칙 확장 가능.
            return f"{airport} A{number}"

        return re.sub(r'\b([A-Z]{4})\s+([A-Z]?\d{4}/\d{2})\b', replacer, text)
    
# 사용되지 않는 배치 번역 관련 메서드 제거됨 (integrated_translator에서 처리)