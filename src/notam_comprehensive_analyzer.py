
#!/usr/bin/env python3
"""
NOTAM 종합 분석기 - GEMINI AI를 활용한 고급 NOTAM 분석
"""

import google.generativeai as genai
import os
import re
from typing import List, Dict, Any, Optional
from datetime import datetime

# .env 파일 로드
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv가 설치되지 않은 경우 무시



class NotamComprehensiveAnalyzer:
    """GEMINI AI를 활용한 NOTAM 종합 분석기"""
    
    def __init__(self):
        """초기화"""
        import logging
        logger = logging.getLogger(__name__)
        
        self.api_key = os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
        if self.api_key:
            logger.info("GEMINI API 키 발견, 모델 초기화 중...")
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel('gemini-2.5-flash-lite')
            logger.info("GEMINI 모델 초기화 완료")
        else:
            logger.warning("GEMINI API 키가 설정되지 않았습니다. (GEMINI_API_KEY 또는 GOOGLE_API_KEY 환경변수 확인)")
            self.model = None
    
    def analyze_airport_notams(self, airport_code: str, notams_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        공항별 NOTAM을 종합적으로 분석 (GEMINI AI 활용) - API 호환성을 위한 별칭
        
        Args:
            airport_code: 공항 코드
            notams_data: NOTAM 데이터 리스트
            
        Returns:
            Dict[str, Any]: 종합 분석 결과
        """
        return self.analyze_airport_notams_comprehensive(airport_code, notams_data)
    
    def analyze_airport_notams_comprehensive(self, airport_code: str, notams_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        공항별 NOTAM을 종합적으로 분석 (GEMINI AI 활용)
        
        Args:
            airport_code: 공항 코드
            notams_data: NOTAM 데이터 리스트
            
        Returns:
            Dict[str, Any]: 종합 분석 결과
        """
        if not self.model:
            return self._fallback_analysis(airport_code, notams_data)
        
        # 모델이 None이 아닌지 확인
        if self.model is None:
            return self._fallback_analysis(airport_code, notams_data)
        
        # 이미 필터링된 NOTAM 데이터를 그대로 사용
        airport_notams = notams_data
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"분석할 NOTAM 개수: {len(airport_notams)}")
        
        if not airport_notams:
            return {
                'airport_code': airport_code,
                'analysis_type': 'comprehensive',
                'summary': f'{airport_code} 공항에는 현재 NOTAM이 없습니다.',
                'gemini_analysis': f'{airport_code} 공항에는 현재 NOTAM이 없습니다.',
                'critical_issues': [],
                'approach_landing_guidance': [],
                'ground_operations': [],
                'recommendations': []
            }
        
        # GEMINI AI로 종합 분석
        analysis_result = self._gemini_comprehensive_analysis(airport_code, airport_notams)
        
        return analysis_result
    
    def _filter_airport_notams(self, airport_code: str, notams_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """특정 공항의 NOTAM 필터링 (실제 필터링 수행)"""
        import logging
        logger = logging.getLogger(__name__)
        
        filtered_notams = []
        logger.info(f"=== {airport_code} 공항 NOTAM 필터링 시작 ===")
        logger.info(f"전체 NOTAM 개수: {len(notams_data)}")
        
        for notam in notams_data:
            # airports 필드에서 확인
            airports = notam.get('airports', [])
            if isinstance(airports, list) and airport_code in airports:
                filtered_notams.append(notam)
                logger.debug(f"NOTAM {notam.get('notam_number', 'N/A')} - airports 필드에서 {airport_code} 발견")
                continue
            
            # airport_code 필드에서 확인
            if notam.get('airport_code') == airport_code:
                filtered_notams.append(notam)
                logger.debug(f"NOTAM {notam.get('notam_number', 'N/A')} - airport_code 필드에서 {airport_code} 발견")
                continue
            
            # text/description에서 공항 코드 확인
            text = notam.get('text', '').upper()
            description = notam.get('description', '').upper()
            
            if airport_code in text or airport_code in description:
                filtered_notams.append(notam)
                logger.debug(f"NOTAM {notam.get('notam_number', 'N/A')} - 텍스트에서 {airport_code} 발견")
        
        logger.info(f"{airport_code} 관련 NOTAM 필터링 완료: {len(filtered_notams)}개")
        return filtered_notams
    
    def _gemini_comprehensive_analysis(self, airport_code: str, notams: List[Dict[str, Any]]) -> Dict[str, Any]:
        """GEMINI AI를 활용한 종합 분석"""
        import logging
        logger = logging.getLogger(__name__)
        
        logger.info(f"=== GEMINI AI 분석 시작: {airport_code} ===")
        logger.info(f"분석할 NOTAM 개수: {len(notams)}")
        
        # NOTAM 텍스트 준비
        notam_texts = []
        for i, notam in enumerate(notams, 1):
            text = notam.get('text', '')
            description = notam.get('description', '')
            korean_translation = notam.get('korean_translation', '')
            # NOTAM 번호 추출 (우선순위: notam_number > number > 기본값)
            notam_number = notam.get('notam_number') or notam.get('number') or f'#{i}'
            
            # 우선순위: korean_translation > text > description
            content = korean_translation if korean_translation else (text if text else description)
            
            notam_texts.append(f"[NOTAM {notam_number}]: {content}")
            logger.info(f"NOTAM {i} 준비: {notam_number} - {content[:50]}...")
        
        notam_summary = "\n".join(notam_texts)
        logger.info(f"NOTAM 요약 길이: {len(notam_summary)} 문자")
        
        # NOTAM이 없는 경우 처리 - 임시로 테스트용 NOTAM 추가
        if not notam_summary.strip():
            logger.warning(f"{airport_code} 공항에 대한 NOTAM 내용이 없습니다. 테스트용 NOTAM 추가.")
            notam_summary = f"[NOTAM #TEST]: {airport_code} 공항 테스트용 NOTAM - 활주로 정비 중"
        
        # GEMINI AI 프롬프트 (사용자 요청한 새로운 형식)
        prompt = f"""You are an AI assistant designed to help pilots by summarizing NOTAMs. Your task is to analyze the provided NOTAM text and generate a concise, professional briefing. The output should be easy for a pilot to read and understand at a glance.

**Instructions:**

1.  **Extract and categorize key information.** Identify all critical information from the NOTAMs, including:
    * **Major operational warnings** (e.g., GPS interference, specific gate procedures).
    * **Status of runways and taxiways** (e.g., closures, maintenance).
    * **Important schedule changes or temporary procedures.**
    * **Miscellaneous safety information** (e.g., temporary structures, training flights).

2.  **Use specific markdown headings.** Structure the final output using these exact headings:
    * 📢 **주요 운항 주의사항** (Major Operational Cautions)
    * ⚠️ **활주로 및 유도로 상태** (Runway & Taxiway Status)
    * ✈️ **기타 중요 정보** (Other Important Information)

3.  **Summarize each point clearly.** For each extracted piece of information, write a brief, direct summary. Do not include NOTAM numbers or other non-essential details. Focus on the direct impact on flight operations.

4.  **Use bold text for emphasis.** Bold key terms or phrases that are critical for pilot attention (e.g., **GPS 신호 간섭**, **폐쇄**, **재확인**).

5.  **Maintain a professional and clear tone.** The language should be concise, professional, and directly address the pilot's needs. Use emojis (📢, ⚠️, ✈️) as specified to visually categorize the information.

**Input Text:**

{notam_summary}

**Desired Output:**

[The exact formatted briefing from the user's initial request.]"""
        
        try:
            # 모델이 유효한지 다시 확인
            if self.model is None:
                logger.error("GEMINI 모델이 None입니다. API 키를 확인하세요.")
                return self._fallback_analysis(airport_code, notams)
            
            logger.info(f"GEMINI API 호출 시작: {airport_code}")
            logger.info(f"프롬프트 길이: {len(prompt)} 문자")
            
            # Gemini API 호출 시 파라미터 설정
            generation_config = genai.types.GenerationConfig(
                temperature=0.5,
                top_p=0.9,
                top_k=40,
                max_output_tokens=4096  # 토큰 제한을 2048에서 4096으로 증가
            )
            
            response = self.model.generate_content(
                prompt,
                generation_config=generation_config
            )
            
            logger.info("GEMINI API 호출 성공")
            result_text = response.text.strip()
            
            # HTML 태그 및 특수 문자 제거
            result_text = re.sub(r'<[^>]+>', '', result_text)  # HTML 태그 제거
            result_text = re.sub(r'\)">\s*', '', result_text)  # )"> 패턴 제거
            result_text = re.sub(r'\'\)">\s*', '', result_text)  # ')" 패턴 제거
            result_text = re.sub(r'&nbsp;', ' ', result_text)  # HTML 엔티티 제거
            result_text = re.sub(r'&lt;', '<', result_text)
            result_text = re.sub(r'&gt;', '>', result_text)
            result_text = re.sub(r'&amp;', '&', result_text)
            
            # 줄바꿈 정리 (연속된 공백은 정리하되 줄바꿈은 유지)
            result_text = re.sub(r'[ \t]+', ' ', result_text)  # 탭과 공백만 정리
            result_text = re.sub(r'\n\s*\n\s*\n+', '\n\n', result_text)  # 3개 이상 연속 줄바꿈을 2개로
            result_text = re.sub(r'^\s+', '', result_text, flags=re.MULTILINE)  # 줄 시작 공백 제거
            result_text = re.sub(r'\s+$', '', result_text, flags=re.MULTILINE)  # 줄 끝 공백 제거
            
            # 중복된 문장 제거 (같은 내용이 반복되는 경우)
            lines = result_text.split('\n')
            cleaned_lines = []
            seen_sentences = set()
            
            for line in lines:
                line = line.strip()
                if line and line not in seen_sentences:
                    # HTML 태그 잔재가 있는 문장도 정리
                    clean_line = re.sub(r'[^\w\s가-힣.,!?():-]', '', line)
                    if clean_line and clean_line not in seen_sentences:
                        cleaned_lines.append(line)
                        seen_sentences.add(line)
                        seen_sentences.add(clean_line)
            
            result_text = '\n'.join(cleaned_lines).strip()
            
            # 응답이 잘렸는지 확인 (일반적인 잘림 패턴 감지)
            if result_text.endswith('...') or len(result_text) < 100:
                # 응답이 너무 짧거나 잘린 것으로 보이는 경우
                import logging
                logging.warning(f"GEMINI 응답이 짧거나 잘린 것으로 보임: {len(result_text)} 문자")
                # fallback 분석으로 대체
                return self._fallback_analysis(airport_code, notams)
            
            # 새로운 텍스트 형식 프롬프트에 맞는 응답 처리
            return {
                'airport_code': airport_code,
                'analysis_type': 'comprehensive',
                'summary': result_text,  # Gemini의 전체 응답을 summary로 사용
                'gemini_analysis': result_text,
                'critical_issues': [],
                'approach_landing_guidance': [],
                'ground_operations': [],
                'recommendations': [],
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            # 인코딩 문제 방지를 위해 로깅 대신 사용
            import logging
            logging.error(f"GEMINI analysis error: {e}")
            return self._fallback_analysis(airport_code, notams)
    
    def _fallback_analysis(self, airport_code: str, notams: List[Dict[str, Any]]) -> Dict[str, Any]:
        """GEMINI 사용 불가 시 기본 분석"""
        import logging
        logger = logging.getLogger(__name__)
        
        # NOTAM 내용 요약 생성
        notam_summary = []
        for i, notam in enumerate(notams[:5], 1):  # 최대 5개만 표시
            text = notam.get('text', '')
            korean_translation = notam.get('korean_translation', '')
            # NOTAM 번호 추출 (우선순위: notam_number > number > 기본값)
            notam_number = notam.get('notam_number') or notam.get('number') or f'#{i}'
            
            content = korean_translation if korean_translation else text
            if content:
                notam_summary.append(f"NOTAM {notam_number}: {content[:100]}...")
        
        summary_text = f"**{airport_code} 공항 NOTAM 분석 결과**\n\n"
        summary_text += f"총 {len(notams)}개의 NOTAM이 발견되었습니다.\n\n"
        
        if notam_summary:
            summary_text += "**주요 NOTAM 내용:**\n\n"
            for i, notam in enumerate(notam_summary, 1):
                summary_text += f"{i}. {notam}\n\n"
        else:
            summary_text += "NOTAM 내용을 확인할 수 없습니다."
        
        logger.info(f"Fallback 분석 완료: {airport_code} - {len(notams)}개 NOTAM")
        
        return {
            'airport_code': airport_code,
            'analysis_type': 'basic',
            'summary': summary_text,
            'gemini_analysis': summary_text,
            'total_notams': len(notams),
            'critical_issues': [],
            'approach_landing_guidance': [],
            'ground_operations': [],
            'recommendations': ['GEMINI AI 분석을 위해 API 키를 설정해주세요.'],
            'timestamp': datetime.now().isoformat()
        }

def analyze_flight_airports_comprehensive(dep: str, dest: str, altn: Optional[str] = None, edto: Optional[str] = None, notams_data: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """
    항공편의 모든 공항에 대한 종합 NOTAM 분석 (GEMINI AI 활용)
    
    Args:
        dep: 출발 공항
        dest: 목적지 공항
        altn: 대체 공항 (선택)
        edto: EDTO 공항 (선택)
        notams_data: NOTAM 데이터
        
    Returns:
        Dict[str, Any]: 전체 종합 분석 결과
    """
    if not notams_data:
        notams_data = []
    
    analyzer = NotamComprehensiveAnalyzer()
    
    # 각 공항별 종합 분석
    airports = {
        'DEP': dep,
        'DEST': dest
    }
    
    if altn:
        airports['ALTN'] = altn
    
    # EDTO 처리: 여러 공항이 있을 수 있으므로 개별적으로 처리
    if edto:
        edto_airports = edto.split()  # 공백으로 분리
        for i, airport_code in enumerate(edto_airports):
            if airport_code.strip():  # 빈 문자열 제외
                airports[f'EDTO_{i+1}'] = airport_code.strip()
    
    results = {}
    for airport_type, airport_code in airports.items():
        results[airport_type] = analyzer.analyze_airport_notams_comprehensive(airport_code, notams_data)
    
    # 전체 요약 - 임시로 모든 NOTAM 개수 사용
    total_notams = len(notams_data)  # 임시로 전체 NOTAM 개수 사용
    
    return {
        'airports': results,
        'summary': {
            'total_airports': len(airports),
            'total_notams': total_notams,
            'analysis_type': 'comprehensive_gemini'
        },
        'timestamp': datetime.now().isoformat()
    }
