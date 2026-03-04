#!/usr/bin/env python3
"""
병렬 처리 개선된 하이브리드 NOTAM 번역기
"""

import os
import re
import logging
import google.generativeai as genai
from dotenv import load_dotenv
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import hashlib
import json
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from notam_filter import apply_color_styles
from constants import NO_TRANSLATE_TERMS, DEFAULT_ABBR_DICT
import csv

# 환경 변수 로드
load_dotenv()

# 로깅 설정
logger = logging.getLogger(__name__)

class ParallelHybridNOTAMTranslator:
    """병렬 처리 개선된 하이브리드 NOTAM 번역기"""
    
    def __init__(self):
        """초기화"""
        self.gemini_enabled = False
        self.cache_dir = "cache"
        self.max_workers = 5  # 동시 처리할 최대 스레드 수
        
        # 캐시 디렉토리 생성
        os.makedirs(self.cache_dir, exist_ok=True)
        
        # 공항 코드 로드 및 NO_TRANSLATE_TERMS 확장
        self.no_translate_terms = self._load_airport_codes()
        
        try:
            api_key = os.getenv('GOOGLE_API_KEY')
            if api_key:
                genai.configure(api_key=api_key)
                self.model = genai.GenerativeModel(
                    'gemini-2.5-flash-lite',
                    generation_config=genai.types.GenerationConfig(temperature=0.3)
                )
                self.gemini_enabled = True
                logger.info("병렬 처리 하이브리드 NOTAM Translator 초기화 완료 (온도: 0.3)")
            else:
                logger.warning("GOOGLE_API_KEY가 설정되지 않음")
        except Exception as e:
            logger.error(f"병렬 처리 하이브리드 NOTAM Translator 초기화 실패: {str(e)}")
            self.gemini_enabled = False
    
    def _load_airport_codes(self):
        """공항 코드를 로드하여 NO_TRANSLATE_TERMS에 추가"""
        # 기본 NO_TRANSLATE_TERMS 복사
        no_translate_terms = list(NO_TRANSLATE_TERMS)
        
        try:
            # src 폴더의 공항 데이터 사용
            csv_path = os.path.join(os.path.dirname(__file__), 'airports_timezones.csv')
            
            if os.path.exists(csv_path):
                with open(csv_path, 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    airport_codes = []
                    for row in reader:
                        icao_code = row.get('ident')  # CSV 파일의 실제 컬럼명
                        if icao_code and len(icao_code) == 4:  # 유효한 ICAO 코드만
                            airport_codes.append(icao_code)
                    
                    # 공항 코드를 NO_TRANSLATE_TERMS에 추가
                    no_translate_terms.extend(airport_codes)
                    logger.info(f"공항 코드 {len(airport_codes)}개를 NO_TRANSLATE_TERMS에 추가했습니다.")
            else:
                logger.warning(f"공항 데이터 파일을 찾을 수 없습니다: {csv_path}")
                
        except Exception as e:
            logger.error(f"공항 코드 로드 중 오류: {e}")
        
        return no_translate_terms
    
    def get_cache_key(self, text: str) -> str:
        """텍스트의 캐시 키 생성"""
        return hashlib.md5(text.encode('utf-8')).hexdigest()
    
    def get_cached_translation(self, text: str) -> Optional[Dict]:
        """캐시된 번역 결과 조회"""
        try:
            cache_key = self.get_cache_key(text)
            cache_file = os.path.join(self.cache_dir, f"{cache_key}.json")
            
            if os.path.exists(cache_file):
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cached_data = json.load(f)
                    logger.debug(f"캐시에서 번역 결과 조회: {cache_key[:8]}...")
                    return cached_data
        except Exception as e:
            logger.warning(f"캐시 조회 중 오류: {e}")
        
        return None
    
    def cache_translation(self, text: str, translation_result: Dict):
        """번역 결과 캐싱"""
        try:
            cache_key = self.get_cache_key(text)
            cache_file = os.path.join(self.cache_dir, f"{cache_key}.json")
            
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(translation_result, f, ensure_ascii=False, indent=2)
                logger.debug(f"번역 결과 캐싱: {cache_key[:8]}...")
        except Exception as e:
            logger.warning(f"캐싱 중 오류: {e}")
    
    def extract_e_section(self, notam_text: str) -> str:
        """NOTAM 텍스트에서 E 섹션만 추출합니다."""
        e_section_patterns = [
            r'E\)\s*(.*?)(?=\s*[A-Z]\)|$)',
            r'E\)\s*(.*?)(?=\s*[A-Z][A-Z]\)|$)',
            r'E\)\s*(.*?)(?=\s*RMK|$)',
            r'E\)\s*(.*?)(?=\s*COMMENT|$)',
        ]
        
        for pattern in e_section_patterns:
            match = re.search(pattern, notam_text, re.DOTALL)
            if match:
                e_section = match.group(1).strip()
                e_section = re.sub(r'CREATED:.*$', '', e_section, flags=re.DOTALL).strip()
                e_section = re.sub(r'RMK:.*$', '', e_section, flags=re.DOTALL).strip()
                e_section = re.sub(r'COMMENT\).*$', '', e_section, flags=re.DOTALL).strip()
                # 카테고리 마커 제거 (◼ 또는 ■ 뒤에 오는 모든 텍스트 제거)
                # 예: ◼ RUNWAY, ■ TAXIWAY, ◼ COMPANY MINIMA FOR CAT II/III 등
                e_section = re.sub(r'[◼■]\s*[^\n]*(?:\n|$)', '', e_section, flags=re.MULTILINE).strip()
                
                if e_section:
                    return e_section
        
        # E 섹션이 없는 경우, 핵심 내용만 추출
        # 날짜, 시간, 공항 코드, NOTAM 번호 제거
        cleaned_text = notam_text.strip()
        
        # 날짜 패턴 제거 (예: 20FEB25 00:00 - UFN 또는 03SEP25 23:11 - 02OCT25 23:59)
        cleaned_text = re.sub(r'\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*-\s*(?:UFN|\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2})', '', cleaned_text)
        
        # 공항 코드와 NOTAM 번호 제거 (예: RKSI COAD01/25)
        cleaned_text = re.sub(r'[A-Z]{4}\s+[A-Z0-9]+/\d{2}', '', cleaned_text)
        
        # 메타데이터 제거
        cleaned_text = re.sub(r'CREATED:.*$', '', cleaned_text, flags=re.DOTALL).strip()
        cleaned_text = re.sub(r'RMK:.*$', '', cleaned_text, flags=re.DOTALL).strip()
        cleaned_text = re.sub(r'COMMENT\).*$', '', cleaned_text, flags=re.DOTALL).strip()
        # 카테고리 마커 제거 (◼ 또는 ■ 뒤에 오는 모든 텍스트 제거)
        # 예: ◼ RUNWAY, ■ TAXIWAY, ◼ COMPANY MINIMA FOR CAT II/III 등
        cleaned_text = re.sub(r'[◼■]\s*[^\n]*(?:\n|$)', '', cleaned_text, flags=re.MULTILINE).strip()
        
        # NO CURRENT NOTAMS FOUND 이후의 내용 제거
        cleaned_text = re.sub(r'\*{8}\s*NO CURRENT NOTAMS FOUND\s*\*{8}.*$', '', cleaned_text, flags=re.DOTALL | re.IGNORECASE).strip()
        
        # 연속된 공백 정리
        cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()
        
        return cleaned_text
    
    def extract_notam_number(self, text: str) -> str:
        """NOTAM 텍스트에서 NOTAM 번호를 추출합니다."""
        patterns = [
            r'([A-Z]{4}\s+COAD\d{2}/\d{2})',
            r'(AIRAC\s+AIP\s+SUP\s+\d{2}/\d{2})',
            r'([A-Z]{4}\s+AIRAC\s+AIP\s+SUP\s+\d{2}/\d{2})',
            r'(AIP\s+SUP\s+\d{2}/\d{2})',
            r'([A-Z]{4}\s+AIP\s+SUP\s+\d{2}/\d{2})',
            r'([A-Z]{4}\s+[A-Z]\d{4}/\d{2})',
            r'([A-Z]{4}\s+[A-Z]\d{3,4}/\d{2})',
            r'([A-Z]{4}\s+\d{3,4}/\d{2})',
            r'(COAD\d{2}/\d{2})',
            r'([A-Z]\d{4}/\d{2})',
            r'([A-Z]\d{3,4}/\d{2})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1).strip()
        
        words = text.split()
        return words[0] if words else 'UNKNOWN'
    
    def identify_notam_type(self, notam_number: str) -> str:
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
    
    def extract_airport_code(self, text: str) -> str:
        """NOTAM 텍스트에서 공항 코드를 추출합니다."""
        airport_pattern = r'\b([A-Z]{4})\b'
        matches = re.findall(airport_pattern, text)
        
        notam_header_pattern = r'\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*-\s*\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s+([A-Z]{4})\s+[A-Z]\d{4}/\d{2}'
        header_match = re.search(notam_header_pattern, text)
        if header_match:
            return header_match.group(1)
        
        patterns = [
            r'\b([A-Z]{4})\s+[A-Z]\d{4}/\d{2}',
            r'\b([A-Z]{4})\s+AIP\s+SUP',
            r'\b([A-Z]{4})\s+NOTAM',
            r'^([A-Z]{4})\s+',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
        
        return matches[0] if matches else 'UNKNOWN'
    
    def _preprocess_for_translation(self, text: str) -> str:
        """번역 전 텍스트 전처리 - 번역하지 않을 용어들을 토큰으로 변환"""
        processed_text = text
        
        # 특별한 용어들 먼저 처리 (공백이 있는 용어들)
        special_terms = [
            "AIRAC AIP SUP", "AIP SUP", "AIP AMDT", "TRIGGER NOTAM",
            "Eastern Standard Time"
        ]
        
        for i, term in enumerate(special_terms):
            token = f"NO_TRANSLATE_TOKEN_{i}"
            processed_text = processed_text.replace(term, token)
        
        # 단일 단어 용어들 처리 (동적으로 로드된 공항 코드 포함)
        for i, term in enumerate(self.no_translate_terms):
            if term not in special_terms:  # 이미 처리한 항목 제외
                token = f"NO_TRANSLATE_TOKEN_{len(special_terms) + i}"
                # 단어 경계를 고려한 정확한 매칭
                processed_text = re.sub(r'\b' + re.escape(term) + r'\b', token, processed_text)
        
        return processed_text
    
    def _postprocess_translation(self, text: str) -> str:
        """번역 후 텍스트 후처리 - 토큰을 원래 용어로 복원"""
        processed_text = text
        
        # 특별한 용어들 먼저 복원
        special_terms = [
            "AIRAC AIP SUP", "AIP SUP", "AIP AMDT", "TRIGGER NOTAM",
            "Eastern Standard Time"
        ]
        
        # 토큰 번호를 정확히 파싱하여 복원
        import re
        
        # NO_TRANSLATE_TOKEN_숫자 패턴 찾기
        def replace_token(match):
            token = match.group(0)
            token_num = int(token.split('_')[-1])
            
            # special_terms 범위인지 확인
            if token_num < len(special_terms):
                return special_terms[token_num]
            else:
                # no_translate_terms 범위
                idx = token_num - len(special_terms)
                if idx < len(self.no_translate_terms):
                    return self.no_translate_terms[idx]
                else:
                    return token  # 매칭되지 않으면 원래 토큰 유지
        
        # 토큰 패턴 매칭 및 교체
        processed_text = re.sub(r'NO_TRANSLATE_TOKEN_\d+', replace_token, processed_text)
        
        return processed_text
    
    def _expand_abbreviations(self, text: str) -> str:
        """영어 번역에서 약어를 확장합니다."""
        expanded_text = text
        
        # 약어 확장 적용 (긴 것부터 먼저 처리)
        sorted_abbreviations = sorted(DEFAULT_ABBR_DICT.items(), key=lambda x: len(x[0]), reverse=True)
        
        for abbr, expansion in sorted_abbreviations:
            # 단어 경계를 고려한 정확한 매칭
            pattern = r'\b' + re.escape(abbr) + r'\b'
            expanded_text = re.sub(pattern, expansion, expanded_text, flags=re.IGNORECASE)
        
        return expanded_text
    
    def perform_translation(self, text: str, target_lang: str, notam_type: str) -> str:
        """Gemini를 사용하여 NOTAM 번역 수행"""
        try:
            # E 섹션만 추출하여 번역
            e_section = self.extract_e_section(text)
            if not e_section:
                return "번역할 내용이 없습니다."

            # 번역하지 않을 용어들을 임시 토큰으로 변환
            processed_text = self._preprocess_for_translation(e_section)
            
            if target_lang == "en":
                prompt = f"""Summarize the following NOTAM(s) focusing on critical operational information for flight crews. Organize the summary into the following key categories:

Affected Location(s): Clearly state the airport(s), runway(s), taxiway(s), or specific areas impacted.

Nature of the Issue/Change: Describe what the NOTAM is announcing (e.g., closure, restriction, service outage, new procedure, hazard).

Operational Impact & Pilot Actions: Explain how this affects flight operations and what specific actions pilots need to take or be aware of (e.g., alternative procedures, increased caution, specific equipment settings).

Effective Dates & Times: Provide the start and end dates/times, or indicate if it's permanent/indefinite. Note any delays or schedule changes.

Additional Important Details: Include any other crucial information such as contact numbers, reference documents (AIP SUP, charts), or specific aircraft type considerations.

Ensure the summary is concise, easy to understand for immediate operational awareness, and prioritizes safety-critical information.

{processed_text}"""
            else:  # Korean
                prompt = f"""다음 NOTAM 텍스트를 한국어로 번역하세요. 설명, 주석, 추가 정보를 포함하지 마세요. 직접 번역만 반환하세요:

중요한 번역 규칙:
1. "-- BY SELOE--"는 반드시 "-- SELOE --"로 번역 (BY 제거)
2. "-- BY SELOQ--"는 반드시 "-- SELOQ --"로 번역 (BY 제거)
# 3. "BY"는 절대 번역하지 않음
4. "REF"는 "참조"로 번역
# 5. "PLZ"는 "제발" 또는 "부탁드립니다"로 번역
6. "NO_TRANSLATE_TOKEN_숫자" 형태의 토큰은 절대 번역하지 말고 그대로 유지하세요
7. "1. 2. 3. 4. 5." 같은 번호 목록이 있어도 전체 문장을 끝까지 번역하세요
8. 번호 목록의 각 항목을 모두 번역하세요
9. "AS FLW"는 "다음과 같습니다"로 번역하세요
10. 번호 목록이 있어도 번역을 중단하지 마세요
11. 반드시 전체 텍스트를 끝까지 번역하세요
12. "FLOW CTL AS FLW"는 "흐름 통제는 다음과 같습니다"로 번역하세요
13. 번호 목록의 각 항목을 개별적으로 번역하세요 (예: "1. RTE : A593 VIA SADLI" → "1. 노선: A593 VIA SADLI")
14. "CEILING"은 반드시 "운고"로 번역하세요
15. "TXL"은 "택시레인"으로 번역하세요 (Taxilane: 주기장이나 격납고 주변에서 주차 공간 사이를 이동하기 위한 보조 이동로)
16. TXL 뒤에 나오는 것은 택시레인의 이름입니다 (예: TXL DC = 택시레인 DC)
17. "TWY LINK nn" 또는 "LINK nn"(예: LINK 30)은 번역 시 "LINK 30"처럼 그대로 유지하세요. LINK는 택시웨이와 에이프런을 연결하는 구간을 일컫는 용어이므로 "택시레인"으로 번역하지 마세요.

원문: {processed_text}

번역문:"""
            
            response = self.model.generate_content(prompt)
            translated_text = response.text.strip()
            
            # 번역 후 원래 용어들로 복원
            translated_text = self._postprocess_translation(translated_text)
            
            # 한국어 번역 시 특별 처리
            if target_lang == "ko":
                # "-- BY SELOE--"를 "-- SELOE --"로 변환
                translated_text = re.sub(r'--\s*BY\s+SELOE\s*--', '-- SELOE --', translated_text, flags=re.IGNORECASE)
                # "-- BY SELOQ--"를 "-- SELOQ --"로 변환
                translated_text = re.sub(r'--\s*BY\s+SELOQ\s*--', '-- SELOQ --', translated_text, flags=re.IGNORECASE)
            
            # 영어 번역 시 약어 확장 적용
            if target_lang == "en":
                translated_text = self._expand_abbreviations(translated_text)
            
            return translated_text
            
        except Exception as e:
            logger.error(f"번역 수행 중 오류 발생: {str(e)}")
            return "번역 중 오류가 발생했습니다."
    
    def translate_single_notam(self, notam_data: Dict[str, Any]) -> Dict[str, Any]:
        """단일 NOTAM 번역 (병렬 처리용)"""
        try:
            description = notam_data.get('description', '')
            original_text = notam_data.get('original_text', description)
            
            # 캐시 확인 (임시로 비활성화)
            # cached_result = self.get_cached_translation(original_text)
            # if cached_result:
            #     logger.debug(f"캐시된 번역 사용: {notam_data.get('notam_number', 'UNKNOWN')}")
            #     enhanced_notam = notam_data.copy()
            #     enhanced_notam.update(cached_result)
            #     return enhanced_notam
            
            # NOTAM 번호와 타입 추출 (notam_data에서 우선 가져오기)
            notam_number = notam_data.get('notam_number') or notam_data.get('id') or self.extract_notam_number(original_text)
            notam_type = self.identify_notam_type(notam_number)
            
            # 한국어 번역
            korean_translation = self.perform_translation(description, 'ko', notam_type)
            # 색상 스타일 적용
            korean_translation = apply_color_styles(korean_translation)
            
            # 영어 번역
            english_translation = self.perform_translation(description, 'en', notam_type)
            # 색상 스타일 적용
            english_translation = apply_color_styles(english_translation)
            
            # 요약 생성
            korean_summary = self.create_summary(korean_translation, 'ko')
            english_summary = self.create_summary(english_translation, 'en')
            
            # 결과 구성
            translation_result = {
                'korean_translation': korean_translation,
                'korean_summary': korean_summary,
                'english_translation': english_translation,
                'english_summary': english_summary,
                'notam_type': notam_type,
                'notam_number': notam_number,
                'e_section': self.extract_e_section(description)
            }
            
            # 캐시 저장
            self.cache_translation(original_text, translation_result)
            
            enhanced_notam = notam_data.copy()
            enhanced_notam.update(translation_result)
            
            logger.info(f"NOTAM 번역 완료: {notam_number} ({notam_type})")
            return enhanced_notam
            
        except Exception as e:
            logger.error(f"NOTAM 번역 중 오류: {str(e)}")
            enhanced_notam = notam_data.copy()
            enhanced_notam.update({
                'korean_translation': '번역 실패',
                'korean_summary': '요약 실패',
                'english_translation': 'Translation failed',
                'english_summary': 'Summary failed',
                'notam_type': 'UNKNOWN',
                'notam_number': 'UNKNOWN',
                'e_section': '',
                'error_message': str(e)
            })
            return enhanced_notam
    
    def create_summary(self, translation: str, language: str) -> str:
        """고급 요약 생성 (summary.py 기반)"""
        try:
            if language == 'ko':
                return self._create_korean_summary(translation)
            else:
                return self._create_english_summary(translation)
        except Exception as e:
            logger.error(f"요약 생성 중 오류: {str(e)}")
            # 폴백: 간단한 키워드 기반 요약
            return self._create_simple_summary(translation, language)
    
    def _create_korean_summary(self, translation: str) -> str:
        """한국어 고급 요약 생성"""
        try:
            prompt = f"""다음 NOTAM 번역을 한국어로 요약하되, 핵심 정보만 포함하도록 하세요:

번역된 NOTAM:
{translation}

⚠️ 가장 중요한 규칙: ⚠️
1. 절대로 다음 정보를 포함하지 마세요:
   - 시간 정보 (날짜, 시간, 기간, UTC)
   - 문서 참조 (AIRAC, AIP, AMDT, SUP)
   - "새로운 정보", "정보 포함", "정보 변경" 등의 표현
   - 공항명
   - 좌표
   - 불필요한 괄호나 특수문자
   - 중복되는 단어나 구문

2. 포함할 내용:
   - 주요 변경사항 또는 영향
   - 변경사항의 구체적 세부사항
   - 변경 사유

3. 간단명료하게 작성:
   - 가능한 짧게 표현
   - 직접적이고 능동적인 표현 사용
   - 핵심 정보만 포함

4. 활주로 방향 표시:
   - 항상 "L/R" 형식을 사용하세요 (예: "활주로 15 L/R")
   - "L/R"을 "좌/우"로 번역하지 마세요
   - 활주로 번호와 L/R 사이에 공백을 유지하세요 (예: "활주로 15 L/R")

핵심 정보를 간단히 요약해주세요."""

            response = self.model.generate_content(prompt)
            summary = response.text.strip()
            
            # 후처리: 불필요한 정보 제거
            summary = self._post_process_korean_summary(summary, translation)
            
            return summary
            
        except Exception as e:
            logger.error(f"한국어 요약 생성 실패: {str(e)}")
            return self._create_simple_summary(translation, 'ko')
    
    def _create_english_summary(self, translation: str) -> str:
        """영어 고급 요약 생성"""
        try:
            prompt = f"""Create a very brief English summary of this NOTAM (maximum 2 sentences):

{translation}

Rules:
- Only include the main operational impact
- No dates, times, or technical details
- Keep it under 50 words
- Focus on what pilots need to know

Summary:"""

            response = self.model.generate_content(prompt)
            summary = response.text.strip()
            
            # 후처리: 불필요한 정보 제거
            summary = self._post_process_english_summary(summary, translation)
            
            return summary
            
        except Exception as e:
            logger.error(f"영어 요약 생성 실패: {str(e)}")
            return self._create_simple_summary(translation, 'en')
    
    def _post_process_korean_summary(self, summary: str, translation: str) -> str:
        """한국어 요약 후처리"""
        import re
        
        # 공항명 패턴 제거
        airport_pattern = r'[가-힣]+(?:국제)?공항'
        summary = re.sub(airport_pattern, '', summary)
        
        # 시간 정보 패턴 제거
        time_patterns = [
            r'\d{2}/\d{2}\s+\d{2}:\d{2}\s*-\s*\d{2}/\d{2}\s+\d{2}:\d{2}',
            r'\(\d{2}/\d{2}\s+\d{2}:\d{2}\s*-\s*\d{2}/\d{2}\s+\d{2}:\d{2}\)',
            r'\d{2}/\d{2}',
            r'\d{2}:\d{2}',
            r'\d{4}\s*UTC',
            r'\d{4}년\s*\d{1,2}월\s*\d{1,2}일',
            r'~까지',
            r'부터',
            r'까지'
        ]
        
        for pattern in time_patterns:
            summary = re.sub(pattern, '', summary)
        
        # 주기장 정보 특별 처리
        if '주기장' in summary or 'STANDS' in translation.upper() or 'STAND' in translation.upper():
            # 주기장 번호 추출
            all_numbers = []
            
            # 다양한 패턴으로 주기장 번호 추출
            patterns = [
                r'STANDS?\s*(?:NR\.)?\s*(\d+)(?:\s*(?:가|changing to|to)\s*(\d+))?,?\s*(?:,\s*(\d+))?',
                r'주기장\s*(\d+)(?:\s*(?:에서|가|changing to|to)\s*(\d+))?,?\s*(?:,\s*(\d+))?',
                r',\s*(\d+)(?:\s*closed)?'
            ]
            
            for pattern in patterns:
                matches = re.finditer(pattern, translation)
                for match in matches:
                    groups = match.groups()
                    all_numbers.extend([num for num in groups if num])
            
            if all_numbers:
                all_numbers = sorted(list(set(all_numbers)), key=int)
                stands_text = ', '.join(all_numbers)
                summary = f"주기장 {stands_text} 포장 공사로 폐쇄"
                if '운용 제한' in translation or '운항 제한' in translation:
                    summary += ", 운용 제한"
            else:
                current_numbers = re.findall(r'\d+', summary)
                if current_numbers:
                    current_numbers = sorted(list(set(current_numbers)), key=int)
                    stands_text = ', '.join(current_numbers)
                    summary = f"주기장 {stands_text} 포장 공사로 폐쇄"
                    if '운용 제한' in translation or '운항 제한' in translation:
                        summary += ", 운용 제한"
        
        # 불필요한 공백과 쉼표 정리
        summary = re.sub(r'\s+', ' ', summary)
        summary = re.sub(r',\s*,', ',', summary)
        summary = re.sub(r'\s*,\s*$', '', summary)
        
        return summary.strip()
    
    def _post_process_english_summary(self, summary: str, translation: str) -> str:
        """영어 요약 후처리"""
        import re
        
        # 시간 정보 패턴 제거
        time_patterns = [
            r'\d{2}/\d{2}\s+\d{2}:\d{2}\s*-\s*\d{2}/\d{2}\s+\d{2}:\d{2}',
            r'\(\d{2}/\d{2}\s+\d{2}:\d{2}\s*-\s*\d{2}/\d{2}\s+\d{2}:\d{2}\)',
            r'\d{2}/\d{2}',
            r'\d{2}:\d{2}',
            r'\d{4}\s*UTC'
        ]
        
        for pattern in time_patterns:
            summary = re.sub(pattern, '', summary)
        
        # 불필요한 공백 정리
        summary = re.sub(r'\s+', ' ', summary)
        
        return summary.strip()
    
    def _create_simple_summary(self, translation: str, language: str) -> str:
        """간단한 키워드 기반 요약 (폴백)"""
        if language == 'ko':
            keywords = []
            if 'RWY' in translation or '활주로' in translation:
                keywords.append('활주로')
            if 'CLOSED' in translation or '폐쇄' in translation:
                keywords.append('폐쇄')
            if 'MAINT' in translation or '정비' in translation:
                keywords.append('정비')
            if 'U/S' in translation or '사용 불가' in translation:
                keywords.append('사용 불가')
            if 'OBST' in translation or '장애물' in translation:
                keywords.append('장애물')
            
            if keywords:
                return f"{', '.join(keywords)} 관련 NOTAM"
            else:
                return "항공 관련 NOTAM"
        else:
            keywords = []
            if 'RWY' in translation or 'RUNWAY' in translation:
                keywords.append('Runway')
            if 'CLOSED' in translation:
                keywords.append('Closed')
            if 'MAINTENANCE' in translation or 'MAINT' in translation:
                keywords.append('Maintenance')
            if 'U/S' in translation or 'UNSERVICEABLE' in translation:
                keywords.append('Unserviceable')
            if 'OBST' in translation or 'OBSTACLE' in translation:
                keywords.append('Obstacle')
            
            if keywords:
                return f"{', '.join(keywords)} related NOTAM"
            else:
                return "Aviation related NOTAM"
    
    def process_notams_parallel(self, notams_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """병렬 처리로 NOTAM들을 처리합니다."""
        if not notams_data:
            return []
        
        logger.info(f"병렬 번역 시작: {len(notams_data)}개 NOTAM (최대 {self.max_workers}개 동시 처리)")
        start_time = time.time()
        
        results = []
        
        # ThreadPoolExecutor를 사용한 병렬 처리
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 모든 NOTAM에 대해 번역 작업 제출
            future_to_notam = {
                executor.submit(self.translate_single_notam, notam): notam 
                for notam in notams_data
            }
            
            # 완료된 작업들을 순서대로 수집
            completed_count = 0
            for future in as_completed(future_to_notam):
                try:
                    result = future.result()
                    results.append(result)
                    completed_count += 1
                    
                    logger.info(f"병렬 번역 진행: {completed_count}/{len(notams_data)} 완료")
                    
                except Exception as e:
                    logger.error(f"병렬 번역 중 오류: {str(e)}")
                    # 오류 발생 시 원본 데이터로 결과 생성
                    original_notam = future_to_notam[future]
                    error_result = original_notam.copy()
                    error_result.update({
                        'korean_translation': '번역 실패',
                        'korean_summary': '요약 실패',
                        'english_translation': 'Translation failed',
                        'english_summary': 'Summary failed',
                        'notam_type': 'UNKNOWN',
                        'notam_number': 'UNKNOWN',
                        'e_section': '',
                        'error_message': str(e)
                    })
                    results.append(error_result)
        
        # 원래 순서대로 정렬 (필요한 경우)
        # results.sort(key=lambda x: notams_data.index(x) if x in notams_data else 0)
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        logger.info(f"병렬 번역 완료: {len(results)}개 NOTAM, {processing_time:.2f}초")
        logger.info(f"평균 처리 시간: {processing_time/len(results):.2f}초/NOTAM")
        
        return results

# 편의 함수
def translate_notams_parallel(notams_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """병렬 NOTAM 번역 (원샷 함수)"""
    translator = ParallelHybridNOTAMTranslator()
    return translator.process_notams_parallel(notams_data)

if __name__ == "__main__":
    # 테스트 코드
    logging.basicConfig(level=logging.INFO)
    
    # 샘플 NOTAM 데이터
    sample_notams = [
        {
            'notam_number': 'A2702/25',
            'description': '''E) DOPPLER WX RADAR SYSTEM (METEOR 60DX10-S) U/S FOR REPAIR RMK: LOW-LEVEL WS ALERT SYSTEM (LLWAS) NML OPS. RWY | CLOSURE MODE & PERIOD | DAYS OF CLOSURE 07L/25R | STANDBY 1800-2259 (UTC) | EVERY MON, WED, SAT (NORTH) | MAINT 1800-2359 (UTC) | EVERY TUE, THU 07C/25C | MAINT 1800-2359 (UTC) | EVERY SUN, FRI (CENTRE) 07R/25L | STANDBY 1800-2259 (UTC) | EVERY SUN, TUE, THU, FRI (SOUTH) | MAINT 1800-2359 (UTC) | EVERY MON, WED, SAT 2. ANY REVISION TO RWY CLOSURE WILL BE PROMULGATED BY NOTAM. 3. IN THE EVENT THAT THE OPERATIONAL RWY BECOMES UNAVBL, THE CLOSED RWY ON STANDBY WILL BE AVBL WITHIN 20 MINS. DEPENDENT ON THE WORK BEING CARRIED OUT AT THE TIME, IT MAY TAKE UP TO 2 HRS FOR A CLOSED RWY ON MAINT IS AVBL.''',
            'airport_code': 'RKSI',
            'effective_time': '20AUG25 08:33',
            'expiry_time': '30SEP25 23:59'
        }
    ]
    
    # 성능 테스트
    print("=== 병렬 처리 NOTAM 번역 시스템 테스트 ===")
    
    results = translate_notams_parallel(sample_notams)
    
    for result in results:
        print(f"\nNOTAM {result['notam_number']} ({result['notam_type']}):")
        print(f"  한국어: {result.get('korean_translation', 'N/A')[:200]}...")
        print(f"  요약: {result.get('korean_summary', 'N/A')}")
