"""
Gemini API 학습 및 개선 모듈
Few-shot Learning, 학습 데이터 관리, 프롬프트 최적화 기능 제공
"""

import os
import json
import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from pathlib import Path
import hashlib

logger = logging.getLogger(__name__)

class GeminiLearningManager:
    """Gemini API 학습 데이터 관리 및 Few-shot Learning 지원"""
    
    def __init__(self, learning_data_dir: str = "learning_data"):
        """
        Args:
            learning_data_dir: 학습 데이터 저장 디렉토리
        """
        self.learning_data_dir = Path(learning_data_dir)
        self.learning_data_dir.mkdir(exist_ok=True)
        
        # 학습 데이터 파일 경로
        self.translation_examples_file = self.learning_data_dir / "translation_examples.json"
        self.analysis_examples_file = self.learning_data_dir / "analysis_examples.json"
        self.feedback_file = self.learning_data_dir / "feedback.json"
        
        # 학습 데이터 로드
        self.translation_examples = self._load_examples(self.translation_examples_file)
        self.analysis_examples = self._load_examples(self.analysis_examples_file)
        self.feedback_data = self._load_examples(self.feedback_file)
        
        logger.info(f"학습 데이터 로드 완료: 번역 예제 {len(self.translation_examples)}개, 분석 예제 {len(self.analysis_examples)}개")
    
    def _load_examples(self, file_path: Path) -> List[Dict]:
        """학습 데이터 파일 로드"""
        if file_path.exists():
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data if isinstance(data, list) else []
            except Exception as e:
                logger.error(f"학습 데이터 로드 실패 ({file_path}): {e}")
                return []
        return []
    
    def _save_examples(self, file_path: Path, examples: List[Dict]):
        """학습 데이터 파일 저장"""
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(examples, f, ensure_ascii=False, indent=2)
            logger.debug(f"학습 데이터 저장 완료: {file_path}")
        except Exception as e:
            logger.error(f"학습 데이터 저장 실패 ({file_path}): {e}")
    
    def add_translation_example(self, 
                                original: str, 
                                translation: str, 
                                summary: str,
                                language: str = 'ko',
                                quality_score: float = 1.0,
                                metadata: Optional[Dict] = None):
        """
        번역 예제 추가
        
        Args:
            original: 원본 NOTAM 텍스트
            translation: 번역 결과
            summary: 요약 결과
            language: 대상 언어 ('ko' 또는 'en')
            quality_score: 품질 점수 (0.0 ~ 1.0)
            metadata: 추가 메타데이터
        """
        example = {
            'id': hashlib.md5(f"{original}_{language}".encode()).hexdigest()[:16],
            'original': original,
            'translation': translation,
            'summary': summary,
            'language': language,
            'quality_score': quality_score,
            'metadata': metadata or {},
            'created_at': datetime.now().isoformat()
        }
        
        # 중복 제거 (같은 ID가 있으면 업데이트)
        existing_idx = next(
            (i for i, ex in enumerate(self.translation_examples) 
             if ex.get('id') == example['id']), 
            None
        )
        
        if existing_idx is not None:
            # 기존 예제의 품질 점수가 더 높으면 유지
            if self.translation_examples[existing_idx].get('quality_score', 0) >= quality_score:
                logger.debug(f"기존 예제 유지 (더 높은 품질 점수): {example['id']}")
                return
            self.translation_examples[existing_idx] = example
        else:
            self.translation_examples.append(example)
        
        # 품질 점수 순으로 정렬 (높은 점수 우선)
        self.translation_examples.sort(key=lambda x: x.get('quality_score', 0), reverse=True)
        
        # 최대 100개까지만 유지 (메모리 효율성)
        if len(self.translation_examples) > 100:
            self.translation_examples = self.translation_examples[:100]
        
        self._save_examples(self.translation_examples_file, self.translation_examples)
        logger.info(f"번역 예제 추가 완료: {example['id']} (품질 점수: {quality_score})")
    
    def add_analysis_example(self,
                            route: str,
                            notam_data: str,
                            analysis_result: str,
                            quality_score: float = 1.0,
                            metadata: Optional[Dict] = None):
        """
        분석 예제 추가
        
        Args:
            route: 항로
            notam_data: NOTAM 데이터
            analysis_result: 분석 결과
            quality_score: 품질 점수 (0.0 ~ 1.0)
            metadata: 추가 메타데이터
        """
        example = {
            'id': hashlib.md5(f"{route}_{notam_data[:100]}".encode()).hexdigest()[:16],
            'route': route,
            'notam_data': notam_data[:500],  # 처음 500자만 저장
            'analysis_result': analysis_result,
            'quality_score': quality_score,
            'metadata': metadata or {},
            'created_at': datetime.now().isoformat()
        }
        
        # 중복 제거
        existing_idx = next(
            (i for i, ex in enumerate(self.analysis_examples) 
             if ex.get('id') == example['id']), 
            None
        )
        
        if existing_idx is not None:
            if self.analysis_examples[existing_idx].get('quality_score', 0) >= quality_score:
                return
            self.analysis_examples[existing_idx] = example
        else:
            self.analysis_examples.append(example)
        
        # 품질 점수 순으로 정렬
        self.analysis_examples.sort(key=lambda x: x.get('quality_score', 0), reverse=True)
        
        # 최대 50개까지만 유지
        if len(self.analysis_examples) > 50:
            self.analysis_examples = self.analysis_examples[:50]
        
        self._save_examples(self.analysis_examples_file, self.analysis_examples)
        logger.info(f"분석 예제 추가 완료: {example['id']} (품질 점수: {quality_score})")
    
    def get_few_shot_examples(self, 
                             task_type: str = 'translation',
                             language: str = 'ko',
                             max_examples: int = 3) -> List[Dict]:
        """
        Few-shot Learning용 예제 가져오기
        
        Args:
            task_type: 작업 유형 ('translation' 또는 'analysis')
            language: 대상 언어 ('ko' 또는 'en')
            max_examples: 최대 예제 수
            
        Returns:
            예제 리스트 (품질 점수 높은 순)
        """
        if task_type == 'translation':
            examples = [
                ex for ex in self.translation_examples 
                if ex.get('language') == language
            ]
        elif task_type == 'analysis':
            examples = self.analysis_examples
        else:
            return []
        
        # 품질 점수 순으로 정렬하고 상위 N개 반환
        examples.sort(key=lambda x: x.get('quality_score', 0), reverse=True)
        return examples[:max_examples]
    
    def add_feedback(self,
                    task_type: str,
                    original: str,
                    result: str,
                    feedback_type: str,  # 'positive' 또는 'negative'
                    comment: Optional[str] = None,
                    suggested_improvement: Optional[str] = None):
        """
        사용자 피드백 추가
        
        Args:
            task_type: 작업 유형 ('translation' 또는 'analysis')
            original: 원본 텍스트
            result: 결과 텍스트
            feedback_type: 피드백 유형 ('positive' 또는 'negative')
            comment: 피드백 코멘트
            suggested_improvement: 개선 제안
        """
        feedback = {
            'id': hashlib.md5(f"{original}_{task_type}_{datetime.now().isoformat()}".encode()).hexdigest()[:16],
            'task_type': task_type,
            'original': original[:500],  # 처음 500자만 저장
            'result': result[:500],
            'feedback_type': feedback_type,
            'comment': comment,
            'suggested_improvement': suggested_improvement,
            'created_at': datetime.now().isoformat()
        }
        
        if not hasattr(self, 'feedback_data'):
            self.feedback_data = []
        
        self.feedback_data.append(feedback)
        
        # 최대 200개까지만 유지
        if len(self.feedback_data) > 200:
            self.feedback_data = self.feedback_data[-200:]
        
        self._save_examples(self.feedback_file, self.feedback_data)
        logger.info(f"피드백 추가 완료: {feedback['id']} ({feedback_type})")
        
        # 부정적 피드백인 경우 학습 데이터에서 해당 예제 제거 또는 품질 점수 감소
        if feedback_type == 'negative' and task_type == 'translation':
            self._handle_negative_feedback(original, result)
    
    def _handle_negative_feedback(self, original: str, result: str):
        """부정적 피드백 처리"""
        example_id = hashlib.md5(f"{original}_ko".encode()).hexdigest()[:16]
        
        for i, ex in enumerate(self.translation_examples):
            if ex.get('id') == example_id:
                # 품질 점수 감소
                current_score = ex.get('quality_score', 1.0)
                new_score = max(0.0, current_score - 0.2)
                self.translation_examples[i]['quality_score'] = new_score
                
                # 품질 점수가 너무 낮으면 제거
                if new_score < 0.3:
                    self.translation_examples.pop(i)
                    logger.info(f"낮은 품질 예제 제거: {example_id}")
                else:
                    self._save_examples(self.translation_examples_file, self.translation_examples)
                    logger.info(f"예제 품질 점수 감소: {example_id} ({current_score} → {new_score})")
                break
    
    def build_few_shot_prompt(self,
                            base_prompt: str,
                            task_type: str = 'translation',
                            language: str = 'ko',
                            num_examples: int = 3) -> str:
        """
        Few-shot Learning 프롬프트 생성
        
        Args:
            base_prompt: 기본 프롬프트
            task_type: 작업 유형 ('translation' 또는 'analysis')
            language: 대상 언어 ('ko' 또는 'en')
            num_examples: 예제 수
            
        Returns:
            Few-shot Learning이 포함된 프롬프트
        """
        examples = self.get_few_shot_examples(task_type, language, num_examples)
        
        if not examples:
            return base_prompt
        
        # 예제 섹션 생성
        if task_type == 'translation':
            examples_section = self._build_translation_examples_section(examples, language)
        else:
            examples_section = self._build_analysis_examples_section(examples)
        
        # Few-shot Learning 프롬프트 조합
        few_shot_prompt = f"""다음은 이전에 성공적으로 처리된 예제들입니다. 이 예제들의 패턴을 참고하여 일관된 품질의 결과를 생성하세요.

{examples_section}

---

이제 다음 작업을 수행하세요:

{base_prompt}
"""
        return few_shot_prompt
    
    def _build_translation_examples_section(self, examples: List[Dict], language: str) -> str:
        """번역 예제 섹션 생성"""
        section = "## 번역 예제\n\n"
        
        for i, ex in enumerate(examples, 1):
            section += f"### 예제 {i} (품질 점수: {ex.get('quality_score', 0):.2f})\n\n"
            section += f"**원본 NOTAM:**\n```\n{ex['original'][:300]}...\n```\n\n"
            
            if language == 'ko':
                section += f"**한국어 번역:**\n```\n{ex['translation'][:300]}...\n```\n\n"
                section += f"**요약:**\n```\n{ex['summary']}\n```\n\n"
            else:
                section += f"**영어 번역:**\n```\n{ex['translation'][:300]}...\n```\n\n"
                section += f"**요약:**\n```\n{ex['summary']}\n```\n\n"
            
            section += "---\n\n"
        
        return section
    
    def _build_analysis_examples_section(self, examples: List[Dict]) -> str:
        """분석 예제 섹션 생성"""
        section = "## 항로 분석 예제\n\n"
        
        for i, ex in enumerate(examples, 1):
            section += f"### 예제 {i} (품질 점수: {ex.get('quality_score', 0):.2f})\n\n"
            section += f"**항로:** {ex['route']}\n\n"
            section += f"**NOTAM 데이터:**\n```\n{ex['notam_data'][:200]}...\n```\n\n"
            section += f"**분석 결과:**\n```\n{ex['analysis_result'][:500]}...\n```\n\n"
            section += "---\n\n"
        
        return section
    
    def get_statistics(self) -> Dict:
        """학습 데이터 통계 반환"""
        stats = {
            'translation_examples': len(self.translation_examples),
            'analysis_examples': len(self.analysis_examples),
            'feedback_count': len(self.feedback_data) if hasattr(self, 'feedback_data') else 0,
            'avg_translation_quality': (
                sum(ex.get('quality_score', 0) for ex in self.translation_examples) / 
                len(self.translation_examples) if self.translation_examples else 0
            ),
            'avg_analysis_quality': (
                sum(ex.get('quality_score', 0) for ex in self.analysis_examples) / 
                len(self.analysis_examples) if self.analysis_examples else 0
            )
        }
        return stats

