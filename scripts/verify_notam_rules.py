#!/usr/bin/env python3
"""
NOTAM 분석 및 번역 규칙 검증 스크립트
규칙에 어긋나게 분석된 NOTAM이나 이상한 번역이 있는지 확인
"""

import re
import sys
import os

# 프로젝트 루트를 Python 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def check_twy_txl_translation(text):
    """TWY와 TXL 번역 규칙 검증"""
    issues = []
    
    # TWY가 "택시레인"으로 잘못 번역된 경우
    if re.search(r'택시레인\s*[A-Z]\d*', text):
        issues.append("TWY가 '택시레인'으로 잘못 번역됨")
    
    # TXL이 "택시웨이"로 잘못 번역된 경우
    if re.search(r'택시웨이\s*DC', text, re.IGNORECASE):
        issues.append("TXL이 '택시웨이'로 잘못 번역됨")
    
    # TXL이 "텍사스"나 "딜레이"로 잘못 번역된 경우
    if re.search(r'(텍사스|딜레이).*DC', text, re.IGNORECASE):
        issues.append("TXL이 '텍사스'나 '딜레이'로 잘못 번역됨")
    
    return issues

def check_de_anti_icing_translation(text):
    """DE/ANTI-ICING FLUID 번역 규칙 검증"""
    issues = []
    
    # "안티이싱 유체"로 잘못 번역된 경우
    if re.search(r'안티이싱\s*유체', text):
        issues.append("DE/ANTI-ICING FLUID가 '안티이싱 유체'로 잘못 번역됨")
    
    # "방빙 용액"만 있고 "제/방빙 용액"이 아닌 경우 (DE/ANTI-ICING인 경우)
    if re.search(r'방빙\s*용액', text) and '제/방빙' not in text:
        # 원문에 DE/ANTI-ICING이 있는 경우에만 문제
        if 'DE/ANTI-ICING' in text.upper() or 'DE-ANTI-ICING' in text.upper():
            issues.append("DE/ANTI-ICING FLUID가 '제/방빙 용액'이 아닌 '방빙 용액'으로 번역됨")
    
    return issues

def check_company_name_translation(text, original_text):
    """회사명 번역 규칙 검증"""
    issues = []
    
    # INLAND가 "국내"로 번역된 경우
    if 'INLAND' in original_text.upper() and re.search(r'국내\s*(제/방빙|제빙|방빙|TYPE)', text):
        issues.append("INLAND가 '국내'로 잘못 번역됨")
    
    # Purolator가 번역된 경우
    if 'PUROLATOR' in original_text.upper() and 'Purolator' not in text and 'PUROLATOR' not in text:
        issues.append("Purolator가 번역됨 (번역하지 않고 그대로 유지해야 함)")
    
    return issues

def check_original_text_completeness(original_text, d_field, e_field, f_field, g_field, comment_field):
    """original_text가 모든 필드를 포함하는지 검증"""
    issues = []
    
    # D) 필드가 있는데 original_text에 없는 경우
    if d_field and 'D)' not in original_text:
        issues.append("original_text에 D) 필드가 누락됨")
    
    # E) 필드가 있는데 original_text에 없는 경우
    if e_field and 'E)' not in original_text:
        issues.append("original_text에 E) 필드가 누락됨")
    
    # F) 필드가 있는데 original_text에 없는 경우
    if f_field and 'F)' not in original_text:
        issues.append("original_text에 F) 필드가 누락됨")
    
    # G) 필드가 있는데 original_text에 없는 경우
    if g_field and 'G)' not in original_text:
        issues.append("original_text에 G) 필드가 누락됨")
    
    # COMMENT) 필드가 있는데 original_text에 없는 경우
    if comment_field and 'COMMENT)' not in original_text:
        issues.append("original_text에 COMMENT) 필드가 누락됨")
    
    return issues

def check_coad_notam_header(original_text, notam_number):
    """COAD NOTAM의 원문에 시간 정보와 NOTAM 번호 헤더가 포함되지 않았는지 확인"""
    issues = []
    
    if 'COAD' in notam_number.upper():
        # 시간 정보 패턴 (예: 18NOV25 06:00 - 30APR26 23:59)
        time_pattern = r'\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*-\s*(?:UFN|PERM|\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2})'
        if re.search(time_pattern, original_text):
            issues.append("COAD NOTAM 원문에 시간 정보 헤더가 포함됨 (제거해야 함)")
        
        # NOTAM 번호 패턴 (예: RKSI COAD04/25)
        notam_pattern = r'[A-Z]{4}\s+COAD\d{2}/\d{2}'
        if re.search(notam_pattern, original_text):
            issues.append("COAD NOTAM 원문에 NOTAM 번호 헤더가 포함됨 (제거해야 함)")
    
    return issues

def verify_notam(notam_dict):
    """단일 NOTAM 검증"""
    issues = []
    
    notam_number = notam_dict.get('notam_number', '')
    original_text = notam_dict.get('original_text', '')
    korean_translation = notam_dict.get('korean_translation', '')
    english_translation = notam_dict.get('english_translation', '')
    d_field = notam_dict.get('d_field', '')
    e_field = notam_dict.get('e_field', '')
    f_field = notam_dict.get('f_field', '')
    g_field = notam_dict.get('g_field', '')
    comment_field = notam_dict.get('comment_field', '')
    
    # HTML 태그 제거 (검증을 위해)
    original_text_clean = re.sub(r'<[^>]+>', '', original_text)
    korean_translation_clean = re.sub(r'<[^>]+>', '', korean_translation)
    english_translation_clean = re.sub(r'<[^>]+>', '', english_translation)
    
    # original_text 완전성 검증
    issues.extend(check_original_text_completeness(
        original_text_clean, d_field, e_field, f_field, g_field, comment_field
    ))
    
    # COAD NOTAM 헤더 검증
    issues.extend(check_coad_notam_header(original_text_clean, notam_number))
    
    # 번역 규칙 검증
    issues.extend(check_twy_txl_translation(korean_translation_clean))
    issues.extend(check_de_anti_icing_translation(korean_translation_clean))
    issues.extend(check_company_name_translation(korean_translation_clean, original_text_clean))
    
    return issues

def main():
    """메인 함수"""
    print("NOTAM 분석 및 번역 규칙 검증 스크립트")
    print("=" * 60)
    print("\n이 스크립트는 NOTAM 분석 결과를 검증합니다.")
    print("실제 NOTAM 데이터를 로드하려면 app.py의 결과를 사용하거나")
    print("saved_results/ 디렉토리의 HTML 파일을 파싱해야 합니다.")
    print("\n검증 항목:")
    print("1. original_text가 D), E), F), G), COMMENT) 필드를 모두 포함하는지")
    print("2. COAD NOTAM의 원문에 시간 정보와 NOTAM 번호 헤더가 포함되지 않았는지")
    print("3. TWY vs TXL 번역 규칙 준수 여부")
    print("4. DE/ANTI-ICING FLUID 번역 규칙 준수 여부")
    print("5. 회사명(Purolator, INLAND) 번역 규칙 준수 여부")
    print("\n실제 검증을 수행하려면 NOTAM 데이터를 제공해야 합니다.")

if __name__ == '__main__':
    main()

