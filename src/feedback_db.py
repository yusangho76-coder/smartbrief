"""
Supabase 기반 피드백 수집 시스템
Few-shot learning을 위한 번역 피드백 데이터베이스 모듈
"""

import os
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from dotenv import load_dotenv

try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    logging.warning("Supabase 클라이언트가 설치되지 않았습니다. pip install supabase 실행 필요")

load_dotenv()

logger = logging.getLogger(__name__)


class FeedbackDB:
    """Supabase 피드백 데이터베이스 클라이언트"""
    
    def __init__(self, supabase_url=None, supabase_key=None):
        # 파라미터로 받은 값이 있으면 사용, 없으면 환경변수에서 가져옴
        self.supabase_url = supabase_url or os.getenv('SUPABASE_URL')
        self.supabase_key = supabase_key or os.getenv('SUPABASE_ANON_KEY') or os.getenv('SUPABASE_KEY')
        
        if not SUPABASE_AVAILABLE:
            self.client = None
            self.enabled = False
            logger.warning("Supabase 클라이언트를 사용할 수 없습니다.")
            return
        
        if not self.supabase_url or not self.supabase_key:
            self.client = None
            self.enabled = False
            logger.warning("Supabase 환경 변수가 설정되지 않았습니다. (SUPABASE_URL, SUPABASE_ANON_KEY)")
            return
        
        try:
            self.client: Client = create_client(self.supabase_url, self.supabase_key)
            self.enabled = True
            logger.info("Supabase 피드백 데이터베이스 연결 성공")
        except Exception as e:
            self.client = None
            self.enabled = False
            logger.error(f"Supabase 연결 실패: {e}")
    
    def submit_feedback(
        self,
        original_text: str,
        current_translation_ko: Optional[str] = None,
        current_translation_en: Optional[str] = None,
        current_summary_ko: Optional[str] = None,
        current_summary_en: Optional[str] = None,
        feedback_type: str = 'correction',
        corrected_translation_ko: Optional[str] = None,
        corrected_translation_en: Optional[str] = None,
        corrected_summary_ko: Optional[str] = None,
        corrected_summary_en: Optional[str] = None,
        feedback_comment: Optional[str] = None,
        notam_number: Optional[str] = None,
        airport_code: Optional[str] = None,
        user_id: Optional[str] = None,
        user_email: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        번역 피드백 제출
        
        Args:
            original_text: 원문 NOTAM 텍스트
            current_translation_ko: 현재 한국어 번역
            current_translation_en: 현재 영어 번역
            current_summary_ko: 현재 한국어 요약
            current_summary_en: 현재 영어 요약
            feedback_type: 피드백 타입 ('correction', 'improvement', 'error', 'approval')
            corrected_translation_ko: 수정된 한국어 번역
            corrected_translation_en: 수정된 영어 번역
            corrected_summary_ko: 수정된 한국어 요약
            corrected_summary_en: 수정된 영어 요약
            feedback_comment: 사용자 코멘트
            notam_number: NOTAM 번호
            airport_code: 공항 코드
            user_id: 사용자 ID (익명 가능)
            user_email: 사용자 이메일 (선택적)
            session_id: 세션 ID
        
        Returns:
            제출된 피드백 정보
        """
        if not self.enabled:
            return {'success': False, 'error': '피드백 시스템이 활성화되지 않았습니다.'}
        
        try:
            feedback_data = {
                'original_text': original_text,
                'original_notam_number': notam_number,
                'airport_code': airport_code,
                'current_translation_ko': current_translation_ko,
                'current_translation_en': current_translation_en,
                'current_summary_ko': current_summary_ko,
                'current_summary_en': current_summary_en,
                'feedback_type': feedback_type,
                'corrected_translation_ko': corrected_translation_ko,
                'corrected_translation_en': corrected_translation_en,
                'corrected_summary_ko': corrected_summary_ko,
                'corrected_summary_en': corrected_summary_en,
                'feedback_comment': feedback_comment,
                'user_id': user_id,
                'user_email': user_email,
                'session_id': session_id,
                'status': 'pending'
            }
            
            result = self.client.table('translation_feedback').insert(feedback_data).execute()
            
            if result.data:
                logger.info(f"피드백 제출 성공: {result.data[0].get('id')}")
                return {'success': True, 'id': result.data[0].get('id'), 'data': result.data[0]}
            else:
                return {'success': False, 'error': '피드백 제출 실패'}
                
        except Exception as e:
            logger.error(f"피드백 제출 오류: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}
    
    def get_learning_examples(
        self,
        limit: int = 100,
        min_priority: int = 0,
        airport_code: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Few-shot learning용 승인된 피드백 예제 가져오기
        
        Args:
            limit: 가져올 예제 수
            min_priority: 최소 우선순위
            airport_code: 특정 공항 코드 필터 (선택적)
        
        Returns:
            학습 예제 리스트
        """
        if not self.enabled:
            return []
        
        try:
            query = self.client.table('learning_examples').select('*')
            
            if airport_code:
                query = query.eq('airport_code', airport_code)
            
            query = query.gte('learning_priority', min_priority)
            query = query.limit(limit)
            
            result = query.execute()
            
            return result.data if result.data else []
            
        except Exception as e:
            logger.error(f"학습 예제 조회 오류: {e}", exc_info=True)
            return []
    
    def get_feedback_stats(self) -> Dict[str, Any]:
        """피드백 통계 조회"""
        if not self.enabled:
            return {}
        
        try:
            result = self.client.table('feedback_stats').select('*').execute()
            return result.data if result.data else {}
        except Exception as e:
            logger.error(f"통계 조회 오류: {e}", exc_info=True)
            return {}
    
    def approve_feedback(
        self,
        feedback_id: str,
        reviewed_by: str,
        is_approved_for_learning: bool = True,
        learning_priority: int = 0
    ) -> Dict[str, Any]:
        """
        피드백 승인 (관리자용)
        
        Args:
            feedback_id: 피드백 ID
            reviewed_by: 검토자
            is_approved_for_learning: 학습용 승인 여부
            learning_priority: 학습 우선순위
        
        Returns:
            업데이트 결과
        """
        if not self.enabled:
            return {'success': False, 'error': '피드백 시스템이 활성화되지 않았습니다.'}
        
        try:
            update_data = {
                'status': 'approved',
                'reviewed_by': reviewed_by,
                'reviewed_at': datetime.now().isoformat(),
                'is_approved_for_learning': is_approved_for_learning,
                'learning_priority': learning_priority
            }
            
            result = self.client.table('translation_feedback').update(update_data).eq('id', feedback_id).execute()
            
            if result.data:
                return {'success': True, 'data': result.data[0]}
            else:
                return {'success': False, 'error': '피드백 승인 실패'}
                
        except Exception as e:
            logger.error(f"피드백 승인 오류: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}
    
    def get_feedback_by_id(self, feedback_id: str) -> Optional[Dict[str, Any]]:
        """피드백 ID로 조회"""
        if not self.enabled:
            return None
        
        try:
            result = self.client.table('translation_feedback').select('*').eq('id', feedback_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"피드백 조회 오류: {e}", exc_info=True)
            return None

