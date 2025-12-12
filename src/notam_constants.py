"""
NOTAM 처리 관련 공통 상수 및 패턴 정의
"""

import re

# NOTAM 시작 패턴
NOTAM_START_PATTERNS = {
    'airport': re.compile(r'^(\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*-|[A-Z]{4}(?:\s+[A-Z]+)?\s*\d{1,3}/\d{2}$|[A-Z]{4}\s+[A-Z]\d{4}/\d{2}$|[A-Z]{4}\s+COAD\d{2}/\d{2}$)'),
    'package': re.compile(r"^\s*(?:E\))?\s*\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*-\s*(?:\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}|UFN|PERM)(?:\s+[A-Z]{4}(?:\s+(?:[A-Z0-9]+/\d{2}|AIP\s+(?:SUP|AD)\s+\d+(?:\.\d+)?))?)?")
}

# 섹션 종료 패턴
SECTION_END_PATTERNS = [
    r'^\*{8}\s*NO CURRENT NOTAMS FOUND\s*\*{8}$',
    r'^END OF KOREAN AIR NOTAM PACKAGE',
    r'^KOREAN AIR NOTAM PACKAGE',
    r'^SECY\s*/\s*SECURITY INFORMATION',
    r'^\[ALTN\]\s*[A-Z]{4}/.*',
    r'^\[DEST\]\s*[A-Z]{4}/.*',
    r'^\[EDTO\]\s*[A-Z]{4}/.*',
    r'^\[\d+%?\s*ERA\]\s*[A-Z]{4}/.*',
    r'^\[ERA\]\s*[A-Z]{4}/.*',
    r'^\[ERA\]\s+[A-Z]{4}/.*',
    r'^\[FIR\]\s*[A-Z]{4}/.*',
    r'^\[FIR\]\s+[A-Z]{4}/.*',
]

# 추가 정보 제거 패턴
ADDITIONAL_INFO_PATTERNS = [
    r'^\d+\.\s*COMPANY\s+RADIO\s*:',
    r'^\d+\.\s*COMPANY\s+ADVISORY\s*:',
    r'^\d+\.\s*RADIO\s*:',
    r'^\d+\.\s*ADVISORY\s*:',
    r'^\d+\.\s*[A-Z\s]+\s*:',
    r'^\[PAX\]',
    r'^\[JINAIR\]',
    r'^CTC\s+TWR',
    r'^NIL',
    # 번호가 매겨진 COMPANY ADVISORY 항목들
    r'^\d+\.\s+\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*-\s*(?:UFN|PERM)\s+[A-Z]{4}\s+COAD\d+/\d+',
    r'^\d+\.\s+\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*-\s*(?:UFN|PERM)\s+[A-Z]{4}\s+[A-Z]+\d+/\d+',
    # OCR 오류 패턴들
    r'â—C¼O\s*MPANY',
    r'â—C¼O\s*COMPANY',
    r'â—A¼R\s*RIVAL',
    r'â—O¼B\s*STRUCTION',
    r'â—G¼P\s*S',
    r'â—R¼U\s*NWAY',
    r'â—A¼PP\s*ROACH',
    r'â—T¼A\s*XIWAY',
    r'â—N¼A\s*VAID',
    r'â—D¼E\s*PARTURE',
    r'â—R¼U\s*NWAY\s*LIGHT',
    r'â—A¼IP',
    r'â—O¼T\s*HER'
]

# 불필요한 키워드
UNWANTED_KEYWORDS = [
    'â—R¼A MP', 'â—O¼B STRUCTION', 'â—G¼P S', 'â—R¼U NWAY', 'â—A¼PP ROACH', 'â—T¼A XIWAY',
    'â—N¼A VAID', 'â—D¼E PARTURE', 'â—R¼U NWAY LIGHT', 'â—A¼IP', 'â—O¼T HER'
]

# COMPANY ADVISORY 패턴
COMPANY_ADVISORY_PATTERNS = [
    r'COMPANY ADVISORY',
    r'MPANY ADVISORY'
]

# END OF NOTAMs 패턴
END_OF_NOTAMS_PATTERNS = [
    r'END OF KOREAN AIR NOTAM PACKAGE'
]
