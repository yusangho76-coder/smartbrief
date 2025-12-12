"""
Gemini-based NOTAM Translator
Gemini API를 사용한 고급 NOTAM 번역 및 요약 모듈
참조: SmartNOTAMgemini_GCR/notam_translator.py, summary.py
"""

import os
import logging
from typing import Dict, List, Optional
import re
from datetime import datetime

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

from .constants import (
    NO_TRANSLATE_TERMS, 
    DEFAULT_ABBR_DICT, 
    RED_STYLE_TERMS, 
    BLUE_STYLE_PATTERNS,
    COLOR_STYLES
)

class GeminiNOTAMTranslator:
    """Gemini API를 사용한 NOTAM 번역 및 요약 클래스"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.logger = logging.getLogger(__name__)
        self.api_key = api_key or os.getenv('GOOGLE_API_KEY')
        
        if GEMINI_AVAILABLE and self.api_key:
            try:
                genai.configure(api_key=self.api_key)
                self.model = genai.GenerativeModel(
                    'gemini-2.0-flash-exp',
                    generation_config=genai.types.GenerationConfig(temperature=0.3)
                )
                self.gemini_enabled = True
                self.logger.info("Gemini API 초기화 완료")
            except Exception as e:
                self.logger.warning(f"Gemini API 초기화 실패: {str(e)}")
                self.gemini_enabled = False
        else:
            self.gemini_enabled = False
            self.logger.info("Gemini API 사용 불가 - 사전 기반 번역 사용")
    
    def apply_color_styles(self, text: str) -> str:
        """
        텍스트에 색상 스타일을 적용
        참조 파일의 apply_color_styles 함수 적용
        
        Args:
            text (str): 원본 텍스트
            
        Returns:
            str: 스타일이 적용된 텍스트
        """
        # HTML 태그가 이미 있는지 확인하고 제거
        text = re.sub(r'<span[^>]*>', '', text)
        text = re.sub(r'</span>', '', text)
        
        # Runway를 RWY로 변환
        text = re.sub(r'\bRunway\s+', 'RWY ', text, flags=re.IGNORECASE)
        text = re.sub(r'\brunway\s+', 'RWY ', text, flags=re.IGNORECASE)
        
        # GPS RAIM을 하나의 단어로 처리
        text = re.sub(
            r'\bGPS\s+RAIM\b',
            f'{COLOR_STYLES["red"]}GPS RAIM{COLOR_STYLES["end"]}',
            text
        )
        
        # 빨간색 스타일 적용 (위험/주의사항)
        for term in RED_STYLE_TERMS:
            if term not in ['GPS RAIM']:  # GPS RAIM은 이미 처리됨
                pattern = r'\b' + re.escape(term) + r'\b'
                replacement = f'{COLOR_STYLES["red"]}{term}{COLOR_STYLES["end"]}'
                text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        
        # 파란색 스타일 적용 (항공시설/정보)
        for pattern in BLUE_STYLE_PATTERNS:
            def replace_func(match):
                return f'{COLOR_STYLES["blue"]}{match.group(0)}{COLOR_STYLES["end"]}'
            text = re.sub(pattern, replace_func, text)
        
        return text
    
    def translate_with_gemini(self, notam_text: str) -> str:
        """
        Gemini API를 사용한 NOTAM 번역
        
        Args:
            notam_text (str): 원본 NOTAM 텍스트
            
        Returns:
            str: 번역된 텍스트
        """
        if not self.gemini_enabled:
            return self.translate_with_dictionary(notam_text)
        
        try:
            prompt = f"""다음 NOTAM(Notice to Airmen)을 한국어로 번역해주세요. 
항공 전문용어는 정확하게 번역하고, 중요한 정보는 명확하게 전달해주세요.

번역 규칙:
1. 항공 전문용어는 한국 항공업계 표준 용어 사용
2. 공항 코드, 시간, 좌표는 원문 그대로 유지
3. 중요한 안전 정보는 강조하여 번역
4. 자연스러운 한국어로 번역하되 정확성 우선

NOTAM 원문:
{notam_text}

한국어 번역:"""

            response = self.model.generate_content(prompt)
            return response.text.strip()
            
        except Exception as e:
            self.logger.error(f"Gemini 번역 중 오류: {str(e)}")
            return self.translate_with_dictionary(notam_text)
    
    def translate_with_dictionary(self, text: str) -> str:
        """
        사전 기반 번역 (Gemini 사용 불가능한 경우)
        
        Args:
            text (str): 원본 텍스트
            
        Returns:
            str: 번역된 텍스트
        """
        translated = text
        
        # 기본 약어 확장
        for abbr, full in DEFAULT_ABBR_DICT.items():
            pattern = r'\b' + re.escape(abbr) + r'\b'
            translated = re.sub(pattern, full, translated, flags=re.IGNORECASE)
        
        # 한국어 용어 사전 적용
        korean_terms = {
            'RUNWAY': '활주로',
            'TAXIWAY': '유도로',
            'APRON': '계류장',
            'CLOSED': '폐쇄',
            'MAINTENANCE': '정비',
            'CONSTRUCTION': '공사',
            'OBSTACLE': '장애물',
            'LIGHTING': '조명',
            'CAUTION': '주의',
            'TEMPORARY': '임시',
            'PERMANENT': '영구',
            'AVAILABLE': '이용가능',
            'UNAVAILABLE': '이용불가'
        }
        
        for english, korean in korean_terms.items():
            if english not in NO_TRANSLATE_TERMS:
                pattern = r'\b' + re.escape(english) + r'\b'
                translated = re.sub(pattern, korean, translated, flags=re.IGNORECASE)
        
        return translated
    
    def summarize_with_gemini(self, notam_text: str, english_translation: str, korean_translation: str) -> str:
        """
        Gemini API를 사용한 NOTAM 요약
        참조 파일의 summarize_notam 함수 적용
        
        Args:
            notam_text (str): 원본 NOTAM 텍스트
            english_translation (str): 영어 번역
            korean_translation (str): 한국어 번역
            
        Returns:
            str: 요약된 텍스트
        """
        if not self.gemini_enabled:
            return self.summarize_with_template(notam_text)
        
        try:
            prompt = f"""다음 NOTAM을 간단명료하게 요약해주세요.

원본 NOTAM:
{notam_text}

한국어 번역:
{korean_translation}

⚠️ 중요한 규칙:
1. 다음 정보는 포함하지 마세요:
   - 시간 정보 (날짜, 시간, 기간, UTC)
   - 문서 참조 (AIRAC, AIP, AMDT, SUP)
   - "새로운 정보가 있습니다", "정보에 관하여" 같은 문구
   - 공항 이름
   - 좌표
   - 불필요한 괄호나 특수 문자

2. 중점 사항:
   - 핵심 변경사항이나 영향
   - 변경에 대한 구체적인 세부사항
   - 변경 이유

3. 간결하고 명확하게:
   - 가능한 한 짧게 작성
   - 직접적이고 능동적인 표현 사용
   - 필수 정보만 포함

4. 활주로 방향은 "L/R" 형식 사용 (예: "RWY 15 L/R")

한국어 요약:"""

            response = self.model.generate_content(prompt)
            return response.text.strip()
            
        except Exception as e:
            self.logger.error(f"Gemini 요약 중 오류: {str(e)}")
            return self.summarize_with_template(notam_text)
    
    def summarize_with_template(self, notam_text: str) -> str:
        """템플릿 기반 요약"""
        # 기본 템플릿 요약 로직
        summary_parts = []
        
        # 주요 키워드 추출
        if any(keyword in notam_text.upper() for keyword in ['CLOSED', 'CLOSE']):
            summary_parts.append("시설 폐쇄")
        if any(keyword in notam_text.upper() for keyword in ['OBSTACLE', 'OBSTRUCTION']):
            summary_parts.append("장애물 설치")
        if any(keyword in notam_text.upper() for keyword in ['MAINTENANCE', 'MAINT']):
            summary_parts.append("정비 작업")
        if any(keyword in notam_text.upper() for keyword in ['CONSTRUCTION']):
            summary_parts.append("공사 진행")
        
        # 활주로/유도로 정보
        rwy_match = re.search(r'RWY\s+(\d+[LRC]?)', notam_text, re.IGNORECASE)
        if rwy_match:
            summary_parts.append(f"활주로 {rwy_match.group(1)}")
        
        twy_match = re.search(r'TWY\s+([A-Z]+)', notam_text, re.IGNORECASE)
        if twy_match:
            summary_parts.append(f"유도로 {twy_match.group(1)}")
        
        return " | ".join(summary_parts) if summary_parts else "항공정보 업데이트"
    
    def process_notam_complete(self, notam_data: Dict) -> Dict:
        """
        NOTAM 데이터를 완전 처리 (번역 + 요약 + 스타일 적용)
        
        Args:
            notam_data (Dict): 원본 NOTAM 데이터
            
        Returns:
            Dict: 처리된 NOTAM 데이터
        """
        processed = notam_data.copy()
        
        original_text = notam_data.get('description', '')
        
        # 번역
        korean_translation = self.translate_with_gemini(original_text)
        processed['korean_translation'] = korean_translation
        
        # 요약
        summary = self.summarize_with_gemini(original_text, original_text, korean_translation)
        processed['summary'] = summary
        
        # 색상 스타일 적용
        styled_korean = self.apply_color_styles(korean_translation)
        processed['styled_korean'] = styled_korean
        
        styled_summary = self.apply_color_styles(summary)
        processed['styled_summary'] = styled_summary
        
        # 처리 시간 기록
        processed['processed_at'] = datetime.now().isoformat()
        
        return processed
    
    def create_flight_briefing(self, notams: List[Dict], flight_route: Optional[List[str]] = None) -> str:
        """
        비행 브리핑용 NOTAM 요약 생성
        
        Args:
            notams (List[Dict]): NOTAM 리스트
            flight_route (List[str]): 비행 경로 공항 코드들
            
        Returns:
            str: 비행 브리핑 텍스트
        """
        briefing = "=== 대한항공 NOTAM 브리핑 ===\n\n"
        briefing += f"생성 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        
        if flight_route:
            briefing += f"비행 경로: {' → '.join(flight_route)}\n\n"
        
        # 우선순위별 분류
        critical_notams = []
        normal_notams = []
        
        for notam in notams:
            priority = notam.get('priority', 0)
            if priority >= 10:  # 높은 우선순위
                critical_notams.append(notam)
            else:
                normal_notams.append(notam)
        
        # 중요 NOTAM
        if critical_notams:
            briefing += "🚨 중요 NOTAM:\n"
            for notam in critical_notams:
                summary = notam.get('summary', notam.get('description', ''))
                briefing += f"- {summary[:100]}...\n"
            briefing += "\n"
        
        # 일반 NOTAM
        if normal_notams:
            briefing += "📋 일반 NOTAM:\n"
            for notam in normal_notams:
                summary = notam.get('summary', notam.get('description', ''))
                briefing += f"- {summary[:100]}...\n"
        
        return briefing


# 하위 호환성을 위한 별칭
NOTAMTranslator = GeminiNOTAMTranslator