"""
AI 항로 분석 모듈 - GEMINI를 사용한 NOTAM 분석

주요 기능:
1. 항로에서 공항, 웨이포인트, 항로 코드, FIR 코드 추출
2. 좌표 형식의 waypoint 자동 감지 (N17E139, 17N139E 등)
3. KZAK FIR 경계 내 좌표 자동 확인
4. KZAK FIR 교차 시 관련 NOTAM 우선 분석
5. AI 기반 NOTAM 브리핑 자료 생성

사용 예시:
- analyzer = AIRouteAnalyzer()
- result = analyzer.analyze_route(route, notam_data)
- debug_info = analyzer.debug_route_extraction(route)
"""

import os
import re
import logging
import json
import time
from datetime import datetime

# .env 로드 (가능한 경우)
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    pass
from typing import Optional, List, Tuple, Dict, Any
from fir_reference import get_fir_name, get_fir_info, is_oceanic_fir, get_package3_fir_codes, validate_fir_code
from fir_geo_reference import fir_geo_reference
from nav_data_loader import nav_data_loader

logger = logging.getLogger(__name__)

# Rate Limiter: Gemini API 분당 호출 제한 관리
_last_api_call_time = 0
_min_api_interval = 3  # 최소 3초 간격으로 API 호출


class AIRouteAnalyzer:
    """AI 기반 항로 분석 클래스"""
    
    def __init__(self):
        self.api_key = os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
        if not self.api_key:
            logger.warning("GEMINI API 키가 설정되지 않았습니다.")
        
        # FIR/Waypoint 참조 데이터 (Lazy initialization)
        # 실제 사용 시점에만 초기화되도록 지연
        self._fir_geo = None
        self._navdata = None
    
    def _get_fir_geo(self):
        """FIR GeoJSON 레퍼런스 가져오기 (lazy)"""
        if self._fir_geo is None:
            from fir_geo_reference import get_fir_geo_reference
            self._fir_geo = get_fir_geo_reference()
            if self._fir_geo is None:
                logger.warning("FIR GeoJSON 레퍼런스를 초기화하지 못했습니다. FIR 추적 기능이 제한될 수 있습니다.")
        return self._fir_geo
    
    def _get_navdata(self):
        """NavData 로더 가져오기 (lazy)"""
        if self._navdata is None:
            from nav_data_loader import get_nav_data_loader
            self._navdata = get_nav_data_loader()
            if self._navdata and getattr(self._navdata, "load_nav_data", None):
                try:
                    self._navdata.load_nav_data()
                except Exception as exc:
                    logger.warning("NavData 로드를 초기화하는 중 경고: %s", exc)
            elif self._navdata is None:
                logger.warning("NavData 로더를 사용할 수 없습니다. 항로 좌표 해석 기능이 제한됩니다.")
        return self._navdata
    
    # FIR별 운영 정보 힌트 저장 (Package3 원문 기반)
    _fir_ops_hints: Dict[str, List[str]] = {}
    
    def analyze_route(self, route: str, notam_data: list, **kwargs) -> str:
        """
        항로 분석 메인 함수
        
        Args:
            route: 분석할 항로
            notam_data: NOTAM 데이터 리스트
            **kwargs: 추가 옵션들 (dep, dest, altn, flight_details 등)
        
        Returns:
            분석 결과 문자열
        """
        try:
            import google.generativeai as genai
            
            if not self.api_key:
                return "GEMINI API 키가 설정되지 않았습니다."

            genai.configure(api_key=self.api_key)
            
            # 생성 설정 (NOTAM 분석 일관성 유지)
            generation_config = {
                "temperature": 0.2,  # NOTAM 분석은 일관성이 중요
                "top_p": 0.8,       # 적절한 토큰 선택 범위
                "top_k": 20,        # 적절한 토큰 후보 수
                "max_output_tokens": 16384,
            }
            model = genai.GenerativeModel(
                model_name='gemini-2.5-flash-lite',
                generation_config=generation_config,  # type: ignore[arg-type]
            )

            # 파라미터 추출
            dep = kwargs.get('dep')
            dest = kwargs.get('dest')
            flight_details = kwargs.get('flight_details', '')
            current_date = kwargs.get('current_date', datetime.now().strftime('%Y-%m-%d'))
            fir_order = kwargs.get('fir_order') or []

            # NOTAM 데이터에서 Package 3만 추출하여 단순화
            actual_fir_list = []  # 실제 NOTAM에 존재하는 FIR 목록
            package3_text = None  # Package 3 원본 텍스트 저장 (FIR 라인 추출용)
            try:
                if isinstance(notam_data, list) and len(notam_data) > 0 and isinstance(notam_data[0], str):
                    # 리스트의 첫 번째 요소가 문자열인 경우 (전체 NOTAM 텍스트)
                    full_notam_text = '\n'.join(notam_data)
                    package3_text = self._extract_package3_from_text(full_notam_text)
                    # Package 3 텍스트에서 실제 FIR 목록 추출
                    fir_sections = self._parse_package3_fir_sections(package3_text)
                    actual_fir_list = list(fir_sections.keys())
                    logger.info(f"📋 Package 3에서 추출된 FIR: {actual_fir_list}")
                    # FIR별 운영 정보 힌트 사전 구축
                    self._fir_ops_hints = {code: self._extract_operational_hints_from_fir_content(content)
                                           for code, content in fir_sections.items()}
                    logger.info(f"🗂️ FIR 운영 정보 힌트 구축 완료: { {k: len(v) for k,v in self._fir_ops_hints.items()} }")
                    notam_text = self._format_notam_data([package3_text])
                else:
                    # 기존 방식으로 처리
                    notam_text = self._format_notam_data(notam_data)
            except Exception as e:
                logger.error(f"❌ FIR 리스트/NOTAM 파싱 오류: {e}")
                notam_text = self._format_notam_data(notam_data)
            else:
                # 기존 방식으로 처리
                notam_text = self._format_notam_data(notam_data)

            # 항로에서 공항 추출
            airports = self._extract_airports_from_route(route)
            
            # KZAK FIR 교차 확인
            kzak_intersection = self._check_kzak_fir_intersection(route)
            if kzak_intersection['intersects_kzak']:
                logger.info(f"KZAK FIR 교차 감지: {len(kzak_intersection['kzak_coordinates'])}개 좌표")
                logger.info(f"KZAK FIR 좌표: {kzak_intersection['kzak_coordinates']}")
            
            # 공항 정보 설정
            if not dep and airports:
                try:
                    dep = airports[0]
                except Exception as e:
                    logger.warning(f"dep 인덱싱 오류: {e}")
                    dep = None
            if not dest and airports and len(airports) >= 2:
                try:
                    dest = airports[-1]
                except Exception as e:
                    logger.warning(f"dest 인덱싱 오류: {e}")
                    dest = None
            
            flight_info = flight_details if flight_details else f"항공편 {dep or 'XXXX'}/{dest or 'XXXX'}"
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M Z')
            
            # 프롬프트 생성 전, NOTAM 본문 유효성 점검 및 보강
            try:
                import re as _re_chk
                notam_chars = len(notam_text or "")
                notam_id_count = len(_re_chk.findall(r"\[[A-Z][0-9]{4}\/[0-9]{2}\]:", notam_text or ""))
                logger.info(f"🧪 NOTAM 본문 점검: chars={notam_chars}, id_count={notam_id_count}")
                # 본문이 비정상적으로 짧거나 NOTAM ID가 거의 없으면 Package 3 원문으로 보강
                if (notam_chars < 2000 or notam_id_count < 10) and package3_text:
                    logger.warning("⚠️ NOTAM 본문이 빈약하여 Package 3 원문으로 보강합니다")
                    notam_text = package3_text
            except Exception as _e_chk:
                logger.debug(f"NOTAM 본문 점검 스킵: {_e_chk}")

            # 프롬프트 생성 (실제 FIR 목록 전달)
            prompt = self._create_analysis_prompt(route, notam_text, flight_info, current_time, kzak_intersection, actual_fir_list, fir_order)
            
            # 디버깅: 프롬프트 로깅 (파일 저장은 제거)
            logger.debug(f"AI 프롬프트 길이: {len(prompt)} 문자")
            logger.info(f"🔍 프롬프트 시작 1000자:\n{prompt[:1000]}")
            
            # fir_order_info가 프롬프트에 포함되었는지 확인
            if fir_order:
                if "FIR 표시 순서(파일 기반, 절대 준수)" in prompt:
                    logger.info("✅ FIR 순서가 프롬프트에 포함되었습니다")
                else:
                    logger.error("❌ FIR 순서가 프롬프트에 포함되지 않았습니다!")

            # Dry-run: 모델 호출 없이 FIR 블록 뼈대만 생성해 필터/정렬 검증
            if kwargs.get('dry_run_validate_firs'):
                allowed_firs = []
                if isinstance(fir_order, list) and len(fir_order) > 0:
                    allowed_firs = [c.strip().upper() for c in fir_order if isinstance(c, str) and len(c.strip()) == 4]
                elif isinstance(actual_fir_list, list) and len(actual_fir_list) > 0:
                    allowed_firs = [c.strip().upper() for c in actual_fir_list if isinstance(c, str) and len(c.strip()) == 4]

                lines = []
                for code in allowed_firs:
                    name = get_fir_name(code)
                    lines.append(f"#### [{code}] {name}")
                    lines.append("<div style=\"border-top: 3px solid #28a745; margin: 10px 0;\"></div>")
                    lines.append("해당 항로와 관련된 NOTAM이 없습니다.\n\n---\n")
                return "\n".join(lines)

            # AI 분석 실행 (Rate Limit 방지를 위한 Rate Limiter 사용)
            global _last_api_call_time, _min_api_interval
            
            current_time = time.time()
            time_since_last_call = current_time - _last_api_call_time
            
            if time_since_last_call < _min_api_interval:
                wait_time = _min_api_interval - time_since_last_call
                logger.info(f"⏳ API 호출 전 딜레이: {wait_time:.2f}초 (Rate Limit 방지)...")
                time.sleep(wait_time)
            
            _last_api_call_time = time.time()
            
            try:
                response = model.generate_content(prompt)
                result = response.text.strip()
            except Exception as e:
                if "429" in str(e) or "Quota exceeded" in str(e):
                    logger.error(f"⚠️ Rate Limit 오류 발생. 5초 대기 후 재시도...")
                    time.sleep(5)
                    response = model.generate_content(prompt)
                    result = response.text.strip()
                else:
                    raise
            
            # 결과 정리 (날짜/시간 제거 포함)
            logger.info("=== Before Clean ===")
            logger.info(f"Result length: {len(result)}")
            logger.info(f"First 500 chars: {result[:500]}")
            
            result = self._clean_analysis_result(result)

            # 허용된 FIR만 유지 (우선순위: fir_order > Package3 FIR: 라인 > actual_fir_list)
            try:
                allowed_firs: List[str] = []

                if isinstance(fir_order, list) and len(fir_order) > 0:
                    allowed_firs = [c.strip().upper() for c in fir_order if isinstance(c, str) and len(c.strip()) == 4]
                if not allowed_firs:
                    # Package 3 본문에서 'FIR:' 라인 우선 추출 (package3_text가 있으면 사용, 없으면 notam_text 사용)
                    try:
                        source_text = package3_text if package3_text else (notam_text or '')
                        fir_line_codes = self._extract_fir_codes_from_fir_line(source_text)
                        if fir_line_codes:
                            allowed_firs = fir_line_codes
                            logger.info(f"📌 'FIR:' 라인에서 허용 FIR 추출 ({len(fir_line_codes)}개): {allowed_firs}")
                    except Exception as _e0:
                        logger.debug(f"FIR 라인 추출 스킵: {_e0}")
                if not allowed_firs and isinstance(actual_fir_list, list) and len(actual_fir_list) > 0:
                    allowed_firs = [c.strip().upper() for c in actual_fir_list if isinstance(c, str) and len(c.strip()) == 4]

                if allowed_firs:
                    result = self._keep_only_allowed_firs_blocks(result, allowed_firs)

                # 태평양 좌표가 없으면 PACOTS/TDM 트랙 전용 RJJJ/KZAK 블록 제거
                pacific_present = any(token in (route or '').upper() for token in ['N17E', 'N11E', 'N04E', 'N20E', 'N30E', 'N40E'])
                if not pacific_present:
                    result = self._drop_pacific_track_only_blocks(result)

                # FIR 보강: fir_order가 없으면 allowed_firs 기반으로 누락 섹션 보강
                if (not fir_order or len(fir_order) == 0) and allowed_firs:
                    try:
                        result = self._add_missing_fir_sections(result, allowed_firs)
                    except Exception as _e2:
                        logger.debug(f"allowed_firs 기반 FIR 보강 스킵: {_e2}")
            except Exception as _e:
                logger.warning(f"후처리 FIR 필터 적용 중 경고(계속 진행): {_e}")

            # 파일 기반 FIR 순서가 제공되면 재정렬 시도 (기존 II/III 섹션이 없으면 그대로 통과)
            if fir_order:
                try:
                    result = self._add_missing_fir_sections(result, fir_order)
                    result = self._reorder_fir_sections(result, fir_order)
                except Exception as e:
                    logger.warning(f"FIR 섹션 재정렬 실패(무시하고 진행): {e}")
            
            logger.info("=== After Clean ===")
            logger.info(f"Result length: {len(result)}")
            logger.info(f"First 1000 chars: {result[:1000]}")
            
            return result

        except Exception as e:
            logger.error(f"AI 항로 분석 중 오류: {str(e)}")
            return f"AI 분석 중 오류가 발생했습니다: {str(e)}"
    
    def _extract_fir_codes_from_fir_line(self, text: str) -> List[str]:
        """Package 3 본문에서 'FIR:' 블록의 FIR 코드를 모두 추출한다.

        - 'FIR:'가 있는 줄부터 시작해, 다음 줄들에서 연속으로 4글자 FIR 코드가 나열된 블록 전체를 수집
        - 공백 줄을 만나거나, 코드가 아닌 라인(영문 문장/다른 섹션 헤더 등)이 나오면 종료
        - 중복 제거, 대문자 정규화, 입력 순서 유지
        """
        import re
        try:
            lines = text.splitlines()
            start_idx = -1
            for i, line in enumerate(lines):
                if re.search(r"^\s*FIR:\s*", line):
                    start_idx = i
                    break
            if start_idx == -1:
                return []

            collected: List[str] = []
            for j in range(start_idx, min(start_idx + 30, len(lines))):  # 안전 상한선 30줄
                line = lines[j].strip()
                if j == start_idx:
                    # 'FIR:' 접두 제거
                    line = re.sub(r"^FIR:\s*", "", line, flags=re.IGNORECASE)
                if not line:
                    break
                # 4글자 대문자 코드들만 추출
                codes = re.findall(r"\b[A-Z]{4}\b", line.upper())
                if not codes:
                    # 코드가 전혀 없는 라인이면 블록 종료로 판단
                    break
                collected.extend(codes)

            # 고유화 및 정규화(입력 순서 유지)
            unique_ordered: List[str] = []
            seen = set()
            for c in collected:
                if len(c) == 4 and c not in seen:
                    seen.add(c)
                    unique_ordered.append(c)
            return unique_ordered
        except Exception:
            return []

    def _extract_airports_from_route(self, route: str) -> list:
        """항로에서 공항 코드, 웨이포인트, 항로 코드, FIR 코드 추출"""
        route_upper = route.upper()
        
        # 1. 4자리 공항 코드 추출 (ICAO 공항 코드)
        airports = re.findall(r"\b[A-Z]{4}\b", route_upper)
        
        # 2. 웨이포인트 추출 (5자리 코드)
        waypoints = re.findall(r"\b[A-Z]{5}\b", route_upper)
        
        # 3. 항로 코드 추출 (문자+숫자 조합)
        airways = re.findall(r"\b[A-Z]+\d+\b", route_upper)
        
        # 모든 요소 결합
        all_elements = airports + waypoints + airways
        
        # 중복 제거하면서 순서 유지
        return list(dict.fromkeys(all_elements))
    
    def _parse_coordinate_waypoint(self, coord_str: str) -> Optional[Tuple[float, float]]:
        """좌표 형식의 waypoint 파싱 (다양한 형식 지원)"""
        coord_str = coord_str.strip().upper()
        
        # 패턴 1: N17E139 형식
        match = re.match(r'([NS])(\d{2}(?:\.\d+)?)([EW])(\d{3}(?:\.\d+)?)', coord_str)
        if match:
            lat_dir, lat_val, lon_dir, lon_val = match.groups()
            lat = float(lat_val)
            lon = float(lon_val)
            
            if lat_dir == 'S':
                lat = -lat
            if lon_dir == 'W':
                lon = -lon
                
            return (lat, lon)
        
        # 패턴 2: 17N139E 형식
        match = re.match(r'(\d{2}(?:\.\d+)?)([NS])(\d{3}(?:\.\d+)?)([EW])', coord_str)
        if match:
            lat_val, lat_dir, lon_val, lon_dir = match.groups()
            lat = float(lat_val)
            lon = float(lon_val)
            
            if lat_dir == 'S':
                lat = -lat
            if lon_dir == 'W':
                lon = -lon
                
            return (lat, lon)
        
        return None
    
    def _split_route_tokens(self, route: str) -> List[str]:
        """항로 문자열을 토큰 단위로 분할"""
        if not route:
            return []
        normalized = route.replace("/", " ")
        tokens = re.split(r"\s+|\.\.+", normalized.upper())
        clean_tokens: List[str] = []
        for token in tokens:
            token = token.strip(" ,;-")
            if not token:
                continue
            # 항로 코드 뒤에 따라붙는 쉼표 등 제거
            if token.endswith((",", ".")):
                token = token.rstrip(",.")
            clean_tokens.append(token)
        return clean_tokens

    def _resolve_token_coordinate(
        self,
        token: str,
        reference: Optional[Tuple[float, float]] = None,
    ) -> Optional[Tuple[float, float]]:
        """토큰을 NavData 또는 좌표 패턴으로 해석해 위경도를 반환"""
        if not token:
            return None

        coord = self._parse_coordinate_waypoint(token)
        if coord:
            return coord

        navdata = self._get_navdata()
        if navdata:
            try:
                resolved = navdata.get_waypoint_coordinates(token, reference=reference)
                if resolved:
                    return float(resolved[0]), float(resolved[1])
            except Exception as exc:
                logger.debug("토큰 좌표 해석 실패(%s): %s", token, exc)
        return None

    def _extract_route_coordinates(self, route: str) -> List[Tuple[str, float, float]]:
        """항로 토큰을 순회하며 (토큰, 위도, 경도) 리스트를 구성"""
        tokens = self._split_route_tokens(route)
        resolved: List[Tuple[str, float, float]] = []
        reference: Optional[Tuple[float, float]] = None

        for token in tokens:
            coord = self._resolve_token_coordinate(token, reference=reference)
            if coord is None:
                continue
            lat, lon = coord
            resolved.append((token, lat, lon))
            reference = coord

        return resolved

    def _check_kzak_fir_intersection(self, route: str) -> dict:
        """항로가 KZAK FIR을 통과하는지 FIR GeoJSON과 NavData로 확인"""
        result = {
            'intersects_kzak': False,
            'coordinate_waypoints': [],
            'kzak_coordinates': [],
            'fir_sections': [],
            'route_coordinates': [],
        }

        route_points = self._extract_route_coordinates(route)
        result['route_coordinates'] = route_points
        result['coordinate_waypoints'] = [(lat, lon) for _, lat, lon in route_points]

        if not route_points:
            return result

        fir_ref = self._get_fir_geo()

        if fir_ref:
            latlon_sequence = [(lat, lon) for _, lat, lon in route_points]
            try:
                trace = fir_ref.trace_route(latlon_sequence)
            except Exception as exc:
                logger.warning("FIR 경계 추적 중 오류 발생(폴백 사용): %s", exc)
                trace = {}

            fir_sequence = trace.get('fir_sequence', []) if isinstance(trace, dict) else []
            waypoint_firs = trace.get('waypoint_firs', []) if isinstance(trace, dict) else []

            if 'KZAK' in fir_sequence:
                result['intersects_kzak'] = True

            kzak_segments = []
            for idx, fir_code in enumerate(waypoint_firs):
                if fir_code == 'KZAK':
                    lat, lon = latlon_sequence[idx]
                    result['kzak_coordinates'].append((lat, lon))
            if isinstance(trace, dict):
                kzak_segments = [
                    segment for segment in trace.get('segments', []) if segment.get('fir') == 'KZAK'
                ]
            if result['kzak_coordinates']:
                result['intersects_kzak'] = True
            elif kzak_segments:
                # 세그먼트 정보만 있을 경우 대표 좌표를 기록
                for segment in kzak_segments:
                    start_idx = segment.get('start_index', 0)
                    start_idx = min(max(int(start_idx), 0), len(latlon_sequence) - 1)
                    lat, lon = latlon_sequence[start_idx]
                    result['kzak_coordinates'].append((lat, lon))
                    result['intersects_kzak'] = True
                    break
            result['fir_sections'] = kzak_segments
        else:
            logger.debug("FIR Geo 레퍼런스가 없어 NavData 패턴으로 KZAK 교차를 추정합니다.")
            for token, lat, lon in route_points:
                fir_code = None
                navdata = self._get_navdata()
                if navdata and hasattr(navdata, "estimate_waypoint_fir"):
                    try:
                        fir_code = navdata.estimate_waypoint_fir(token)
                    except Exception:
                        fir_code = None
                if fir_code == 'KZAK':
                    result['intersects_kzak'] = True
                    result['kzak_coordinates'].append((lat, lon))

        return result
    
    def debug_route_extraction(self, route: str) -> dict:
        """항로 추출 결과를 디버깅용으로 반환"""
        route_upper = route.upper()
        
        airports = re.findall(r"\b[A-Z]{4}\b", route_upper)
        waypoints = re.findall(r"\b[A-Z]{5}\b", route_upper)
        airways = re.findall(r"\b[A-Z]+\d+\b", route_upper)
        
        # KZAK FIR 교차 확인
        kzak_intersection = self._check_kzak_fir_intersection(route)
        
        return {
            'airports': airports,
            'waypoints': waypoints,
            'airways': airways,
            'total_elements': len(airports) + len(waypoints) + len(airways),
            'kzak_intersection': kzak_intersection
        }
    
    def _extract_airports_from_notams(self, notams: list) -> list:
        """NOTAM 리스트에서 공항 코드 추출"""
        airports = set()
        for notam in notams:
            if isinstance(notam, dict):
                airport_code = notam.get('airport_code', '')
                if airport_code:
                    airports.add(airport_code)
            elif isinstance(notam, str):
                # 문자열 형태의 NOTAM에서 4자리 공항 코드 추출
                import re
                codes = re.findall(r'\b[A-Z]{4}\b', notam)
                airports.update(codes)
        return sorted(list(airports))
    
    def _deduplicate_notams(self, notam_list: list) -> list:
        """NOTAM 리스트에서 중복 제거 (NOTAM 번호와 원본 텍스트 기준)"""
        seen = set()
        unique_notams = []
        for notam in notam_list:
            if isinstance(notam, dict):
                key = (notam.get('notam_number'), notam.get('original_text'))
            else:
                # 문자열 형태의 NOTAM인 경우
                key = (str(notam), str(notam))
            
            if key not in seen:
                seen.add(key)
                unique_notams.append(notam)
        return unique_notams
    
    def _extract_package3_from_text(self, notam_text: str) -> str:
        """NOTAM 텍스트에서 Package 3 섹션만 추출"""
        if not notam_text:
            return ""
        
        # Package 3 시작과 끝을 찾기
        package3_start = notam_text.find("KOREAN AIR NOTAM PACKAGE 3")
        if package3_start == -1:
            logger.warning("Package 3 섹션을 찾을 수 없습니다.")
            return notam_text  # 전체 텍스트 반환
        
        package3_end = notam_text.find("END OF KOREAN AIR NOTAM PACKAGE 3", package3_start)
        if package3_end == -1:
            logger.warning("Package 3 섹션의 끝을 찾을 수 없습니다.")
            return notam_text[package3_start:]  # 시작부터 끝까지
        
        # Package 3 섹션만 추출
        package3_text = notam_text[package3_start:package3_end + len("END OF KOREAN AIR NOTAM PACKAGE 3")]
        logger.info(f"Package 3 섹션 추출 완료: {len(package3_text)} 문자")
        
        return package3_text

    def _parse_package3_fir_sections(self, package3_text: str) -> dict:
        """Package 3 텍스트를 FIR별로 분리"""
        fir_sections = {}
        
        # FIR 섹션 패턴 찾기
        fir_pattern = r'\[FIR\]\s+([A-Z]{4})/'
        fir_matches = list(re.finditer(fir_pattern, package3_text))
        
        for i, match in enumerate(fir_matches):
            fir_code = match.group(1)
            start_pos = match.start()
            
            # 다음 FIR 섹션의 시작 위치 찾기
            if i + 1 < len(fir_matches):
                end_pos = fir_matches[i + 1].start()
            else:
                end_pos = len(package3_text)
            
            # FIR 섹션 내용 추출
            fir_content = package3_text[start_pos:end_pos].strip()
            fir_sections[fir_code] = fir_content
        
        logger.info(f"Package 3 FIR 섹션 분리 완료: {list(fir_sections.keys())}")
        return fir_sections
    
    def _extract_notam_entries_from_fir_section(self, fir_content: str, fir_code: str) -> list:
        """FIR 섹션에서 개별 NOTAM 엔트리 추출"""
        notam_entries = []
        
        # NOTAM 엔트리는 "날짜 시간 - 날짜 시간 FIR코드 번호" 또는 "날짜 시간 - UFN FIR코드 번호" 형식
        # 패턴 예시:
        # "24MAR23 16:00 - UFN RKRR CHINA SUP 16/21"
        # "30SEP25 01:10 - 31OCT25 15:00 RKRR Z1140/25"
        # "25OCT25 07:00 - 25OCT25 21:00 RJJJ Q2553/25"
        
        # NOTAM 시작 패턴 찾기 (날짜+시간으로 시작하는 라인)
        # 종료 날짜 뒤에 시간이 있을 수도 있고 없을 수도 있음
        notam_start_pattern = r'(\d{2}[A-Z]{3}\d{2})\s+\d{2}:\d{2}\s+-\s+(UFN|(?:\d{2}[A-Z]{3}\d{2}(?:\s+\d{2}:\d{2})?))\s+([A-Z]{4})\s+([^\s]+(?:\s+[^\s]+)*)'
        
        lines = fir_content.split('\n')
        current_notam = None
        current_notam_lines = []
        notam_number = None
        
        for line in lines:
            # NOTAM 시작 라인 찾기
            match = re.match(notam_start_pattern, line)
            if match:
                # 이전 NOTAM 저장
                if current_notam and notam_number:
                    notam_entries.append({
                        'notam_number': notam_number,
                        'content': '\n'.join(current_notam_lines)
                    })
                
                # 새 NOTAM 시작
                start_date, end_date, fir, number = match.groups()
                notam_number = f"{number.strip()}" if number else "UNKNOWN"
                current_notam_lines = [line]
            else:
                if current_notam_lines:
                    current_notam_lines.append(line)
        
        # 마지막 NOTAM 저장
        if current_notam_lines and notam_number:
            notam_entries.append({
                'notam_number': notam_number,
                'content': '\n'.join(current_notam_lines)
            })
        
        logger.info(f"{fir_code} FIR에서 추출된 NOTAM: {len(notam_entries)}개")
        return notam_entries

    def _format_notam_data(self, notam_data: list) -> str:
        """NOTAM 데이터를 분석용 문자열로 변환 (package 1,2 제외하고 package 3만 포함)"""
        if not notam_data:
            return "현재 NOTAM 데이터가 없습니다."

        # 먼저 중복 제거
        unique_notams = self._deduplicate_notams(notam_data)
        logger.info(f"NOTAM 중복 제거: {len(notam_data)}개 → {len(unique_notams)}개")

        formatted_text = "NOTAM 목록:\n\n"
        
        # Package 필터링: package 1, 2 제외하고 package 3만 포함
        # Package 3 FIR: RKRR, RJJJ, KZAK, PGZU, AYPM, YBBB
        package3_airports = get_package3_fir_codes()
        
        filtered_notams = []
        for notam in unique_notams:
            # 문자열 형태의 NOTAM 처리
            if isinstance(notam, str):
                # package 3 공항이 포함된 NOTAM만 필터링
                if any(airport in notam for airport in package3_airports):
                    filtered_notams.append(notam)
            # 딕셔너리 형태의 NOTAM 처리
            elif isinstance(notam, dict):
                airports = notam.get('airports', [])
                if not airports:
                    airport = notam.get('airport', 'N/A')
                    airports = [airport] if airport != 'N/A' else []
                
                # package 3 공항이 포함된 NOTAM만 필터링
                if any(airport in package3_airports for airport in airports):
                    filtered_notams.append(notam)
            else:
                # 기타 타입은 제외
                continue
        
        logger.info(f"Package 필터링 결과: 전체 {len(notam_data)}개 → package 3 관련 {len(filtered_notams)}개")
        
        # 필터링된 데이터 처리
        for i, notam in enumerate(filtered_notams):
            # 디버깅: NOTAM 데이터 타입과 내용 확인
            logger.info(f"NOTAM {i}: 타입={type(notam)}, 내용={str(notam)[:200] if not isinstance(notam, dict) else list(notam.keys())}")
            
            if isinstance(notam, str):
                # Package 3 텍스트를 FIR별로 구조화
                if "KOREAN AIR NOTAM PACKAGE 3" in notam:
                    # FIR별로 분리하여 처리
                    fir_sections = self._parse_package3_fir_sections(notam)
                    for fir_code, fir_content in fir_sections.items():
                        formatted_text += f"\n========================================\n"
                        formatted_text += f"=== {fir_code} FIR ===\n"
                        formatted_text += f"========================================\n"
                        
                        # FIR 섹션에서 개별 NOTAM 엔트리 추출
                        notam_entries = self._extract_notam_entries_from_fir_section(fir_content, fir_code)
                        
                        # 각 NOTAM을 개별적으로 포맷팅
                        for entry in notam_entries:
                            notam_number = entry['notam_number']
                            notam_content = entry['content']
                            
                            formatted_text += f"\n### NOTAM 번호: {notam_number} ###\n"
                            formatted_text += f"공항: {fir_code}\n"
                            formatted_text += f"내용:\n{notam_content}\n"
                            formatted_text += "---\n"
                        
                        formatted_text += f"\n========================================\n"
                        formatted_text += "\n"
                else:
                    # 일반 문자열 형태의 NOTAM 처리
                    formatted_text += f"NOTAM {i+1}:\n"
                    formatted_text += f"내용: {notam}\n"
                    formatted_text += "---\n"
            elif isinstance(notam, dict):
                # 딕셔너리 형태의 NOTAM 처리
                notam_number = notam.get('notam_number') or notam.get('id')
                
                # NOTAM 번호가 없으면 텍스트에서 추출 시도
                if not notam_number or 'NOTAM #' in str(notam_number):
                    text = notam.get('text', '') or notam.get('description', '')
                    if text:
                        # 원본 텍스트에서 NOTAM 번호 패턴 찾기
                        import re
                        notam_patterns = [
                            r'\b([A-Z]{4}\s+(?:CHINA\s+SUP|AIP\s+SUP|COAD|[A-Z]\d{3,4})/\d{2})\b',
                            r'\b(COAD\d{2}/\d{2})\b',
                            r'\b([A-Z]\d{3,4}/\d{2})\b',
                            r'\b(AIP\s+SUP\s+\d+/\d+)\b',
                            r'\b(CHINA\s+SUP\s+\d+/\d+)\b',
                        ]
                        
                        for pattern in notam_patterns:
                            match = re.search(pattern, text)
                            if match:
                                notam_number = match.group(1)
                                logger.info(f"✅ NOTAM 번호 추출 성공: {notam_number}")
                                break
                
                # 여전히 번호가 없으면 기본값 사용
                if not notam_number:
                    notam_number = f'N/A-{i+1}'
                    logger.warning(f"⚠️ NOTAM 번호를 찾을 수 없음, 기본값 사용: {notam_number}")
                
                airports = notam.get('airports', [])
                if not airports:
                    airport = notam.get('airport', 'N/A')
                    airports = [airport] if airport != 'N/A' else []
                airport_str = ', '.join(airports) if airports else 'N/A'
                
                # 디버깅: NOTAM 번호 확인
                logger.info(f"NOTAM 딕셔너리 keys: {list(notam.keys())}")
                logger.info(f"최종 NOTAM 번호: {notam_number}")
                
                # NOTAM 번호를 최상단에 명시적으로 표시
                formatted_text += f"\n### NOTAM 번호: {notam_number} ###\n"
                formatted_text += f"공항: {airport_str}\n"
                
                # 본문 전체 포함 (길이 제한 제거)
                text = notam.get('text', '') or ''
                formatted_text += f"내용: {text}\n"
                formatted_text += "---\n"

        # 디버깅: 포맷팅된 데이터 로깅 (파일 저장은 제거)
        logger.debug(f"포맷팅된 NOTAM 데이터 길이: {len(formatted_text)} 문자")
        logger.debug(f"처리된 NOTAM 수: {len(notam_data)} → {len(filtered_notams)}")

        return formatted_text
    
    def _create_analysis_prompt(self, route: str, notam_text: str, flight_info: str, current_time: str, kzak_intersection: Optional[Dict[str, Any]] = None, actual_fir_list: Optional[List[str]] = None, fir_order: Optional[List[str]] = None) -> str:
        """강화된 조종사 브리핑용 프롬프트 생성"""
        
        logger.info("🔄 강화된 조종사 브리핑 프롬프트 생성 중...")
        
        # 타임스탬프 추가 (캐시 방지)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # KZAK FIR 교차 정보 추가 (더 엄격한 조건)
        kzak_info = ""
        if (kzak_intersection and kzak_intersection['intersects_kzak'] and 
            len(kzak_intersection['kzak_coordinates']) > 0):
            
            kzak_coords = kzak_intersection['kzak_coordinates']
            coord_strs = [f"N{int(coord[0])}E{int(coord[1])}" for coord in kzak_coords]
            kzak_info = f"""

<kzak_fir_intersection>
⚠️ 중요: 이 항로는 KZAK (OAKLAND OCEANIC FIR)을 지나갑니다.
교차 좌표: {', '.join(coord_strs)}
KZAK FIR 관련 NOTAM을 반드시 포함하여 분석하세요.
</kzak_fir_intersection>"""
        
        # 실제 FIR 목록 정보 생성
        fir_list_info = ""
        if actual_fir_list:
            fir_list_info = f"""
✅ **생성해야 할 FIR 섹션:** {', '.join([f'{fir} ({get_fir_name(fir)})' for fir in actual_fir_list])}
"""
            logger.info(f"📝 프롬프트에 전달할 FIR 목록: {actual_fir_list}")
        else:
            logger.warning("⚠️ FIR 목록이 추출되지 않았습니다. 기본 방식으로 진행합니다.")

        # split.txt 기반 FIR 표시 순서가 제공된 경우, 절대 우선 규칙으로 추가
        fir_order_info = ""
        if fir_order:
            named = [f"{code} ({get_fir_name(code)})" for code in fir_order]
            fir_order_info = f"""
🔢 **FIR 표시 순서(파일 기반, 절대 준수):** {', '.join(named)}

⚠️ **중요 지시사항 - 반드시 준수:**
1. 위 순서대로 **정확히 {len(fir_order)}개의 FIR 섹션**을 생성하십시오
2. 각 FIR은 **반드시 위 순서대로** 출력하십시오 (단일 FIR 형식)
3. NOTAM이 없는 FIR도 헤더는 생성하고 "이 FIR에는 항로에 영향을 주는 NOTAM이 없습니다"라고 명시하십시오
4. 본 순서가 제공된 경우, '출발지→경유→도착지' 경로 기반 순서 규칙은 완전히 무시합니다
5. **절대로** 이 순서를 변경하거나 FIR을 생략하지 마십시오

✅ **올바른 출력 예시:**
#### [RKRR] Incheon FIR
<div style="border-top: 3px solid #28a745; margin: 10px 0;"></div>
[NOTAM 내용 또는 "이 FIR에는 항로에 영향을 주는 NOTAM이 없습니다"]

#### [RJJJ] Fukuoka FIR
<div style="border-top: 3px solid #28a745; margin: 10px 0;"></div>
[NOTAM 내용 또는 "이 FIR에는 항로에 영향을 주는 NOTAM이 없습니다"]

... (나머지 FIR도 순서대로)
"""
            logger.info(f"🧭 파일 기반 FIR 순서 적용: {fir_order}")
            logger.info(f"📋 FIR 순서 프롬프트 블록:\n{fir_order_info}")

        # 출력 언어와 형식 강제 지시
        language_rule = """
⚠️ 모든 출력은 100% 한국어로만 작성합니다. 영어 문장이나 원문을 그대로 출력하지 마십시오. 기술 용어(코드, 항공로명, 웨이포인트, NOTAM 번호)만 영문 유지, 나머지는 반드시 한국어로 서술하세요.
"""

        route_order_guidance = """
**🚨 FIR 표시 순서: 출발지 FIR → 경유 FIR → 도착지 FIR 순서로 표시**
- 예: 출발지→중간 FIR들(경유)→도착지 순서로 일관되게 정렬
"""

        # 파일 기반 순서가 제공된 경우에는 경로 기반 순서 안내를 생략하여 충돌 방지
        route_order_block = "" if fir_order else route_order_guidance

        # FIR 순서가 제공된 경우 프롬프트 맨 앞에 배치
        opening_instruction = ""
        if fir_order and len(fir_order) > 0:
            # FIR 목록을 동적으로 생성
            fir_list_lines = []
            for i, fir_code in enumerate(fir_order, 1):
                fir_list_lines.append(f"{i}. {fir_code} ({get_fir_name(fir_code)})")
            
            opening_instruction = f"""
🚨🚨🚨 **절대 준수 - 최우선 지시사항** 🚨🚨🚨

**FIR 출력 순서 (변경 불가):**
{chr(10).join(fir_list_lines)}

⚠️ **반드시 위 순서대로 {len(fir_order)}개 FIR 모두 출력하십시오**
⚠️ **NOTAM이 없는 FIR도 반드시 헤더를 생성하고 "해당 항로와 관련된 NOTAM이 없습니다" 메시지를 포함하십시오**
⚠️ **이 순서를 절대 변경하거나 생략하지 마십시오**

"""

        return f"""{opening_instruction}당신은 항공 브리핑 전문가로서 조종사에게 **비행 경로와 직접 관련된 NOTAM만** 선별하여 보고해야 합니다.

**🚨 최우선 규칙: 날짜/시간 완전 제거 (절대 준수)**
- **모든 NOTAM 설명에서 날짜와 시간 정보를 100% 제거하십시오**
- 다음 패턴을 모두 찾아 제거:
  - ❌ 한국어: "11월 1일", "10월 31일", "10:31 UTC", "15:54 UTC부터", "11월 1일 10:31 UTC부터 11월 01 UTC까지"
  - ❌ 영어: "2025-10-27", "25OCT25", "16:00 UTC", "0000-2359", "10월 31일 22:00 UTC부터 11월 1일 22:00 UTC까지"
  - ❌ 기타: UFN, PERM, "영구적으로", "부터", "까지" (날짜/시간과 함께 사용된 경우)
- ✅ **올바른 출력**: 날짜/시간 없이 내용만 작성
- ✅ 예시: "**[Z1255/25]:** 인천 FIR 내에서 GPS 신호가 간헐적으로 불안정하거나 손실될 수 있으니 GPS 사용 시 각별한 주의가 필요합니다."
- ❌ **잘못된 출력**: "**[Z1255/25]:** 11월 1일 10:31 UTC부터 11월 01 UTC까지 인천 FIR 내에서 GPS 신호가 불안정합니다."

---

        <!-- 분석 ID: {timestamp} -->{fir_list_info}{fir_order_info}
{language_rule}

<input>
<flight_route>
**비행 경로**: {route}

**경로 분석 필수 요소:**
- 공항 코드: {', '.join(self._extract_airports_from_route(route)[:5]) if self._extract_airports_from_route(route) else '없음'}
- 항로/웨이포인트: 위 경로에서 추출
- 태평양 좌표: {'있음 (PACOTS/TDM Track 필수)' if any(coord in route.upper() for coord in ['N17E139', 'N11E141', 'N04E143', 'N20E', 'N30E', 'N40E']) else '없음'}
</flight_route>

<notam_package>
{notam_text}
</notam_package>{kzak_info}

**🚨 항로 매칭 지침 🚨**

아래 지침에 따라 사용자가 제공한 실제 항로에서 항로명/웨이포인트/좌표를 추출하여 매칭하세요.

{route_order_block}

[각 FIR마다 다음 형식으로 작성:]
- "Q2551/25: PACOTS Track ALPHA..." → ✅ 항로에 태평양 좌표 있음
- "A4735/25: TDM Track 2..." → ✅ 항로에 태평양 좌표 있음
- "Y208 INVOK-BASEM CDR..." → ✅ "Y208", "INVOK", "BASEM"이 항로에 있음
- "G339 LUKRA routing..." → ✅ "G339", "LUKRA"가 항로에 있음
**[NOTAM번호]:** 간결한 1~2줄 설명. 위치, 고도, 영향 항로, 대체 절차 포함.
   - **공역 제한(AIRSPACE) NOTAM의 경우 반드시 고도 범위와 위치 정보 포함!**
   - NOTAM에 F)SFC G)7000FT AMSL 같은 고도 정보가 있으면 반드시 분석 결과에 포함
   - COMMENT) 필드에 위치 정보(예: INCLUDE WJU)가 있으면 반드시 포함
   - 고도 정보 형식: "위치명 SFC~7000FT" 또는 "위치명 하한고도~상한고도"
   - 예: "F)SFC G)7000FT AMSL COMMENT) INCLUDE WJU" → "WJU SFC~7000FT"
   - 예: "F)SFC G)1641FT AMSL" → "SFC~1641FT" (COMMENT가 없으면 위치명 생략 가능)
   - 고도 정보가 있으면 항공편이 해당 고도에서 비행할 때 영향을 받는지 명시

**❌ 반드시 제외해야 할 NOTAM:**
- 사용자의 항로에 없는 웨이포인트/항로명만 언급
- 항로와 150NM 이상 떨어진 좌표만 언급
**⚠️ 이 섹션은 한국어로만 작성! 영어 원문 절대 금지!**
- 공항 시설 전용 공지(RWY/TWY/Apron 등)는 En-route 분석에서 제외
[FIR별로 Flow Control, CDR 등 운영 정보를 간략히 정리. 항로 순서대로 FIR 표시]
**⚠️ 중요 주의사항:**
- **Flow Control NOTAM도 항로 매칭 필수!** (해당 항로명/웨이포인트/구간을 실제로 통과하는지 확인)
- **공역 NOTAM도 거리/경로 일치 확인 필수!**
- **공역 제한/금지 구역 NOTAM 분석 시 고도 정보와 위치 정보 필수 포함!**
  - NOTAM에 F)SFC G)7000FT AMSL 형식의 고도 정보가 있으면 반드시 분석 결과에 포함
  - COMMENT) 필드에 위치 정보(예: INCLUDE WJU)가 있으면 반드시 포함
  - F)는 Lower(하한), G)는 Upper(상한) 고도를 의미
  - 고도 정보 형식: "위치명 SFC~7000FT" 또는 "위치명 하한고도~상한고도"
  - 예: "F)SFC G)7000FT AMSL COMMENT) INCLUDE WJU" → "WJU SFC~7000FT"
  - 예: "F)SFC G)1641FT AMSL" → "SFC~1641FT" (COMMENT가 없으면 위치명 생략 가능)
  - 고도 범위를 명시하여 해당 고도에서 비행 시 영향을 받는지 표시

---

**🎯 NOTAM 선별 3단계 프로세스**

**1단계: 항로 요소 추출**
현재 항로에서 다음을 추출하세요:
- 항로명: 사용자 항로에서 등장하는 항로명 전체
- 웨이포인트: 사용자 항로에서 등장하는 모든 웨이포인트
- 좌표: 사용자 항로에 포함된 좌표 표기(NxxE/Exx, SxxE 등)
- 태평양 좌표 포함 시 → PACOTS/TDM 필수

**2단계: 각 NOTAM 검사 (예/아니오 질문)**
각 NOTAM마다:
1. ❓ "이 NOTAM이 위 항로명(Y782 등) 중 하나를 언급하는가?" → YES면 ✅ 포함
2. ❓ "이 NOTAM이 위 웨이포인트(TGU 등) 중 하나를 언급하는가?" → YES면 ✅ 포함
3. ❓ "이 NOTAM이 위 좌표(N17E139 등) 인근을 언급하는가?" → YES면 ✅ 포함
4. ❓ "이 NOTAM이 FIR 전역 GPS/통신 장애를 언급하는가?" → YES면 ✅ 포함
5. ❓ "이 NOTAM이 PACOTS/TDM Track이고 항로에 태평양 좌표가 있는가?" → YES면 ✅ 포함
6. 위 1-5가 **모두 NO**인가? → ❌ 제외

**3단계: 출력 형식**
- NOTAM 번호: **[Z1233/25]:** (대괄호 + 콜론)
- **날짜/시간: 절대적으로 모두 제거** (다음 모든 형식 포함):
  - ❌ 한국어 날짜: "11월 1일", "10월 31일", "12월 30일"
  - ❌ 한국어 시간: "10:31 UTC부터", "15:54 UTC까지", "10:00 UTC부터 21:00 UTC까지"
  - ❌ 영어 날짜: "2025-10-27", "25OCT25", "24MAR23"
  - ❌ 영어 시간: "16:00 UTC", "0000-2359", "12:10 UTC부터 12:55 UTC까지"
  - ❌ 기타: UFN, PERM, "영구적으로", "부터", "까지" (날짜/시간과 함께 사용된 경우)
- 내용: 1-2줄로 요약 (날짜/시간 없이)
- ✅ 올바른 예: "**[Z1255/25]:** 인천 FIR 내에서 GPS 신호가 간헐적으로 불안정하거나 손실될 수 있으니 GPS 사용 시 각별한 주의가 필요합니다."
- ❌ 잘못된 예: "**[Z1255/25]:** 11월 1일 10:31 UTC부터 11월 01 UTC까지 인천 FIR 내에서 GPS 신호가 불안정합니다."

**FIR 코드/이름 참고:** 일부 주요 예시
- RKRR = Incheon FIR, RJJJ = Fukuoka FIR, KZAK = Oakland Oceanic FIR 등
- 공항 코드는 FIR가 아님 (예: RKSI) → FIR 섹션 생성 금지
- Package 3에서 추출된 FIR 전체에 대해 섹션 생성 (actual_fir_list / fir_order 기준)

**카테고리 필터링:**

✅ **포함 (En-Route 영향 + 항로 매칭)**:
1. 항공로 상태 (CDR, PACOTS/TDM Track, 항로 폐쇄)
2. 공역 제한 (제한구역, 군사 활동) - **단, 항로 인근만**
3. 항법 지원 (VOR/DME/GPS 장애) - **단, 항로에 영향 주는 경우만**
4. Flow Control, 관제 변경

❌ **제외**:
1. 항로와 무관한 공역 (먼 좌표의 제한/금지 구역)
2. 공항 시설 (RWY/TWY, 램프, 게이트)
3. 접근 절차 (SID/STAR) - **단, En-Route 항법에 영향 없는 경우**
4. 회사 전용, 일반 공지

</input>

<output_format>
단일 FIR 기반 출력 형식 (아래 형식과 순서만 사용):

#### [FIR코드] FIR이름
<div style="border-top: 3px solid #28a745; margin: 10px 0;"></div>

**[NOTAM번호]:** 1~2줄 요약 (위치/고도/영향 항로/대체 절차)
   - **공역 제한(AIRSPACE) NOTAM의 경우 반드시 고도 범위와 위치 정보 포함!**
   - COMMENT) 필드에 위치 정보(예: INCLUDE WJU)가 있으면 반드시 포함
   - 고도 정보 형식: "위치명 SFC~7000FT" 또는 "위치명 하한고도~상한고도"
   - 예: "F)SFC G)7000FT AMSL COMMENT) INCLUDE WJU" → "WJU SFC~7000FT"
   - 예: "F)SFC G)1641FT AMSL" → "SFC~1641FT" (COMMENT가 없으면 위치명 생략 가능)
   - 고도 정보가 있으면 분석 결과에 명시하여 해당 고도에서 비행 시 영향을 받는지 표시
... (해당 FIR 관련 항로-매칭 NOTAM을 위 형식으로 나열)

[해당 FIR에 일치하는 NOTAM이 없으면 아래 문장만]
해당 항로와 관련된 NOTAM이 없습니다.

---

#### [다음 FIR코드] FIR이름
<div style="border-top: 3px solid #28a745; margin: 10px 0;"></div>

... (모든 FIR을 같은 형식으로 반복)

⚠️ 주의:
- 모든 내용은 각 FIR 섹션 내부에만 작성합니다. 별도의 I/II/III 섹션을 만들지 마십시오.
- Flow Control/CDR 등 운영 정보는 해당 FIR 섹션의 마지막에 간단히 요약해 추가하십시오.
</output_format>

<critical_rules>
4. **PACOTS/OTS 트랙 매칭**: 항로에 태평양 횡단 좌표(N17E139 등)가 있으면 PACOTS/OTS 트랙 NOTAM 필수 포함
   - 예: 항로에 "N17E139..N11E141"이 있으면 PACOTS Track 정보 → ✅ 반드시 포함
   - 예: KZAK/RJJJ FIR의 TDM Track 정보 → ✅ 반드시 포함

5. **FIR 전역 영향 확인**: GPS 장애, 통신 주파수 변경 등 FIR 전체에 영향을 주는 NOTAM
   - 예: "Incheon FIR 전역 GPS 불안정" → ✅ 항상 포함
   - 예: 특정 공항만 해당하는 주파수 변경 → ❌ 제외

**⚠️ 중요: 항로와 무관한 NOTAM은 En-Route 카테고리여도 반드시 제외하십시오!**

---

**NOTAM 카테고리 필터링 규칙:**

✅ **포함 (En-Route 영향):**
1. **항공로 상태**: 항공로 폐쇄/제한, CDR 설정, PACOTS 트랙
2. **공역 제한**: 제한구역 활성화, 군사 활동, 공역 등급 변경
   - **⚠️ 공역 제한 NOTAM 분석 시 고도 정보와 위치 정보 필수 포함!**
   - NOTAM에 F)SFC G)7000FT AMSL 같은 고도 정보가 있으면 반드시 분석 결과에 포함
   - COMMENT) 필드에 위치 정보(예: INCLUDE WJU)가 있으면 반드시 포함
   - 고도 범위를 명시하여 항공편이 해당 고도에서 비행할 때 영향을 받는지 표시
   - **⚠️ 중요: 공역 제한 NOTAM 분석 시 반드시 고도 정보와 위치 정보 포함!**
   - 고도 정보 형식: "위치명 SFC~7000FT" 또는 "위치명 하한고도~상한고도"
   - F)SFC G)7000FT AMSL (F=Lower, G=Upper)
   - 예: "F)SFC G)7000FT AMSL COMMENT) INCLUDE WJU" → "WJU SFC~7000FT"
   - 예: "F)SFC G)1641FT AMSL" → "SFC~1641FT" (COMMENT가 없으면 위치명 생략 가능)
   - 예: "F)5000FT G)FL200" → "5000FT~FL200" (COMMENT가 없으면 위치명 생략 가능)
   - 고도 정보가 있으면 반드시 분석 결과에 포함하여 항공편이 해당 고도에서 비행할 때 영향을 받는지 명시
3. **항법 지원**: VOR/DME/NDB 사용불가, GPS/GNSS 장애
4. **흐름 제어**: Flow Control, 고도/항로 제한
5. **관제 변경**: 관제권 이양 변경, 통신 주파수 변경

❌ **제외 (공항 전용 또는 항로 무관):**
1. **공항 시설**: RWY/TWY 폐쇄, 램프/게이트 제한
2. **접근 절차**: SID/STAR 사용불가 (En-Route 항법에 영향 없는 경우)
3. **회사 전용**: Company Minima, COAD, SECY
4. **일반 공지**: AIP AMDT 통보
5. **항로와 무관한 공역**: 비행 경로에서 멀리 떨어진 제한/금지 구역

</input>

<fir_output_guidelines>
**⚠️ 주의: 이 섹션은 AI가 읽고 이해해야 할 지시사항입니다. 출력 결과에 포함하지 마세요!**

FIR 단일 섹션 작성 지침:

1. 모든 내용은 FIR별 블록으로만 구성합니다. I/II/III 헤더 금지.
2. 다음 중 하나라도 해당하면 해당 FIR 블록의 최상단에 먼저 배치:
   - FIR 전역 GPS/GNSS/SBAS 불안정/손실
   - 핵심 항법시설 완전 불가(VOR/DME/NDB 등)
   - 대규모 제한/금지 공역, 미사일/로켓 발사
   - 주요 항공로 완전 폐쇄, 특정 고도 전체 사용 불가
3. 키워드 체크: GPS, GNSS, VOR, DME, NDB, MILITARY, PROHIBITED, CLOSED 등
</fir_output_guidelines>

<critical_rules>
**🔥 위반 시 심각한 오류 - 12가지 절대 규칙 🔥**

RULE 1: **태평양 항로 PACOTS/TDM 필수**
- 항로에 N17E139, N11E141, N04E143 등 태평양 좌표가 **하나라도** 있으면:
  - RJJJ FIR의 **모든** PACOTS Track NOTAM (Q2551, Q2552, Q2553 등) → ✅ 반드시 포함
  - KZAK FIR의 **모든** TDM Track NOTAM (A4731, A4735, A4736 등) → ✅ 반드시 포함
- "비행 경로와 직접 관련된 NOTAM이 없습니다" 문구 사용 **절대 금지**

RULE 2: **항로 매칭 - 웨이포인트/항로명 엄격 검증**
- **NOTAM에 언급된 웨이포인트/항로명이 사용자 항로에 있는지 확인 필수**
- NOTAM에 항로의 항로명(Y782 등) 언급 → ✅ 포함
- NOTAM에 항로의 웨이포인트(TGU 등) 언급 → ✅ 포함
- **NOTAM에 항로에 없는 항로명/웨이포인트만 언급 → ❌ 반드시 제외**
 - **구체적 제외 예시 (현재 사용자 항로에 포함되지 않은 요소들만 언급하는 경우)**:
  - ❌ 항로에 없는 항로명/웨이포인트만 언급 → 제외
  - ❌ 항로에 없는 좌표만 언급 → 제외

RULE 3: **좌표 거리 검증**
- NOTAM 좌표와 항로 좌표 비교 (35N129E vs N17E139 = 약 2000km 차이)
- 150NM 이상 차이나면 → ❌ 제외
- 예: 항로가 N17E139인데 35N129E NOTAM → ❌ 제외

RULE 4: **공항 시설 제외**
- RWY, TWY, APRON, GATE, SID/STAR 관련 NOTAM → ❌ 완전 제외
- En-Route 항로 분석이므로 공항 내부 시설은 무관

RULE 5: **FIR 전역 영향만 포함**
- GPS 장애: "FIR 내" 또는 "전 지역" 언급 시만 → ✅ 포함
- 특정 좌표 GPS 장애 (예: 35N129E 반경 1NM) → ❌ 제외

RULE 6: **FIR 헤더 형식 (절대 준수!)**:
     - **반드시 `####` 마크다운 4개로 시작 (HTML 태그 X, `#` 3개 이하 X)**
     - 형식: `#### [4자코드] FIR이름` (정확히 `#` 4개 + 공백 1개 + 대괄호)
     - 예: `#### [RJJJ] Fukuoka FIR`, `#### [RKRR] Incheon FIR`, `#### [KZAK] Oakland Oceanic FIR`
   - 잘못된 예: `[RJJJ] Fukuoka FIR` (#### 없음) → ❌
     - 잘못된 예: `### [RJJJ] Fukuoka FIR` (# 3개만) → ❌
     - 올바른 예: `#### [RJJJ] Fukuoka FIR` (# 4개 + 공백 + 대괄호) → ✅

RULE 7: **녹색 구분선 (FIR 헤더 바로 다음 줄에 필수!)**:
   - 형식: `<div style="border-top: 3px solid #28a745; margin: 10px 0;"></div>`
   - **모든 FIR 헤더 다음에 반드시 삽입**
   - **빈 줄 없이 바로 다음 줄에 삽입**
     - **실제 출력 예시 (정확히 이 형식으로 출력):**
         ```
         #### [RKRR] Incheon FIR
         <div style="border-top: 3px solid #28a745; margin: 10px 0;"></div>
         **[Z1233/25]:** ...
         ```

RULE 8: **NOTAM 번호 형식 통일**: `**[NOTAM번호]:**` (대괄호 + 콜론, 예: `**[Z1233/25]:**`)
   - ❌ 틀린 예: `[RJJJ NOTAM 111]:`, `[A4735/25]` (굵게 표시 없음), `NOTAM #87`
   - ✅ 올바른 예: `**[Z1233/25]:**`, `**[Q2551/25]:**`, `**[A4735/25]:**`

RULE 9: **날짜/시간 완전 제거 - 절대 준수**: 다음 모든 시간/날짜 정보를 **100% 제거**하십시오:
  - ❌ 한국어 날짜: "11월 1일", "10월 31일", "12월 30일", "11월 20일"
  - ❌ 한국어 시간: "10:31 UTC", "15:54 UTC", "16:14 UTC", "23:00 UTC", "21:00 UTC"
  - ❌ 한국어 날짜+시간: "11월 1일 10:31 UTC부터", "10월 31일 15:54 UTC부터 12월 30일 16:14 UTC까지", "11월 1일 10:40 UTC부터 11월 20 UTC까지"
  - ❌ 영어 날짜: "2025-10-27", "25OCT25", "24MAR23", "30SEP25", "22OCT25"
  - ❌ 영어 시간: "16:00 UTC", "0000-2359", "12:10 UTC", "04:55 UTC"
  - ❌ 시간 범위: "10:31 UTC부터 11:01 UTC까지", "05:00 UTC부터 21:00 UTC까지", "19:00 UTC부터 11월 2일 08:00 UTC까지"
  - ❌ 특수 표기: UFN, PERM, "영구적으로", "현재까지"
  - ✅ **모든 NOTAM 설명에서 날짜/시간을 완전히 삭제하고 내용만 남기십시오**
  - ✅ 예시: 
    - ❌ 잘못됨: "11월 1일 10:31 UTC부터 11월 01 UTC까지 고도 FL600 이하에서 MASTA-UPGOS 구간에 조건부 항로(CDR2)가 설정됩니다."
    - ✅ 올바름: "고도 FL600 이하에서 MASTA-UPGOS 구간에 조건부 항로(CDR2)가 설정됩니다."
    - ❌ 잘못됨: "10월 31일 15:54 UTC부터 12월 30일 16:14 UTC까지 KSLV II 발사로 인한 영향이 있습니다."
    - ✅ 올바름: "KSLV II(Korea Space Launch Vehicle II) 발사로 인한 영향이 있습니다."

RULE 10: **모든 FIR 섹션 생성**: Package 3에서 추출된 실제 FIR 전체에 대해 헤더 필수 생성 (actual_fir_list / fir_order 기반)

RULE 11: **항로 필터링 엄격 적용 - 다음 NOTAM은 무조건 제외:**
     - ❌ **출발/도착 공항에서 100km 이상 떨어진 공역** (항로와 거리/구간 불일치)
   - ❌ **항로와 무관한 지역 공역** (항로가 해당 지역을 통과하지 않으면 제외)
   - ❌ **특정 공항 내부 시설** (RWY, TWY, APRON, GATE, SID/STAR, 특정 공항 CTA)
   - ❌ **항로에 없는 항로명/웨이포인트** (SADLI, ATOTI, MUGUS 등 - 항로에 있는지 꼭 확인!)
   - ❌ **항로 좌표와 1000km 이상 떨어진 좌표** (35N129E vs N17E139 = 2000km)
   - ✅ **포함 가능**: 항로 항로명/웨이포인트 매칭, FIR 전역 GPS/통신 장애, 항로 통과 지역 공역, PACOTS/TDM

RULE 11-1: **공역(Airspace) 포함 판단 기준:**
   - CTA, TRA, Restricted Area 등 공역은 **항로가 실제로 그 공역을 통과하는지** 확인
     - 예1: 항로 좌표/구간과 멀리 떨어진 다른 지역 공역은 제외
   - 예2: "RKSI..N17E139" 항로인데 "35N129E TRA" → 35N과 N17E는 1800km 차이 → ❌ 제외
   - 예3: "FIR 전역 GPS 간섭" → 모든 항공편 영향 → ✅ 포함
     - 특정 지역의 공역이 항로의 실제 통과 경로와 지리적으로 크게 벗어나면 제외
   - **⚠️ 공역 제한/금지 구역 NOTAM 분석 시 고도 정보와 위치 정보 필수 포함!**
     - NOTAM에 F)SFC G)7000FT AMSL 같은 고도 정보가 있으면 반드시 분석 결과에 포함
     - COMMENT) 필드에 위치 정보(예: INCLUDE WJU)가 있으면 반드시 포함
     - F)는 Lower(하한), G)는 Upper(상한) 고도를 의미
     - 고도 정보 형식: "위치명 SFC~7000FT" 또는 "위치명 하한고도~상한고도"
     - 예: "F)SFC G)7000FT AMSL COMMENT) INCLUDE WJU" → "WJU SFC~7000FT"
     - 예: "F)SFC G)1641FT AMSL" → "SFC~1641FT" (COMMENT가 없으면 위치명 생략 가능)
     - 고도 범위를 명시하여 항공편이 해당 고도에서 비행할 때 영향을 받는지 표시

RULE 12: **한국어 작성**: 모든 설명 한국어 (NOTAM 번호, 기술 용어만 영어)
</critical_rules>

**🎯 최종 검증 체크리스트 (출력 전 필수 확인):**
✅ 항로에 태평양 좌표(N17E139 등) 있는가? → RJJJ PACOTS (Q2551 등) + KZAK TDM (A4731 등) 포함했는가?
✅ **각 NOTAM이 항로의 항로명/웨이포인트/좌표 중 하나를 언급하는가?**
✅ **항로에 없는 SADLI, ATOTI, KABAM, MUGUS, ONIKU 등 웨이포인트만 언급하는 NOTAM 제외했는가?**
✅ **항로와 무관한 특정 지역 공역을 제외했는가?** (거리/구간 불일치)
✅ 35N129E 같은 먼 좌표 NOTAM 제외했는가?
✅ **모든 FIR 헤더를 정확히 `#### [코드] 이름` 형식으로 작성했는가?** (# 4개 + 공백 + 대괄호)
✅ **모든 FIR 헤더 바로 다음 줄에 녹색 구분선 삽입했는가?**
✅ **FIR 출력 순서가 지시된 순서와 일치하는가?**
✅ NOTAM 번호 형식 `**[Z1233/25]:**` 맞는가? (굵게 표시 + 대괄호 + 콜론)
✅ **날짜/시간 정보 모두 제거했는가? (한국어 날짜 "11월 1일", "10월 31일" 등 포함, 영어 날짜/시간, UTC 시간 등 모든 형식 제거 확인)**

**🚨 Flow Control NOTAM 특별 규칙:**
- Flow Control, CDR 관련 NOTAM은 해당 FIR 블록의 하단에 "운영 정보"로 간략히 정리
- 실제 항로/시설/공역 변경은 동일 FIR 블록 내 일반 NOTAM 항목으로 표기

**최종 지시:** 
1. **위 체크리스트 전 항목 확인 후 출력**
2. 불필요한 서론 생략하고 FIR 블록부터 시작
3. <output_format> 구조 100% 준수, 모든 <critical_rules> 절대 준수
4. **각 NOTAM이 항로의 항로명/웨이포인트/좌표를 언급하는지 다시 한번 확인**
5. **🚨 날짜/시간 제거 최종 확인: 출력 전 모든 NOTAM 설명에서 다음 패턴이 있는지 재검토:**
   - "월 일" (예: "11월 1일", "10월 31일")
   - "UTC" (예: "10:31 UTC", "15:54 UTC부터")
   - "부터", "까지" (날짜/시간과 함께 사용된 경우)
   - 숫자+시간 형식 (예: "2025-10-27", "25OCT25", "0000-2359")
   - **위 패턴이 발견되면 즉시 제거하고 내용만 남기십시오**
"""
    
    def _remove_date_time_from_notam_text(self, text: str) -> str:
        """NOTAM 텍스트에서 날짜/시간 정보 제거 (전처리) - 한국어 및 영어 모두 처리"""
        import re
        
        result = text
        
        # 0. 라인 선두에 붙은 날짜 대괄호 프리픽스 제거: [24MAR25 12:00 - 25MAR25 15:00]:
        result = re.sub(r'^\[[^\]]{5,}\]\s*:\s*', '', result)
        # 0-1. 제거 후 앞에 남는 고아 토큰 정리: ]:, ] : 등
        result = re.sub(r'^\]\s*:\s*', '', result)
        
        # 한국어 날짜/시간 패턴 제거 (먼저 처리)
        # "11월 1일", "10월 31일", "12월 30일" 등
        result = re.sub(r'\d{1,2}월\s+\d{1,2}일', '', result)
        # "11월 1일 10:31 UTC부터", "10월 31일 15:54 UTC부터 12월 30일 16:14 UTC까지" 등
        result = re.sub(r'\d{1,2}월\s+\d{1,2}일\s+\d{2}:\d{2}\s*UTC(?:부터|까지)?', '', result)
        result = re.sub(r'\d{1,2}월\s+\d{1,2}일\s+\d{2}:\d{2}\s*UTC부터\s+\d{1,2}월\s+\d{1,2}일\s+\d{2}:\d{2}\s*UTC까지', '', result)
        result = re.sub(r'\d{1,2}월\s+\d{1,2}일\s+\d{2}:\d{2}\s*UTC부터\s+\d{1,2}월\s+\d{1,2}일\s+\d{2}:\d{2}\s*UTC까지', '', result)
        # "10:31 UTC부터", "15:54 UTC까지", "05:00 UTC부터 21:00 UTC까지" 등
        result = re.sub(r'\d{2}:\d{2}\s*UTC(?:부터|까지)?', '', result)
        result = re.sub(r'\d{2}:\d{2}\s*UTC부터\s+\d{2}:\d{2}\s*UTC까지', '', result)
        # "부터", "까지" 단독 제거 (날짜/시간과 함께 사용된 경우)
        result = re.sub(r'\s+부터\s+', ' ', result)
        result = re.sub(r'\s+까지\s+', ' ', result)
        
        # 1. 모든 날짜 패턴 제거 (더 포괄적으로)
        # 년월일 + 시간 조합
        result = re.sub(r'\d{4}년\s+\d{1,2}월\s+\d{1,2}일\s+\d{1,2}:\d{2}\s*Z[^\s]*', '', result)
        # 년월일 ~ 년월일 + 시간
        result = re.sub(r'\d{4}년\s+\d{1,2}월\s+\d{1,2}일[^\s]*부터\s+\d{4}년\s+\d{1,2}월\s+\d{1,2}일[^\s]*까지', '', result)
        # 년월일 ~ 까지
        result = re.sub(r'\d{4}년\s+\d{1,2}월\s+\d{1,2}일[^\s]*까지', '', result)
        # 년월일부터
        result = re.sub(r'\d{4}년\s+\d{1,2}월\s+\d{1,2}일[^\s]*부터', '', result)
        # 월일 ~ 월일
        result = re.sub(r'\d{1,2}월\s+\d{1,2}일[^\s]*부터\s+\d{1,2}월\s+\d{1,2}일[^\s]*까지', '', result)
        # 월일까지
        result = re.sub(r'\d{1,2}월\s+\d{1,2}일[^\s]*까지', '', result)
        # 월일부터
        result = re.sub(r'\d{1,2}월\s+\d{1,2}일[^\s]*부터', '', result)
        
        # 2. 숫자 날짜 형식 (예: 25OCT25)
        result = re.sub(r'\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*Z[^\s]*', '', result)
        result = re.sub(r'\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*Z부터\s+\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*Z까지', '', result)
        result = re.sub(r'\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*Z까지', '', result)
        result = re.sub(r'\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*Z부터', '', result)
        
        # 2-1. "26일 08:00Z까지", "25일 22:00Z까지" 같은 형식 제거
        result = re.sub(r'\d{1,2}일\s+\d{2}:\d{2}\s*Z까지', '', result)
        result = re.sub(r'\d{1,2}일\s+\d{2}:\d{2}\s*Z부터', '', result)
        
        # 2-2. "11월 20일 15:00Z까지", "10월 28일 08:00Z까지", "12월 31일 23:59Z까지" 형식 제거
        result = re.sub(r'\d{1,2}월\s+\d{1,2}일\s+\d{2}:\d{2}\s*Z까지', '', result)
        result = re.sub(r'\d{1,2}월\s+\d{1,2}일\s+\d{2}:\d{2}\s*Z부터', '', result)
        
        # 2-3. "21:00Z까지", "14:30Z까지" 같은 시간만 있는 패턴 제거
        result = re.sub(r'\d{2}:\d{2}\s*Z까지', '', result)
        result = re.sub(r'\d{2}:\d{2}\s*Z부터', '', result)
        
        # 2-4. "2510251900부터 2510260800까지" 같은 년월일시 분리된 형식 제거
        result = re.sub(r'\d{10}부터\s+\d{10}까지', '', result)
        result = re.sub(r'\d{10}부터', '', result)
        result = re.sub(r'\d{10}까지', '', result)
        
        # 3. UFN, PERM, 영구
        result = re.sub(r'영구적으로', '', result)
        result = re.sub(r'PERM까지', '', result)
        result = re.sub(r'UFN까지', '', result)
        result = re.sub(r'상시적으로', '', result)
        result = re.sub(r'현재까지', '', result)
        
        # 4. "까지"로 끝나는 모든 날짜 표현
        result = re.sub(r'\d{4}년\s+\d{1,2}월\s+\d{1,2}일\s+\d{1,2}:\d{2}\s*Z까지', '', result)
        result = re.sub(r'\d{1,2}월\s+\d{1,2}일[^\s]*까지', '', result)
        
        # 5. "부터"로 시작하는 모든 날짜 표현
        result = re.sub(r'\d{4}년\s+\d{1,2}월[^\s]*부터', '', result)
        result = re.sub(r'\d{1,2}월[^\s]*부터', '', result)
        
        # 6. 완전한 날짜(년월일만)
        result = re.sub(r'\d{4}년\s+\d{1,2}월\s+\d{1,2}일', '', result)
        
        # 여러 공백 정리
        result = re.sub(r'\s+', ' ', result)
        result = re.sub(r'\s+마십시오', ' 마십시오', result)
        result = re.sub(r'\s+입니다', ' 입니다', result)
        result = re.sub(r'\s+\.', '.', result)  # 마침표 앞 공백 제거
        
        return result.strip()
    
    def _clean_analysis_result(self, text: str) -> str:
        """AI 분석 결과를 정리 및 검증 (후처리)"""
        if not text:
            return text
        
        lines = text.split('\n')
        cleaned_lines = []
        
        for line in lines:
            original_line = line
            line = line.strip()
            if not line:
                continue
                
            # 중복된 내용 제거
            if line in cleaned_lines:
                continue
                
            # 불필요한 패턴 제거
            if any(pattern in line.lower() for pattern in ['번역:', 'translation:', '이건 필요없는']):
                continue
            
            # 날짜/시간 정보 제거 (후처리) - 모든 라인에 적용 (헤더 제외)
            # "⚠️", "🔹", "####", "기준 시간" 시작하는 라인만 제외
            if not (line.startswith('⚠️') or line.startswith('🔹') or line.startswith('#') or '기준 시간' in line or '경로 직접 영향' in line):
                line = self._remove_date_time_from_notam_text(line)
            
            # NOTAM 번호 검증 및 수정
            line = self._validate_notam_numbers(line)

            # 시간 문구만 남은 빈약한 문장(예: "[Z1234/25]: 06:00부터 08:00까지 적용되는 NOTAM입니다.") 제거
            try:
                import re as _re_chk
                # 굵게 처리 전/후 모두 커버: '**[Z1234/25]:** ...' 또는 '[Z1234/25]: ...'
                m = _re_chk.match(r"^(?:\*\*)?\[([A-Z][0-9]{4}\/[0-9]{2})\]:\*\*?\s*(.+)$", line)
                if not m:
                    m = _re_chk.match(r"^\[([A-Z][0-9]{4}\/[0-9]{2})\]:\s*(.+)$", line)
                if m:
                    tail = m.group(2)
                    # '부터 ~ 까지 적용되는 NOTAM입니다' 류 문구만 있는지 판정
                    if _re_chk.fullmatch(r".*?\d{1,2}:\d{2}.*?부터.*?\d{1,2}:\d{2}.*?까지.*?(적용되는\s*NOTAM입니다\.?|적용됩니다\.?|유효합니다\.?)\s*", tail) or \
                       _re_chk.fullmatch(r".*?(적용되는\s*NOTAM입니다\.?|적용됩니다\.?|유효합니다\.?)\s*", tail):
                        # 내용이 없다고 판단하여 이 라인은 스킵
                        continue
            except Exception:
                pass
            
            # FIR 헤더 형식 검증 및 수정
            line = self._validate_fir_headers(line)

            # 프론트에서 카테고리 배지를 처리하므로 백엔드에서는 주석/아이콘을 추가하지 않습니다.
            
            # 잘못된 FIR 해석 수정 (한국어)
            if '평양(RKRR)' in line or '평양 (RKRR)' in line:
                line = line.replace('평양(RKRR)', '서울(RKRR)')
                line = line.replace('평양 (RKRR)', '서울 (RKRR)')
                logger.warning("AI가 잘못 해석한 RKRR을 서울 FIR로 수정했습니다.")
            
            # 잘못된 FIR 해석 수정 (영어)
            if 'Pyongyang (RKRR)' in line or 'Pyongyang(RKRR)' in line:
                line = line.replace('Pyongyang (RKRR)', 'Seoul (RKRR)')
                line = line.replace('Pyongyang(RKRR)', 'Seoul(RKRR)')
                logger.warning("AI가 잘못 해석한 RKRR을 Seoul FIR로 수정했습니다.")
            
            # 일반적인 RKRR 오해석 수정
            if 'RKRR' in line and ('평양' in line or 'Pyongyang' in line):
                line = line.replace('평양', '서울')
                line = line.replace('Pyongyang', 'Seoul')
                logger.warning("RKRR과 함께 언급된 잘못된 지명을 수정했습니다.")
                
            cleaned_lines.append(line)
        
        result = '\n'.join(cleaned_lines)
        
        # FIR 헤더 정규화: [CODE] FIR이름 → #### [CODE] FIR이름
        # AI가 #### 없이 출력한 경우 추가
        try:
            # [CODE] FIR이름 패턴을 #### [CODE] FIR이름으로 변환
            # 단, 이미 #### 로 시작하지 않는 경우만
            result = re.sub(
                r"^(?!####)\[([A-Z]{4})\]\s+(.+?)$",
                r"#### [\1] \2",
                result,
                flags=re.MULTILINE
            )
            logger.info("✅ FIR 헤더 정규화 완료 (#### 추가)")
        except Exception as e:
            logger.warning(f"FIR 헤더 정규화 실패(무시하고 진행): {e}")
        
        # FIR 헤더 다음에 녹색 구분선이 누락된 경우 자동 삽입
        try:
            result = re.sub(
                r"(^#### \[[A-Z]{4}\][^\n]*\n)(?!<div style=\"border-top: 3px solid #28a745; margin: 10px 0;\"></div>\n)",
                r"\1<div style=\"border-top: 3px solid #28a745; margin: 10px 0;\"></div>\n",
                result,
                flags=re.MULTILINE
            )
            logger.info("✅ 녹색 구분선 자동 삽입 완료")
        except Exception as e:
            logger.debug(f"녹색 구분선 자동 삽입 스킵: {e}")

        # div의 이스케이프된 따옴표(\")를 정상 따옴표(")로 정규화
        result = result.replace('<div style=\\"border-top: 3px solid #28a745; margin: 10px 0;\\"></div>',
                                 '<div style="border-top: 3px solid #28a745; margin: 10px 0;"></div>')
        result = result.replace('<div style=\\"border-top: 3px solid #28a745; margin: 10px 0;\\\"></div>',
                                 '<div style="border-top: 3px solid #28a745; margin: 10px 0;"></div>')

        # 내용이 비어있는 FIR 블록에 기본 메시지 보강
        try:
            import re as _re
            def _fill_empty_block(m):
                header = m.group(1)
                divider = m.group(2)
                body = m.group(3)
                if not body.strip():
                    body = "해당 항로와 관련된 NOTAM이 없습니다.\n"
                return f"{header}{divider}{body}\n\n---\n\n"

            pattern = _re.compile(
                r"(#### \[[A-Z]{4}\][^\n]*\n)(<div style=\"border-top: 3px solid #28a745; margin: 10px 0;\"></div>\n)([\s\S]*?)(?=^#### \[|\Z)",
                _re.MULTILINE
            )
            result = pattern.sub(_fill_empty_block, result)
        except Exception as e:
            logger.debug(f"빈 FIR 블록 보강 스킵: {e}")

        # 최종 검증 로그
        logger.info("=== 분석 결과 후처리 완료 ===")
        logger.info(f"전체 라인 수: {len(cleaned_lines)}")
        
        # 최종 강제 정규화: 섹션 잔존 또는 비표준 FIR 헤더가 있으면 전체를 FIR 블록으로 재조립
        try:
            if re.search(r"^#{0,2}\s*[I|II|III]\.\s*", result, re.MULTILINE) or not re.search(r"^#### \[[A-Z]{4}\]", result, re.MULTILINE):
                rebuilt = self._rebuild_fir_blocks_from_any(result)
                if rebuilt.strip():
                    result = rebuilt
        except Exception as e:
            logger.warning(f"최종 FIR 재조립 스킵: {e}")
        
        # 결과 전반에 NOTAM 라인 주석(카테고리/아이콘) 보강
        try:
            result = self._annotate_all_notam_lines(result)
        except Exception:
            pass

        return result

    def _convert_sectioned_to_fir_only(self, text: str) -> str:
        """[사용 안 함] 모델이 I/II/III 섹션으로 출력했을 때 FIR 단일 형식으로 변환합니다.
        
        이 함수는 더 이상 사용되지 않습니다. 현재 시스템은 단일 FIR 형식만 사용합니다.
        """
        # 이 함수는 사용되지 않으므로 바로 반환
        return text
        
        # 아래 코드는 사용되지 않음 (I/II/III 섹션 형식은 더 이상 지원하지 않음)
        # 함수는 단일 FIR 형식만 사용하는 현재 시스템에서는 실행되지 않음

    def _rebuild_fir_blocks_from_any(self, text: str) -> str:
        """본문 전체를 스캔해 FIR 블록으로 재조립하는 최후의 안전장치.
        지원 헤더 패턴:
          1) #### [CODE] Name
          2) [CODE] Name
          3) Name (CODE): 또는 Name (CODE)
        """
        import re

        s = text
        # 모든 헤더 후보를 하나의 목록으로 수집 (start index, code, name)
        headers = []

        for m in re.finditer(r"^#### \[([A-Z]{4})\]\s+([^\n:]+)(?::)?\s*$", s, re.MULTILINE):
            headers.append((m.start(), m.group(1), m.group(2).strip()))

        for m in re.finditer(r"^\[([A-Z]{4})\]\s+([^\n:]+)(?::)?\s*$", s, re.MULTILINE):
            headers.append((m.start(), m.group(1), m.group(2).strip()))

        for m in re.finditer(r"^([^\n]+?)\s*\(([A-Z]{4})\)\s*:?\s*$", s, re.MULTILINE):
            headers.append((m.start(), m.group(2), m.group(1).strip()))

        if not headers:
            return text  # 헤더가 없으면 원문 반환

        # 시작 위치로 정렬
        headers.sort(key=lambda x: x[0])

        parts = []
        for idx, (pos, code, name) in enumerate(headers):
            start = pos
            end = headers[idx + 1][0] if idx + 1 < len(headers) else len(s)
            # 본문 추출 (헤더 라인 제외)
            block_text = s[start:end]
            # 헤더 라인을 제거
            block_text = re.sub(r"^.*$\n?", "", block_text, count=1, flags=re.MULTILINE)
            body = block_text.strip()
            # 운영 정보 힌트 보강
            ops = []
            if hasattr(self, '_fir_ops_hints'):
                ops = self._fir_ops_hints.get(code) or []
            if ops:
                body = (body + "\n\n" if body else "") + "운영 정보\n" + "\n".join(ops)
            header = f"#### [{code}] {name}\n<div style=\"border-top: 3px solid #28a745; margin: 10px 0;\"></div>\n"
            parts.append(header + ("\n" + body if body else "\n해당 항로와 관련된 NOTAM이 없습니다.") + "\n\n---\n\n")

        return "".join(parts).strip()

    def _extract_operational_hints_from_fir_content(self, fir_content: str) -> List[str]:
        """FIR 섹션 원문에서 운영 정보(ADS-C/CPDLC/LOGON/ADS-B 등) 키워드 기반 요약 라인 생성"""
        hints: List[str] = []
        text = fir_content.upper()
        def add(msg: str) -> None:
            if msg not in hints:
                hints.append(msg)
        # CPDLC/LOGON
        if 'CPDLC' in text or 'LOGON' in text:
            if 'ADDRESS' in text or 'LOGON ADDRESS' in text or 'READ BACK' in text:
                add('CPDLC 로그온/주소 전달 절차 준수(로그온 주소 읽어내기, FPL 식별/등록 일치 확인)')
            else:
                add('CPDLC 서비스/절차 관련 운영 정보 확인 필요')
        # ADS-C
        if 'ADS-C' in text:
            add('ADS-C 데이터링크 운용: 인접 FIR 진입 시 자동 연결 전송 예상')
        # ADS-B
        if 'ADS-B' in text:
            if 'SPACE-BASED' in text:
                add('우주 기반 ADS-B 운용 개시(감시 품질 개선)')
            else:
                add('ADS-B 관련 운영 정보 확인')
        # 데이터 링크 일반
        if 'DATA LINK' in text or 'FANS 1/A' in text:
            add('데이터 링크(FANS 1/A) 서비스 적용 안내')
        # 반환 형식: 간결 한국어 라인
        return hints

    def _populate_section_i_if_empty(self, text: str) -> str:
        """Section I이 비어있으면 Section II에서 중요 NOTAM을 승격시킵니다."""
        import re
        
        logger.info("="*80)
        logger.info("🚨🚨 _populate_section_i_if_empty 함수 시작 🚨🚨🚨")
        logger.info("="*80)
        logger.info(f"입력 텍스트 길이: {len(text)}")
        logger.info(f"입력 텍스트 첫 500자:\n{text[:500]}")
        logger.info("="*80)
        
        logger.info("🔍 Section I 내용 확인 중...")
        
        # Section I 찾기 (## I. 또는 I. 형식 모두 지원)
        section_i_match = re.search(r"^#{0,2}\s*I\.\s*최우선 조치 사항[^\n]*\n+(.*?)(?=\n*-{3,}\n*#{0,2}\s*II\.|#{0,2}\s*II\.|$)", text, re.MULTILINE | re.DOTALL)
        if not section_i_match:
            logger.warning("⚠️ Section I을 찾을 수 없습니다. 자동으로 추가합니다.")
            # Section II가 있으면 그 앞에 Section I 추가, 없으면 맨 앞에 추가
            section_ii_match = re.search(r"^#{0,2}\s*II\.\s*경로별 주요 영향", text, re.MULTILINE)
            if section_ii_match:
                # Section II 앞에 Section I 추가
                section_i_header = "## I. 최우선 조치 사항 (Immediate Action Required)\n\n"
                section_i_content = "해당 항로에는 즉각 조치가 필요한 NOTAM이 없습니다.\n\n---\n\n"
                insert_position = section_ii_match.start()
                text = text[:insert_position] + section_i_header + section_i_content + text[insert_position:]
                logger.info("✅ Section I이 추가되었습니다 (Section II 앞)")
            else:
                # 맨 앞에 Section I 추가
                section_i_header = "## I. 최우선 조치 사항 (Immediate Action Required)\n\n"
                section_i_content = "해당 항로에는 즉각 조치가 필요한 NOTAM이 없습니다.\n\n---\n\n"
                text = section_i_header + section_i_content + text
                logger.info("✅ Section I이 추가되었습니다 (맨 앞)")
            # 다시 Section I 찾기
            section_i_match = re.search(r"^#{0,2}\s*I\.\s*최우선 조치 사항[^\n]*\n+(.*?)(?=\n*-{3,}\n*#{0,2}\s*II\.|#{0,2}\s*II\.|$)", text, re.MULTILINE | re.DOTALL)
            if not section_i_match:
                logger.error("❌ Section I 추가 후에도 찾을 수 없습니다")
                return text
        
        logger.info(f"✅ Section I 발견됨")
        section_i_content = section_i_match.group(1).strip()
        logger.info(f"Section I 내용 길이: {len(section_i_content)}")
        logger.info(f"Section I 내용:\n{section_i_content[:300]}")

            # Section I에서 프롬프트/지침/출력 안내/예시 등 제거

        # Section I에서 실제 NOTAM 또는 absence message만 남기고, 그 앞뒤 모든 안내문/지침/예시/설명 블록 제거
        # [Zxxxx/xx]: 또는 absence message만 남김
        # NOTAM 패턴: **[NOTAM번호]: 또는 [NOTAM번호]: 형식 모두 지원
        notam_block_pattern = r'(\*{0,2}\[[A-Z]\d{4}/\d{2}\]:.*?)(?=\n{2,}|$|\n\*{0,2}\[|\n해당 항로|즉각 조치)'
        notam_blocks = re.findall(notam_block_pattern, section_i_content, re.DOTALL | re.MULTILINE)
        # NOTAM 블록에서 설명 부분만 추출 (NOTAM 번호 줄과 그 다음 줄들)
        if notam_blocks:
            # 각 NOTAM 블록을 정리
            cleaned_blocks = []
            for block in notam_blocks:
                block = block.strip()
                # NOTAM 번호로 시작하는지 확인
                if re.match(r'\*{0,2}\[[A-Z]\d{4}/\d{2}\]:', block):
                    # 앞뒤 불필요한 문자 제거 및 ** 추가
                    if not block.startswith('**'):
                        block = '**' + block.lstrip('*') if block.startswith('*') else '**' + block
                    cleaned_blocks.append(block)
            notam_blocks = cleaned_blocks
        
        # "없습니다" 메시지 패턴
        absence_patterns = [
            r'즉각 조치가 필요한 NOTAM이 없습니다',
            r'해당 항로에는 즉각 조치가 필요한 NOTAM이 없습니다'
        ]
        has_absence_message = any(re.search(pattern, section_i_content, re.IGNORECASE) for pattern in absence_patterns)
        
        if notam_blocks:
            # NOTAM이 있으면 NOTAM만 출력 (없습니다 메시지 제거)
            cleaned_section_i_content = '\n\n'.join([block.strip() for block in notam_blocks])
            logger.info(f"✅ Section I에서 {len(notam_blocks)}개 NOTAM 발견. '없습니다' 메시지 제거됨")
        elif has_absence_message:
            # NOTAM이 없고 absence 메시지만 있으면 일관된 메시지로 통일
            cleaned_section_i_content = '해당 항로에는 즉각 조치가 필요한 NOTAM이 없습니다.'
            logger.info("✅ Section I에 absence 메시지만 있음")
        else:
            # Section I이 비어있거나 설명만 있는 경우 일관된 메시지 출력
            cleaned_section_i_content = '해당 항로에는 즉각 조치가 필요한 NOTAM이 없습니다.'
            logger.info("⚠️ Section I이 비어있음. 기본 메시지 추가")
        text = re.sub(
            r'(^#{0,2}\s*I\.\s*최우선 조치 사항[^\n]*\n+)(.*?)(?=\n*-{3,}\n*#{0,2}\s*II\.|#{0,2}\s*II\.|$)',
            r'\1' + cleaned_section_i_content + '\n',
            text,
            flags=re.MULTILINE | re.DOTALL
        )

        
        # Section I이 비어있는지 확인 (3가지 조건 모두 체크)
        is_empty_message = (
            "즉각 조치가 필요한 NOTAM이 없습니다" in cleaned_section_i_content or
            "해당 항로에는 즉각 조치가 필요한 NOTAM이 없습니다" in cleaned_section_i_content or
            "중대한 NOTAM을 포함합니다" in cleaned_section_i_content  # AI가 설명 문구만 출력한 경우
        )
        
        if not is_empty_message and cleaned_section_i_content and len(cleaned_section_i_content) > 100:
            logger.info("✅ Section I에 이미 실제 NOTAM 내용이 있습니다")
            return text
        
        logger.warning("⚠️ Section I이 비어있습니다. Section II에서 중요 NOTAM 검색 중...")
        
        # Section II에서 중요한 키워드를 포함하는 NOTAM 찾기
        critical_keywords = [
            r'GPS.*(불안정|손실|신호|unavailable|jamming|interference)',
            r'GNSS.*(불안정|손실|신호|unavailable|interference)',
            r'(GPS|GNSS|SBAS).*신호.*(불안정|손실)',
            r'(VOR|DME|NDB|VORTAC).*사용(\s*불가|불가|중단|out of service|unserviceable|교체)',
            r'(군사|military|미군).*활동',
            r'(금지|제한|prohibited|restricted).*구역',
            r'(미사일|로켓|missile|rocket).*발사',
            r'항로.*(폐쇄|사용\s*불가|closed|not available)',
            r'(통과|transit).*(금지|prohibited)',
            r'FL\d+.*(사용\s*불가|not available)',
            r'GPS.*주의',
            r'GPS.*각별한 주의',
            r'VORTAC.*사용 불가',
            r'GPS.*대체 항법',
            r'GPS.*불안정',
            r'GPS.*손실',
        ]
        
        # Section II 찾기 (## II. 또는 II. 형식 모두 지원)
        section_ii_match = re.search(r"^#{0,2}\s*II\.\s*경로별 주요 영향[^\n]*\n+(.*?)(?=\n+#{0,2}\s*III\.|$)", text, re.MULTILINE | re.DOTALL)
        if not section_ii_match:
            logger.warning("Section II를 찾을 수 없습니다")
            return text
        
        section_ii_content = section_ii_match.group(1)
        logger.info(f"📊 Section II 길이: {len(section_ii_content)} 문자")
        logger.info(f"📊 Section II 첫 500자:\n{section_ii_content[:500]}")
        try:
            section_ii_match = re.search(r"^#{0,2}\s*II\.\s*경로별 주요 영향[^\n]*\n+(.*?)(?=\n+#{0,2}\s*III\.|$)", text, re.MULTILINE | re.DOTALL)
            if not section_ii_match:
                logger.warning("Section II를 찾을 수 없습니다")
                return text
            section_ii_content = section_ii_match.group(1)
            logger.info(f"📊 Section II 길이: {len(section_ii_content)} 문자")
            logger.info(f"📊 Section II 첫 500자:\n{section_ii_content[:500]}")
        except Exception as e:
            logger.error(f"❌ Section II 추출 중 오류: {e}")
            return text
        
        # RKRR 포함 여부 확인
        if "RKRR" in section_ii_content:
            logger.info("✅ Section II에 RKRR FIR 발견됨")
        else:
            logger.warning("⚠️ Section II에 RKRR FIR이 없습니다!")
        
        # GPS 키워드 포함 여부 확인
        if "GPS" in section_ii_content or "GNSS" in section_ii_content:
            logger.info("✅ Section II에 GPS/GNSS 키워드 발견됨")
        else:
            logger.warning("⚠️ Section II에 GPS/GNSS 키워드가 없습니다!")
        
        # 중요 NOTAM 수집
        critical_notams = []
        
        # FIR 블록별로 처리
        fir_blocks = re.finditer(r'#### \[([A-Z]{4})\](.*?)(?=#### \[|^#{0,2}\s*III\.|$)', section_ii_content, re.MULTILINE | re.DOTALL)
        
        fir_blocks_list = list(fir_blocks)
        logger.info(f"🗺️ Section II에서 발견된 FIR 블록 수: {len(fir_blocks_list)}")
        
        for fir_match in fir_blocks_list:
            try:
                fir_code = fir_match.group(1)
                fir_content = fir_match.group(2)
                logger.info(f"🔍 [{fir_code}] FIR 블록 검사 중... (길이: {len(fir_content)})")
                
                # 각 NOTAM 항목 찾기 (** 포함 여부 모두 지원)
                # NOTAM 추출: [Z1140/25]: ... 여러 줄 설명도 포함
                notam_items = re.finditer(r'\[([A-Z]\d{4}/\d{2})\]:\s*((?:[^\n]*\n?)+?)(?=\n\[|\n####|\n+#{0,2}\s*III\.|$)', fir_content)
                
                notam_count = 0
                for notam in notam_items:
                    try:
                        notam_number = notam.group(1)
                        notam_text = notam.group(2).strip()
                        notam_count += 1
                        
                        # 키워드 매칭
                        for keyword_pattern in critical_keywords:
                            if re.search(keyword_pattern, notam_text, re.IGNORECASE):
                                critical_notams.append(f"**[{notam_number}]:** {notam_text}")
                                logger.info(f"  ✅ 중요 NOTAM 발견: [{fir_code}] {notam_number} - {notam_text[:50]}...")
                                break  # 하나의 키워드만 매칭되면 충분
                    except Exception as e:
                        logger.error(f"❌ NOTAM 항목 추출 오류: {e}")
                
                logger.info(f"  ℹ️ [{fir_code}]에서 {notam_count}개 NOTAM 검사 완료")
            except Exception as e:
                logger.error(f"❌ FIR 블록 추출 오류: {e}")
        
        # 중요 NOTAM이 없으면 원본 반환
        if not critical_notams:
            logger.info("  ℹ️ Section II에서 중요 NOTAM을 찾을 수 없습니다")
            logger.info(f"  🔎 Section II 전체 내용: {section_ii_content[:1000]}")
            logger.info(f"  🔎 사용된 키워드: {critical_keywords}")
            return text

        logger.info(f"  ✅ Section II에서 승격된 중요 NOTAM 목록:")
        for idx, notam in enumerate(critical_notams, 1):
            logger.info(f"    [{idx}] {notam[:120]}")

        # Section I 내용을 중요 NOTAM으로 교체
        new_section_i_content = "\n\n".join(critical_notams)

        # ## I. 또는 I. 형식 모두 지원
        new_text = re.sub(
            r"(^#{0,2}\s*I\.\s*최우선 조치 사항[^\n]*\n+).*?(?=\n+#{0,2}\s*II\.)",
            rf"\1{new_section_i_content}\n\n---\n\n",
            text,
            flags=re.MULTILINE | re.DOTALL
        )

        logger.info(f"  ✅ Section I에 {len(critical_notams)}개의 중요 NOTAM 추가됨")

        return new_text
    
    def _add_missing_fir_sections(self, text: str, fir_order: list) -> str:
        """fir_order에 있지만 AI 출력에 누락된 FIR 섹션을 추가합니다 (순서는 _reorder_fir_sections에서 처리)."""
        import re
        
        logger.info(f"🔍 누락된 FIR 섹션 확인 중...")
        
        # 단일 FIR 형식에서만 처리 (II/III 섹션 제거됨)
        # 전체 텍스트에서 현재 존재하는 FIR 찾기
        existing_firs = set()
        for match in re.finditer(r"^#### \[([A-Z]{4})\]", text, re.MULTILINE):
            existing_firs.add(match.group(1))
        
        logger.info(f"  기존 FIR: {existing_firs}")
        
        # 누락된 FIR 찾기
        missing_firs = [fir for fir in fir_order if fir not in existing_firs]
        
        if missing_firs:
            logger.warning(f"  ⚠️ 누락된 FIR 발견: {missing_firs}")
            
            # 텍스트 끝에 누락된 FIR 섹션 추가
            for fir_code in missing_firs:
                fir_name = get_fir_name(fir_code)
                missing_section = f"""
#### [{fir_code}] {fir_name}
<div style="border-top: 3px solid #28a745; margin: 10px 0;"></div>

해당 항로와 관련된 NOTAM이 없습니다.

"""
                text += missing_section
                logger.info(f"  ✅ {fir_code} 섹션 추가됨")
        else:
            logger.info("  ✅ 모든 FIR 섹션이 존재합니다")
        
        return text
    
    def _reorder_fir_sections(self, text: str, fir_order: list) -> str:
        """FIR 블록을 제공된 fir_order 순서로 재정렬합니다.

        - FIR 블록 식별: '#### [CODE] ...' 헤더와 그 다음 블록을 하나로 본다.
        - 재정렬 대상 범위: 전체 텍스트에서 FIR 블록을 찾아 재정렬.
        - 단일 FIR 형식에서 처리 (II/III 섹션 제거됨).
        """
        import re

        logger.info(f"🔄 FIR 섹션 재정렬 시작, 목표 순서: {fir_order}")

        # 단일 FIR 형식에서만 처리 (II/III 섹션 제거됨)
        prefix = ""
        target_section = text
        suffix = ""

        # FIR 블록 추출: 헤더부터 다음 헤더 또는 섹션 끝까지
        # #### [CODE] 형식을 찾음
        block_pattern = re.compile(r"(^#### \[(?P<code>[A-Z]{4})\][^\n]*\n)(?:<div[^\n]*>\n)?(.*?)(?=^#### \[|^III\.|\Z)", re.DOTALL | re.MULTILINE)
        blocks = []
        for m in block_pattern.finditer(target_section):
            code = m.group('code')
            block_text = m.group(0)
            blocks.append((code, block_text))
            logger.info(f"  발견된 FIR 블록: {code} ({len(block_text)} 문자)")

        if not blocks:
            logger.warning("FIR 블록을 찾을 수 없습니다")
            return text

        logger.info(f"총 {len(blocks)}개의 FIR 블록 발견: {[code for code, _ in blocks]}")

        # 코드별로 빠른 조회
        block_map = {code: blk for code, blk in blocks}

        # 제공된 순서대로 재구성, 남은 블록은 기존 순서대로 뒤에 붙임
        used = set()
        reordered_blocks = []
        for code in fir_order:
            if code in block_map:
                reordered_blocks.append(block_map[code])
                used.add(code)
                logger.info(f"  ✅ {code} 블록 추가 (순서대로)")
            else:
                logger.warning(f"  ⚠️ {code} 블록을 찾을 수 없음 (스킵)")

        for code, blk in blocks:
            if code not in used:
                reordered_blocks.append(blk)
                logger.info(f"  ➕ {code} 블록 추가 (순서 외)")

        # 단일 FIR 형식: 전체를 재정렬된 블록으로 교체
        new_section = ''.join(reordered_blocks)

        logger.info(f"✅ FIR 섹션 재정렬 완료: {[code for code in fir_order if code in block_map]}")
        return prefix + new_section + suffix

    def _keep_only_allowed_firs_blocks(self, text: str, allowed_firs: list) -> str:
        """허용된 FIR 코드 블록만 유지합니다. 단일 FIR 형식에서 처리."""
        import re
        try:
            # 단일 FIR 형식에서만 처리 (II/III 섹션 제거됨)
            prefix = ""
            target_section = text
            suffix = ""

            block_pattern = re.compile(r"(^#### \[(?P<code>[A-Z]{4})\][^\n]*\n)(?:<div[^\n]*>\n)?([\s\S]*?)(?=^#### \[|^III\.|\Z)", re.MULTILINE)
            kept_blocks = []
            for m in block_pattern.finditer(target_section):
                code = (m.group('code') or '').upper()
                if code in set(allowed_firs):
                    kept_blocks.append(m.group(0))

            # 단일 FIR 형식: 허용된 블록만 반환
            new_section = ''.join(kept_blocks)

            return prefix + new_section + suffix
        except Exception:
            return text

    def _drop_pacific_track_only_blocks(self, text: str) -> str:
        """PACOTS/TDM 트랙 나열만 있는 RJJJ/KZAK 블록 제거. 단일 FIR 형식에서 처리."""
        import re
        try:
            # 단일 FIR 형식에서만 처리 (II/III 섹션 제거됨)
            prefix = ""
            target_section = text
            suffix = ""

            block_pattern = re.compile(r"(^#### \[(?P<code>RJJJ|KZAK)\][^\n]*\n)(?:<div[^\n]*>\n)?([\s\S]*?)(?=^#### \[|^III\.|\Z)", re.MULTILINE)
            idx = 0
            output = []
            for m in block_pattern.finditer(target_section):
                # append text before this block
                output.append(target_section[idx:m.start()])
                block = m.group(0)
                body = (m.group(2) or '')
                track_markers = len(re.findall(r"\b(PACOTS|OTS|TDM)\b", body))
                notam_items = len(re.findall(r"\*\*\[[A-Z]\d{4}/\d{2}\]:\*\*|\[([A-Z]\d{4}/\d{2})\]:", body))
                # 트랙 단어는 많은데 실제 NOTAM 항목이 거의 없으면 제거
                if track_markers >= 2 and notam_items <= 1:
                    # drop block (skip)
                    pass
                else:
                    output.append(block)
                idx = m.end()
            output.append(target_section[idx:])
            return prefix + ''.join(output) + suffix
        except Exception:
            return text
    
    def _validate_notam_numbers(self, text: str) -> str:
        """NOTAM 번호 검증 및 수정"""
        import re
        
        # AI가 잘못 추출한 "NOTAM #XX" 패턴 제거 (실제 NOTAM 번호가 아님)
        # 예: "NOTAM #81:" → 제거
        text = re.sub(r'NOTAM\s*#\d+:\s*', '', text, flags=re.IGNORECASE)
        
        # "NOTAM:" 다음에 실제 번호가 없는 경우만 제거
        # 예: "NOTAM: 설명..." → "설명..."
        # 단, "NOTAM Z1140/25:" 같은 형식은 유지
        if re.match(r'^NOTAM:\s*[^A-Z0-9]', text, re.IGNORECASE):
            text = re.sub(r'^NOTAM:\s*', '', text, flags=re.IGNORECASE)
        
        # "**NOTAM:**" 같은 잘못된 형식 제거 (실제 NOTAM 번호가 없을 때만)
        # 예: "**NOTAM:** 설명..." → "설명..."
        text = re.sub(r'\*\*NOTAM:\*\*\s*', '', text, flags=re.IGNORECASE)
        
        # 라인 내 임의 위치에 존재하는 실제 NOTAM 번호를 선두로 끌어올려 표준화
        # 1순위: 표준 패턴 [A1234/25]
        # 2순위: SUP 계열 (예: CHINA SUP 16/21, AIP SUP 20/25)
        patterns = [
            r'\b([A-Z]\d{4}/\d{2})\b',
            r'\b([A-Z]{2,}\s+SUP\s+\d+/\d{2})\b',
            r'\b(AIP\s*SUP\s+\d+/\d{2})\b',
            # 예: RCAA AIP ENR 3.2 / RCAA AIP ENR 3.1-5 / RCAA AIP ENR 1.8.2.3
            r'\b([A-Z]{4}\s+AIP\s+ENR\s+[0-9][0-9.\-]*)\b',
        ]
        notam_id = None
        start_idx = None
        for p in patterns:
            m = re.search(p, text)
            if m:
                notam_id = m.group(1)
                start_idx = m.end(1)
                break
        if notam_id:
            # NOTAM ID 이후의 잔여 텍스트 추출 (불필요 접두어/구분자 제거)
            tail = text[start_idx if start_idx is not None else 0:].lstrip(' -:\u00A0\t')
            # 고아 "]:" 토큰 제거
            tail = re.sub(r'^\]\s*:\s*', '', tail)
            # 중복 패턴 정리 "]: ]:" → ":"
            tail = re.sub(r'\]:\s*\]:', ']:', tail)
            # 선행부(날짜/라벨 등) 제거하고 표준 포맷으로 재구성
            text = f"**[{notam_id}]:** {tail}"
        
        return text
    
    def _validate_fir_headers(self, text: str) -> str:
        """FIR 헤더 형식 검증 및 수정"""
        import re
        
        # 패턴 1: "#### [CODE] FIR이름" 형식 검증
        # 예: "#### RKRR INCHEON FIR" → 올바름
        # 예: "RKRR INCHEON FIR" → "#### RKRR INCHEON FIR"로 수정
        
        if re.match(r'^[A-Z]{4}\s+[A-Z\s]+FIR', text):
            # "####"가 없는 경우 추가
            if not text.startswith('#'):
                text = f"#### {text}"
                logger.warning(f"FIR 헤더에 '####' 추가: {text}")
        
        # 패턴 2: 잘못된 FIR 헤더 형식 수정
        # 예: "🔹 RKRR INCHEON FIR" → "#### RKRR INCHEON FIR"
        text = re.sub(r'^🔹\s*([A-Z]{4})\s+(.+FIR)', r'#### \1 \2', text)
        
        # 패턴 3: 녹색 바 검증 (HTML div)
        # <div style="border-top: 3px solid #28a745; ...>가 있어야 하는데 없으면 추가
        
        return text

    def _looks_like_notam_item(self, text: str) -> bool:
        """해당 라인이 NOTAM 항목 형식인지 간단 판별"""
        import re
        if re.match(r"^\*\*\[[A-Z]\d{4}/\d{2}\]:\*\*", text):
            return True
        if re.match(r"^\[([A-Z]\d{4}/\d{2})\]:", text):
            return True
        return False

    def _annotate_notam_line(self, text: str) -> str:
        """NOTAM 항목 라인 앞에 카테고리/행동 필요 여부 태그를 자동 부착"""
        # 프론트엔드에서 배지를 자동 삽입하므로, 백엔드는 라인을 수정하지 않습니다.
        return text

    def _annotate_all_notam_lines(self, text: str) -> str:
        """백엔드에서 카테고리 주석을 붙이지 않습니다(프론트에서 처리)."""
        return text


# 전역 인스턴스 생성
ai_analyzer = AIRouteAnalyzer()


def analyze_route_with_gemini(route: str, notam_data: list, **kwargs) -> str:
    """
    GEMINI를 사용한 항로 분석 함수 (기존 호환성 유지)
    
    Args:
        route: 분석할 항로
        notam_data: NOTAM 데이터 리스트
        **kwargs: 추가 옵션들
        
    Returns:
        분석 결과 문자열
    """
    return ai_analyzer.analyze_route(route, notam_data, **kwargs)


# 테스트 함수 제거됨 (필요시 별도 테스트 파일로 분리)
