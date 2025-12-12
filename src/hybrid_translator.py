#!/usr/bin/env python3
"""
하이브리드 NOTAM 번역기
SmartNOTAMgemini_GCR의 전문적인 기능 + 간단한 프롬프트
"""

import os
import re
import logging
import google.generativeai as genai
from dotenv import load_dotenv
from typing import List, Dict, Any, Optional

# 환경 변수 로드
load_dotenv()

# 로깅 설정
logger = logging.getLogger(__name__)

# 번역하지 않을 용어 목록 (SmartNOTAMgemini_GCR 기반)
NO_TRANSLATE_TERMS = [
    "NOTAM", "NOTAMN", "NOTAMR", "NOTAMC", "TRIGGER NOTAM",
    "AIRAC", "AIP", "AIP SUP", "AIP AMDT",
    "RKSS", "RKSI", "RKRR", "KLAX", "KSEA", "LFLN", "LFGN",
    "ILS", "VOR", "DME", "NDB", "ADF", "RNAV", "GPS", "RAIM",
    "LPV", "LOC", "S-LOC", "MDA", "DA", "HAT", "VDP",
    "RWY", "TWY", "APRON", "TWR", "ATIS", "CTR", "FIR", "TMA",
    "STAND", "STANDS", "PARKING", "GATE",
    "UTC", "EST", "FT", "NM", "KM", "M", "MHZ", "KHZ",
    "ATC", "CNS", "MET", "VHF", "HF", "UHF", "RADAR", "TCAS",
    "GPWS", "EGPWS", "ACAS", "SID", "STAR", "IAP", "NPA",
    "SR", "SS", "SFC", "ASFC", "AMSL", "AGL",
    "N", "S", "E", "W", "NE", "NW", "SE", "SW",
    "L", "R", "C", "LEFT", "RIGHT", "CENTER",
    "CLSD", "U/S", "AVBL", "ACT", "INOP", "WIP",
    "TEMP", "PERM", "EST", "REF", "INFO",
    "FM", "TO", "BTN", "EXC", "DUE", "REF", "INFO",
    "MAINT", "OPR", "SVC", "THR", "TIL", "UFN"
]

# 색상 스타일 적용 용어 (SmartNOTAMgemini_GCR 기반)
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
    r'\bDVOR\b', r'\bAPRON\b', r'\bANTI-ICING\b', r'\bDE-ICING\b',
    r'\bSTAND\s+NUMBER\s+\d+\b', r'\bSTAND\s+\d+\b', r'\bSTAND\b',
    r'\bILS\b', r'\bLOC\b', r'\bS-LOC\b', r'\bMDA\b', r'\bCAT\b',
    r'\bVIS\b', r'\bRVR\b', r'\bHAT\b',
    r'\bRWY\s+(?:\d{2}[LRC]?(?:/\d{2}[LRC]?)?)\b',
    r'\bTWY\s+(?:[A-Z]|[A-Z]{2}|[A-Z]\d{1,2})\b',
    r'\bVOR\b', r'\bDME\b', r'\bTWR\b', r'\bATIS\b',
    r'\bAPPROACH MINIMA\b', r'\bVDP\b', r'\bEST\b',
    r'\bEastern Standard Time\b', r'\bIAP\b', r'\bRNAV\b',
    r'\bGPS\s+(?:APPROACH|APP|APPROACHES)\b', r'\bLPV\b', r'\bDA\b',
    r'\b주기장\b', r'\b주기장\s+\d+\b', r'\b활주로\s+\d+[A-Z]?\b',
    r'\bP\d+\b', r'\bSTANDS?\s*(?:NR\.)?\s*(\d+)\b'
]

class HybridNOTAMTranslator:
    """하이브리드 NOTAM 번역기 (전문적인 기능 + 간단한 프롬프트)"""
    
    def __init__(self):
        """초기화"""
        self.gemini_enabled = False
        try:
            api_key = os.getenv('GOOGLE_API_KEY')
            if api_key:
                genai.configure(api_key=api_key)
                self.model = genai.GenerativeModel('gemini-2.5-flash-lite')
                self.gemini_enabled = True
                logger.info("Hybrid NOTAM Translator 초기화 완료")
            else:
                logger.warning("GOOGLE_API_KEY가 설정되지 않음")
        except Exception as e:
            logger.error(f"Hybrid NOTAM Translator 초기화 실패: {str(e)}")
            self.gemini_enabled = False
    
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
    
    def extract_e_section(self, notam_text: str) -> str:
        """NOTAM 텍스트에서 E 섹션만 추출합니다."""
        # E 섹션 패턴 매칭 (개선된 버전)
        e_section_patterns = [
            r'E\)\s*(.*?)(?=\s*[A-Z]\)|$)',  # 기존 패턴
            r'E\)\s*(.*?)(?=\s*[A-Z][A-Z]\)|$)',  # 두 글자 섹션 고려
            r'E\)\s*(.*?)(?=\s*RMK|$)',  # RMK 섹션 고려
            r'E\)\s*(.*?)(?=\s*COMMENT|$)',  # COMMENT 섹션 고려
        ]
        
        for pattern in e_section_patterns:
            match = re.search(pattern, notam_text, re.DOTALL)
            if match:
                e_section = match.group(1).strip()
                # 불필요한 텍스트 제거
                e_section = re.sub(r'CREATED:.*$', '', e_section, flags=re.DOTALL).strip()
                e_section = re.sub(r'RMK:.*$', '', e_section, flags=re.DOTALL).strip()
                e_section = re.sub(r'COMMENT\).*$', '', e_section, flags=re.DOTALL).strip()
                # 카테고리 마커 제거 (◼ 또는 ■ 뒤에 오는 모든 텍스트 제거)
                # 예: ◼ RUNWAY, ■ TAXIWAY, ◼ COMPANY MINIMA FOR CAT II/III 등
                e_section = re.sub(r'[◼■]\s*[^\n]*(?:\n|$)', '', e_section, flags=re.MULTILINE).strip()
                
                if e_section:  # 빈 문자열이 아닌 경우만 반환
                    return e_section
        
        # E 섹션을 찾지 못한 경우 전체 텍스트에서 불필요한 부분 제거
        cleaned_text = notam_text.strip()
        cleaned_text = re.sub(r'CREATED:.*$', '', cleaned_text, flags=re.DOTALL).strip()
        cleaned_text = re.sub(r'RMK:.*$', '', cleaned_text, flags=re.DOTALL).strip()
        cleaned_text = re.sub(r'COMMENT\).*$', '', cleaned_text, flags=re.DOTALL).strip()
        # 카테고리 마커 제거 (◼ 또는 ■ 뒤에 오는 모든 텍스트 제거)
        # 예: ◼ RUNWAY, ■ TAXIWAY, ◼ COMPANY MINIMA FOR CAT II/III 등
        cleaned_text = re.sub(r'[◼■]\s*[^\n]*(?:\n|$)', '', cleaned_text, flags=re.MULTILINE).strip()
        
        return cleaned_text
    
    def preprocess_notam_text(self, notam_text: str) -> str:
        """NOTAM 텍스트를 번역 전에 전처리합니다."""
        # AIRAC AIP SUP과 UTC를 임시 토큰으로 대체
        notam_text = re.sub(r'\bAIRAC AIP SUP\b', 'AIRAC_AIP_SUP', notam_text)
        notam_text = re.sub(r'\bUTC\b', 'UTC_TOKEN', notam_text)
        
        # 다른 NO_TRANSLATE_TERMS 처리
        for term in NO_TRANSLATE_TERMS:
            if term not in ["AIRAC AIP SUP", "UTC"]:  # 이미 처리한 항목 제외
                notam_text = re.sub(r'\b' + re.escape(term) + r'\b', term.replace(' ', '_'), notam_text)
        
        return notam_text
    
    def postprocess_translation(self, translated_text: str) -> str:
        """번역된 텍스트를 후처리합니다."""
        # 임시 토큰을 원래 형태로 복원
        translated_text = translated_text.replace("AIRAC_AIP_SUP", "AIRAC AIP SUP")
        translated_text = translated_text.replace("UTC_TOKEN", "UTC")
        
        # 다른 NO_TRANSLATE_TERMS 복원
        for term in NO_TRANSLATE_TERMS:
            if term not in ["AIRAC AIP SUP", "UTC"]:  # 이미 처리한 항목 제외
                translated_text = translated_text.replace(term.replace(' ', '_'), term)
        
        return translated_text
    
    def apply_color_styles(self, text: str) -> str:
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
        for term in RED_STYLE_TERMS:
            if term != 'GPS RAIM':  # GPS RAIM은 이미 처리됨
                pattern = r'\b' + re.escape(term) + r'\b'
                replacement = f'<span style="color: red; font-weight: bold;">{term}</span>'
                text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        
        # 파란색 스타일 적용
        for pattern in BLUE_STYLE_PATTERNS:
            text = re.sub(
                pattern,
                lambda m: f'<span style="color: blue; font-weight: bold;">{m.group()}</span>',
                text,
                flags=re.IGNORECASE
            )
        
        # 중복된 span 태그 정리
        text = re.sub(r'(<span[^>]*>)+', r'\1', text)
        text = re.sub(r'(</span>)+', r'\1', text)
        text = re.sub(r'\s+', ' ', text)  # 중복 공백 제거
        
        return text.strip()
    
    def perform_translation(self, text: str, target_lang: str, notam_type: str) -> str:
        """Gemini를 사용하여 NOTAM 번역 수행 (개선된 프롬프트)"""
        try:
            # E 섹션만 추출
            e_section = self.extract_e_section(text)
            if not e_section:
                return "번역할 내용이 없습니다."

            # 개선된 번역 프롬프트 설정
            if target_lang == "en":
                prompt = f"""Summarize the following NOTAM(s) focusing on critical operational information for flight crews. Organize the summary into the following key categories:

Affected Location(s): Clearly state the airport(s), runway(s), taxiway(s), or specific areas impacted.

Nature of the Issue/Change: Describe what the NOTAM is announcing (e.g., closure, restriction, service outage, new procedure, hazard).

Operational Impact & Pilot Actions: Explain how this affects flight operations and what specific actions pilots need to take or be aware of (e.g., alternative procedures, increased caution, specific equipment settings).

Effective Dates & Times: Provide the start and end dates/times, or indicate if it's permanent/indefinite. Note any delays or schedule changes.

Additional Important Details: Include any other crucial information such as contact numbers, reference documents (AIP SUP, charts), or specific aircraft type considerations.

Ensure the summary is concise, easy to understand for immediate operational awareness, and prioritizes safety-critical information.

{e_section}"""
            else:  # Korean
                prompt = f"""다음 NOTAM 텍스트를 한국어로 번역하세요. 설명, 주석, 추가 정보를 포함하지 마세요. 직접 번역만 반환하세요:

중요한 번역 규칙:
- "CEILING"은 반드시 "운고"로 번역하세요
- "CLOSED"는 "폐쇄"로 번역하세요
- "REF"는 "참조"로 번역하세요
- "TXL"은 "택시레인"으로 번역하세요 (Taxilane: 주기장이나 격납고 주변에서 주차 공간 사이를 이동하기 위한 보조 이동로)
- TXL 뒤에 나오는 것은 택시레인의 이름입니다 (예: TXL DC = 택시레인 DC)
- 전문용어는 정확한 한국어 용어로 번역하세요

{e_section}"""
            
            # Gemini API 호출
            response = self.model.generate_content(prompt)
            translated_text = response.text.strip()
            
            # 후처리
            translated_text = self.postprocess_translation(translated_text)
            
            return translated_text
            
        except Exception as e:
            logger.error(f"번역 수행 중 오류 발생: {str(e)}")
            return "번역 중 오류가 발생했습니다."
    
    def extract_airport_code(self, text: str) -> str:
        """NOTAM 텍스트에서 공항 코드를 추출합니다."""
        import re
        
        # ICAO 공항 코드 패턴 (4글자 대문자)
        # 첫 번째 문자: 지역 코드 (A-Z)
        # 두 번째 문자: 국가 코드 (A-Z) 
        # 세 번째 문자: 지역 코드 (A-Z)
        # 네 번째 문자: 공항 식별자 (A-Z)
        airport_pattern = r'\b([A-Z]{4})\b'
        matches = re.findall(airport_pattern, text)
        
        # NOTAM에서 일반적으로 나타나는 위치에서 공항 코드 찾기
        # 패턴: 날짜 시간 공항코드 NOTAM번호
        # 예: "08SEP25 04:02 - 22OCT25 23:00 KSEA A2379/25"
        notam_header_pattern = r'\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*-\s*\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s+([A-Z]{4})\s+[A-Z]\d{4}/\d{2}'
        header_match = re.search(notam_header_pattern, text)
        if header_match:
            return header_match.group(1)
        
        # 다른 일반적인 패턴들
        patterns = [
            r'\b([A-Z]{4})\s+[A-Z]\d{4}/\d{2}',  # 공항코드 NOTAM번호
            r'\b([A-Z]{4})\s+AIP\s+SUP',         # 공항코드 AIP SUP
            r'\b([A-Z]{4})\s+NOTAM',             # 공항코드 NOTAM
            r'^([A-Z]{4})\s+',                   # 줄 시작의 공항코드
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
        
        # 마지막으로 모든 4글자 코드 중에서 첫 번째 반환
        # (NOTAM에서 가장 먼저 나타나는 것이 보통 공항 코드)
        return matches[0] if matches else 'UNKNOWN'
    
    def extract_notam_number(self, text: str) -> str:
        """NOTAM 텍스트에서 NOTAM 번호를 추출합니다."""
        import re
        
        # 디버깅을 위한 로그
        logger.debug(f"NOTAM 번호 추출 시작 - 텍스트: {text[:200]}...")
        
        # 다양한 NOTAM 번호 패턴들 (우선순위 순서)
        patterns = [
            # 패턴 1: 공항코드 + COAD + 번호/년도 (예: RKSI COAD01/25)
            r'([A-Z]{4}\s+COAD\d{2}/\d{2})',
            # 패턴 2: AIRAC AIP SUP + 번호/년도 (예: AIRAC AIP SUP 63/25) - 하나의 단어로 처리
            r'(AIRAC\s+AIP\s+SUP\s+\d{2}/\d{2})',
            # 패턴 3: 공항코드 + AIRAC AIP SUP + 번호/년도 (예: RKSI AIRAC AIP SUP 63/25)
            r'([A-Z]{4}\s+AIRAC\s+AIP\s+SUP\s+\d{2}/\d{2})',
            # 패턴 4: AIP SUP + 번호/년도 (예: AIP SUP 63/25) - 하나의 단어로 처리
            r'(AIP\s+SUP\s+\d{2}/\d{2})',
            # 패턴 5: 공항코드 + AIP SUP + 번호/년도 (예: RKSI AIP SUP 63/25)
            r'([A-Z]{4}\s+AIP\s+SUP\s+\d{2}/\d{2})',
            # 패턴 6: 공항코드 + 일반 NOTAM 번호 (예: RKSI A1242/25)
            r'([A-Z]{4}\s+[A-Z]\d{4}/\d{2})',
            # 패턴 7: 공항코드 + 특수 NOTAM 번호 (예: RKSI Z0816/25)
            r'([A-Z]{4}\s+[A-Z]\d{3,4}/\d{2})',
            # 패턴 8: 공항코드 + 숫자로 시작하는 NOTAM 번호 (예: RKSI 1234/25)
            r'([A-Z]{4}\s+\d{3,4}/\d{2})',
            # 패턴 9: COAD만 있는 경우 (예: COAD01/25)
            r'(COAD\d{2}/\d{2})',
            # 패턴 10: 일반 NOTAM 번호만 (예: A1242/25)
            r'([A-Z]\d{4}/\d{2})',
            # 패턴 11: 특수 NOTAM 번호만 (예: Z0816/25)
            r'([A-Z]\d{3,4}/\d{2})',
        ]
        
        for i, pattern in enumerate(patterns):
            match = re.search(pattern, text)
            if match:
                result = match.group(1).strip()
                logger.debug(f"패턴 {i+1} 매칭 성공: {result}")
                return result
        
        # 마지막으로 첫 번째 단어를 NOTAM 번호로 사용
        words = text.split()
        if words:
            logger.debug(f"패턴 매칭 실패, 첫 번째 단어 사용: {words[0]}")
            return words[0]
        
        logger.debug("NOTAM 번호 추출 실패")
        return 'UNKNOWN'
    
    def translate_notam(self, text: str) -> Dict[str, str]:
        """NOTAM 텍스트를 영어와 한국어로 번역합니다."""
        try:
            # NOTAM 번호 추출 (개선된 로직)
            notam_number = self.extract_notam_number(text)
            # NOTAM 타입 식별
            notam_type = self.identify_notam_type(notam_number)
            # 공항 코드 추출
            airport_code = self.extract_airport_code(text)
            
            # 영어 번역
            english_translation = self.perform_translation(text, "en", notam_type)
            english_translation = self.apply_color_styles(english_translation)
            
            # 한국어 번역
            korean_translation = self.perform_translation(text, "ko", notam_type)
            korean_translation = self.apply_color_styles(korean_translation)
            
            return {
                'english_translation': english_translation,
                'korean_translation': korean_translation,
                'notam_type': notam_type,
                'notam_number': notam_number,
                'airport_code': airport_code,
                'error_message': None
            }
        except Exception as e:
            logger.error(f"번역 수행 중 오류 발생: {str(e)}")
            return {
                'english_translation': 'Translation failed',
                'korean_translation': '번역 실패',
                'notam_type': 'UNKNOWN',
                'notam_number': 'UNKNOWN',
                'error_message': str(e)
            }
    
    def _calculate_optimal_batch_size(self, notams_data: List[Dict[str, Any]]) -> int:
        """NOTAM 길이와 복잡도에 따라 최적 배치 크기 계산"""
        if not notams_data:
            return 1
        
        total_length = sum(len(notam.get('description', '')) for notam in notams_data)
        avg_length = total_length / len(notams_data)
        
        # 길이 기반 배치 크기 결정 (보수적으로 설정)
        if avg_length < 200:  # 짧은 NOTAM
            return min(3, len(notams_data))
        elif avg_length < 500:  # 중간 길이 NOTAM
            return min(2, len(notams_data))
        else:  # 긴 NOTAM
            return 1
    
    def _create_batch_prompt(self, batch_notams: List[Dict[str, Any]], target_language: str) -> str:
        """배치 번역을 위한 프롬프트 생성"""
        prompt_parts = []
        
        if target_language == 'ko':
            prompt_parts.append("다음 NOTAM들을 한국어로 번역하세요. 각 NOTAM은 [NOTAM #n]으로 시작합니다:")
        else:
            prompt_parts.append("Translate the following NOTAMs to English. Each NOTAM starts with [NOTAM #n]:")
        
        prompt_parts.append("")
        
        for i, notam in enumerate(batch_notams):
            notam_text = notam.get('description', '')
            prompt_parts.append(f"[NOTAM #{i+1}] {notam_text}")
            prompt_parts.append("")
        
        if target_language == 'ko':
            prompt_parts.append("결과는 각 NOTAM별로 [NOTAM #n]: 번역 내용 형식으로 작성하세요.")
        else:
            prompt_parts.append("Please format the result as [NOTAM #n]: translated content for each NOTAM.")
        
        return "\n".join(prompt_parts)
    
    def _parse_batch_response(self, response: str, batch_size: int) -> List[str]:
        """배치 번역 응답을 개별 번역으로 파싱"""
        translations = [''] * batch_size
        
        # [NOTAM #n]: 패턴으로 분리
        pattern = r'\[NOTAM #(\d+)\]:\s*(.*?)(?=\[NOTAM #\d+\]:|$)'
        matches = re.findall(pattern, response, re.DOTALL)
        
        for match_num, translation in matches:
            try:
                idx = int(match_num) - 1
                if 0 <= idx < batch_size:
                    translations[idx] = translation.strip()
            except ValueError:
                continue
        
        return translations
    
    def _create_batch_summary_prompt(self, translations: List[str], language: str) -> str:
        """배치 요약을 위한 프롬프트 생성"""
        prompt_parts = []
        
        if language == 'ko':
            prompt_parts.append("다음 번역된 NOTAM들의 핵심 내용을 간단히 요약하세요. 각 NOTAM은 [NOTAM #n]으로 시작합니다:")
        else:
            prompt_parts.append("Summarize the key points of the following translated NOTAMs. Each NOTAM starts with [NOTAM #n]:")
        
        prompt_parts.append("")
        
        for i, translation in enumerate(translations):
            if translation.strip():
                prompt_parts.append(f"[NOTAM #{i+1}] {translation}")
                prompt_parts.append("")
        
        if language == 'ko':
            prompt_parts.append("결과는 각 NOTAM별로 [NOTAM #n]: 요약 내용 형식으로 작성하세요. 핵심 변경사항만 간단히 요약하세요.")
        else:
            prompt_parts.append("Please format the result as [NOTAM #n]: summary content for each NOTAM. Summarize only the key changes briefly.")
        
        return "\n".join(prompt_parts)
    
    def _parse_batch_summary_response(self, response: str, batch_size: int) -> List[str]:
        """배치 요약 응답을 개별 요약으로 파싱"""
        summaries = [''] * batch_size
        
        # [NOTAM #n]: 패턴으로 분리
        pattern = r'\[NOTAM #(\d+)\]:\s*(.*?)(?=\[NOTAM #\d+\]:|$)'
        matches = re.findall(pattern, response, re.DOTALL)
        
        for match_num, summary in matches:
            try:
                idx = int(match_num) - 1
                if 0 <= idx < batch_size:
                    summaries[idx] = summary.strip()
            except ValueError:
                continue
        
        return summaries

    def process_notams_hybrid(self, notams_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """스마트 배치 처리로 NOTAM들을 처리합니다."""
        if not notams_data:
            return []
        
        # 최적 배치 크기 계산
        optimal_batch_size = self._calculate_optimal_batch_size(notams_data)
        logger.info(f"하이브리드 번역 시작: {len(notams_data)}개 NOTAM (최적 배치 크기: {optimal_batch_size})")
        
        results = []
        
        # 배치로 나누어 처리
        for batch_start in range(0, len(notams_data), optimal_batch_size):
            batch_end = min(batch_start + optimal_batch_size, len(notams_data))
            batch_notams = notams_data[batch_start:batch_end]
            
            logger.info(f"배치 {batch_start//optimal_batch_size + 1} 처리 중: NOTAM {batch_start+1}-{batch_end}")
            
            # 배치 크기가 1이면 개별 처리
            if len(batch_notams) == 1:
                notam = batch_notams[0]
                description = notam.get('description', '')
                original_text = notam.get('original_text', description)
                
                # 개별 번역 수행
                translation_result = self.translate_notam(original_text)
                
                # 요약 생성
                korean_summary = self.create_hybrid_summary(translation_result['korean_translation'], 'ko')
                english_summary = self.create_hybrid_summary(translation_result['english_translation'], 'en')
                
                enhanced_notam = notam.copy()
                enhanced_notam.update({
                    'korean_translation': translation_result['korean_translation'],
                    'korean_summary': korean_summary,
                    'english_translation': translation_result['english_translation'],
                    'english_summary': english_summary,
                    'notam_type': translation_result['notam_type'],
                    'notam_number': translation_result['notam_number'],
                    'e_section': self.extract_e_section(description)
                })
                results.append(enhanced_notam)
                
                logger.info(f"NOTAM {batch_start+1} ({translation_result['notam_number']}) 개별 번역 완료 - 타입: {translation_result['notam_type']}")
            
            else:
                # 배치 번역 수행
                try:
                    # 한국어 배치 번역
                    korean_prompt = self._create_batch_prompt(batch_notams, 'ko')
                    korean_response = self.perform_translation(korean_prompt, 'ko', 'BATCH')
                    korean_translations = self._parse_batch_response(korean_response, len(batch_notams))
                    
                    # 영어 배치 번역
                    english_prompt = self._create_batch_prompt(batch_notams, 'en')
                    english_response = self.perform_translation(english_prompt, 'en', 'BATCH')
                    english_translations = self._parse_batch_response(english_response, len(batch_notams))
                    
                    # 배치 결과를 개별 NOTAM에 적용
                    for i, notam in enumerate(batch_notams):
                        global_index = batch_start + i
                        description = notam.get('description', '')
                        original_text = notam.get('original_text', description)
                        
                        # NOTAM 번호와 타입 추출 (개별 처리)
                        notam_number = self.extract_notam_number(original_text)
                        notam_type = self.identify_notam_type(notam_number)
                        
                        # 번역 결과 가져오기 (배치에서 실패한 경우 개별 처리)
                        korean_translation = korean_translations[i] if i < len(korean_translations) and korean_translations[i] else self.perform_translation(description, 'ko', notam_type)
                        english_translation = english_translations[i] if i < len(english_translations) and english_translations[i] else self.perform_translation(description, 'en', notam_type)
                        
                        # 요약 생성 (개별 처리)
                        korean_summary = self.create_hybrid_summary(korean_translation, 'ko')
                        english_summary = self.create_hybrid_summary(english_translation, 'en')
                        
                        enhanced_notam = notam.copy()
                        enhanced_notam.update({
                            'korean_translation': korean_translation,
                            'korean_summary': korean_summary,
                            'english_translation': english_translation,
                            'english_summary': english_summary,
                            'notam_type': notam_type,
                            'notam_number': notam_number,
                            'e_section': self.extract_e_section(description)
                        })
                        results.append(enhanced_notam)
                        
                        logger.info(f"NOTAM {global_index+1} ({notam_number}) 배치 번역 완료 - 타입: {notam_type}")
                
                except Exception as e:
                    logger.error(f"배치 번역 실패, 개별 처리로 전환: {e}")
                    # 배치 실패 시 개별 처리로 폴백
                    for i, notam in enumerate(batch_notams):
                        global_index = batch_start + i
                        description = notam.get('description', '')
                        original_text = notam.get('original_text', description)
                        
                        translation_result = self.translate_notam(original_text)
                        
                        korean_summary = self.create_hybrid_summary(translation_result['korean_translation'], 'ko')
                        english_summary = self.create_hybrid_summary(translation_result['english_translation'], 'en')
                        
                        enhanced_notam = notam.copy()
                        enhanced_notam.update({
                            'korean_translation': translation_result['korean_translation'],
                            'korean_summary': korean_summary,
                            'english_translation': translation_result['english_translation'],
                            'english_summary': english_summary,
                            'notam_type': translation_result['notam_type'],
                            'notam_number': translation_result['notam_number'],
                            'e_section': self.extract_e_section(description)
                        })
                        results.append(enhanced_notam)
                        
                        logger.info(f"NOTAM {global_index+1} ({translation_result['notam_number']}) 개별 폴백 번역 완료 - 타입: {translation_result['notam_type']}")
        
        logger.info(f"하이브리드 번역 완료: {len(results)}개 NOTAM")
        return results
    
    def create_hybrid_summary(self, translation: str, language: str) -> str:
        """하이브리드 요약 생성 (summary.py 기반 고급 요약)"""
        try:
            if language == 'ko':
                return self._create_korean_summary(translation)
            else:
                return self._create_english_summary(translation)
        except Exception as e:
            self.logger.error(f"요약 생성 중 오류: {str(e)}")
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
            self.logger.error(f"한국어 요약 생성 실패: {str(e)}")
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
            self.logger.error(f"영어 요약 생성 실패: {str(e)}")
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

# 편의 함수
def translate_notams_hybrid(notams_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """하이브리드 NOTAM 번역 (원샷 함수)"""
    translator = HybridNOTAMTranslator()
    return translator.process_notams_hybrid(notams_data)

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
    print("=== 하이브리드 NOTAM 번역 시스템 테스트 ===")
    
    results = translate_notams_hybrid(sample_notams)
    
    for result in results:
        print(f"\nNOTAM {result['notam_number']} ({result['notam_type']}):")
        print(f"  한국어: {result.get('korean_translation', 'N/A')[:200]}...")
        print(f"  요약: {result.get('korean_summary', 'N/A')}")
