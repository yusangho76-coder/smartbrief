"""
NOTAM 처리 관련 공통 유틸리티 함수
"""

import re
from .notam_constants import (
    SECTION_END_PATTERNS, ADDITIONAL_INFO_PATTERNS, UNWANTED_KEYWORDS,
    COMPANY_ADVISORY_PATTERNS, END_OF_NOTAMS_PATTERNS
)

def clean_additional_info(text):
    """
    NOTAM 텍스트에서 추가 정보 제거
    """
    lines = text.split('\n')
    cleaned_lines = []
    
    for line in lines:
        line_stripped = line.strip()
        
        # 불필요한 키워드 체크
        if any(keyword in line for keyword in UNWANTED_KEYWORDS):
            continue
            
        # 추가 정보 패턴 체크
        if any(re.search(pattern, line_stripped, re.IGNORECASE) for pattern in ADDITIONAL_INFO_PATTERNS):
            continue
            
        cleaned_lines.append(line)
    
    return '\n'.join(cleaned_lines).strip()

def split_notams_unified(text, notam_type='package'):
    """
    통합된 NOTAM 분리 함수
    """
    import re
    from .notam_constants import NOTAM_START_PATTERNS
    
    notam_start_pattern = NOTAM_START_PATTERNS[notam_type]
    lines = text.split('\n')
    notams = []
    current_notam = []
    skip_mode = False
    
    for line in lines:
        line_stripped = line.strip()
        
        # skip_mode가 활성화된 경우 새 NOTAM 시작 패턴이 아니면 건너뛰기
        if skip_mode:
            if notam_start_pattern.match(line):
                skip_mode = False
            else:
                continue
        
        # END OF KOREAN AIR NOTAM PACKAGE 처리
        if any(re.search(pattern, line_stripped, re.IGNORECASE) for pattern in END_OF_NOTAMS_PATTERNS):
            if current_notam:
                notams.append('\n'.join(current_notam).strip())
                current_notam = []
            skip_mode = True
            continue
            
        # COMPANY ADVISORY 섹션 완전 제외
        if any(re.search(pattern, line_stripped, re.IGNORECASE) for pattern in COMPANY_ADVISORY_PATTERNS):
            if current_notam:
                notams.append('\n'.join(current_notam).strip())
                current_notam = []
            skip_mode = True
            continue
            
        # [ALTN] 패턴 처리
        if re.search(r'\[ALTN\]', line_stripped, re.IGNORECASE):
            if current_notam:
                notams.append('\n'.join(current_notam).strip())
                current_notam = []
            skip_mode = True
            continue
            
        # section_end_patterns 처리
        if any(re.match(pattern, line_stripped, re.IGNORECASE) for pattern in SECTION_END_PATTERNS):
            if current_notam:
                notams.append('\n'.join(current_notam).strip())
                current_notam = []
            skip_mode = True
            continue
            
        # 새 NOTAM 시작
        if notam_start_pattern.match(line):
            if current_notam:
                notams.append('\n'.join(current_notam).strip())
                current_notam = []
            current_notam.append(line)
        elif current_notam:  # 현재 NOTAM이 있으면 내용 추가
            current_notam.append(line)
    
    if current_notam:
        notams.append('\n'.join(current_notam).strip())
    
    return notams

def remove_separators(text):
    """
    구분자 제거
    """
    separators = ['=' * 60, '_' * 60]  # 대시 제거, 등호와 언더스코어만 유지
    for separator in separators:
        text = text.replace(separator, '')
    return text.strip()

def merge_notam_lines(text):
    """
    NOTAM 라인 병합 및 정리
    """
    # 먼저 추가 정보 제거
    cleaned_text = clean_additional_info(text)
    
    lines = cleaned_text.split('\n')
    merged_lines = []
    i = 0
    
    notam_id_pattern = r'^[A-Z]{4}(?:\s+AIP\s+SUP)?\s+\d{1,3}/\d{2}$|^[A-Z]{4}\s+[A-Z]\d{4}/\d{2}$'
    date_line_pattern = r'^\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*-'
    
    while i < len(lines):
        line = lines[i].strip()
        if re.match(notam_id_pattern, line):
            if i + 1 < len(lines) and re.match(date_line_pattern, lines[i+1].strip()):
                merged_lines.append(f"{lines[i+1].strip()} {line}")
                i += 2
                continue
        merged_lines.append(line)
        i += 1
    
    return '\n'.join(merged_lines)
