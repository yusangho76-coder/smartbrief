"""
최적화된 NOTAM 번역 및 요약 시스템

주요 최적화 기능:
1. 배치 처리: 여러 NOTAM을 한 번에 처리
2. 병렬 처리: 동시 API 호출
3. 통합 처리: 번역과 요약을 한 번에
4. 스마트 캐싱: 유사한 내용 재사용
"""

import os
import asyncio
import logging
import time
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import google.generativeai as genai
from dotenv import load_dotenv
import re

# 환경 변수 로드
load_dotenv()

# 로깅 설정
logger = logging.getLogger(__name__)

@dataclass
class NotamBatch:
    """NOTAM 배치 처리를 위한 데이터 클래스"""
    notams: List[Dict[str, Any]]
    batch_id: str
    language: str  # 'en' 또는 'ko'

class TranslationCache:
    """번역 결과 캐싱 시스템"""
    
    def __init__(self, max_size: int = 1000):
        self.cache = {}
        self.max_size = max_size
        self.access_count = {}
    
    def get_hash(self, text: str) -> str:
        """텍스트의 해시값 생성"""
        return hashlib.md5(text.encode('utf-8')).hexdigest()
    
    def get(self, text: str, operation_type: str) -> Optional[Dict[str, Any]]:
        """캐시에서 결과 조회"""
        key = f"{operation_type}_{self.get_hash(text)}"
        if key in self.cache:
            self.access_count[key] = self.access_count.get(key, 0) + 1
            logger.debug(f"캐시 히트: {operation_type} for {text[:50]}...")
            return self.cache[key]
        return None
    
    def set(self, text: str, operation_type: str, result: Dict[str, Any]):
        """캐시에 결과 저장"""
        if len(self.cache) >= self.max_size:
            # LRU 방식으로 가장 적게 사용된 항목 제거
            least_used = min(self.access_count.items(), key=lambda x: x[1])
            del self.cache[least_used[0]]
            del self.access_count[least_used[0]]
        
        key = f"{operation_type}_{self.get_hash(text)}"
        self.cache[key] = result
        self.access_count[key] = 1
        logger.debug(f"캐시 저장: {operation_type} for {text[:50]}...")

class OptimizedNOTAMTranslator:
    """최적화된 NOTAM 번역기"""
    
    def __init__(self, max_workers: int = 5, batch_size: int = 10):
        """
        초기화
        
        Args:
            max_workers: 병렬 처리 워커 수
            batch_size: 배치 처리 크기
        """
        self.max_workers = max_workers
        self.batch_size = batch_size
        self.cache = TranslationCache()
        
        # Gemini 설정
        self.gemini_enabled = False
        try:
            api_key = os.getenv('GOOGLE_API_KEY')
            if api_key:
                genai.configure(api_key=api_key)
                self.model = genai.GenerativeModel('gemini-2.5-flash-lite')
                self.gemini_enabled = True
                logger.info("Gemini API 초기화 완료")
            else:
                logger.warning("GOOGLE_API_KEY가 설정되지 않음")
        except Exception as e:
            logger.error(f"Gemini 초기화 실패: {str(e)}")
            self.gemini_enabled = False
    
    def extract_e_section(self, notam_text: str) -> str:
        """
        NOTAM에서 E 섹션 추출 (사용하지 않음 - 이미 추출된 original_text 사용)
        이 함수는 하위 호환성을 위해 유지되지만 실제로는 사용되지 않습니다.
        """
        # 더 이상 사용하지 않음 - original_text를 직접 사용
        logger.warning("extract_e_section 함수가 호출되었지만 사용되지 않습니다. original_text를 직접 사용하세요.")
        return notam_text.strip()
    
    def create_batch_prompt(self, notams: List[str], target_language: str, include_summary: bool = True) -> str:
        """배치 처리용 프롬프트 생성"""
        
        if target_language == 'ko':
            lang_instruction = "한국어로 번역"
            summary_instruction = "각 NOTAM의 핵심 내용을 한 줄로 요약" if include_summary else ""
            
            # 한국어 번역용 상세 프롬프트
            prompt_parts = [
                f"You are an aviation NOTAM translation expert. Please {lang_instruction} the following NOTAMs.",
                "",
                "Instructions:",
                f"1. {lang_instruction} each NOTAM accurately",
                "",
                "2. 다음 용어는 그대로 유지:",
                "   - NOTAM, AIRAC, AIP, SUP, AMDT, WEF, TIL, UTC",
                "   - GPS, RAIM, PBN, RNAV, RNP",
                "   - RWY, TWY, APRON, TAXI, SID, STAR, IAP",
                "   - SFC, AMSL, AGL, MSL",
                "   - PSN, RADIUS, HGT, HEIGHT",
                "   - TEMP, PERM, OBST, FIREWORKS",
                "   - 모든 좌표, 주파수, 측정값",
                "   - 모든 날짜와 시간은 원래 형식 유지",
                "   - 모든 항공기 주기장 번호와 참조",
                "",
                "3. 특정 용어 번역:",
                "   - 'CLOSED'는 '폐쇄'로 번역",
                "   - 'PAVEMENT CONSTRUCTION'은 '포장 공사'로 번역",
                "   - 'OUTAGES'는 '기능 상실'로 번역",
                "   - 'PREDICTED FOR'는 '에 영향을 줄 것으로 예측됨'으로 번역",
                "   - 'WILL TAKE PLACE'는 '진행될 예정'으로 번역",
                "   - 'NPA'는 '비정밀접근'으로 번역",
                "   - 'FLW'는 '다음과 같이'로 번역",
                "   - 'ACFT'는 '항공기'로 번역",
                "   - 'NR.'는 '번호'로 번역",
                "   - 'ESTABLISHMENT OF'는 '신설'로 번역",
                "   - 'INFORMATION OF'는 '정보'로 번역",
                "   - 'CIRCLE'은 '원형'으로 번역",
                "   - 'CENTERED'는 '중심'으로 번역",
                "   - 'DUE TO'는 '로 인해'로 번역",
                "   - 'MAINT'는 '정비'로 번역",
                "   - 'NML OPS'는 '정상 운영'으로 번역",
                "   - 'U/S'는 '사용 불가'로 번역",
                "   - 'STANDBY'는 '대기'로 번역",
                "   - 'MAINT'는 '정비'로 번역",
                "   - 'AVBL'는 '사용 가능'로 번역",
                "   - 'UNAVBL'는 '사용 불가'로 번역",
                "   - 'CEILING'은 '운고'로 번역",
                "   - 괄호 안의 내용은 가능한 한 번역",
                "   - 열린 괄호는 반드시 닫기",
                "",
                "4. 다음 형식 정확히 유지:",
                "   - 여러 항목 (예: '1.PSN: ..., 2.PSN: ...')",
                "   - 좌표와 측정값",
                "   - 날짜와 시간",
                "   - NOTAM 섹션",
                "   - 항공기 주기장 번호와 참조",
                "   - 문장이나 구절이 완성되지 않은 경우 완성",
                "",
                "5. 다음 내용 포함하지 않음:",
                "   - NOTAM 번호",
                "   - E 섹션 외부의 날짜나 시간",
                "   - 공항 코드",
                "   - 'E:' 접두사",
                "   - 추가 설명이나 텍스트",
                "   - 'CREATED:' 이후의 텍스트",
                "",
                "6. 번역 스타일:",
                "   - 자연스러운 한국어 어순 사용",
                "   - 불필요한 조사나 어미 제거",
                "   - 간결하고 명확한 표현 사용",
                "   - 중복된 표현 제거",
                "   - 띄어쓰기 오류 없도록 주의",
                "   - 'DUE TO'는 항상 '로 인해'로 번역하고 'TO'를 추가하지 않음",
                "",
                "7. 중요한 규칙:",
                "   - 번역 결과에 '번역:', '공간', '이건 필요없는 말이야' 등의 불필요한 텍스트를 절대 포함하지 마세요",
                "   - 순수하게 NOTAM 내용만 번역하세요",
                "   - 번역 과정이나 메타데이터를 포함하지 마세요",
                "   - 완전한 문장으로 번역하세요",
                "   - 번역이 중간에 끊어지지 않도록 주의하세요",
            ]
        else:
            lang_instruction = "translate to English"
            summary_instruction = "summarize each NOTAM's key content in one line" if include_summary else ""
            
            # 영어 번역용 프롬프트 (개선된 버전)
            prompt_parts = [
                f"You are an aviation NOTAM translation expert. Please {lang_instruction} the following NOTAMs.",
                "",
                "⚠️ CRITICAL TRANSLATION RULES ⚠️",
                "1. ALWAYS translate ALL numbered lists completely:",
                "   - '1. RTE : A593 VIA SADLI' → '1. ROUTE: A593 VIA SADLI'",
                "   - '2. ACFT : LANDING RKRR' → '2. AIRCRAFT: LANDING RKRR'",
                "   - '3. PROC : FL330 AT OR BELOW AVBL' → '3. PROCEDURE: FL330 AT OR BELOW AVAILABLE'",
                "",
                "2. Handle 'FLOW CTL AS FLW' pattern:",
                "   - 'FLOW CTL AS FLW' → 'FLOW CONTROL AS FOLLOWING'",
                "   - Translate ALL subsequent numbered items (1. 2. 3. ...)",
                "   - DO NOT stop translation at numbered lists",
                "",
                "3. NEVER stop translation:",
                "   - Translate the entire text even if it's long",
                "   - Translate all numbered lists completely",
                "   - Handle complex structures fully",
                "",
                "4. Expand abbreviations and acronyms to full English words:",
                "   - 'FLW' → 'FOLLOWING'",
                "   - 'AS FLW' → 'AS FOLLOWING'",
                "   - 'FLOW CTL AS FLW' → 'FLOW CONTROL AS FOLLOWING'",
                "   - 'ACFT' → 'AIRCRAFT'",
                "   - 'RTE' → 'ROUTE'",
                "   - 'PROC' → 'PROCEDURE'",
                "   - 'RMK' → 'REMARK'",
                "   - 'WIP' → 'WORK IN PROGRESS'",
                "   - 'CLSD' → 'CLOSED'",
                "   - 'NML OPS' → 'NORMAL OPERATIONS'",
                "   - 'AVBL' → 'AVAILABLE'",
                "   - 'UNAVBL' → 'UNAVAILABLE'",
                "   - 'NOT AVBL' → 'NOT AVAILABLE'",
                "   - 'MAINT' → 'MAINTENANCE'",
                "   - 'U/S' → 'UNSERVICEABLE'",
                "",
                "5. Keep the following terms as is (aviation standards):",
                "   - NOTAM, AIRAC, AIP, SUP, AMDT, WEF, TIL, UTC",
                "   - GPS, RAIM, PBN, RNAV, RNP",
                "   - RWY, TWY, APRON, TAXI, SID, STAR, IAP",
                "   - All coordinates, frequencies, measurements",
                "   - All dates and times in original format",
                "   - Airport codes (RKSI, RJJJ, etc.)",
                "",
                "6. Translation Example:",
                "   Original: 'FLOW CTL AS FLW 1. RTE : A593 VIA SADLI 2. ACFT : LANDING RKRR 3. PROC : FL330 AT OR BELOW AVBL'",
                "   Translation: 'FLOW CONTROL AS FOLLOWING 1. ROUTE: A593 VIA SADLI 2. AIRCRAFT: LANDING RKRR 3. PROCEDURE: FL330 AT OR BELOW AVAILABLE'",
                "",
                "7. Improve grammar and sentence structure:",
                "   - Fix incomplete sentences",
                "   - Add proper articles (a, an, the)",
                "   - Use proper verb tenses",
                "   - Make sentences clear and readable",
            ]
        
        if include_summary:
            prompt_parts.append(f"8. {summary_instruction}")
            prompt_parts.append("9. Format: NOTAM_ID|TRANSLATION|SUMMARY")
        else:
            prompt_parts.append(f"8. Format: NOTAM_ID|TRANSLATION")
        
        prompt_parts.extend([
            "",
            "NOTAMs to process:",
            ""
        ])
        
        # NOTAM 목록 추가
        for i, notam in enumerate(notams, 1):
            prompt_parts.append(f"NOTAM_{i:03d}: {notam}")
            prompt_parts.append("")
        
        return "\n".join(prompt_parts)
    
    def parse_batch_response(self, response: str, notam_count: int, include_summary: bool = True) -> List[Dict[str, str]]:
        """배치 응답 파싱 (개선된 버전)"""
        results = []
        lines = response.strip().split('\n')
        
        logger.info(f"배치 응답 파싱 시작: {len(lines)}줄")
        logger.info(f"응답 내용: {response}")
        
        current_result = {}
        current_translation = ""
        current_summary = ""
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # NOTAM_ID|TRANSLATION|SUMMARY 형태 파싱
            if '|' in line and ('NOTAM_' in line or 'NOTAM' in line):
                # 이전 결과가 있으면 저장
                if current_result:
                    results.append(current_result)
                    current_result = {}
                
                parts = line.split('|', 2 if include_summary else 1)
                if len(parts) >= 2:
                    notam_id = parts[0].strip()
                    translation = parts[1].strip()
                    summary = parts[2].strip() if include_summary and len(parts) > 2 else ""
                    
                    current_result = {
                        'notam_id': notam_id,
                        'translation': translation,
                        'summary': summary
                    }
                    
                    # 번역이 완전하지 않은 경우 다음 줄들을 확인
                    if not translation or len(translation) < 10:
                        current_translation = translation
                        current_summary = summary
                continue
            
            # 현재 결과가 있고 번역이 불완전한 경우 계속 추가
            if current_result and current_translation:
                # 번역 내용이 계속되는 경우
                if not line.startswith(('NOTAM_', 'Format:', 'Instructions:', 'NOTAMs to process:')):
                    current_result['translation'] += ' ' + line
                    current_translation = current_result['translation']
        
        # 마지막 결과 저장
        if current_result:
            results.append(current_result)
        
        # 파싱된 결과가 없으면 전체 응답을 하나의 번역으로 처리
        if not results and response.strip():
            logger.warning("파싱된 결과가 없음. 전체 응답을 번역으로 처리")
            # 응답에서 번역 부분만 추출 시도
            translation_text = response.strip()
            # 불필요한 프롬프트 부분 제거
            if "NOTAMs to process:" in translation_text:
                translation_text = translation_text.split("NOTAMs to process:")[-1].strip()
            if "Format:" in translation_text:
                translation_text = translation_text.split("Format:")[0].strip()
            
            results.append({
                'notam_id': 'NOTAM_001',
                'translation': translation_text,
                'summary': '전체 응답'
            })
        
        # 결과가 부족하면 기본값으로 채움
        while len(results) < notam_count:
            results.append({
                'notam_id': f'NOTAM_{len(results)+1:03d}',
                'translation': '번역 실패',
                'summary': '요약 실패' if include_summary else ''
            })
        
        # 결과가 너무 많으면 잘라냄
        results = results[:notam_count]
        
        # 각 결과의 번역이 너무 짧으면 개별 번역 시도 필요
        for i, result in enumerate(results):
            if result['translation'] and len(result['translation']) < 20:
                logger.warning(f"NOTAM {i+1} 번역이 너무 짧음: '{result['translation']}'")
        
        logger.debug(f"파싱 완료: {len(results)}개 결과")
        return results
    
    async def translate_batch_async(self, notams: List[str], target_language: str, include_summary: bool = True) -> List[Dict[str, str]]:
        """비동기 배치 번역"""
        if not self.gemini_enabled:
            return [{'translation': notam, 'summary': ''} for notam in notams]
        
        # 캐시 확인
        batch_key = f"batch_{target_language}_{hashlib.md5(''.join(notams).encode()).hexdigest()}"
        cached = self.cache.get(batch_key, 'batch_translation')
        if cached:
            return cached
        
        try:
            prompt = self.create_batch_prompt(notams, target_language, include_summary)
            
            # 비동기 API 호출
            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(self.model.generate_content, prompt)
                response = await loop.run_in_executor(None, lambda: future.result())
            
            # 응답 파싱
            results = self.parse_batch_response(response.text, len(notams), include_summary)
            
            # 캐시에 저장
            self.cache.set(batch_key, 'batch_translation', results)
            
            return results
            
        except Exception as e:
            logger.error(f"배치 번역 오류: {e}")
            return [{'translation': f'번역 오류: {str(e)}', 'summary': '오류'} for _ in notams]
    
    def translate_individual_simple(self, notam_text: str, target_language: str) -> str:
        """간단한 개별 번역 (폴백용)"""
        if not self.gemini_enabled:
            return notam_text
        
        try:
            if target_language == 'ko':
                prompt = f"""다음 NOTAM을 한국어로 번역하세요. 항공 용어는 그대로 유지하고 자연스러운 한국어로 번역하세요.

{notam_text}

번역:"""
            else:
                prompt = f"""Translate the following NOTAM to English. Maintain aviation terminology and translate naturally.

{notam_text}

Translation:"""
            
            response = self.model.generate_content(prompt)
            return response.text.strip()
            
        except Exception as e:
            logger.error(f"간단한 개별 번역 실패: {e}")
            return notam_text

    def translate_batch(self, notams: List[str], target_language: str, include_summary: bool = True) -> List[Dict[str, str]]:
        """동기 배치 번역 (비동기 래퍼)"""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        return loop.run_until_complete(
            self.translate_batch_async(notams, target_language, include_summary)
        )
    
    def process_notams_optimized(self, notams_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        최적화된 NOTAM 처리 (배치 + 병렬)
        
        주요 변경사항:
        - E 섹션을 재추출하지 않고 이미 추출된 original_text를 직접 사용
        - _extract_content_after_notam_number()에서 추출한 원문을 그대로 번역에 활용
        - HTML 태그만 제거하고 원문 내용은 보존
        """
        if not notams_data:
            return []
        
        logger.info(f"최적화된 번역 시작: {len(notams_data)}개 NOTAM")
        start_time = time.time()
        
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
            
            original_texts.append(clean_text)
            
            # 디버깅을 위한 로깅
            if not clean_text:
                logger.warning(f"NOTAM {i} ({notam.get('notam_number', 'N/A')}): 원문 추출 실패")
                logger.warning(f"original_text: '{original_text[:100]}...' (길이: {len(original_text)})")
                logger.warning(f"description: '{notam.get('description', '')[:100]}...'")
            else:
                logger.debug(f"NOTAM {i} ({notam.get('notam_number', 'N/A')}): 원문 사용 (길이: {len(clean_text)})")
                logger.debug(f"원문 내용: '{clean_text[:100]}...'")
        
        # e_sections를 original_texts로 변경
        e_sections = original_texts
        
        # 배치로 나누기
        batches = []
        for i in range(0, len(e_sections), self.batch_size):
            batch = e_sections[i:i + self.batch_size]
            batches.append(batch)
        
        results = []
        
        # 병렬 배치 처리
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 한국어 번역+요약 작업 제출
            korean_futures = {
                executor.submit(self.translate_batch, batch, 'ko', True): i 
                for i, batch in enumerate(batches)
            }
            
            # 영어 번역+요약 작업 제출
            english_futures = {
                executor.submit(self.translate_batch, batch, 'en', True): i 
                for i, batch in enumerate(batches)
            }
            
            # 결과 수집
            korean_results = {}
            english_results = {}
            
            # 한국어 결과 수집
            for future in as_completed(korean_futures):
                batch_idx = korean_futures[future]
                try:
                    batch_result = future.result()
                    korean_results[batch_idx] = batch_result
                    logger.info(f"한국어 배치 {batch_idx + 1}/{len(batches)} 완료")
                except Exception as e:
                    logger.error(f"한국어 배치 {batch_idx} 오류: {e}")
                    logger.error(f"오류 타입: {type(e).__name__}")
                    import traceback
                    logger.error(f"스택 트레이스: {traceback.format_exc()}")
                    korean_results[batch_idx] = []
            
            # 영어 결과 수집
            for future in as_completed(english_futures):
                batch_idx = english_futures[future]
                try:
                    batch_result = future.result()
                    english_results[batch_idx] = batch_result
                    logger.info(f"영어 배치 {batch_idx + 1}/{len(batches)} 완료")
                except Exception as e:
                    logger.error(f"영어 배치 {batch_idx} 오류: {e}")
                    logger.error(f"오류 타입: {type(e).__name__}")
                    import traceback
                    logger.error(f"스택 트레이스: {traceback.format_exc()}")
                    english_results[batch_idx] = []
        
        # 결과 조합 (순서 보장)
        korean_flat = []
        english_flat = []
        
        for i in range(len(batches)):
            korean_batch_result = korean_results.get(i, [])
            english_batch_result = english_results.get(i, [])
            
            # 배치 결과가 비어있지 않은 경우에만 추가
            if korean_batch_result:
                korean_flat.extend(korean_batch_result)
            else:
                # 빈 배치의 경우 빈 결과 추가
                batch_size = len(batches[i])
                korean_flat.extend([{'translation': '', 'summary': ''} for _ in range(batch_size)])
            
            if english_batch_result:
                english_flat.extend(english_batch_result)
            else:
                # 빈 배치의 경우 빈 결과 추가
                batch_size = len(batches[i])
                english_flat.extend([{'translation': '', 'summary': ''} for _ in range(batch_size)])
        
        # 최종 결과 구성
        for i, notam in enumerate(notams_data):
            korean_result = korean_flat[i] if i < len(korean_flat) else {}
            english_result = english_flat[i] if i < len(english_flat) else {}
            
            # 번역 결과가 비어있는 경우 개별 번역 시도
            korean_translation = korean_result.get('translation', '')
            english_translation = english_result.get('translation', '')
            
            # 배치 번역 실패 시 개별 번역 시도 (더 엄격한 조건)
            korean_summary = korean_result.get('summary', '요약 실패')
            if (not korean_translation or korean_translation == '번역 실패' or len(korean_translation) < 20) and e_sections[i]:
                logger.warning(f"NOTAM {i} ({notam.get('notam_number', 'N/A')}) 한국어 번역 실패 또는 불완전, 개별 번역 시도")
                try:
                    # 개별 번역 시도
                    individual_result = self.translate_batch([e_sections[i]], 'ko', True)
                    if individual_result and len(individual_result) > 0:
                        individual_translation = individual_result[0].get('translation', '')
                        individual_summary = individual_result[0].get('summary', '')
                        
                        # 개별 번역이 더 완전한 경우에만 사용
                        if individual_translation and len(individual_translation) > len(korean_translation):
                            korean_translation = individual_translation
                            korean_summary = individual_summary
                            logger.info(f"NOTAM {i} 개별 한국어 번역 성공 (길이: {len(individual_translation)})")
                        else:
                            logger.warning(f"NOTAM {i} 개별 한국어 번역도 불완전함")
                    else:
                        logger.error(f"NOTAM {i} 개별 한국어 번역 결과 없음")
                except Exception as e:
                    logger.error(f"개별 한국어 번역 실패: {e}")
                    # 개별 번역도 실패한 경우 간단한 번역 시도
                    try:
                        simple_translation = self.translate_individual_simple(e_sections[i], 'ko')
                        if simple_translation and len(simple_translation) > len(korean_translation):
                            korean_translation = simple_translation
                            korean_summary = '간단 번역'
                            logger.info(f"NOTAM {i} 간단 한국어 번역 성공")
                        else:
                            korean_translation = e_sections[i]
                            korean_summary = '원문 표시'
                    except Exception as e2:
                        logger.error(f"간단 한국어 번역도 실패: {e2}")
                        korean_translation = e_sections[i]
                        korean_summary = '원문 표시'
            
            english_summary = english_result.get('summary', 'Summary failed')
            if (not english_translation or english_translation == 'Translation failed' or len(english_translation) < 20) and e_sections[i]:
                logger.warning(f"NOTAM {i} ({notam.get('notam_number', 'N/A')}) 영어 번역 실패 또는 불완전, 개별 번역 시도")
                try:
                    # 개별 번역 시도
                    individual_result = self.translate_batch([e_sections[i]], 'en', True)
                    if individual_result and len(individual_result) > 0:
                        individual_translation = individual_result[0].get('translation', '')
                        individual_summary = individual_result[0].get('summary', '')
                        
                        # 개별 번역이 더 완전한 경우에만 사용
                        if individual_translation and len(individual_translation) > len(english_translation):
                            english_translation = individual_translation
                            english_summary = individual_summary
                            logger.info(f"NOTAM {i} 개별 영어 번역 성공 (길이: {len(individual_translation)})")
                        else:
                            logger.warning(f"NOTAM {i} 개별 영어 번역도 불완전함")
                    else:
                        logger.error(f"NOTAM {i} 개별 영어 번역 결과 없음")
                except Exception as e:
                    logger.error(f"개별 영어 번역 실패: {e}")
                    # 개별 번역도 실패한 경우 간단한 번역 시도
                    try:
                        simple_translation = self.translate_individual_simple(e_sections[i], 'en')
                        if simple_translation and len(simple_translation) > len(english_translation):
                            english_translation = simple_translation
                            english_summary = 'Simple translation'
                            logger.info(f"NOTAM {i} 간단 영어 번역 성공")
                        else:
                            english_translation = e_sections[i]
                            english_summary = 'Original text'
                    except Exception as e2:
                        logger.error(f"간단 영어 번역도 실패: {e2}")
                        english_translation = e_sections[i]
                        english_summary = 'Original text'
            
            # 요약이 비어있거나 실패한 경우 개별 요약 시도
            if (not korean_summary or korean_summary == '요약 실패') and korean_translation and korean_translation != '번역 실패':
                logger.warning(f"NOTAM {i} ({notam.get('notam_number', 'N/A')}) 한국어 요약 실패, 개별 요약 시도")
                try:
                    # 개별 요약 시도 (번역만)
                    individual_summary_result = self.translate_batch([e_sections[i]], 'ko', True)
                    if individual_summary_result and len(individual_summary_result) > 0:
                        korean_summary = individual_summary_result[0].get('summary', '요약 실패')
                        logger.info(f"NOTAM {i} 개별 한국어 요약 성공")
                except Exception as e:
                    logger.error(f"개별 한국어 요약 실패: {e}")
                    korean_summary = '요약 실패'
            
            if (not english_summary or english_summary == 'Summary failed') and english_translation and english_translation != 'Translation failed':
                logger.warning(f"NOTAM {i} ({notam.get('notam_number', 'N/A')}) 영어 요약 실패, 개별 요약 시도")
                try:
                    # 개별 요약 시도 (번역만)
                    individual_summary_result = self.translate_batch([e_sections[i]], 'en', True)
                    if individual_summary_result and len(individual_summary_result) > 0:
                        english_summary = individual_summary_result[0].get('summary', 'Summary failed')
                        logger.info(f"NOTAM {i} 개별 영어 요약 성공")
                except Exception as e:
                    logger.error(f"개별 영어 요약 실패: {e}")
                    english_summary = 'Summary failed'
            
            enhanced_notam = notam.copy()
            enhanced_notam.update({
                'korean_translation': korean_translation or '번역 실패',
                'korean_summary': korean_summary or '요약 실패',
                'english_translation': english_translation or 'Translation failed',
                'english_summary': english_summary or 'Summary failed',
                'e_section': e_sections[i] if i < len(e_sections) else ''
            })
            results.append(enhanced_notam)
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        logger.info(f"최적화된 번역 완료: {len(results)}개 NOTAM, {processing_time:.2f}초")
        logger.info(f"평균 처리 시간: {processing_time/len(results):.2f}초/NOTAM")
        
        return results
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """캐시 통계 반환"""
        return {
            'cache_size': len(self.cache.cache),
            'total_access': sum(self.cache.access_count.values()),
            'hit_rate': len(self.cache.cache) / max(sum(self.cache.access_count.values()), 1)
        }

# 편의 함수들
def create_optimized_translator(max_workers: int = 5, batch_size: int = 10) -> OptimizedNOTAMTranslator:
    """최적화된 번역기 생성"""
    return OptimizedNOTAMTranslator(max_workers=max_workers, batch_size=batch_size)

def translate_notams_fast(notams_data: List[Dict[str, Any]], 
                         max_workers: int = 5, 
                         batch_size: int = 10) -> List[Dict[str, Any]]:
    """빠른 NOTAM 번역 (원샷 함수)"""
    translator = create_optimized_translator(max_workers, batch_size)
    return translator.process_notams_optimized(notams_data)

if __name__ == "__main__":
    # 테스트 코드
    logging.basicConfig(level=logging.INFO)
    
    # 샘플 NOTAM 데이터
    sample_notams = [
        {
            'id': 'A1234/25',
            'description': 'E) RWY 24 CLSD DUE TO CONSTRUCTION. COMMENT) RUNWAY CLOSED FOR MAINTENANCE.',
            'airport_code': 'KSEA'
        },
        {
            'id': 'A5678/25',
            'description': 'E) TWY A BTN AIR CARGO RAMP CLSD. COMMENT) TAXIWAY CLOSED.',
            'airport_code': 'KLAX'
        }
    ]
    
    # 성능 테스트
    print("=== 최적화된 번역 시스템 테스트 ===")
    start_time = time.time()
    
    results = translate_notams_fast(sample_notams, max_workers=3, batch_size=5)
    
    end_time = time.time()
    
    print(f"처리 시간: {end_time - start_time:.2f}초")
    print(f"처리된 NOTAM: {len(results)}개")
    
    for result in results:
        print(f"\nNOTAM {result['id']}:")
        print(f"  한국어: {result.get('korean_translation', 'N/A')}")
        print(f"  요약: {result.get('korean_summary', 'N/A')}")