import requests
import json
import os
import csv
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import logging

# 로깅 설정
logger = logging.getLogger(__name__)

class TimezoneAPI:
    """
    API 기반 시간대 계산 시스템
    ICAO 코드 -> 좌표 -> 실시간 시간대 정보 (DST 자동 적용)
    """
    
    def __init__(self):
        self.cache = {}  # 키: ICAO -> { data, timestamp }
        self.cache_tzid = {}  # 키: ICAO -> { tzid, timestamp }
        self.timeout = 8  # 각 외부 호출 타임아웃 (초)
        self.csv_airports = self._load_local_airports()
        self.csv_timezones = self._load_timezone_csv()  # airports_timezones.csv 로드
        
    def get_timezone_by_icao(self, icao_code):
        """
        ICAO 코드로 실시간 시간대 정보 조회
        
        Args:
            icao_code (str): ICAO 공항 코드
            
        Returns:
            dict: {
                'timezone_id': 'America/New_York',
                'utc_offset': '-04:00',
                'utc_offset_seconds': -14400,
                'dst_active': True,
                'current_time': '2024-09-23T12:00:00'
            }
        """
        if not icao_code or len(icao_code) != 4:
            return self._get_default_timezone()
            
        icao_upper = icao_code.upper()
        
        # 캐시 확인
        if icao_upper in self.cache:
            cached_data = self.cache[icao_upper]
            # 캐시가 1시간 이내라면 재사용
            if datetime.now().timestamp() - cached_data['timestamp'] < 3600:
                logger.info(f"캐시에서 {icao_upper} 시간대 정보 조회")
                return cached_data['data']
        
        try:
            # 1단계: IANA 타임존 ID 해석 (로컬 CSV/정적맵 우선)
            tzid = self.get_timezone_id_by_icao(icao_upper)
            if tzid:
                # 현재 시점 기준의 요약 정보 구성
                now_utc = datetime.now(timezone.utc)
                try:
                    zi = ZoneInfo(tzid)
                    local = now_utc.astimezone(zi)
                    offset = local.utcoffset() or local.fold and local.utcoffset() or None
                    if offset is None:
                        raise Exception('Failed to compute utcoffset')
                    seconds = int(offset.total_seconds())
                    utc_offset_str = self._format_offset_str(seconds)
                    data = {
                        'timezone_id': tzid,
                        'utc_offset': utc_offset_str,
                        'utc_offset_seconds': seconds,
                        'dst_active': bool(local.dst() and local.dst().total_seconds() != 0),
                        'current_time': local.isoformat(),
                        'coordinates': self._get_coordinates_by_icao(icao_upper)
                    }
                    # 캐시 저장
                    self.cache[icao_upper] = { 'data': data, 'timestamp': datetime.now().timestamp() }
                    return data
                except Exception:
                    # zoneinfo 실패 시 WorldTimeAPI 폴백 시도
                    wt = self._get_timezone_by_worldtimeapi(tzid)
                    if wt:
                        self.cache[icao_upper] = { 'data': wt, 'timestamp': datetime.now().timestamp() }
                        return wt
                    # 마지막 폴백: 좌표 기반 TimeAPI.io (기존 경로)
            
            coordinates = self._get_coordinates_by_icao(icao_upper)
            if not coordinates:
                logger.warning(f"{icao_upper} 좌표 조회 실패, 기본값 사용")
                return self._get_default_timezone()

            timezone_info = self._get_timezone_by_coordinates(coordinates['lat'], coordinates['lon'])
            if not timezone_info:
                logger.warning(f"{icao_upper} 시간대 조회 실패, 기본값 사용")
                return self._get_default_timezone()

            self.cache[icao_upper] = { 'data': timezone_info, 'timestamp': datetime.now().timestamp() }
            return timezone_info

        except Exception as e:
            logger.error(f"{icao_upper} API 조회 중 오류: {e}")
            return self._get_default_timezone()

    def get_timezone_id_by_icao(self, icao_code, allow_remote: bool = True):
        """ICAO 코드로 IANA timezone ID 획득 (캐시/로컬/원격 폴백)

        allow_remote=False이면 원격 호출(TimeAPI.io, Nominatim, WorldTimeAPI)을 사용하지 않음.
        """
        if not icao_code:
            return None
        icao_upper = icao_code.upper()

        # 캐시 우선
        cached = self.cache_tzid.get(icao_upper)
        if cached and (datetime.now().timestamp() - cached['timestamp'] < 86400 * 7):  # 7일 TTL
            return cached['tzid']

        # FIR 코드 직접 처리 (CSV에 없는 경우)
        fir_tzid = self._get_fir_timezone_id(icao_upper)
        if fir_tzid:
            self.cache_tzid[icao_upper] = { 'tzid': fir_tzid, 'timestamp': datetime.now().timestamp() }
            return fir_tzid

        # airports_timezones.csv에서 UTC 오프셋 조회 → IANA timezone ID로 변환
        if icao_upper in self.csv_timezones:
            utc_offset_str = self.csv_timezones[icao_upper]
            tzid = self._utc_offset_to_tzid(icao_upper, utc_offset_str)
            if tzid:
                self.cache_tzid[icao_upper] = { 'tzid': tzid, 'timestamp': datetime.now().timestamp() }
                return tzid

        # 로컬 CSV 좌표 → (원격 허용 시) TimeAPI.io로 tzid 조회
        coords = None
        if icao_upper in self.csv_airports:
            coords = self.csv_airports[icao_upper]
        elif allow_remote:
            coords = self._get_coordinates_by_icao(icao_upper)

        if coords and allow_remote:
            tzid = self._resolve_timezone_id_by_coordinates(coords['lat'], coords['lon'])
            if tzid:
                self.cache_tzid[icao_upper] = { 'tzid': tzid, 'timestamp': datetime.now().timestamp() }
                return tzid
        return None
    
    def _load_local_airports(self):
        """src/airports.csv에서 ICAO->(lat,lon) 맵을 로드"""
        mapping = {}
        try:
            base_dir = os.path.dirname(__file__)
            csv_path = os.path.join(base_dir, 'airports.csv')
            if os.path.exists(csv_path):
                with open(csv_path, 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        ident = (row.get('ident') or '').strip().upper()
                        if len(ident) == 4:
                            try:
                                lat = float(row.get('latitude_deg'))
                                lon = float(row.get('longitude_deg'))
                                mapping[ident] = {'lat': lat, 'lon': lon}
                            except Exception:
                                continue
        except Exception as e:
            logger.error(f"로컬 공항 CSV 로드 오류: {e}")
        return mapping
    
    def _load_timezone_csv(self):
        """src/airports_timezones.csv에서 ICAO->timezone 맵을 로드"""
        mapping = {}
        try:
            base_dir = os.path.dirname(__file__)
            csv_path = os.path.join(base_dir, 'airports_timezones.csv')
            if os.path.exists(csv_path):
                with open(csv_path, 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        ident_raw = row.get('ident')
                        time_zone_raw = row.get('time_zone')
                        if ident_raw and time_zone_raw:
                            ident = ident_raw.strip().upper()
                            time_zone = time_zone_raw.strip()
                            if len(ident) == 4 and time_zone:
                                mapping[ident] = time_zone
        except Exception as e:
            logger.error(f"타임존 CSV 로드 오류: {e}")
        return mapping
    
    def _get_fir_timezone_id(self, icao_code):
        """FIR 코드에 대한 IANA timezone ID 반환"""
        fir_timezone_map = {
            # 한국
            'RKRR': 'Asia/Seoul',
            
            # 일본
            'RJJJ': 'Asia/Tokyo',
            
            # 미국
            'KZAK': 'America/Los_Angeles',  # Oakland Oceanic FIR (PST)
            
            # 파푸아뉴기니
            'AYPM': 'Pacific/Port_Moresby',  # Port Moresby FIR
            
            # 오스트레일리아
            'YBBB': 'Australia/Brisbane',  # Brisbane FIR
        }
        return fir_timezone_map.get(icao_code)
    
    def _utc_offset_to_tzid(self, icao_code, utc_offset_str):
        """UTC 오프셋 문자열(예: "UTC+9")을 IANA timezone ID로 변환"""
        if not utc_offset_str or not utc_offset_str.startswith('UTC'):
            return None
        
        # UTC+9 -> +9 추출
        offset_sign = '+' if '+' in utc_offset_str else '-'
        offset_str = utc_offset_str.replace('UTC', '').replace('+', '').replace('-', '')
        if not offset_str:
            return None
        
        offset_key = offset_sign + offset_str
        first_letter = icao_code[0] if icao_code else ''
        prefix = icao_code[:2] if len(icao_code) >= 2 else first_letter
        
        # 공항 코드 기반 매핑 (ICAO 지역 코드 활용)
        # 한국/일본: R, RJ + UTC+9
        if offset_key == '+9':
            if prefix == 'RJ' or icao_code.startswith('RJ'):
                return 'Asia/Tokyo'
            elif first_letter == 'R':
                return 'Asia/Seoul'
        
        # 중국: Z + UTC+8
        if offset_key == '+8' and first_letter == 'Z':
            return 'Asia/Shanghai'
        
        # 오스트레일리아: Y + UTC+10 or UTC+9
        if offset_key == '+10' and first_letter == 'Y':
            return 'Australia/Sydney'
        if offset_key == '+9' and first_letter == 'Y':
            return 'Australia/Adelaide'
        
        # 태평양: P + UTC+10
        if offset_key == '+10' and first_letter == 'P':
            return 'Pacific/Guam'
        if offset_key == '-9' and first_letter == 'P':
            return 'America/Anchorage'
        
        # 미국: K + UTC-5/-6/-8
        if offset_key == '-5' and first_letter == 'K':
            return 'America/New_York'
        if offset_key == '-8' and first_letter == 'K':
            return 'America/Los_Angeles'
        if offset_key == '-6' and first_letter == 'K':
            return 'America/Chicago'
        
        # 유럽: L, E + UTC+1
        if offset_key == '+1' and first_letter in ['L', 'E']:
            return 'Europe/Paris' if first_letter == 'L' else 'Europe/Berlin'
        
        # 러시아: U + UTC+3
        if offset_key == '+3' and first_letter == 'U':
            return 'Europe/Moscow'
        
        # 투르크메니스탄 지역(UT**) + UTC+5
        if offset_key == '+5' and prefix == 'UT':
            return 'Asia/Ashgabat'
        
        # 폴백: 오프셋만으로 대략적인 매핑
        fallback_map = {
            '+9': 'Asia/Seoul',
            '+10': 'Australia/Sydney',
            '+8': 'Asia/Shanghai',
            '-5': 'America/New_York',
            '-8': 'America/Los_Angeles',
        }
        return fallback_map.get(offset_key, None)

    def _get_coordinates_by_icao(self, icao_code):
        """로컬 CSV 우선 사용, 없으면 Nominatim으로 폴백"""
        try:
            if icao_code in self.csv_airports:
                return self.csv_airports[icao_code]

            # 최후 폴백: Nominatim
            url = 'https://nominatim.openstreetmap.org/search'
            params = {'q': f'{icao_code} airport', 'format': 'json', 'limit': 1}
            headers = {'User-Agent': 'SmartBrief/1.0 (timezone lookup)'}
            response = requests.get(url, params=params, headers=headers, timeout=self.timeout)
            if response.status_code == 200:
                data = response.json()
                if data:
                    result = data[0]
                    return {'lat': float(result['lat']), 'lon': float(result['lon']), 'display_name': result['display_name']}
            return None
        except Exception as e:
            logger.error(f"좌표 조회 오류: {e}")
            return None
    
    def _get_timezone_by_coordinates(self, lat, lon):
        """
        TimeAPI.io로 좌표의 시간대 정보 조회
        """
        try:
            url = f'https://timeapi.io/api/TimeZone/coordinate'
            params = {
                'latitude': lat,
                'longitude': lon
            }
            
            response = requests.get(url, params=params, timeout=self.timeout)
            if response.status_code == 200:
                data = response.json()
                
                # UTC 오프셋 계산
                utc_offset_obj = data.get('currentUtcOffset', {})
                utc_offset_seconds = utc_offset_obj.get('seconds', 0)
                
                # 시간대 형식 변환
                hours = utc_offset_seconds // 3600
                minutes = abs(utc_offset_seconds % 3600) // 60
                utc_offset_str = f"UTC{hours:+d}" if minutes == 0 else f"UTC{hours:+d}:{minutes:02d}"
                
                # DST 활성 여부 판단 (표준시간과 현재시간 비교)
                standard_offset = data.get('standardUtcOffset', {}).get('seconds', 0)
                dst_active = utc_offset_seconds != standard_offset
                
                return {
                    'timezone_id': data.get('timeZone', 'UTC'),
                    'utc_offset': utc_offset_str,
                    'utc_offset_seconds': utc_offset_seconds,
                    'dst_active': dst_active,
                    'current_time': data.get('currentLocalTime', ''),
                    'coordinates': {'lat': lat, 'lon': lon}
                }
            return None
            
        except Exception as e:
            logger.error(f"시간대 조회 오류: {e}")
            return None

    def _resolve_timezone_id_by_coordinates(self, lat, lon):
        """TimeAPI.io로부터 IANA tzid만 추출"""
        try:
            url = 'https://timeapi.io/api/TimeZone/coordinate'
            params = {'latitude': lat, 'longitude': lon}
            resp = requests.get(url, params=params, timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json()
                return data.get('timeZone')
        except Exception as e:
            logger.error(f"tzid 조회 오류: {e}")
        return None

    def _get_timezone_by_worldtimeapi(self, timezone_id):
        """WorldTimeAPI로 현재 시점 시간대 정보 조회 (현재 시점 전용)"""
        try:
            url = f'https://worldtimeapi.org/api/timezone/{timezone_id}'
            resp = requests.get(url, timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json()
                utc_offset = data.get('utc_offset', '+00:00')
                # "+09:00" 형태에서 초 계산
                sign = 1 if utc_offset.startswith('+') else -1
                hh = int(utc_offset[1:3]); mm = int(utc_offset[4:6])
                seconds = sign * (hh * 3600 + mm * 60)
                return {
                    'timezone_id': data.get('timezone', timezone_id),
                    'utc_offset': utc_offset,
                    'utc_offset_seconds': seconds,
                    'dst_active': bool(data.get('dst', False)),
                    'current_time': data.get('datetime'),
                    'coordinates': None
                }
        except Exception as e:
            logger.error(f"WorldTimeAPI 조회 오류: {e}")
        return None

    def _format_offset_str(self, offset_seconds: int) -> str:
        sign = '+' if offset_seconds >= 0 else '-'
        total = abs(offset_seconds)
        h, r = divmod(total, 3600)
        m = r // 60
        return f"{sign}{h:02d}:{m:02d}"

    # 새 헬퍼: 특정 UTC 시각에 대한 오프셋 계산 (zoneinfo 기반)
    def get_offset_for_datetime(self, icao_code: str, dt_utc: datetime, allow_remote: bool = True) -> str | None:
        """주어진 UTC 시각에 대해 정확한 UTC 오프셋("+HH:MM")을 반환"""
        try:
            tzid = self.get_timezone_id_by_icao(icao_code, allow_remote=allow_remote)
            if not tzid:
                return None
            if dt_utc.tzinfo is None:
                dt_utc = dt_utc.replace(tzinfo=timezone.utc)
            try:
                zi = ZoneInfo(tzid)
            except Exception as e:
                # Windows에서 tzdata가 없을 때 폴백: UTC 오프셋 문자열에서 직접 계산
                if icao_code.upper() in self.csv_timezones:
                    utc_offset_str = self.csv_timezones[icao_code.upper()]
                    # UTC+9 -> +09:00 변환
                    if utc_offset_str.startswith('UTC'):
                        offset_part = utc_offset_str.replace('UTC', '')
                        sign = '+' if '+' in offset_part or not offset_part.startswith('-') else '-'
                        offset_part = offset_part.replace('+', '').replace('-', '')
                        if offset_part:
                            try:
                                offset_hours = int(offset_part)
                                return f"{sign}{abs(offset_hours):02d}:00"
                            except ValueError:
                                pass
                logger.debug(f"ZoneInfo 로드 실패({tzid}), 폴백 사용: {e}")
                return None
            local = dt_utc.astimezone(zi)
            offset = local.utcoffset()
            if offset is None:
                return None
            return self._format_offset_str(int(offset.total_seconds()))
        except Exception as e:
            logger.error(f"오프셋 계산 오류({icao_code}): {e}")
            return None
    
    def _get_default_timezone(self):
        """
        기본 시간대 정보 반환
        """
        return {
            'timezone_id': 'UTC',
            'utc_offset': 'UTC+0',
            'utc_offset_seconds': 0,
            'dst_active': False,
            'current_time': datetime.utcnow().isoformat(),
            'coordinates': None
        }
    
    def get_simple_utc_offset(self, icao_code):
        """
        기존 호환성을 위한 간단한 UTC 오프셋 반환
        
        Args:
            icao_code (str): ICAO 공항 코드
            
        Returns:
            str: UTC 오프셋 (예: "UTC-4", "UTC+9")
        """
        timezone_info = self.get_timezone_by_icao(icao_code)
        return timezone_info['utc_offset']

# 전역 인스턴스
_timezone_api = TimezoneAPI()

def get_utc_offset_api(icao_code):
    """
    API 기반 UTC 오프셋 조회 (기존 함수와 호환)
    
    Args:
        icao_code (str): ICAO 공항 코드
        
    Returns:
        str: UTC 오프셋 (예: "UTC-4", "UTC+9")
    """
    return _timezone_api.get_simple_utc_offset(icao_code)

def get_timezone_info_api(icao_code):
    """
    API 기반 상세 시간대 정보 조회
    
    Args:
        icao_code (str): ICAO 공항 코드
        
    Returns:
        dict: 상세 시간대 정보
    """
    return _timezone_api.get_timezone_by_icao(icao_code)