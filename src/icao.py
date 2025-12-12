import csv
import os
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

# API 기반 시간대 시스템 import
try:
    from timezone_api import get_utc_offset_api
    API_AVAILABLE = True
except ImportError:
    try:
        from .timezone_api import get_utc_offset_api
        API_AVAILABLE = True
    except ImportError:
        API_AVAILABLE = False

# CSV 파일에서 공항 시간대 정보 로드
_airport_timezones = {}
_csv_loaded = False

def _load_airport_timezones():
    """CSV 파일에서 공항 시간대 정보를 로드"""
    global _airport_timezones, _csv_loaded
    
    if _csv_loaded:
        return
    
    # 실제 CSV 파일 경로 설정
    csv_path = os.path.join(os.path.dirname(__file__), 'airports_timezones.csv')
    
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                icao_code = row.get('ident', '').upper()
                timezone = row.get('time_zone', '')
                if icao_code and timezone:
                    _airport_timezones[icao_code] = timezone
        _csv_loaded = True
        logger.debug(f"공항 시간대 정보 로드 완료: {len(_airport_timezones)}개 공항")
    except Exception as e:
        logger.debug(f"공항 시간대 CSV 로드 오류: {e}")
        _csv_loaded = True  # 오류가 나도 다시 시도하지 않도록

def get_utc_offset(icao_code, use_api=True):
    """
    ICAO 공항 코드의 UTC 시간대를 반환합니다.
    
    우선순위:
    1. API 기반 실시간 조회 (DST 자동 적용)
    2. FIR 패턴 기반 계산
    3. CSV 파일 조회
    4. 기본값 폴백
    
    Args:
        icao_code (str): ICAO 공항 코드 (예: KSEA, RJTT, RKSI)
        use_api (bool): API 사용 여부 (기본값: True)
        
    Returns:
        str: UTC 시간대 (예: UTC+9, UTC-4)
    """
    if not icao_code or len(icao_code) < 2:
        return "UTC+0"
    
    icao_upper = icao_code.upper()
    
    # 1단계: API 기반 실시간 조회 (최우선)
    if use_api and API_AVAILABLE:
        try:
            api_result = get_utc_offset_api(icao_upper)
            if api_result and api_result != "UTC+0":
                logger.debug(f"API로 {icao_upper} 시간대 계산: {api_result}")
                return api_result
        except Exception as e:
            logger.debug(f"API 조회 실패, 폴백 사용: {e}")
    
    # 2단계: FIR 패턴 기반 정확한 시간대 계산
    fir_timezone = get_timezone_by_fir_pattern(icao_upper)
    if fir_timezone != "UTC+0":  # 기본값이 아닌 경우
        logger.debug(f"FIR 패턴으로 {icao_upper} 시간대 계산: {fir_timezone}")
        return fir_timezone
    
    # 3단계: CSV 파일에서 정확한 매칭 시도
    _load_airport_timezones()
    if icao_upper in _airport_timezones:
        result = _airport_timezones[icao_upper]
        logger.debug(f"CSV에서 {icao_upper} 찾음: {result}")
        return result
    
    logger.debug(f"CSV에서 {icao_upper} 찾지 못함, 기본 로직 사용")
    
    # 4단계: 기존 ICAO 첫 글자 기반 매핑 (마지막 수단)
    first_letter = icao_upper[0]
    
    # ICAO 지역 코드별 UTC 시간대 매핑 (기본값)
    utc_offsets = {
        'A': 'UTC+2',  # 남서 아시아
        'B': 'UTC+3',  # 중동
        'C': 'UTC+4',  # 중동
        'D': 'UTC+5',  # 남아시아
        'E': 'UTC+6',  # 남아시아
        'F': 'UTC+7',  # 동남아시아
        'G': 'UTC+8',  # 동남아시아
        'H': 'UTC+9',  # 동아시아
        'I': 'UTC+10', # 오세아니아
        'J': 'UTC+11', # 오세아니아
        'K': 'UTC-5',  # 북미
        'L': 'UTC+1',  # 유럽
        'M': 'UTC+12', # 오세아니아
        'N': 'UTC+12', # 오세아니아
        'O': 'UTC+3',  # 중동
        'P': 'UTC-9',  # 알래스카
        'R': 'UTC+9',  # 동아시아 (한국)
        'S': 'UTC-3',  # 남미
        'T': 'UTC-4',  # 카리브해
        'U': 'UTC+3',  # 러시아
        'V': 'UTC+5',  # 남아시아
        'W': 'UTC+7',  # 동남아시아
        'Y': 'UTC+10', # 오스트레일리아
        'Z': 'UTC+8'   # 중국
    }
    
    return utc_offsets.get(first_letter, 'UTC+0')

def get_timezone_by_fir_pattern(icao_code):
    """
    ICAO 코드의 FIR 패턴으로 정확한 시간대 자동 계산 (일광절약시간 적용)
    
    Args:
        icao_code (str): ICAO 공항 코드 (4자리)
        
    Returns:
        str: UTC 시간대 (예: UTC+9, 일광절약시간 적용된 UTC-4)
    """
    if len(icao_code) < 2:
        return "UTC+0"
    
    # 첫 2글자로 FIR 지역 식별
    fir_prefix = icao_code[:2]
    
    # 현재 날짜 정보
    now = datetime.now()
    current_month = now.month
    current_day = now.day
    
    # 일광절약시간 적용 여부 판단 함수
    def is_dst_active():
        # 3월 둘째 일요일 ~ 11월 첫째 일요일 (미국/캐나다)
        # 3월 마지막 일요일 ~ 10월 마지막 일요일 (유럽)
        # 간단히 3월~10월을 DST 기간으로 설정 (근사치)
        return 3 <= current_month <= 10
    
    dst_active = is_dst_active()
    
    # 동아시아 FIR 매핑 (R으로 시작) - DST 미적용 지역
    if fir_prefix == 'RK':      # 한국 FIR
        return "UTC+9"
    elif fir_prefix == 'RJ':    # 일본 FIR
        return "UTC+9"
    elif fir_prefix == 'RC':    # 대만 FIR
        return "UTC+8"
    elif fir_prefix == 'RP':    # 필리핀 FIR
        return "UTC+8"
    elif fir_prefix == 'RO':    # 오키나와 FIR
        return "UTC+9"
    
    # 중국 FIR 매핑 (Z로 시작)
    elif fir_prefix == 'ZB':    # 베이징 FIR
        return "UTC+8"
    elif fir_prefix == 'ZS':    # 상하이 FIR
        return "UTC+8"
    elif fir_prefix == 'ZG':    # 광저우 FIR
        return "UTC+8"
    elif fir_prefix == 'ZU':    # 우루무치 FIR
        return "UTC+8"
    elif fir_prefix == 'ZY':    # 선양 FIR
        return "UTC+8"
    elif fir_prefix == 'ZW':    # 우한 FIR
        return "UTC+8"
    elif fir_prefix == 'ZL':    # 란저우 FIR
        return "UTC+8"
    
    # 동남아시아 FIR 매핑 (V로 시작)
    elif fir_prefix == 'VH':    # 홍콩 FIR
        return "UTC+8"
    elif fir_prefix == 'VT':    # 태국 FIR
        return "UTC+7"
    elif fir_prefix == 'VV':    # 베트남 FIR
        return "UTC+7"
    elif fir_prefix == 'VM':    # 말레이시아 FIR
        return "UTC+8"
    elif fir_prefix == 'WI':    # 인도네시아 FIR (서부)
        return "UTC+7"
    elif fir_prefix == 'WA':    # 인도네시아 FIR (중부)
        return "UTC+8"
    elif fir_prefix == 'WB':    # 인도네시아 FIR (동부)
        return "UTC+9"
    elif fir_prefix == 'WS':    # 싱가포르 FIR
        return "UTC+8"
    
    # 미국 FIR 매핑 (K로 시작) - DST 적용
    elif fir_prefix == 'KS':    # 서부 (시애틀, 샌프란시스코)
        return "UTC-7" if dst_active else "UTC-8"  # PDT/PST
    elif fir_prefix == 'KL':    # 서부 (로스앤젤레스)
        return "UTC-7" if dst_active else "UTC-8"  # PDT/PST
    elif fir_prefix == 'KD':    # 중부 (덴버)
        return "UTC-6" if dst_active else "UTC-7"  # MDT/MST
    elif fir_prefix == 'KC':    # 중부 (시카고)
        return "UTC-5" if dst_active else "UTC-6"  # CDT/CST
    elif fir_prefix == 'KN' or fir_prefix == 'KJ' or fir_prefix == 'KE':  # 동부
        return "UTC-4" if dst_active else "UTC-5"  # EDT/EST
    elif fir_prefix == 'KM':    # 알래스카
        return "UTC-8" if dst_active else "UTC-9"  # AKDT/AKST
    elif fir_prefix == 'PH':    # 하와이 (DST 미적용)
        return "UTC-10" # HST
    
    # 캐나다 FIR 매핑 (C로 시작) - DST 적용
    elif fir_prefix == 'CY':    # 캐나다 동부
        return "UTC-4" if dst_active else "UTC-5"  # EDT/EST
    elif fir_prefix == 'CZ':    # 캐나다 서부
        return "UTC-7" if dst_active else "UTC-8"  # PDT/PST
    
    # 유럽 FIR 매핑 (E, L로 시작) - DST 적용
    elif fir_prefix == 'EG':    # 영국
        return "UTC+1" if dst_active else "UTC+0"  # BST/GMT
    elif fir_prefix == 'ED':    # 독일
        return "UTC+2" if dst_active else "UTC+1"  # CEST/CET
    elif fir_prefix == 'EF':    # 프랑스
        return "UTC+2" if dst_active else "UTC+1"  # CEST/CET
    elif fir_prefix == 'LF':    # 프랑스
        return "UTC+2" if dst_active else "UTC+1"  # CEST/CET
    elif fir_prefix == 'LE':    # 스페인
        return "UTC+2" if dst_active else "UTC+1"  # CEST/CET
    elif fir_prefix == 'LI':    # 이탈리아
        return "UTC+2" if dst_active else "UTC+1"  # CEST/CET
    
    # 호주/오세아니아 FIR 매핑 (Y로 시작) - 남반구 DST (10월~3월)
    elif fir_prefix == 'YS':    # 호주 동부
        # 남반구는 10-3월이 여름 (DST 적용)
        aus_dst = current_month >= 10 or current_month <= 3
        return "UTC+11" if aus_dst else "UTC+10"  # AEDT/AEST
    elif fir_prefix == 'YP':    # 호주 서부 (DST 미적용)
        return "UTC+8"  # AWST
    elif fir_prefix == 'YC':    # 호주 중부
        aus_dst = current_month >= 10 or current_month <= 3
        return "UTC+10.5" if aus_dst else "UTC+9.5"  # ACDT/ACST
    
    # 기타 주요 FIR
    elif fir_prefix == 'OM':    # 중동 (UAE, 카타르 등)
        return "UTC+4"
    elif fir_prefix == 'OE':    # 사우디아라비아
        return "UTC+3"
    elif fir_prefix == 'LT':    # 터키
        return "UTC+3"
    elif fir_prefix == 'UR':    # 러시아 서부
        return "UTC+3"
    elif fir_prefix == 'UH':    # 러시아 동부
        return "UTC+8"
    
    # 패턴 매칭 실패시 기본값
    return "UTC+0"