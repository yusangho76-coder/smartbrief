"""
통합 NOTAM 번역기 - 번역과 요약을 한 번의 API 호출로 처리
번역과 요약의 일관성을 보장하는 통합 파이프라인
"""

import os
import re
import time
import hashlib
import logging
import threading
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FutureTimeoutError
from datetime import datetime
import google.generativeai as genai
from dotenv import load_dotenv

# 학습 모듈 import (선택적)
try:
    from src.gemini_learning import GeminiLearningManager
    LEARNING_AVAILABLE = True
except ImportError:
    LEARNING_AVAILABLE = False
    GeminiLearningManager = None

# 색상 스타일 상수 (다른 파일에서 가져온 것)
RED_STYLE_TERMS = [
        'CLOSED', 'PAVEMENT CONSTRUCTION', 'OUTAGES', 'PREDICTED FOR', 'WILL TAKE PLACE',
        'NPA', 'FLW', 'ACFT', 'NR.', 'ESTABLISHMENT OF', 'INFORMATION OF', 'CIRCLE',
        'CENTERED', 'DUE TO', 'MAINT', 'NML OPS', 'U/S', 'STANDBY', 'AVBL', 'UNAVBL',
        'GPS RAIM', 'OBST', 'FIREWORKS', 'TEMPORARY', 'PERMANENT', 'RESTRICTED',
        'PROHIBITED', 'DANGER', 'CAUTION', 'WARNING', 'EMERGENCY', 'CRITICAL',
        # 한국어 용어들
        '폐쇄', '폐쇄되었습니다', '폐쇄됨', '포장 공사', '공사', '기능 상실', '예측', '예측됩니다',
        '예정', '예정입니다', '발생', '발생합니다', '설립', '정보', '원형', '중심',
        '로 인해', '때문에', '유지보수', '정상 운영', '사용 불가', '대기', '사용 가능',
        '사용 불가능', 'GPS RAIM', '장애물', '불꽃놀이', '임시', '영구', '제한',
        '금지', '위험', '주의', '경고', '비상', '중요', '주의하십시오', '경고하십시오',
        '위험합니다', '금지됩니다', '제한됩니다', '사용 불가능합니다', '폐쇄됩니다',
        '확인', '확인하십시오', '확인됩니다', '차단', '차단하십시오', '차단됩니다',
        '방지', '방지하십시오', '방지됩니다', '손상', '손상하십시오', '손상됩니다',
        '분리', '분리하십시오', '분리됩니다', '닫힘', '닫으십시오', '닫힙니다',
        '전기', '전기적', '전원', '패널', '상부', '하부', '외부', '내부'
    ]

BLUE_STYLE_PATTERNS = [
    r'\bRWY\s*\d{2}[LRC]?(?:/\d{2}[LRC]?)?\b',  # RWY 15L/33R
    r'\bTWY\s*[A-Z](?:\s+AND\s+[A-Z])*\b',  # TWY D, TWY D AND E
    r'\bTWY\s*[A-Z]\d+\b',  # TWY D1
    r'\bAPRON\s*[A-Z]\d*\b',  # APRON A, APRON A1
    r'\bTAXI\s*[A-Z]\d*\b',  # TAXI A, TAXI A1
    r'\bSID\s*[A-Z]\d*\b',  # SID A, SID A1
    r'\bSTAR\s*[A-Z]\d*\b',  # STAR A, STAR A1
    r'\bIAP\s*[A-Z]\d*\b',  # IAP A, IAP A1
    r'\bGPS\b',  # GPS
    r'\bRAIM\b',  # RAIM
    r'\bPBN\b',  # PBN
    r'\bRNAV\b',  # RNAV
    r'\bRNP\b',  # RNP
    r'\bSFC\b',  # SFC
    r'\bAMSL\b',  # AMSL
    r'\bAGL\b',  # AGL
    r'\bMSL\b',  # MSL
    r'\bPSN\b',  # PSN
    r'\bRADIUS\b',  # RADIUS
    r'\bHGT\b',  # HGT
    r'\bHEIGHT\b',  # HEIGHT
    r'\bTEMP\b',  # TEMP
    r'\bPERM\b',  # PERM
    r'\bOBST\b',  # OBST
    r'\bFIREWORKS\b',  # FIREWORKS
    r'\bSTANDS?\s*(\d+)\b',  # STANDS 711 형식
    # 한국어 패턴들
    r'\b활주로\s*\d{2}[LRC]?(?:/\d{2}[LRC]?)?\b',  # 활주로 15L/33R
    r'\b유도로\s*[A-Z](?:\s+및\s+[A-Z])*\b',  # 유도로 D, 유도로 D 및 E
    r'\b유도로\s*[A-Z]\d+\b',  # 유도로 D1
    r'\b주기장\s*[A-Z]\d*\b',  # 주기장 A, 주기장 A1
    r'\bGPS\b',  # GPS (한국어에서도 그대로 사용)
    r'\bRAIM\b',  # RAIM (한국어에서도 그대로 사용)
    r'\bPBN\b',  # PBN (한국어에서도 그대로 사용)
    r'\bRNAV\b',  # RNAV (한국어에서도 그대로 사용)
    r'\bRNP\b',  # RNP (한국어에서도 그대로 사용)
    r'\b지면\b',  # 지면
    r'\b해발\b',  # 해발
    r'\b지상\b',  # 지상
    r'\b평균해수면\b',  # 평균해수면
    r'\b위치\b',  # 위치
    r'\b반경\b',  # 반경
    r'\b높이\b',  # 높이
    r'\b임시\b',  # 임시
    r'\b영구\b',  # 영구
    r'\b장애물\b',  # 장애물
    r'\b불꽃놀이\b',  # 불꽃놀이
    r'\b스탠드\s*(\d+)\b',  # 스탠드 711 형식
]

# 환경 변수 로드
load_dotenv()

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class IntegratedNOTAMTranslator:
    """통합 NOTAM 번역기 - 번역과 요약을 한 번의 API 호출로 처리"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.logger = logging.getLogger(__name__)
        
        # 환경 변수 강제 재로드 (GCR 환경에서 필요할 수 있음)
        load_dotenv(override=True)
        
        # Gemini API 설정
        self.api_key = api_key or os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
        
        if not self.api_key:
            self.logger.error("Gemini API 키가 설정되지 않음. 번역 기능이 제한됩니다.")
            self.gemini_enabled = False
        else:
            try:
                genai.configure(api_key=self.api_key)
                self.model = genai.GenerativeModel('gemini-2.5-flash-lite')
                self.gemini_enabled = True
            except Exception as e:
                self.logger.error(f"Gemini API 초기화 실패: {e}", exc_info=True)
                self.gemini_enabled = False
        
        # 캐시 설정
        self.cache = {}
        self.cache_enabled = True
        
        # 처리 설정 (개별 처리 최적화 - notam_translator.py 참조)
        # 성능 개선: 워커 수 증가 (3 -> 5)
        self.max_workers = int(os.getenv('TRANSLATION_MAX_WORKERS', '5'))  # 환경변수로 조정 가능, 기본값 5
        self.batch_size = 10  # 배치 크기를 10으로 조정
        # API 호출 타임아웃 (초)
        self.api_timeout = int(os.getenv('GEMINI_API_TIMEOUT', '30'))  # 기본값 30초
        
        # 학습 모듈 초기화 (선택적)
        self.learning_enabled = LEARNING_AVAILABLE and os.getenv('ENABLE_GEMINI_LEARNING', 'false').lower() == 'true'
        if self.learning_enabled:
            try:
                self.learning_manager = GeminiLearningManager()
                self.logger.info("Gemini 학습 모듈 활성화됨")
            except Exception as e:
                self.logger.warning(f"학습 모듈 초기화 실패: {e}")
                self.learning_enabled = False
                self.learning_manager = None
        else:
            self.learning_manager = None
    
    def apply_color_styles(self, text: str) -> str:
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
        # 줄바꿈은 유지하고 중복 공백만 제거
        text = re.sub(r'[ \t]+', ' ', text)  # 탭과 공백만 제거
        
        return text
    
    def convert_markdown_to_html(self, text: str) -> str:
        """마크다운 텍스트를 HTML로 변환"""
        if not text:
            return text
        
        # 줄 단위로 처리
        lines = text.split('\n')
        html_lines = []
        in_list = False
        in_paragraph = False
        paragraph_content = []
        
        for line in lines:
            line = line.strip()
            
            # 빈 줄 처리 - 단락 종료
            if not line:
                if in_paragraph and paragraph_content:
                    # 단락 내용을 하나로 합치기
                    combined_content = ' '.join(paragraph_content)
                    html_lines.append(f'<p>{combined_content}</p>')
                    paragraph_content = []
                    in_paragraph = False
                continue
            
            # 불릿 포인트 처리 (*   로 시작하는 줄)
            if line.startswith('*   '):
                if in_paragraph and paragraph_content:
                    # 기존 단락 종료
                    combined_content = ' '.join(paragraph_content)
                    html_lines.append(f'<p>{combined_content}</p>')
                    paragraph_content = []
                    in_paragraph = False
                if not in_list:
                    html_lines.append('<ul>')
                    in_list = True
                content = line[4:]  # '*   ' 제거
                # 내용에서 **굵은 텍스트** 처리
                content = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', content)
                html_lines.append(f'<li>{content}</li>')
            elif line.startswith('* '):
                # * 로 시작하는 줄도 불릿 포인트로 처리
                if in_paragraph and paragraph_content:
                    # 기존 단락 종료
                    combined_content = ' '.join(paragraph_content)
                    html_lines.append(f'<p>{combined_content}</p>')
                    paragraph_content = []
                    in_paragraph = False
                if not in_list:
                    html_lines.append('<ul>')
                    in_list = True
                content = line[2:]  # '* ' 제거
                # 내용에서 **굵은 텍스트** 처리
                content = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', content)
                html_lines.append(f'<li>{content}</li>')
            else:
                if in_list:
                    html_lines.append('</ul>')
                    in_list = False
                
                # 헤더 처리
                if line.startswith('### '):
                    if in_paragraph and paragraph_content:
                        # 기존 단락 종료
                        combined_content = ' '.join(paragraph_content)
                        html_lines.append(f'<p>{combined_content}</p>')
                        paragraph_content = []
                        in_paragraph = False
                    content = line[4:]
                    content = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', content)
                    html_lines.append(f'<h3>{content}</h3>')
                elif line.startswith('## '):
                    if in_paragraph and paragraph_content:
                        # 기존 단락 종료
                        combined_content = ' '.join(paragraph_content)
                        html_lines.append(f'<p>{combined_content}</p>')
                        paragraph_content = []
                        in_paragraph = False
                    content = line[3:]
                    content = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', content)
                    html_lines.append(f'<h2>{content}</h2>')
                elif line.startswith('# '):
                    if in_paragraph and paragraph_content:
                        # 기존 단락 종료
                        combined_content = ' '.join(paragraph_content)
                        html_lines.append(f'<p>{combined_content}</p>')
                        paragraph_content = []
                        in_paragraph = False
                    content = line[2:]
                    content = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', content)
                    html_lines.append(f'<h1>{content}</h1>')
                else:
                    # 일반 텍스트 처리 - 단락 내용에 추가
                    content = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', line)
                    if content.strip():  # 빈 내용이 아닌 경우만
                        paragraph_content.append(content)
                        in_paragraph = True
        
        # 마지막 단락 처리
        if in_paragraph and paragraph_content:
            combined_content = ' '.join(paragraph_content)
            html_lines.append(f'<p>{combined_content}</p>')
        if in_list:
            html_lines.append('</ul>')
        
        return '\n'.join(html_lines)
    
    def process_single_notam_complete(self, notam: Dict[str, Any], e_section: str, index: int) -> Dict[str, Any]:
        """단일 NOTAM을 완전히 처리 (notam_translator.py 방식 참조)"""
        notam_start_time = time.time()
        notam_number = notam.get('notam_number', 'N/A')
        airport_code = notam.get('airport_code', 'UNKNOWN')
        
        try:
            self.logger.debug(f"[NOTAM {index+1}] 처리 시작: {notam_number} ({airport_code}), 길이: {len(e_section)}자")
            
            # 시간 안내 전용 NOTAM은 번역/요약을 건너뜀
            if self._is_time_notice(e_section or ''):
                self.logger.debug(f"[NOTAM {index+1}] 시간 안내 전용 - 건너뜀")
                enhanced_notam = notam.copy()
                enhanced_notam.update({
                    'korean_translation': '',
                    'korean_summary': '',
                    'english_translation': '',
                    'english_summary': '',
                    'e_section': e_section,
                    'skip_translation': True,
                    'skip_reason': 'time_notice'
                })
                return enhanced_notam

            # 캐시 확인 (성능 최적화: 해시값 사용으로 메모리 및 비교 속도 향상)
            text_hash = hashlib.md5(e_section.encode('utf-8')).hexdigest()[:16]  # MD5 해시 16자리 사용
            cache_key = f"{notam_number}_{text_hash}_{index}"
            if self.cache_enabled and cache_key in self.cache:
                self.logger.debug(f"[NOTAM {index+1}] 캐시 히트 - 건너뜀")
                return self.cache[cache_key]
            
            self.logger.debug(f"[NOTAM {index+1}] 캐시 미스 - API 호출 필요")
            
            # 동시 번역: 원문에서 영어와 한국어를 동시에 번역
            api_start_time = time.time()
            with ThreadPoolExecutor(max_workers=2) as executor:
                # 영어와 한국어 번역을 동시에 실행
                self.logger.debug(f"[NOTAM {index+1}] API 호출 시작 (영어+한국어, 타임아웃: {self.api_timeout * 2}초)")
                english_future = executor.submit(self.process_single_integrated, e_section, 'en', airport_code)
                korean_future = executor.submit(self.process_single_integrated, e_section, 'ko', airport_code)
                
                # 결과 수집 (타임아웃 설정)
                try:
                    english_start = time.time()
                    self.logger.debug(f"[NOTAM {index+1}] 영어 번역 결과 대기 중...")
                    english_result = english_future.result(timeout=self.api_timeout * 2)
                    english_elapsed = time.time() - english_start
                    self.logger.debug(f"[NOTAM {index+1}] 영어 번역 완료 ({english_elapsed:.2f}초)")
                    
                    korean_start = time.time()
                    self.logger.debug(f"[NOTAM {index+1}] 한국어 번역 결과 대기 중...")
                    korean_result = korean_future.result(timeout=self.api_timeout * 2)
                    korean_elapsed = time.time() - korean_start
                    self.logger.debug(f"[NOTAM {index+1}] 한국어 번역 완료 ({korean_elapsed:.2f}초)")
                    
                except FutureTimeoutError as timeout_error:
                    api_elapsed = time.time() - api_start_time
                    self.logger.warning(f"[NOTAM {index+1}] 번역 타임아웃 ({api_elapsed:.2f}초 경과): {timeout_error}")
                    # 타임아웃 시 기본값 반환
                    english_result = {'translation': e_section, 'summary': f'번역 타임아웃 (>{self.api_timeout}초)'}
                    korean_result = {'translation': e_section, 'summary': f'번역 타임아웃 (>{self.api_timeout}초)'}
                except Exception as e:
                    api_elapsed = time.time() - api_start_time
                    self.logger.error(f"[NOTAM {index+1}] 번역 오류 ({api_elapsed:.2f}초 경과): {e}", exc_info=True)
                    # 오류 시 기본값 반환
                    english_result = {'translation': e_section, 'summary': f'번역 오류: {str(e)[:50]}'}
                    korean_result = {'translation': e_section, 'summary': f'번역 오류: {str(e)[:50]}'}
            
            api_elapsed = time.time() - api_start_time
            self.logger.debug(f"[NOTAM {index+1}] API 호출 완료 (총 {api_elapsed:.2f}초)")
            
            english_translation = english_result.get('translation', '')
            english_summary = english_result.get('summary', '')
            korean_translation = korean_result.get('translation', '')
            korean_summary = korean_result.get('summary', '')
            
            # 지시사항 제거 (⚠️ 중요: 등)
            post_process_start = time.time()
            if korean_translation:
                korean_translation = self.remove_instruction_text(korean_translation)
            if english_translation:
                english_translation = self.remove_instruction_text(english_translation)
            
            self.logger.debug(f"[NOTAM {index+1}] 후처리 시작 (지시사항 제거, 스타일 적용)")
            
            # 결과 생성
            enhanced_notam = notam.copy()
            enhanced_notam.update({
                'korean_translation': self.convert_markdown_to_html(self.apply_color_styles(korean_translation)) if korean_translation else '번역 실패',
                'korean_summary': korean_summary or '요약 실패',
                'english_translation': self.apply_color_styles(english_translation) if english_translation else 'Translation failed',
                'english_summary': english_summary or 'Summary failed',
                'e_section': e_section
            })
            
            post_process_elapsed = time.time() - post_process_start
            self.logger.debug(f"[NOTAM {index+1}] 후처리 완료 ({post_process_elapsed:.2f}초)")
            
            # 캐시 저장
            if self.cache_enabled:
                self.cache[cache_key] = enhanced_notam
            
            total_elapsed = time.time() - notam_start_time
            self.logger.debug(f"[NOTAM {index+1}] 처리 완료 - 총 {total_elapsed:.2f}초")
            
            return enhanced_notam
            
        except Exception as e:
            total_elapsed = time.time() - notam_start_time
            self.logger.error(f"[NOTAM {index+1}] 개별 처리 실패 (총 {total_elapsed:.2f}초 경과): {e}", exc_info=True)
            return self._create_fallback_result(notam, e_section)

    def _is_time_notice(self, text: str) -> bool:
        """LOCAL TIME/Daylight Saving 등 시간 안내 전용 NOTAM 판단"""
        if not text:
            return False
        t = text.upper()
        patterns = [
            r"\bLOCAL\s+TIME\s*=\s*UTC\+?[-+]?\d+H?\b",
            r"\bDAYLIGHT\s+SAVING\s+TIME\b",
            r"\bDST\b",
            r"\bSUMMER\s+TIME\b",
            r"\bTIME\s+ZONE\b",
        ]
        for p in patterns:
            if re.search(p, t, re.IGNORECASE):
                return True
        if len(t.strip()) <= 140 and (
            'UTC' in t or 'LOCAL TIME' in t or 'DAYLIGHT' in t or 'DST' in t or 'SUMMER TIME' in t
        ):
            return True
        return False
    
    def _create_fallback_result(self, notam: Dict[str, Any], e_section: str) -> Dict[str, Any]:
        """폴백 결과 생성"""
        enhanced_notam = notam.copy()
        enhanced_notam.update({
            'korean_translation': '번역 실패',
            'korean_summary': '요약 실패',
            'english_translation': 'Translation failed',
            'english_summary': 'Summary failed',
            'e_section': e_section
        })
        return enhanced_notam
        """
        NOTAM들을 통합 처리 (번역 + 요약을 한 번에)
        
        Args:
            notams_data: NOTAM 데이터 리스트
            
        Returns:
            처리된 NOTAM 데이터 리스트
        """
        if not self.gemini_enabled:
            self.logger.warning("Gemini API가 비활성화됨. 원본 데이터 반환")
            return self._create_fallback_results(notams_data)
        
        start_time = time.time()
        results = []
        
        # 고유 ID 추가
        for i, notam in enumerate(notams_data):
            notam['_internal_id'] = f"{notam.get('notam_number', 'N/A')}_{notam.get('airport_code', 'N/A')}_{i}"
        
        # E 섹션 추출
        e_sections = []
        for i, notam in enumerate(notams_data):
            description = notam.get('description', '')
            e_section = self.extract_e_section(description)
            e_sections.append(e_section)
        
        # 긴 NOTAM 감지 및 개별 처리 결정
        long_notams = []
        short_notams = []
        for i, e_section in enumerate(e_sections):
            if len(e_section) > 800:  # 800자 이상은 긴 NOTAM으로 분류 (임계값 상향)
                long_notams.append((i, e_section))
            else:
                short_notams.append((i, e_section))
        
        # 배치로 나누어 처리 (짧은 NOTAM만)
        batches = []
        batch_indices = []
        if short_notams:
            short_sections = [item[1] for item in short_notams]
            short_indices = [item[0] for item in short_notams]
            batches = [short_sections[i:i + self.batch_size] for i in range(0, len(short_sections), self.batch_size)]
            batch_indices = [short_indices[i:i + self.batch_size] for i in range(0, len(short_indices), self.batch_size)]
        
        # 1단계 동시 번역: 원문 → 영어, 한국어 동시 번역
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 영어와 한국어 번역을 동시에 실행
            english_futures = {
                executor.submit(self.process_batch_integrated, batch, 'en'): i 
                for i, batch in enumerate(batches)
            }
            
            korean_futures = {
                executor.submit(self.process_batch_integrated, batch, 'ko'): i 
                for i, batch in enumerate(batches)
            }
            
            # 영어 번역 결과 수집
            english_results = {}
            for future in as_completed(english_futures):
                batch_idx = english_futures[future]
                try:
                    result = future.result()
                    english_results[batch_idx] = result
                except Exception as e:
                    self.logger.error(f"영어 배치 {batch_idx} 처리 실패: {e}")
                    english_results[batch_idx] = []
            
            # 한국어 번역 결과 수집
            korean_results = {}
            for future in as_completed(korean_futures):
                batch_idx = korean_futures[future]
                try:
                    result = future.result()
                    korean_results[batch_idx] = result
                except Exception as e:
                    self.logger.error(f"한국어 배치 {batch_idx} 처리 실패: {e}")
                    korean_results[batch_idx] = []
        
        # 영어 번역 결과를 원래 순서로 정렬
        english_flat = []
        for i in range(len(batches)):
            if i in english_results:
                english_flat.extend(english_results[i])
            else:
                batch_size = len(batches[i])
                english_flat.extend([{'translation': '', 'summary': ''} for _ in range(batch_size)])
        
        # 한국어 번역 결과를 원래 순서로 정렬
        korean_flat = []
        for i in range(len(batches)):
            if i in korean_results:
                korean_flat.extend(korean_results[i])
            else:
                batch_size = len(batches[i])
                korean_flat.extend([{'translation': '', 'summary': ''} for _ in range(batch_size)])
        
        # 긴 NOTAM 개별 처리 (동시 번역)
        long_notam_results = {}
        if long_notams:
            for idx, e_section in long_notams:
                try:
                    # 영어와 한국어 번역을 동시에 실행
                    with ThreadPoolExecutor(max_workers=2) as long_executor:
                        english_future = long_executor.submit(self.process_single_integrated, e_section, 'en')
                        korean_future = long_executor.submit(self.process_single_integrated, e_section, 'ko')
                        
                        # 결과 수집
                        english_result = english_future.result()
                        korean_result = korean_future.result()
                    
                    english_translation = english_result.get('translation', '')
                    english_summary = english_result.get('summary', '')
                    korean_translation = korean_result.get('translation', '')
                    korean_summary = korean_result.get('summary', '')
                    
                    long_notam_results[idx] = {
                        'english_translation': english_translation,
                        'english_summary': english_summary,
                        'korean_translation': korean_translation,
                        'korean_summary': korean_summary
                    }
                except Exception as e:
                    self.logger.error(f"긴 NOTAM {idx+1} 처리 실패: {e}")
                    long_notam_results[idx] = {
                        'english_translation': '처리 오류',
                        'english_summary': '오류',
                        'korean_translation': '처리 오류',
                        'korean_summary': '오류'
                    }
        
        # 최종 결과 구성
        for i, notam in enumerate(notams_data):
            if i in long_notam_results:
                # 긴 NOTAM 결과 사용
                result = long_notam_results[i]
                korean_translation = result['korean_translation']
                korean_summary = result['korean_summary']
                english_translation = result['english_translation']
                english_summary = result['english_summary']
            else:
                # 배치 처리 결과 사용
                batch_idx = next((j for j, batch in enumerate(batch_indices) if i in batch), -1)
                if batch_idx >= 0:
                    batch_position = batch_indices[batch_idx].index(i)
                    korean_translation = korean_flat[batch_position].get('translation', '') if batch_position < len(korean_flat) else ''
                    korean_summary = korean_flat[batch_position].get('summary', '') if batch_position < len(korean_flat) else ''
                    english_translation = english_flat[batch_position].get('translation', '') if batch_position < len(english_flat) else ''
                    english_summary = english_flat[batch_position].get('summary', '') if batch_position < len(english_flat) else ''
                else:
                    korean_translation = ''
                    korean_summary = ''
                    english_translation = ''
                    english_summary = ''
            
            # 개별 처리로 폴백 (통합 처리 실패 시)
            if not english_translation or not english_summary:
                english_result = self.process_single_integrated(e_sections[i], 'en')
                english_translation = english_result.get('translation', '')
                english_summary = english_result.get('summary', '')
            
            if not korean_translation or not korean_summary:
                if english_translation:
                    # 영어 번역 결과를 한국어로 번역
                    korean_result = self.process_single_integrated(english_translation, 'ko')
                    korean_translation = korean_result.get('translation', '')
                    korean_summary = korean_result.get('summary', '')
                else:
                    # 영어 번역도 실패한 경우 원문을 한국어로 번역
                    korean_result = self.process_single_integrated(e_sections[i], 'ko')
                    korean_translation = korean_result.get('translation', '')
                    korean_summary = korean_result.get('summary', '')
            
            enhanced_notam = notam.copy()
            enhanced_notam.update({
                'korean_translation': self.convert_markdown_to_html(self.apply_color_styles(korean_translation)) if korean_translation else '번역 실패',
                'korean_summary': korean_summary or '요약 실패',
                'english_translation': self.apply_color_styles(english_translation) if english_translation else 'Translation failed',
                'english_summary': english_summary or 'Summary failed',
                'e_section': e_sections[i] if i < len(e_sections) else ''
            })
            
            results.append(enhanced_notam)
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        self.logger.debug(f"통합 번역 완료: {len(results)}개, {processing_time:.2f}초")
        
        return results
    
    def process_batch_integrated(self, notams: List[str], target_language: str) -> List[Dict[str, str]]:
        """
        배치 단위로 통합 처리 (번역 + 요약)
        
        Args:
            notams: NOTAM 텍스트 리스트
            target_language: 대상 언어 ('ko' 또는 'en')
            
        Returns:
            번역과 요약이 포함된 결과 리스트
        """
        if not self.gemini_enabled:
            return [{'translation': notam, 'summary': ''} for notam in notams]
        
        # 캐시 확인
        batch_key = f"integrated_{target_language}_{hashlib.md5(''.join(notams).encode()).hexdigest()}"
        if self.cache_enabled and batch_key in self.cache:
            return self.cache[batch_key]
        
        try:
            prompt = self.create_integrated_prompt(notams, target_language)
            response = self.model.generate_content(prompt)
            result = self.parse_integrated_response(response.text, len(notams))
            
            # 캐시 저장
            if self.cache_enabled:
                self.cache[batch_key] = result
            
            return result
            
        except Exception as e:
            self.logger.error(f"배치 통합 처리 오류: {e}")
            self.logger.error(f"오류 발생 배치 - 언어: {target_language}, NOTAM 수: {len(notams)}")
            self.logger.error(f"첫 번째 NOTAM 미리보기: {notams[0][:100] if notams else 'None'}...")
            import traceback
            self.logger.error(f"상세 오류: {traceback.format_exc()}")
            return [{'translation': f'처리 오류: {str(e)}', 'summary': '오류'} for _ in notams]
    
    def process_single_integrated(self, notam_text: str, target_language: str, airport_code: str = None) -> Dict[str, str]:
        """
        단일 NOTAM 통합 처리 (번역 + 요약)
        
        Args:
            notam_text: NOTAM 텍스트
            target_language: 대상 언어 ('ko' 또는 'en')
            airport_code: 공항 코드 (선택사항)
            
        Returns:
            번역과 요약이 포함된 결과
        """
        if not self.gemini_enabled:
            return {'translation': notam_text, 'summary': ''}
        
        # 캐시 확인
        cache_key = f"integrated_single_{target_language}_{hashlib.md5(notam_text.encode()).hexdigest()}"
        if self.cache_enabled and cache_key in self.cache:
            return self.cache[cache_key]
        
        try:
            # 기본 프롬프트 생성
            base_prompt = self.create_integrated_prompt([notam_text], target_language, airport_code)
            
            # 학습 모듈이 활성화되어 있으면 Few-shot Learning 적용
            if self.learning_enabled and self.learning_manager:
                prompt = self.learning_manager.build_few_shot_prompt(
                    base_prompt, 
                    task_type='translation',
                    language=target_language,
                    num_examples=3
                )
            else:
                prompt = base_prompt
            
            response = self.model.generate_content(prompt)
            
            if not response or not hasattr(response, 'text') or not response.text:
                self.logger.error("Gemini 응답이 비어있음")
                return {'translation': notam_text, 'summary': 'Gemini 응답이 비어있습니다'}
            
            results = self.parse_integrated_response(response.text, 1)
            
            if not results:
                # 응답 전체를 번역으로 사용
                result = {
                    'translation': response.text.strip() if response.text.strip() else notam_text,
                    'summary': ''
                }
            else:
                result = results[0]
                
            # 번역 결과 검증
            if not result.get('translation') or result.get('translation') == notam_text:
                result['translation'] = notam_text
            
            # 지시사항 제거 (⚠️ 중요: 등)
            if result.get('translation') and result.get('translation') != notam_text:
                result['translation'] = self.remove_instruction_text(result['translation'])
            
            # 한국어 번역인 경우 마크다운을 HTML로 변환
            if target_language == 'ko' and result.get('translation') and result.get('translation') != notam_text:
                result['translation'] = self.convert_markdown_to_html(self.apply_color_styles(result['translation']))
            
            # 캐시 저장
            if self.cache_enabled and result.get('translation') and result.get('translation') != notam_text:
                self.cache[cache_key] = result
            
            return result
            
        except Exception as e:
            self.logger.error(f"단일 통합 처리 오류: {e}", exc_info=True)
            self.logger.error(f"오류 발생 텍스트: {notam_text[:200]}...")
            return {'translation': notam_text, 'summary': f'처리 오류: {str(e)}'}
    
    def create_integrated_prompt(self, notams: List[str], target_language: str, airport_code: str = None) -> str:
        """
        통합 처리용 프롬프트 생성 (번역 + 요약)
        
        Args:
            notams: NOTAM 텍스트 리스트
            target_language: 대상 언어
            airport_code: 공항 코드 (선택사항)
            
        Returns:
            통합 프롬프트
        """
        if target_language == 'ko':
            return self.create_korean_integrated_prompt(notams, airport_code)
        else:
            return self.create_english_integrated_prompt(notams, airport_code)
    
    def create_korean_integrated_prompt(self, notams: List[str], airport_code: str = None) -> str:
        """한국어 통합 프롬프트 생성"""
        notams_text = "\n\n".join([f"{notam}" for notam in notams])
        
        # 공항 코드 정보 추가 (개인화 제외)
        airport_info = ""
        
        return f"""다음 NOTAM을 명확하고 간결한 한국어로 정리해주세요.

{notams_text}

요청사항:
이 NOTAM을 사용자가 쉽게 이해할 수 있도록 구조화된 한국어로 정리해주세요.

출력 형식 (정확히 이 형식을 따라주세요):
주요 내용:
[핵심 내용을 한 줄로 요약]

상세 내용:

• [구체적인 세부사항을 항목별로 정리]
• [각 항목은 별도의 불릿 포인트로 구분]

운영 지침:

• [운영상 주의사항이나 지침]
• [각 지침은 별도의 불릿 포인트로 구분]

기타:

• [기타 중요한 정보]
• [각信息는 별도의 불릿 포인트로 구분]

번역 규칙:
1. 자연스러운 한국어로 번역하되 전문용어는 정확하게
2. 시간 정보는 KST로 변환하여 표시 (예: 2025년 2월 3일 09:00)
3. 중요한 정보는 굵은 글씨로 표시하지 않고 자연스럽게 표현
4. 사용자가 쉽게 이해할 수 있도록 구조화
5. 불필요한 반복이나 어색한 표현 제거
6. 각 섹션 사이에는 빈 줄을 넣어 가독성 향상
7. 불릿 포인트는 "• " 형식으로 시작
7-1. 공항 코드(ICAO/IATA), 활주로 번호(RWY 07/25 등), 좌표, 고도/거리 수치는 원문 그대로 유지 (절대 변경 금지)
8. "REF", "REFERENCE", "참조"로 시작하는 문장은 자료(예: AIP SUP, AIRAC 등)의 특정 항목을 가리키는 것으로, 해당 자료의 내용을 그대로 단정하지 말고 "해당 문서를 확인하라"는 안내로 설명
9. "ITEM TWY:A,B"처럼 문서 항목을 지칭하는 구절은 유도로 A/B 자체 폐쇄를 의미하지 않으며, 실제 폐쇄 여부는 별도 문장("TWY M1... CLSD")에서만 판단
10. 문서 참조와 실제 조치(폐쇄, 제한 등)를 명확히 구분해 서술
11. ⚠️ 절대 번역 결과에 "NOTAM 정리:", "정리:", "NOTAM 번역:" 등의 제목이나 헤더를 포함하지 마세요. 바로 "주요 내용:" 섹션부터 시작하세요

⚠️ 가장 중요한 규칙: TWY와 TXL 용어 구분 (절대 위반 금지) ⚠️
- TWY = 택시웨이 (Taxiway: 공항 내에서 항공기의 이동을 위해 설계된 공식 통로)
- TXL = 택시레인 (Taxilane: 주기장(에이프런) 또는 격납고 주변에서 주차 공간 사이를 이동하기 위한 보조 이동로)
- "TWY"가 나오면 반드시 "택시웨이"로 번역해야 하며, 절대로 "택시레인"으로 번역하지 마세요
- "TXL"이 나오면 반드시 "택시레인"으로 번역해야 하며, 절대로 "택시웨이"로 번역하지 마세요
- "TAXIWAY"도 "택시웨이"로 번역해야 하며, "택시레인"으로 번역하지 마세요
- 예시:
  * "TWY M1" → "택시웨이 M1" (NOT "택시레인 M1")
  * "TWY A1" → "택시웨이 A1" (NOT "택시레인 A1")
  * "TWY Q1" → "택시웨이 Q1" (NOT "택시레인 Q1")
  * "TWY K" 또는 "TAXIWAY K" → "택시웨이 K" (NOT "택시레인 K")
  * "TWY R1, R2, R3" → "택시웨이 R1, R2, R3" (NOT "택시레인 R1, R2, R3")
  * "TXL DC" → "택시레인 DC" (NOT "택시웨이 DC")
- LINK: "TWY LINK nn" 또는 "LINK nn"(예: LINK 30)은 번역 시 반드시 "LINK 30"처럼 그대로 유지하세요. 택시레인으로 번역하지 마세요. LINK는 택시웨이와 에이프런(주기장)을 연결하는 구간을 일컫는 용어입니다. (예: "TWY LINK 30" → "LINK 30", "택시레인 30" 사용 금지)

항공 전문용어 번역 (정확한 한국어 용어 사용):
- VDGS → 차량유도도킹시스템
- CONCOURSE → 탑승동
- MAINTENANCE → 정비
- AIRCRAFT → 항공기
- MARSHALLER → 유도요원
- DOCKING → 접현
- INFORMATION → 정보
- PROVIDED → 제공
- GUIDED BY → 지시에 따라
- TRIAL OPERATION → 시험운영
- IMPLEMENTED → 실시
- NOTIFIED → 공지
- CHANGE → 변경
- DURING THE PERIOD → 해당기간동안
- REMAINING DISTANCE → 잔여거리
- LEFT AND RIGHT DEVIATION → 좌우편차
- TOBT → 목표 활주로 진입 시간(Target Off-Block Time)
- TSAT → 목표 시동 승인 시간(Target Start-Up Approval Time)
- LGT → 등(燈)/조명등 (Light, 활주로/유도로/대기지점의 조명등. 절대 "가벼운"으로 번역하지 마세요)
- INTERMEDIATE HLDG POINT LGT → 중간 대기 지점 등(燈) (Intermediate Holding Position Lights)
- HLDG POINT LGT → 대기 지점 등(燈) (Holding Position Lights)
- U/S → 사용 불가 (Unserviceable, 고장/비가동 상태)
- HLDG SHORT → ~의 앞에서 대기 (Hold Short, 해당 지점 직전에서 대기)
- SOUTHBOUND → 남쪽 방향 (남하하는 방향)
- NORTHBOUND → 북쪽 방향 (북상하는 방향)
- EASTBOUND → 동쪽 방향
- WESTBOUND → 서쪽 방향
- WIP → 작업 진행 중 (Work In Progress, 공사/작업)
- A-CDM → 공항협력결정관리(A-CDM)
- NON-PRIORITY FLIGHTS → 비우선 항공편 (응급/요인 비행 등 우선순위 비행을 제외한 일반 항공편. 절대 "비영리 항공편"으로 번역하지 마세요)
- PRIORITY FLIGHTS → 우선순위 항공편 (응급 환자 수송, 국가 요인 비행, 비상 선포 항공기 등)
- TOBT → 목표 활주로 진입 시간(Target Off-Block Time)
- TSAT → 목표 시동 승인 시간(Target Start-Up Approval Time)
- UTC → 협정세계시
- FROM ... TO ... → ...부터 ...까지
- DUE TO → 로 인해
- SERVICE → 서비스
- CEILING → 운고
- CLOSED → 폐쇄
- NR. → 번호
- RWY → 활주로
- WIP → 작업 진행
- CLSD → 폐쇄
- NML OPS → 정상 운영
- SIMULTANEOUS PARALLEL APPROACHES → 동시 평행 접근
- SUSPENDED → 중단
- REF → 참조
- DE/ANTI-ICING FLUID → 제/방빙 용액 (절대 "안티이싱 유체"로 번역하지 마세요)
- DE-ICING FLUID → 제빙 용액
- ANTI-ICING FLUID → 방빙 용액
- DE/ANTI-ICING → 제/방빙
- FICON → 마찰 계수 (Friction Coefficient, 활주로 표면 상태를 나타내는 값)
- FICON 값은 일반적으로 활주로를 세 부분(착륙 구역, 중간 지점, 이륙/출발 구역)으로 나누어 측정되며, 예: "FICON 5/5/5"는 세 지점 모두 마찰 계수 5를 의미
- 마찰 계수는 0(측정 불가능)부터 5 또는 6(가장 좋음)까지의 척도를 사용하며, 5는 일반적으로 좋은(Good) 마찰 조건을 의미
- WET SANDED → 젖은 상태에서 모래/제설제 살포 (활주로 표면이 젖은 상태에서 모래나 제설제를 살포한 상태)
- SANDED → 모래/제설제 살포 (활주로 표면에 모래나 제설제를 살포한 상태)
- PCT → 퍼센트 (percent의 약자)
- FROST → 서리

NOTAM 고도 필드 번역 규칙 (F)와 G) 필드):
- F) 필드는 Lower Level(고도 하한)을 의미합니다
- G) 필드는 Upper Level(고도 상한)을 의미합니다
- F) SFC G) UNL → "하한고도: 지표면(SFC), 상한고도: 무한대(UNL)" 또는 "지표면(SFC)부터 무한대(UNL) 고도까지"
- F) SFC G) 7000FT AMSL → "하한고도: 지표면(SFC), 상한고도: 7000피트 AMSL" 또는 "지표면(SFC)부터 7000피트 AMSL까지"
- SFC → 지표면 (Surface)
- UNL → 무한대 (Unlimited)
- AMSL → 평균해수면 (Above Mean Sea Level)
- AGL → 지상고도 (Above Ground Level)
- MSL → 평균해수면 (Mean Sea Level)
- 고도 정보가 있는 경우 "기타" 섹션에 "• 적용 고도: [하한고도]부터 [상한고도]까지" 형식으로 명시

제빙 용액 제조 회사명 (번역하지 않고 그대로 유지):
- INLAND → INLAND (Inland Technologies 회사명, 절대 "국내"로 번역하지 마세요)
- DOW → DOW (DOW Chemical 회사명, 번역하지 않음)
- KILFROST → KILFROST (KILFROST 회사명, 번역하지 않음)
- KAS → KAS (회사명, 번역하지 않음)

공항 내 회사명 및 지명 (번역하지 않고 그대로 유지):
- PUROLATOR → PUROLATOR 또는 Purolator (Purolator Inc., 캐나다 택배/물류 회사, 번역하지 않음)

⚠️ TWY와 TXL 번역 규칙 (반드시 준수) ⚠️
- TWY 또는 TAXIWAY → 택시웨이 (Taxiway: 공항 내에서 항공기의 이동을 위해 설계된 공식 통로)
- TXL → 택시레인 (Taxilane: 주기장(에이프런) 또는 격납고 주변에서 주차 공간 사이를 이동하기 위한 보조 이동로)
- TWY 뒤에 나오는 것은 택시웨이의 이름입니다 (예: TWY M1 = 택시웨이 M1, TWY A1 = 택시웨이 A1, TWY Q1 = 택시웨이 Q1, TWY K = 택시웨이 K)
- TXL 뒤에 나오는 것은 택시레인의 이름입니다 (예: TXL DC = 택시레인 DC)
- "TWY M1"은 반드시 "택시웨이 M1"으로 번역해야 하며, 절대로 "택시레인 M1"으로 번역하지 마세요
- "TWY A1"은 반드시 "택시웨이 A1"으로 번역해야 하며, 절대로 "택시레인 A1"으로 번역하지 마세요
- "TWY Q1"은 반드시 "택시웨이 Q1"으로 번역해야 하며, 절대로 "택시레인 Q1"으로 번역하지 마세요
- "TWY K" 또는 "TAXIWAY K"는 반드시 "택시웨이 K"로 번역해야 하며, 절대로 "택시레인 K"로 번역하지 마세요
- "TWY R1, R2, R3"은 반드시 "택시웨이 R1, R2, R3"으로 번역해야 하며, 절대로 "택시레인 R1, R2, R3"으로 번역하지 마세요
- "TXL DC"는 "택시레인 DC"로 번역해야 하며, "텍사스 딜레이"나 "계류장" 등으로 잘못 번역하지 마세요
- TXL은 절대 "텍사스"나 "딜레이"로 번역하지 마세요
- TWY는 절대 "택시레인"으로 번역하지 마세요 - 반드시 "택시웨이"로 번역해야 합니다
- "TWY LINK nn" 또는 "LINK nn"(예: LINK 30, LINK 25)은 번역 시 "LINK 30", "LINK 25"처럼 그대로 유지하세요. LINK는 택시웨이와 에이프런을 연결하는 구간을 일컫는 용어이므로 "택시레인"으로 번역하지 마세요.

예시:
원문: "VDGS CLOSED DUE TO MAINTENANCE OF SERVICE FOR CONCOURSE"

주요 내용:
탑승동(Concourse)의 차량유도도킹시스템(VDGS)가 서비스 정비로 인해 폐쇄됩니다.

상세 내용:

• 차량유도도킹시스템(VDGS)가 서비스 정비로 인해 폐쇄됩니다.
• 탑승동(Concourse)에서의 VDGS 서비스가 중단됩니다.

운영 지침:

• 항공기 도킹 시 유도요원의 지시를 따라야 합니다.

기타:

• 정비 완료 후 별도 공지될 예정입니다.

원문: "THE AIRCRAFT SHALL BE GUIDED BY MARSHALLER"

주요 내용:
항공기는 유도요원의 지시에 따라야 합니다.

상세 내용:

• 항공기 유도 시 유도요원(Marshaller)의 지시를 따라야 합니다.

운영 지침:

• 자동 유도 시스템 사용 불가 시 유도요원 지시 준수

기타:

• 안전한 항공기 유도를 위한 필수 절차입니다.

원문: "TWY M1 AND PART OF M2 WILL BE RENAMED TWY R1, R2 AND R3"

주요 내용:
택시웨이 M1 및 M2 일부 구간의 명칭이 택시웨이 R1, R2, R3으로 변경됩니다.

상세 내용:

• 택시웨이 M1 및 M2 일부 구간의 명칭이 택시웨이 R1, R2, R3으로 변경됩니다.
• 변경 구간은 A1/A2와 택시웨이 Q1 교차점 사이입니다.

⚠️ 중요: "TWY M1", "TWY R1, R2, R3", "TWY Q1"은 모두 "택시웨이"로 번역해야 하며, 절대로 "택시레인"으로 번역하지 마세요.

원문: "TAXIWAY K CLOSED"

주요 내용:
택시웨이 K가 폐쇄됩니다.

상세 내용:

• 택시웨이 K가 폐쇄됩니다.

⚠️ 중요: "TAXIWAY K"는 "택시웨이 K"로 번역해야 하며, 절대로 "택시레인 K"로 번역하지 마세요.

원문: "TXL DC AVBL FOR ACFT UP TO ICAO CODE D"

주요 내용:
ICAO 코드 D 이하의 항공기에 대해 택시레인 DC 사용이 가능합니다.

상세 내용:

• ICAO 코드 D 이하의 항공기에 대해 택시레인 DC 사용이 가능합니다.

운영 지침:

• 해당 규정은 ICAO 코드 D 이하의 항공기에만 적용됩니다.

기타:

• 택시레인 DC는 주기장(에이프런) 또는 격납고 주변에서 주차 공간 사이를 이동하기 위한 보조 이동로입니다.

⚠️ 중요: "TXL DC"를 "텍사스 딜레이"나 "계류장" 등으로 잘못 번역하지 마세요. 반드시 "택시레인 DC"로 번역하세요.

원문: "PORTION OF TWY M BTN TWY A AND TWY LINK 30 DOWNGRADED FOR ACFT UPTO CODE LETTER C. PORTION OF TWY LINK 30 BTN TWY K AND TWY M DOWNGRADED FOR ACFT UPTO CODE LETTER D."

주요 내용:
택시웨이 M 및 LINK 30 일부 구간의 항공기 통행이 제한됩니다.

상세 내용:

• 택시웨이 M의 택시웨이 A와 LINK 30 사이 구간은 ICAO 코드 C 이하의 항공기만 이용 가능합니다.
• LINK 30의 택시웨이 K와 택시웨이 M 사이 구간은 ICAO 코드 D 이하의 항공기만 이용 가능합니다.

⚠️ 중요: "TWY LINK 30"은 "LINK 30"으로 그대로 유지합니다. "택시레인 30"으로 번역하지 마세요.

원문: "[25/26 DE/ANTI-ICING FLUID] [KAS] KILFROST DF PLUS, KILFROST ABC-S PLUS / TYPE 1,4"

주요 내용:
제/방빙 용액으로 KILFROST DF PLUS, KILFROST ABC-S PLUS (Type 1, 4)가 사용됩니다.

상세 내용:

• 제/방빙 용액으로 KILFROST DF PLUS 및 KILFROST ABC-S PLUS가 사용됩니다.
• 이 용액들은 Type 1 및 Type 4에 해당합니다.

⚠️ 중요: "DE/ANTI-ICING FLUID"는 반드시 "제/방빙 용액"으로 번역해야 하며, 절대로 "안티이싱 유체"나 "방빙 용액"으로 번역하지 마세요. "DE-ICING"은 "제빙"(기존 얼음을 제거), "ANTI-ICING"은 "방빙"(얼음 형성 방지)을 의미합니다.

원문: "[25/26 DE/ANTI-ICING FLUID] [INLAND] INLAND TYPE I CONCENTRATE & TYPE I BLENDED, TYPE IV DOW ENDURANCE EG106 / TYPE 1,4"

주요 내용:
제/방빙 용액으로 INLAND Type I Concentrate, Type I Blended, Type IV DOW ENDURANCE EG106 (Type 1, 4)가 사용됩니다.

상세 내용:

• 제/방빙 용액으로 INLAND Type I Concentrate가 사용됩니다.
• 제/방빙 용액으로 INLAND Type I Blended가 사용됩니다.
• 제/방빙 용액으로 Type IV DOW ENDURANCE EG106이 사용됩니다.
• 사용되는 용액은 Type 1 및 Type 4에 해당합니다.

⚠️ 중요: "INLAND"는 제빙 용액 제조 회사명(Inland Technologies)이므로 절대로 "국내"로 번역하지 마세요. 반드시 "INLAND"로 그대로 유지해야 합니다.

원문: "TWY DW AND APN IV W OF PUROLATOR AVBL TO ACFT WITH WINGSPAN 52 METERS 170FT AND SMALLER"

주요 내용:
택시웨이 DW 및 에이프런 IV의 Purolator(택배/물류 회사) 서측 구간은 최대 날개 너비 52미터(170피트) 이하 항공기만 이용 가능합니다.

상세 내용:

• 택시웨이 DW 및 에이프런 IV의 Purolator(택배/물류 회사) 서측 구간은 항공기 이용이 제한됩니다.
• 이용 가능한 항공기는 최대 날개 너비 52미터(170피트) 이하인 항공기에 한정됩니다.

운영 지침:

• 상기 제한 규정을 초과하는 항공기는 해당 구간 이용 시 주의가 필요합니다.

기타:

• 이 제한은 항공기의 안전한 이동을 보장하기 위한 조치입니다.

⚠️ 중요: "PUROLATOR"는 캐나다의 택배/물류 회사인 Purolator Inc.를 의미하므로, 번역하지 않고 "Purolator" 또는 "Purolator(택배/물류 회사)"로 표기해야 합니다.

원문: "ANC RWY 07R FICON 5/5/5 25 PCT FROST AND 75 PCT WET SANDED OBS AT 2511260338"

주요 내용:
07R 활주로의 마찰 계수는 5/5/5(양호)이며, 활주로 표면은 25% 서리, 75% 젖은 상태에서 모래/제설제 살포 상태입니다.

상세 내용:

• 활주로: 07R 활주로
• 마찰 계수: 5/5/5 (착륙 구역, 중간 지점, 이륙/출발 구역 모두 양호한 마찰 조건)
• 표면 상태: 25% 서리, 75% 젖은 상태에서 모래/제설제 살포
• 관측 시간: 2025년 11월 26일 03시 38분 (UTC)

운영 지침:

• 07R 활주로 이용 시 현재 표면 상태를 인지하고 운항해야 합니다.
• 마찰 계수 5/5/5는 양호한 제동 성능을 나타냅니다.

기타:

• FICON은 활주로 표면의 마찰 계수(Friction Coefficient)를 나타내며, 활주로를 세 부분으로 나누어 측정됩니다.
• 마찰 계수 5는 좋은(Good) 제동 성능을 의미합니다.

⚠️ 중요: "FICON 5/5/5"는 마찰 계수가 세 지점 모두 5로 양호하다는 의미이며, "WET SANDED"는 "젖은 상태에서 모래/제설제 살포"를 의미합니다. "25 PCT FROST AND 75 PCT WET SANDED"는 "25% 서리, 75% 젖은 상태에서 모래/제설제 살포"를 의미합니다.

원문: "E) ATTENTION ACFT OPR AND DISPATCHERS OPERATING WITHIN KZAK FIR BE ADVISED OAKLAND SAT VOICE NUMBER HAS CHANGED TO 1-510-745-3498. F) SFC G) UNL"

주요 내용:
KZAK FIR 내 오클랜드 SAT 음성 통신 전화번호가 변경되었습니다.

상세 내용:

• 오클랜드 SAT(위성) 음성 통신 전화번호가 1-510-745-3498로 변경되었습니다.

운영 지침:

• KZAK FIR(비행정보구역) 내에서 운항하는 항공기 운영자 및 관제사는 변경된 전화번호를 사용해야 합니다.

기타:

• 적용 고도: 지표면(SFC)부터 무한대(UNL)까지

⚠️ 중요: F) 필드는 Lower Level(고도 하한), G) 필드는 Upper Level(고도 상한)을 의미합니다. "F) SFC G) UNL"은 "지표면(SFC)부터 무한대(UNL)까지"를 의미하며, "기타" 섹션에 고도 정보를 명시해야 합니다.

NOTAM 발행자 정보 처리 규칙:
- "-- BY SELOQ--", "-- BY SELOE--" 등은 NOTAM을 발행한 주체를 나타냅니다
- "BY"는 "~에 의해"라는 의미이지만, 번역 시에는 "발행자: SELOQ" 또는 "이 NOTAM은 SELOQ가 발행했습니다" 형식으로 "기타" 섹션에 표시
- "운영 지침" 섹션에 "SELOQ에 의해 시행됩니다" 같은 표현을 사용하지 마세요
- 발행자 정보는 "기타" 섹션에 "• 발행자: SELOQ" 형식으로만 표시
- 예시:
  * 원문에 "-- BY SELOQ--"가 있으면 → "기타" 섹션에 "• 발행자: SELOQ" 추가
  * 원문에 "-- BY SELOE--"가 있으면 → "기타" 섹션에 "• 발행자: SELOE" 추가

각 NOTAM을 위 형식과 용어를 사용하여 정리해주세요."""
    

    def _is_tdm_track_notam(self, text: str) -> bool:
        """TDM 트랙 NOTAM인지 판별"""
        if not text:
            return False
        tdm_patterns = [
            r'\bTDM\s+TRK\b',
            r'TRACK\s+[A-Z0-9]+',
            r'\bBOXER\s+KYLLE\s+KANUA',
            r'\bCOUPLED\s+TRACKS',
        ]
        text_upper = text.upper()
        for pattern in tdm_patterns:
            if re.search(pattern, text_upper):
                return True
        return False

    def create_english_integrated_prompt(self, notams: List[str], airport_code: str = None) -> str:
        """영어 통합 프롬프트 생성"""
        notams_text = "\n\n".join([f"{notam}" for notam in notams])
        
        # TDM 트랙 NOTAM인지 확인
        is_tdm = self._is_tdm_track_notam(notams_text)
        
        # 공항 코드 정보 추가
        airport_info = ""
        if airport_code and airport_code != 'UNKNOWN':
            airport_info = f"""
Airport Information:
This NOTAM is about {airport_code} airport.
"""
        
        # TDM 트랙 NOTAM은 특별 처리
        if is_tdm:
            return f"""You are a NOTAM translator. Translate ONLY the technical content below into clear English.

{airport_info}
{notams_text}

CRITICAL: Output ONLY the translation text. Do NOT include any of the following:
- "Here's the translation"
- "Here is the translation"
- "Translation:"
- "The following is"
- Any introductory phrases
- Repetition of the prompt

Start directly with the track information translation:
"""
        
        return f"""Translate and summarize the following NOTAM(s) in clear English for flight crews.

{airport_info}
{notams_text}

⚠️ MOST IMPORTANT RULES: ⚠️
1. NEVER include ANY of the following:
   - Time information (dates, times, periods, UTC)
   - Long document citations (AIRAC, AIP, AMDT, SUP). If a reference is operationally critical, mention it once as "Reference: AIP SUP 213/25" without adding extra interpretation
   - Phrases like "New information is available", "Information regarding", "Information about"
   - Airport names
   - Coordinates
   - Unnecessary parentheses or special characters
   - Redundant words and phrases

2. Focus on:
   - Key changes or impacts
   - Specific details about changes
   - Reasons for changes

3. Keep it concise and clear:
   - Make it as short as possible
   - Use direct and active voice
   - Include only essential information

4. For runway directions:
   - Always use "L/R" format (e.g., "RWY 15 L/R")
   - Do not translate "L/R" to "LEFT/RIGHT" or "좌/우"
   - Keep the space between runway number and L/R (e.g., "RWY 15 L/R")

5. When the NOTAM references other documents (e.g., "REF AIP SUP 213/25 ITEM TWY:A,B"):
   - Treat it strictly as a pointer to supporting material
   - Do NOT infer that the referenced taxiways/runways are closed unless the NOTAM explicitly states "CLSD", "CLOSED", "UNAVAIL", etc.
   - Clearly separate referenced material from actual operational changes described in later sentences

6. CRITICAL: TXL vs TWY Terminology - MUST BE STRICTLY FOLLOWED:
   - TXL = Taxilane (a secondary movement area for aircraft movement between parking spaces on aprons or around hangars)
   - TWY = Taxiway (a designated path on an airport for aircraft to move between runways and aprons)
   - TXL followed by letters/numbers is the name of the taxilane (e.g., "TXL DC" = "Taxilane DC")
   - TWY followed by letters/numbers is the name of the taxiway (e.g., "TWY M1" = "Taxiway M1", "TWY A1" = "Taxiway A1")
   - NEVER translate "TXL" as "Taxiway" or expand it incorrectly
   - NEVER translate "TWY" as "Taxilane" - it must always be "Taxiway"
   - Examples:
     * "TXL DC AVBL" → "Taxilane DC available" (NOT "Taxiway Delta Charlie")
     * "TWY M1 UNDER CONSTRUCTION" → "Taxiway M1 under construction" (NOT "Taxilane M1")
     * "TWY A1 DOWNGRADED" → "Taxiway A1 downgraded" (NOT "Taxilane A1")

6. CRITICAL: De/Anti-icing Fluid Terminology:
   - "DE/ANTI-ICING FLUID" must be translated as "De/Anti-icing fluid" (keep "De" prefix)
   - NEVER translate as just "Anti-icing fluid" - the "De" part is essential
   - "DE/ANTI-ICING" means both de-icing and anti-icing capabilities
   - Examples:
     * "DE/ANTI-ICING FLUID KILFROST DF PLUS" → "De/Anti-icing fluid KILFROST DF PLUS"
     * "DE/ANTI-ICING FLUID TYPE 1,4" → "De/Anti-icing fluid Type 1, 4"
     * "[25/26 DE/ANTI-ICING FLUID] KILFROST DF PLUS" → "De/Anti-icing fluid KILFROST DF PLUS"
     * NEVER translate as "Anti-icing fluid" without "De"
   - The "/" in "DE/ANTI-ICING" must be preserved as "/" in the translation

Example:
Original: "[25/26 DE/ANTI-ICING FLUID] [KAS] KILFROST DF PLUS, KILFROST ABC-S PLUS / TYPE 1,4"
Translation: De/Anti-icing fluid KILFROST DF PLUS, KILFROST ABC-S PLUS Type 1, 4 are available.
Summary: De/Anti-icing fluid KILFROST DF PLUS and KILFROST ABC-S PLUS (Type 1, 4) are available.

Response format:
Translation: [Clear English translation with flight safety focus]
Summary: [Concise operational summary following the rules above]"""
    
    def remove_instruction_text(self, text: str) -> str:
        """
        번역 결과에서 지시사항(⚠️ 중요: 등)을 제거하고 회사명 오번역 수정
        
        Args:
            text: 번역 결과 텍스트
            
        Returns:
            지시사항이 제거되고 회사명이 수정된 텍스트
        """
        if not text:
            return text
        
        # 회사명 오번역 수정 (INLAND가 "국내"로 번역된 경우)
        # 제빙 용액 관련 문맥에서 "국내"가 나오면 "INLAND"로 수정
        # 패턴 1: "국내" + 제빙 용액 관련 키워드
        text = re.sub(r'국내\s*(제/방빙|제빙|방빙|TYPE\s+I|TYPE\s+IV|CONCENTRATE|BLENDED)', r'INLAND \1', text, flags=re.IGNORECASE)
        # 패턴 2: 제빙 용액 관련 키워드 + "국내"
        text = re.sub(r'(제/방빙|제빙|방빙|TYPE\s+I|TYPE\s+IV|CONCENTRATE|BLENDED)\s*국내', r'\1 INLAND', text, flags=re.IGNORECASE)
        # 패턴 3: "국내(INLAND)" → "INLAND"
        text = re.sub(r'국내\s*\(INLAND\)', 'INLAND', text, flags=re.IGNORECASE)
        # 패턴 4: "국내에서 사용" → "INLAND에서 사용" (제빙 용액 문맥)
        if re.search(r'제/방빙|제빙|방빙|DE/ANTI-ICING|DE-ICING|ANTI-ICING|TYPE\s+I|TYPE\s+IV', text, re.IGNORECASE):
            text = re.sub(r'국내에서\s*사용', 'INLAND에서 사용', text, flags=re.IGNORECASE)
            text = re.sub(r'해당.*제/방빙.*국내', lambda m: m.group(0).replace('국내', 'INLAND'), text, flags=re.IGNORECASE)
        
        # HTML 태그가 있는 경우도 처리
        # 먼저 HTML 태그를 임시로 보존하면서 텍스트만 처리
        import html
        
        # ⚠️ 중요: 로 시작하는 줄 또는 패턴 제거
        lines = text.split('\n')
        cleaned_lines = []
        
        for line in lines:
            line_stripped = line.strip()
            
            # ⚠️ 중요: 로 시작하는 줄 완전 제거
            if line_stripped.startswith('⚠️ 중요:'):
                continue
            
            # ⚠️ 중요: 가 포함된 줄에서 해당 부분 제거
            if '⚠️ 중요:' in line:
                # ⚠️ 중요: 이후의 모든 내용 제거
                parts = line.split('⚠️ 중요:')
                if len(parts) > 1:
                    # ⚠️ 중요: 이전 부분만 유지 (빈 문자열이면 제거)
                    before_warning = parts[0].strip()
                    if before_warning:
                        cleaned_lines.append(before_warning)
                    continue
                else:
                    continue
            
            # 지시사항 패턴 제거 (정규식 사용)
            # "반드시 ... 번역해야", "절대로 ... 번역하지 마세요" 등의 패턴
            instruction_patterns = [
                r'⚠️\s*중요:.*',  # ⚠️ 중요: 로 시작하는 모든 내용
                r'.*반드시.*번역해야.*',  # 반드시 ... 번역해야
                r'.*절대로.*번역하지.*',  # 절대로 ... 번역하지
                r'.*잘못 번역하지.*',  # 잘못 번역하지
                r'.*번역하지 마세요.*',  # 번역하지 마세요
                r'.*번역되지 않도록.*',  # 번역되지 않도록
                r'.*번역되지 않도록 주의.*',  # 번역되지 않도록 주의
                r'.*제조 회사명.*번역.*',  # 제조 회사명 ... 번역
                r'.*회사명.*번역.*',  # 회사명 ... 번역
            ]
            
            is_instruction = False
            for pattern in instruction_patterns:
                if re.search(pattern, line_stripped):
                    is_instruction = True
                    break
            
            if is_instruction:
                continue
            
            # "반드시", "절대로" 등이 포함된 지시사항 줄 제거 (더 정확한 패턴)
            if any(keyword in line_stripped for keyword in ['반드시', '절대로', '번역해야', '번역하지 마세요', '잘못 번역하지 마세요', '번역되지 않도록', '주의해야']):
                # 지시사항 키워드가 있고 번역 관련 키워드도 함께 있으면 지시사항으로 판단
                if (('반드시' in line_stripped or '절대로' in line_stripped or '번역되지 않도록' in line_stripped or '주의해야' in line_stripped) and \
                   ('번역해야' in line_stripped or '번역하지' in line_stripped or '번역하세요' in line_stripped or '번역' in line_stripped)) or \
                   ('제조 회사명' in line_stripped and '번역' in line_stripped) or \
                   ('회사명' in line_stripped and '번역' in line_stripped and '주의' in line_stripped):
                    continue
            
            cleaned_lines.append(line)
        
        # 빈 줄 정리
        result = '\n'.join(cleaned_lines)
        # 연속된 빈 줄을 하나로
        result = re.sub(r'\n\s*\n\s*\n+', '\n\n', result)
        # 줄 끝의 공백 제거
        result = re.sub(r'[ \t]+$', '', result, flags=re.MULTILINE)
        
        return result.strip()
    
    def parse_integrated_response(self, response: str, notam_count: int) -> List[Dict[str, str]]:
        """
        통합 응답 파싱 (번역 + 요약)
        
        Args:
            response: 모델 응답 텍스트
            notam_count: 예상 NOTAM 개수
            
        Returns:
            파싱된 결과 리스트
        """
        results = []
        
        # 한국어 응답인 경우 전체를 번역으로 처리
        if '주요 내용:' in response or '상세 내용:' in response:
            # 한국어 구조화된 응답 파싱
            translation = response.strip()
            summary = ""
            
            # 주요 내용에서 요약 추출
            if '주요 내용:' in response:
                lines = response.split('\n')
                for i, line in enumerate(lines):
                    if '주요 내용:' in line:
                        # 다음 비어있지 않은 줄이 요약
                        for j in range(i + 1, len(lines)):
                            next_line = lines[j].strip()
                            if next_line and not next_line.startswith('상세 내용:') and not next_line.startswith('운영 지침:') and not next_line.startswith('기타:'):
                                summary = next_line.replace('*', '').strip()
                                break
                        break
            
            # 지시사항 제거
            cleaned_translation = self.remove_instruction_text(translation)
            
            results.append({
                'translation': cleaned_translation,
                'summary': summary
            })
            return results
        
        # 영어 응답 중간에 간단한 처리 추가 (변수 정의 오류 수정)
        # 이 부분은 현재 사용되지 않으므로 제거
        
        # 개선된 영어 응답 파싱 로직
        lines = response.strip().split('\n')
        
        current_translation = ""
        current_summary = ""
        in_translation = False
        in_summary = False
        
        for line in lines:
            line = line.strip()
            
            # 번역 섹션 감지 (개선된 패턴)
            if (line.startswith('번역:') or line.startswith('Translation:') or 
                line.startswith('Translated NOTAM:') or line.startswith('**Translation:**') or
                line.startswith('**번역:**')):
                in_translation = True
                in_summary = False
                # 콜론 뒤의 내용 추출
                if ':' in line:
                    current_translation = line.split(':', 1)[1].strip()
                else:
                    current_translation = ""
                continue
            
            # 요약 섹션 감지 (개선된 패턴)
            if (line.startswith('요약:') or line.startswith('Summary:') or 
                line.startswith('**Summary:**') or line.startswith('**요약:**')):
                in_translation = False
                in_summary = True
                # 콜론 뒤의 내용 추출
                if ':' in line:
                    current_summary = line.split(':', 1)[1].strip()
                else:
                    current_summary = ""
                continue
            
            # 내용 추가
            if in_translation and line:
                if current_translation:
                    current_translation += " " + line
                else:
                    current_translation = line
            elif in_summary and line:
                if current_summary:
                    current_summary += " " + line
                else:
                    current_summary = line
        
        # 번역과 요약이 있으면 결과에 추가
        if current_translation or current_summary:
            # 지시사항 제거
            cleaned_translation = self.remove_instruction_text(current_translation.strip()) if current_translation else ''
            cleaned_summary = current_summary.strip()  # 요약은 지시사항이 포함될 가능성이 낮음
            
            results.append({
                'translation': cleaned_translation,
                'summary': cleaned_summary
            })
        
        # 결과가 부족하면 기본값으로 채움
        while len(results) < notam_count:
            # 영어 응답의 경우 전체 응답을 번역으로 사용
            if len(results) == 0 and response.strip():
                full_response = response.strip()
                # 첫 번째 줄이 번역 내용일 가능성이 높음
                first_line = full_response.split('\n')[0].strip()
                if first_line and not first_line.startswith('Summary:'):
                    results.append({
                        'translation': first_line,
                        'summary': 'Complete translation'
                    })
                else:
                    results.append({
                        'translation': '번역 실패',
                        'summary': '요약 실패'
                    })
            else:
                results.append({
                    'translation': '번역 실패',
                    'summary': '요약 실패'
                })
        
        # 결과가 너무 많으면 잘라냄
        results = results[:notam_count]
        
        return results
    
    def extract_e_section(self, notam_text: str) -> str:
        """
        NOTAM에서 E 섹션 추출 (사용하지 않음 - 이미 추출된 original_text 사용)
        이 함수는 하위 호환성을 위해 유지되지만 실제로는 사용되지 않습니다.
        
        Args:
            notam_text: NOTAM 텍스트
            
        Returns:
            E 섹션 내용
        """
        if not notam_text:
            return ""
        
        # E 섹션 패턴 찾기 (개선된 패턴 - 순서 변경)
        e_patterns = [
            r'E\)\s*(.*)',  # 전체 텍스트 패턴 (우선순위 1)
            r'^E\)\s*(.*?)(?=\n[A-Z]\)|$)',  # 줄바꿈 기준 패턴 (우선순위 2)
            r'E\)\s*(.*?)(?=\s*[A-Z]\)|$)',  # 기존 패턴 (우선순위 3)
        ]
        
        for pattern in e_patterns:
            match = re.search(pattern, notam_text, re.DOTALL | re.IGNORECASE)
            if match:
                e_section = match.group(1).strip()
                # 메타데이터 제거 (RMK는 중요한 정보이므로 제거하지 않음)
                e_section = re.sub(r'CREATED:.*$', '', e_section, flags=re.DOTALL).strip()
                e_section = re.sub(r'SOURCE:.*$', '', e_section, flags=re.DOTALL).strip()
                e_section = re.sub(r'COMMENT\).*$', '', e_section, flags=re.DOTALL).strip()
                # 카테고리 마커 제거 (◼ 또는 ■ 뒤에 오는 모든 텍스트 제거)
                # 예: ◼ RUNWAY, ■ TAXIWAY, ◼ COMPANY MINIMA FOR CAT II/III 등
                e_section = re.sub(r'[◼■]\s*[^\n]*(?:\n|$)', '', e_section, flags=re.MULTILINE).strip()
                
                # E 섹션이 있으면 반환
                if e_section:
                    return e_section
        
        # E 섹션을 찾지 못한 경우 전체 텍스트에서 핵심 내용만 추출
        cleaned_text = notam_text.strip()
        
        # 날짜 패턴 제거 (예: 20FEB25 00:00 - UFN 또는 03SEP25 23:11 - 02OCT25 23:59)
        cleaned_text = re.sub(r'\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*-\s*(?:UFN|\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2})', '', cleaned_text)
        
        # 공항 코드와 NOTAM 번호 제거 (예: RKSI COAD01/25)
        cleaned_text = re.sub(r'[A-Z]{4}\s+[A-Z0-9]+/\d{2}', '', cleaned_text)
        
        # 메타데이터 제거 (RMK는 중요한 정보이므로 제거하지 않음)
        cleaned_text = re.sub(r'CREATED:.*$', '', cleaned_text, flags=re.DOTALL).strip()
        cleaned_text = re.sub(r'SOURCE:.*$', '', cleaned_text, flags=re.DOTALL).strip()
        cleaned_text = re.sub(r'COMMENT\).*$', '', cleaned_text, flags=re.DOTALL).strip()
        # 카테고리 마커 제거 (◼ 또는 ■ 뒤에 오는 모든 텍스트 제거)
        # 예: ◼ RUNWAY, ■ TAXIWAY, ◼ COMPANY MINIMA FOR CAT II/III 등
        cleaned_text = re.sub(r'[◼■]\s*[^\n]*(?:\n|$)', '', cleaned_text, flags=re.MULTILINE).strip()
        
        # 연속된 공백 정리
        cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()
        
        # 빈 문자열이면 원본 반환
        if not cleaned_text:
            return notam_text.strip()
        
        return cleaned_text
    
    def _create_fallback_results(self, notams_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """폴백 결과 생성 (API 비활성화 시)"""
        results = []
        for notam in notams_data:
            enhanced_notam = notam.copy()
            enhanced_notam.update({
                'korean_translation': notam.get('description', ''),
                'korean_summary': 'API 비활성화',
                'english_translation': notam.get('description', ''),
                'english_summary': 'API disabled',
                'e_section': self.extract_e_section(notam.get('description', ''))
            })
            results.append(enhanced_notam)
        return results
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """캐시 통계 반환"""
        return {
            'cache_enabled': self.cache_enabled,
            'cache_size': len(self.cache),
            'cache_keys': list(self.cache.keys())[:10]  # 처음 10개 키만
        }
    
    def clear_cache(self):
        """캐시 초기화"""
        self.cache.clear()
        self.logger.info("캐시가 초기화되었습니다.")
    
    def process_notams_individual(self, notams_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        NOTAM들을 개별 처리 (배치 처리 문제 해결)
        
        Args:
            notams_data: NOTAM 데이터 리스트
            
        Returns:
            번역 및 요약이 완료된 NOTAM 리스트
        """
        if not notams_data:
            return []
        
        start_time = time.time()
        
        # 고유 ID 추가 및 원문 준비
        for i, notam in enumerate(notams_data):
            notam['_internal_id'] = f"{notam.get('notam_number', 'N/A')}_{notam.get('airport_code', 'N/A')}_{i}"
        
        # 이미 추출된 원문(original_text) 사용 - E 섹션 재추출하지 않음
        original_texts = []
        for i, notam in enumerate(notams_data):
            # original_text가 있으면 그것을 사용, 없으면 description 사용
            original_text = notam.get('original_text', notam.get('description', ''))
            
            # HTML 태그 제거 (색상 스타일 제거)
            if original_text:
                # <span> 태그와 style 속성 제거
                import re
                clean_text = re.sub(r'<span[^>]*>', '', original_text)
                clean_text = re.sub(r'</span>', '', clean_text)
                clean_text = re.sub(r'<[^>]+>', '', clean_text)  # 기타 HTML 태그 제거
                clean_text = clean_text.strip()
            else:
                clean_text = ''
            
            # original_text가 비어있거나 "D)"만 있으면 e_field 사용
            if not clean_text or clean_text.strip() == 'D)' or len(clean_text.strip()) < 10:
                e_field = notam.get('e_field', '')
                if e_field:
                    # e_field도 HTML 태그 제거
                    e_field_clean = re.sub(r'<span[^>]*>', '', e_field)
                    e_field_clean = re.sub(r'</span>', '', e_field_clean)
                    e_field_clean = re.sub(r'<[^>]+>', '', e_field_clean)
                    e_field_clean = e_field_clean.strip()
                    if e_field_clean:
                        clean_text = e_field_clean
            
            original_texts.append(clean_text)
        
        # e_sections를 original_texts로 변경
        e_sections = original_texts
        
        # 모든 NOTAM을 개별적으로 처리 (병렬 처리 최적화)
        # 로깅 최적화: INFO -> DEBUG로 변경하여 성능 향상
        self.logger.debug(f"번역 시작: {len(notams_data)}개 NOTAM, 워커 수: {self.max_workers}, 타임아웃: {self.api_timeout}초")
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 각 NOTAM에 대해 개별 처리 작업 생성
            futures = {}
            submit_start_time = time.time()
            for i, notam in enumerate(notams_data):
                e_section = e_sections[i]
                self.logger.debug(f"[메인] NOTAM {i+1} 작업 제출 중...")
                future = executor.submit(self.process_single_notam_complete, notam, e_section, i)
                futures[future] = i
            submit_elapsed = time.time() - submit_start_time
            self.logger.debug(f"[메인] 모든 작업 제출 완료 ({submit_elapsed:.2f}초, 총 {len(futures)}개)")
            
            # 결과 수집 (완료 순서대로)
            results = [None] * len(notams_data)
            completed_count = 0
            last_progress_log = time.time()
            waiting_start_time = None
            
            self.logger.debug(f"[메인] 결과 수집 시작...")
            for future in as_completed(futures):
                if waiting_start_time is None:
                    waiting_start_time = time.time()
                    self.logger.debug(f"[메인] 첫 번째 완료 대기 시작...")
                
                notam_idx = futures[future]
                future_start_time = time.time()
                try:
                    # 타임아웃 설정 (API 호출 타임아웃보다 약간 길게, 각 NOTAM은 영어+한국어 2개 API 호출)
                    timeout_for_future = self.api_timeout * 2 + 10
                    self.logger.debug(f"[메인] NOTAM {notam_idx+1} 결과 대기 중 (타임아웃: {timeout_for_future}초)...")
                    result = future.result(timeout=timeout_for_future)
                    future_elapsed = time.time() - future_start_time
                    results[notam_idx] = result
                    completed_count += 1
                    self.logger.debug(f"[메인] NOTAM {notam_idx+1} 결과 수신 완료 ({future_elapsed:.2f}초)")
                    
                    # 진행 상황 로깅 최적화: 10개마다 또는 15초마다 또는 마지막에만 출력
                    current_time = time.time()
                    should_log = (
                        completed_count % 10 == 0 or 
                        completed_count == len(notams_data) or
                        current_time - last_progress_log > 15
                    )
                    if should_log:
                        elapsed = current_time - start_time
                        avg_time = elapsed / completed_count if completed_count > 0 else 0
                        remaining = len(notams_data) - completed_count
                        estimated_remaining = avg_time * remaining if avg_time > 0 else 0
                        progress_pct = (completed_count / len(notams_data)) * 100 if len(notams_data) > 0 else 0
                        self.logger.info(
                            f"[메인] 번역 진행: {completed_count}/{len(notams_data)} ({progress_pct:.1f}%) "
                            f"(경과: {elapsed:.1f}초, 예상 남은 시간: {estimated_remaining:.1f}초, "
                            f"평균: {avg_time:.2f}초/개)"
                        )
                        last_progress_log = current_time
                        
                except FutureTimeoutError as e:
                    future_elapsed = time.time() - future_start_time
                    self.logger.error(f"[메인] NOTAM {notam_idx+1} 개별 처리 타임아웃 ({future_elapsed:.2f}초 경과): {e}")
                    # 타임아웃 시 폴백 결과 생성
                    results[notam_idx] = self._create_fallback_result(notams_data[notam_idx], e_sections[notam_idx])
                    completed_count += 1
                except Exception as e:
                    future_elapsed = time.time() - future_start_time
                    self.logger.error(f"[메인] NOTAM {notam_idx+1} 개별 처리 실패 ({future_elapsed:.2f}초 경과): {e}", exc_info=True)
                    # 실패 시 폴백 결과 생성
                    results[notam_idx] = self._create_fallback_result(notams_data[notam_idx], e_sections[notam_idx])
                    completed_count += 1
            
            # None 값 제거 (실패한 경우)
            results = [r for r in results if r is not None]
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        self.logger.debug(f"처리 완료: {len(results)}개, {processing_time:.2f}초, 평균 {processing_time/len(results):.2f}s/개")
        
        return results
