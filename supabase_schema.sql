-- SmartNOTAM3 피드백 수집 시스템 스키마
-- Supabase PostgreSQL 데이터베이스용

-- 1. 번역 피드백 테이블
CREATE TABLE IF NOT EXISTS translation_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- 원문 정보
    original_text TEXT NOT NULL,
    original_notam_number VARCHAR(50),
    airport_code VARCHAR(10),
    
    -- 현재 번역 결과
    current_translation_ko TEXT,  -- 한국어 번역
    current_translation_en TEXT,  -- 영어 번역
    current_summary_ko TEXT,      -- 한국어 요약
    current_summary_en TEXT,       -- 영어 요약
    
    -- 피드백 정보
    feedback_type VARCHAR(20) NOT NULL,  -- 'correction', 'improvement', 'error', 'approval'
    corrected_translation_ko TEXT,       -- 수정된 한국어 번역
    corrected_translation_en TEXT,       -- 수정된 영어 번역
    corrected_summary_ko TEXT,           -- 수정된 한국어 요약
    corrected_summary_en TEXT,           -- 수정된 영어 요약
    feedback_comment TEXT,               -- 사용자 코멘트
    
    -- 메타데이터
    user_id VARCHAR(100),                -- 사용자 식별자 (익명 가능)
    user_email VARCHAR(255),             -- 선택적 이메일
    session_id VARCHAR(100),             -- 세션 ID
    
    -- 상태 관리
    status VARCHAR(20) DEFAULT 'pending', -- 'pending', 'approved', 'rejected', 'applied'
    reviewed_by VARCHAR(100),            -- 검토자
    reviewed_at TIMESTAMP WITH TIME ZONE,
    
    -- Few-shot learning용 플래그
    is_approved_for_learning BOOLEAN DEFAULT FALSE,
    learning_priority INTEGER DEFAULT 0, -- 우선순위 (높을수록 중요)
    
    -- 타임스탬프
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 2. 인덱스 생성 (검색 성능 향상)
CREATE INDEX IF NOT EXISTS idx_feedback_status ON translation_feedback(status);
CREATE INDEX IF NOT EXISTS idx_feedback_type ON translation_feedback(feedback_type);
CREATE INDEX IF NOT EXISTS idx_feedback_airport ON translation_feedback(airport_code);
CREATE INDEX IF NOT EXISTS idx_feedback_learning ON translation_feedback(is_approved_for_learning);
CREATE INDEX IF NOT EXISTS idx_feedback_created ON translation_feedback(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_feedback_notam_number ON translation_feedback(original_notam_number);

-- 3. Full-text search 인덱스 (원문 검색용)
CREATE INDEX IF NOT EXISTS idx_feedback_original_text ON translation_feedback USING gin(to_tsvector('english', original_text));

-- 4. 통계 뷰 (관리자 대시보드용)
CREATE OR REPLACE VIEW feedback_stats AS
SELECT 
    COUNT(*) as total_feedback,
    COUNT(*) FILTER (WHERE status = 'pending') as pending_count,
    COUNT(*) FILTER (WHERE status = 'approved') as approved_count,
    COUNT(*) FILTER (WHERE status = 'applied') as applied_count,
    COUNT(*) FILTER (WHERE is_approved_for_learning = TRUE) as learning_ready_count,
    COUNT(*) FILTER (WHERE feedback_type = 'correction') as correction_count,
    COUNT(*) FILTER (WHERE feedback_type = 'improvement') as improvement_count,
    COUNT(*) FILTER (WHERE feedback_type = 'error') as error_count,
    DATE(created_at) as feedback_date
FROM translation_feedback
GROUP BY DATE(created_at);

-- 5. Few-shot learning용 뷰 (승인된 피드백만)
CREATE OR REPLACE VIEW learning_examples AS
SELECT 
    id,
    original_text,
    original_notam_number,
    airport_code,
    current_translation_ko,
    corrected_translation_ko,
    current_translation_en,
    corrected_translation_en,
    current_summary_ko,
    corrected_summary_ko,
    current_summary_en,
    corrected_summary_en,
    learning_priority,
    created_at
FROM translation_feedback
WHERE is_approved_for_learning = TRUE 
  AND status = 'approved'
  AND corrected_translation_ko IS NOT NULL
ORDER BY learning_priority DESC, created_at DESC;

-- 6. 업데이트 트리거 (updated_at 자동 갱신)
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_translation_feedback_updated_at
    BEFORE UPDATE ON translation_feedback
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- 7. Row Level Security (RLS) 정책 (선택적 - 보안 강화 시)
-- ALTER TABLE translation_feedback ENABLE ROW LEVEL SECURITY;
-- 
-- -- 모든 사용자가 피드백을 추가할 수 있음
-- CREATE POLICY "Anyone can insert feedback" ON translation_feedback
--     FOR INSERT WITH CHECK (true);
-- 
-- -- 모든 사용자가 자신의 피드백을 조회할 수 있음
-- CREATE POLICY "Users can view their own feedback" ON translation_feedback
--     FOR SELECT USING (true);
-- 
-- -- 관리자만 수정/삭제 가능 (서비스 역할 사용)
-- CREATE POLICY "Admins can update feedback" ON translation_feedback
--     FOR UPDATE USING (auth.jwt() ->> 'role' = 'admin');

-- 8. 샘플 데이터 삽입 (테스트용 - 선택적)
-- INSERT INTO translation_feedback (
--     original_text,
--     original_notam_number,
--     airport_code,
--     current_translation_ko,
--     feedback_type,
--     corrected_translation_ko,
--     feedback_comment,
--     status,
--     is_approved_for_learning
-- ) VALUES (
--     '[25/26 DE/ANTI-ICING FLUID] [KAS] KILFROST DF PLUS',
--     'RKSI COAD04/25',
--     'RKSI',
--     '재방빙/방빙 용액으로 KILFROST DF PLUS가 사용됩니다.',
--     'correction',
--     '제/방빙 용액으로 KILFROST DF PLUS가 사용됩니다.',
--     'DE/ANTI-ICING은 제빙/방빙이 아니라 제/방빙으로 번역해야 합니다.',
--     'approved',
--     TRUE
-- );

