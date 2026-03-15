"""
SmartBrief - Smart Briefing System
OFP/NOTAM PDF 기반 비행 브리핑 및 NOTAM 분석 애플리케이션
"""

# 플랫폼별 인코딩 설정
# Windows에서는 콘솔 인코딩을 UTF-8로 명시적으로 설정
# Mac/Linux는 기본적으로 UTF-8을 사용하므로 추가 설정 불필요
import sys
import os
if sys.platform == "win32":
    os.environ["PYTHONIOENCODING"] = "utf-8"

# .env 파일 로드 (한 번만)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv가 설치되지 않은 경우 무시

from flask import Flask, request, render_template, jsonify, redirect, url_for, flash, send_file, send_from_directory, session
import re
from werkzeug.utils import secure_filename
import logging
from datetime import datetime, timedelta, timezone
import json
import glob
import uuid
import webbrowser
import subprocess
import platform
import signal
import atexit
from concurrent.futures import ThreadPoolExecutor

# 로컬 모듈 경로 설정
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

# 모듈 import
from src.pdf_converter import PDFConverter
from src.notam_filter import NOTAMFilter  
from src.integrated_translator import IntegratedNOTAMTranslator
from src.flight_info_extractor import extract_flight_info_from_notams
from src.ai_route_analyzer import analyze_route_with_gemini
from src.notam_comprehensive_analyzer import NotamComprehensiveAnalyzer
from src.api_routes import api_bp
from src.airport_notam_analyzer import AirportNotamAnalyzer
from src.feedback_db import FeedbackDB

# 로깅 설정
# Windows: 인코딩 문제 방지를 위해 UTF-8 명시적 설정 필요
# Mac/Linux: 기본적으로 UTF-8 사용하므로 추가 설정 불필요
if sys.platform == "win32":
    # Windows에서 콘솔 출력 인코딩 설정
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')  # type: ignore
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8')  # type: ignore
    except (AttributeError, Exception):
        pass
    
    # 로깅 핸들러에 UTF-8 인코딩 설정
    try:
        logging.basicConfig(
            level=logging.INFO, 
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(sys.stdout)
            ],
            force=True  # 기존 핸들러 재설정
        )
    except Exception:
        # 폴백: 기본 설정 사용
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
else:
    # Mac/Linux: 기본 UTF-8 인코딩 사용
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

logger = logging.getLogger(__name__)

# 성능 최적화: 번역 모듈의 로깅 레벨 조정
# 디버깅 시: logging.DEBUG로 변경하여 상세 로그 확인 가능
# 운영 시: logging.WARNING으로 설정 (디버그 로그 억제, 성능 향상)
logging.getLogger('src.integrated_translator').setLevel(logging.WARNING)  # 운영 모드: 성능 최적화

# 외부 라이브러리의 DEBUG 로그 억제로 성능 향상
logging.getLogger('pdfminer').setLevel(logging.WARNING)
logging.getLogger('pdfminer.psparser').setLevel(logging.WARNING)
logging.getLogger('pdfminer.pdfinterp').setLevel(logging.WARNING)
logging.getLogger('pdfminer.pdfdocument').setLevel(logging.WARNING)
logging.getLogger('pdfminer.pdfpage').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('requests').setLevel(logging.WARNING)
logging.getLogger('google.generativeai').setLevel(logging.WARNING)
logging.getLogger('google').setLevel(logging.WARNING)
logging.getLogger('google.api_core').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)
logging.getLogger('httpx').setLevel(logging.WARNING)

# Flask 앱 설정
# 템플릿 폴더를 명시적으로 지정하여 실행 위치와 무관하게 템플릿을 찾을 수 있도록 함
template_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
app.secret_key = 'your-secret-key-here'
app.register_blueprint(api_bp)

# 중복 요청 방지를 위한 처리 상태 플래그 (사용자별 세션 기반)
# 각 세션별로 독립적인 락을 관리하여 여러 사용자가 동시에 사용 가능하도록 함
_processing_locks = {}  # {session_id: {'locked': bool, 'lock_time': datetime}}
PROCESSING_LOCK_TIMEOUT = 600  # 10분 타임아웃 (초)

# Supabase 피드백 DB 초기화
SUPABASE_URL = os.getenv('SUPABASE_URL', 'https://vdfipoffvddrhtngyjeq.supabase.co')
SUPABASE_KEY = os.getenv('SUPABASE_ANON_KEY', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZkZmlwb2ZmdmRkcmh0bmd5amVxIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjQxMzQ2MzIsImV4cCI6MjA3OTcxMDYzMn0.gnbspW7OuhgpMWDPMmRcm3qbPDH3iW2X1MZ1e4VIb2Q')
feedback_db = FeedbackDB(supabase_url=SUPABASE_URL, supabase_key=SUPABASE_KEY)

# 설정
UPLOAD_FOLDER = 'uploads'
TEMP_FOLDER = 'temp'
ALLOWED_EXTENSIONS = {'pdf'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['TEMP_FOLDER'] = TEMP_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB

# CORS 설정 및 요청 로깅
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

@app.before_request
def log_request_info():
    # 간소화된 로깅: 중요한 요청만 로깅
    if request.path not in ['/', '/static/favicon.ico']:
        logger.debug(f'{request.method} {request.path}')

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_route_from_page2(pdf_path: str) -> str:
    """
    PDF에서 본경로 route 추출. (NOTAM 분석·구글 지도 항로 표시용)
    우선 2페이지, 실패 시 1·3·0·4페이지 순으로 시도. 로직은 ats_route_extractor.extract_ofp_route_from_page 사용.
    """
    import pdfplumber
    from src.ats_route_extractor import extract_ofp_route_from_page

    try:
        with pdfplumber.open(pdf_path) as pdf:
            total = len(pdf.pages)
            if total == 0:
                logger.debug("extract_route_from_page2: PDF 페이지 없음")
                return ''
            page_indices = [1] if total >= 2 else [0]
            if total >= 3:
                page_indices.extend([0, 2])
            if total >= 5:
                page_indices.append(4)
            for idx in page_indices:
                if idx >= total:
                    continue
                page_text = pdf.pages[idx].extract_text()
                route = extract_ofp_route_from_page(page_text or "")
                if route:
                    logger.info(f"extract_route_from_page2: 페이지 {idx + 1}에서 추출, 길이={len(route)}")
                    return route
            logger.debug("extract_route_from_page2: 모든 시도 페이지에서 경로 패턴을 찾지 못함")
            return ''
    except Exception as e:
        logger.error(f"extract_route_from_page2: 오류 발생 - {str(e)}")
        return ''

def _process_notam_text_as_package(text: str) -> str:
    """
    NOTAM 텍스트를 package 방식으로 처리 (split)
    """
    import re
    
    def merge_notam_lines(text_lines):
        """NOTAM 라인 병합"""
        lines = text_lines.split('\n')
        unwanted_keywords = [
            'â—R¼A MP', 'â—O¼B STRUCTION', 'â—G¼P S', 'â—R¼U NWAY', 'â—A¼PP ROACH', 'â—T¼A XIWAY',
            'â—N¼A VAID', 'â—D¼E PARTURE', 'â—R¼U NWAY LIGHT', 'â—A¼IP', 'â—O¼T HER'
        ]
        filtered_lines = [line for line in lines if not any(keyword in line for keyword in unwanted_keywords)]
        merged_lines = []
        i = 0
        
        notam_id_pattern = r'^[A-Z]{4}(?:\s+[A-Z]+(?:\s+[A-Z]+)*)?\s+\d{1,3}/\d{2}$|^[A-Z]{4}\s+[A-Z]\d{4}/\d{2}$'
        coad_pattern = r'^[A-Z]{4}\s+COAD\d{2}/\d{2}$'
        date_line_pattern = r'^(?:\d+\.\s+)?\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*-'
        
        while i < len(filtered_lines):
            line = filtered_lines[i].strip()
            
            if re.match(coad_pattern, line):
                if i + 1 < len(filtered_lines) and re.match(date_line_pattern, filtered_lines[i+1].strip()):
                    next_line = filtered_lines[i+1].strip()
                    cleaned_date_line = re.sub(r'^\d+\.\s+', '', next_line)
                    merged_lines.append(f"{cleaned_date_line} {line}")
                    i += 2
                    continue
            
            elif re.match(notam_id_pattern, line):
                if i + 1 < len(filtered_lines) and re.match(date_line_pattern, filtered_lines[i+1].strip()):
                    next_line = filtered_lines[i+1].strip()
                    cleaned_date_line = re.sub(r'^\d+\.\s+', '', next_line)
                    merged_lines.append(f"{cleaned_date_line} {line}")
                    i += 2
                    continue
            
            merged_lines.append(line)
            i += 1
        return '\n'.join(merged_lines)
    
    def split_notams(text_lines):
        """NOTAM 분리"""
        lines = text_lines.split('\n')
        notams = []
        current_notam = []
        notam_start_pattern = r'^\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*-'
        # section_start_pattern 제거: [로 시작하는 NOTAM은 없고, 섹션 헤더는 NOTAM 시작이 아님
        notam_id_pattern = r'^[A-Z]{4}(?:\s+[A-Z]+)?\s*\d{1,3}/\d{2}$|^[A-Z]{4}\s+[A-Z]\d{4}/\d{2}$|^[A-Z]{4}\s+COAD\d{2}/\d{2}$'
        end_phrase_pattern = r'ANY CHANGE WILL BE NOTIFIED BY NOTAM\.'
        # COAD 항목 패턴 (예: "3. 18NOV25 06:00 - 30APR26 23:59 RKSI COAD04/25")
        coad_item_pattern = r'^\d+\.\s+\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*-.*COAD\d{2}/\d{2}'
        # 구분선 패턴
        divider_pattern = r'^={60}$'
        
        for i, line in enumerate(lines):
            line_stripped = line.strip()
            
            # 구분선 체크
            is_divider = re.match(divider_pattern, line_stripped)
            
            # 다음 줄이 NOTAM 시작인지 확인
            next_line_is_notam_start = False
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                next_line_is_notam_start = (
                    re.match(notam_start_pattern, next_line) or
                    re.match(coad_item_pattern, next_line) or
                    re.match(notam_id_pattern, next_line)
                )
            
            # COAD 항목 시작 감지 (예: "3. 18NOV25 ... COAD04/25")
            coad_item_match = re.match(coad_item_pattern, line_stripped)
            if coad_item_match:
                # 이전 NOTAM 저장
                if current_notam:
                    notams.append('\n'.join(current_notam).strip())
                    current_notam = []
                # 새 COAD 항목 시작
                current_notam.append(line)
                continue
            
            # 일반 NOTAM 시작 패턴들
            # section_start_pattern은 제거: [로 시작하는 NOTAM은 없고, 섹션 헤더는 NOTAM 시작이 아님
            if (re.match(notam_start_pattern, line_stripped) or 
                re.match(notam_id_pattern, line_stripped)):
                # 이전 NOTAM 저장
                if current_notam:
                    notams.append('\n'.join(current_notam).strip())
                    current_notam = []
                # 새 NOTAM 시작
                current_notam.append(line)
                continue
            
            # 구분선 처리
            if is_divider:
                # 다음 줄이 NOTAM 시작이면 이전 NOTAM 종료
                if next_line_is_notam_start:
                    if current_notam:
                        notams.append('\n'.join(current_notam).strip())
                        current_notam = []
                    # 구분선은 추가하지 않음 (다음 NOTAM 시작 전이므로)
                    continue
                # 다음 줄이 NOTAM 시작이 아니면 현재 NOTAM에 포함하지 않음 (내부 구분선)
                continue
            
            current_notam.append(line)
            
            if re.search(end_phrase_pattern, line):
                notams.append('\n'.join(current_notam).strip())
                current_notam = []
        
        if current_notam:
            notams.append('\n'.join(current_notam).strip())
        return notams
    
    merged_text = merge_notam_lines(text)
    split_notams_list = split_notams(merged_text)
    
    unwanted_keywords = [
        'â—R¼A MP', 'â—O¼B STRUCTION', 'â—G¼P S', 'â—R¼U NWAY', 'â—A¼PP ROACH', 'â—T¼A XIWAY',
        'â—N¼A VAID', 'â—D¼E PARTURE', 'â—R¼U NWAY LIGHT', 'â—A¼IP', 'â—O¼T HER', 'â—A¼IR PORT'
    ]
    def remove_unwanted_lines_from_notam(notam):
        lines = notam.split('\n')
        cleaned_lines = []
        for line in lines:
            # 기존 unwanted_keywords 체크
            if any(keyword in line for keyword in unwanted_keywords):
                continue
            # 카테고리 마커 제거 (◼ 또는 ■ 뒤에 오는 카테고리명)
            if re.search(r'^[◼■]\s*[A-Z\s/]+$', line.strip()):
                continue
            cleaned_lines.append(line)
        return '\n'.join(cleaned_lines)
    
    split_notams_list_cleaned = [remove_unwanted_lines_from_notam(notam) for notam in split_notams_list]
    # pdf_converter.py의 _process_package_notam과 동일하게 구분선 추가
    # 구분선이 있으면 _filter_airport_notams가 NOTAM을 제대로 분리할 수 있음
    return '\n'.join([notam + "\n" + ("="*60) for notam in split_notams_list_cleaned]) + '\n'

def _process_notam_text_as_airport(text: str) -> str:
    """
    NOTAM 텍스트를 airport 방식으로 처리 (split)
    """
    import re
    
    def split_notams(text_lines):
        """NOTAM 분리 함수"""
        lines = text_lines.split('\n')
        notams = []
        current_notam = []
        notam_start_pattern = r'^\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*-\s*(?:\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}|UFN|PERM)(?:\s+[A-Z]{4}\s+COAD\d{2}/\d{2})?'
        notam_id_pattern = r'^[A-Z]{4}(?:\s+[A-Z]+)*(?:\s+[A-Z]+)*\s+\d{1,4}/\d{2}$|^[A-Z]{4}\s+[A-Z]\d{4}/\d{2}$'
        end_phrase_pattern = r'ANY CHANGE WILL BE NOTIFIED BY NOTAM\.'
        
        found_first_notam = False
        for line in lines:
            if re.match(notam_start_pattern, line):
                found_first_notam = True
                if current_notam:
                    notams.append('\n'.join(current_notam).strip())
                    current_notam = []
            if not found_first_notam:
                continue
            if re.match(notam_start_pattern, line) or re.match(notam_id_pattern, line):
                if current_notam:
                    notams.append('\n'.join(current_notam).strip())
                    current_notam = []
            current_notam.append(line)
            if re.search(end_phrase_pattern, line):
                notams.append('\n'.join(current_notam).strip())
                current_notam = []
        if current_notam:
            notams.append('\n'.join(current_notam).strip())
        return notams
    
    def remove_unwanted_lines_from_notam(notam):
        """불필요한 키워드가 포함된 줄 제거"""
        unwanted_keywords = [
            'â—R¼A MP', 'â—O¼B STRUCTION', 'â—G¼P S', 'â—R¼U NWAY', 'â—A¼PP ROACH', 'â—T¼A XIWAY',
            'â—N¼A VAID', 'â—D¼E PARTURE', 'â—R¼U NWAY LIGHT', 'â—A¼IP', 'â—O¼T HER', 'â—A¼IR PORT'
        ]
        lines = notam.split('\n')
        cleaned_lines = []
        for line in lines:
            # 기존 unwanted_keywords 체크
            if any(keyword in line for keyword in unwanted_keywords):
                continue
            # 카테고리 마커 제거 (◼ 또는 ■ 뒤에 오는 카테고리명)
            if re.search(r'^[◼■]\s*[A-Z\s/]+$', line.strip()):
                continue
            cleaned_lines.append(line)
        return '\n'.join(cleaned_lines)
    
    split_notams_list = split_notams(text)
    split_notams_list_cleaned = [remove_unwanted_lines_from_notam(notam) for notam in split_notams_list]
    # pdf_converter.py의 _process_airport_notam과 동일하게 구분선 추가
    # 구분선이 있으면 _filter_airport_notams가 NOTAM을 제대로 분리할 수 있음
    return '\n'.join([notam + "\n" + ("="*60) for notam in split_notams_list_cleaned]) + '\n'

def extract_notam_section_from_docpack(text: str) -> str:
    """
    docpack에서 NOTAM 섹션만 추출 (Package 1, 2, 3 모두 포함)
    시작: "KOREAN AIR NOTAM PACKAGE 1"
    종료: "END OF KOREAN AIR NOTAM PACKAGE 3 FOR 'call sign' 출발/도착 공항"
    """
    text_upper = text.upper()
    
    # NOTAM 섹션 시작 패턴 찾기
    notam_start_patterns = [
        r'KOREAN AIR NOTAM PACKAGE\s*1',  # Package 1로 시작
        r'KOREAN AIR NOTAM',
        r'NOTAM\s+PACKAGE',
    ]
    
    start_idx = -1
    for pattern in notam_start_patterns:
        match = re.search(pattern, text_upper)
        if match:
            start_idx = match.start()
            break
    
    if start_idx == -1:
        # NOTAM 시작을 찾지 못하면 전체 텍스트 반환
        logger.warning("NOTAM 시작 패턴을 찾지 못했습니다. 전체 텍스트를 반환합니다.")
        return text
    
    # NOTAM 종료 위치 찾기
    # "END OF KOREAN AIR NOTAM PACKAGE 3 FOR" 패턴 찾기
    end_idx = len(text)
    remaining_text = text[start_idx:]
    remaining_text_upper = remaining_text.upper()
    remaining_lines = remaining_text.split('\n')
    
    # Package 3 종료 패턴 찾기
    package3_end_pattern = r'END OF KOREAN AIR NOTAM PACKAGE\s*3\s+FOR'
    
    for i, line in enumerate(remaining_lines):
        line_upper = line.strip().upper()
        
        # Package 3 종료 패턴 확인
        if re.search(package3_end_pattern, line_upper):
            # 해당 줄의 끝까지 포함 (다음 줄 시작 전까지)
            # 줄 번호를 사용하여 정확한 위치 계산
            line_start = start_idx + len('\n'.join(remaining_lines[:i]))
            line_end = line_start + len(line) + 1  # 줄바꿈 포함
            end_idx = line_end
            logger.info(f"Package 3 종료 패턴 발견: 라인 {i+1}, 위치 {end_idx}")
            break
    
    # Package 3 종료를 찾지 못한 경우, 다른 종료 패턴 시도
    if end_idx == len(text):
        notam_end_patterns = [
            r'END OF KOREAN AIR NOTAM PACKAGE\s*3',  # Package 3 종료 (FOR 없이)
            r'END OF NOTAM',
            r'END OF KOREAN AIR NOTAM',
            # 기상자료 섹션 시작
            r'^WEATHER\s*$',
            r'^METAR\s*$',
            r'^TAF\s*$',
            # Flight Plan 섹션 시작
            r'^FLIGHT\s+PLAN\s*$',
            r'^FLIGHTPLAN\s*$',
            r'ROUTE\s*:',
        ]
        
        for i, line in enumerate(remaining_lines):
            line_upper = line.strip().upper()
            
            for pattern in notam_end_patterns:
                if re.search(pattern, line_upper):
                    # Package 1이나 2가 아닌 Package 3 종료만 찾기
                    if 'END OF KOREAN AIR NOTAM PACKAGE' in line_upper:
                        # Package 번호 확인
                        package_match = re.search(r'PACKAGE\s*(\d+)', line_upper)
                        if package_match:
                            package_num = int(package_match.group(1))
                            if package_num == 3:
                                # Package 3 종료 발견
                                line_end = start_idx + len('\n'.join(remaining_lines[:i+1]))
                                if line_end < end_idx:
                                    end_idx = line_end
                                    logger.info(f"Package 3 종료 패턴 발견 (패턴 2): 라인 {i+1}, 위치 {end_idx}")
                                    break
                    else:
                        # 다른 종료 패턴
                        line_start = start_idx + len('\n'.join(remaining_lines[:i]))
                        if line_start < end_idx:
                            end_idx = line_start
                            break
    
    logger.info(f"NOTAM 섹션 추출: 시작={start_idx}, 종료={end_idx}, 길이={end_idx-start_idx} 문자")
    return text[start_idx:end_idx]

def cleanup_files(directory, max_files=5):
    """
    지정된 디렉토리에서 최대 파일 개수만 유지하고 나머지는 삭제
    파일은 생성 시간 기준으로 오래된 것부터 삭제
    """
    try:
        if not os.path.exists(directory):
            return
            
        # 디렉토리 내 모든 파일 목록 가져오기
        files = glob.glob(os.path.join(directory, '*'))
        
        # 파일과 디렉토리만 필터링 (숨김 파일 제외)
        files = [f for f in files if os.path.isfile(f) and not os.path.basename(f).startswith('.')]
        
        if len(files) <= max_files:
            return

        # 파일 생성 시간 기준으로 정렬 (오래된 것부터)
        files.sort(key=lambda x: os.path.getctime(x))
        
        # 초과 파일들 삭제
        files_to_delete = files[:-max_files]
        for file_path in files_to_delete:
            try:
                os.remove(file_path)
            except Exception as e:
                logger.error(f"파일 삭제 실패 {file_path}: {str(e)}")
                
    except Exception as e:
        logger.error(f"파일 정리 중 오류 ({directory}): {str(e)}")

# 폴더 생성
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(TEMP_FOLDER, exist_ok=True)

# 파일 정리는 첫 요청 시에만 수행 (lazy initialization)
_files_cleaned = False

def ensure_files_cleaned():
    """파일 정리가 필요하면 수행 (한 번만 실행)"""
    global _files_cleaned
    if not _files_cleaned:
        cleanup_files(UPLOAD_FOLDER, max_files=3)  # 최신 3개만 유지 (용량 절감 + 이전 파일 확인 가능)
        cleanup_files(TEMP_FOLDER, max_files=3)  # 최신 3개만 유지 (용량 절감 + 이전 파일 확인 가능)
        _files_cleaned = True

# 모듈 초기화
pdf_converter = PDFConverter()
notam_filter = NOTAMFilter()

# Lazy initialization을 위한 전역 변수 (None으로 초기화)
_integrated_translator_instance = None
_notam_comprehensive_analyzer_instance = None

def get_integrated_translator():
    """Lazy initialization: 필요할 때만 IntegratedNOTAMTranslator 인스턴스 생성"""
    global _integrated_translator_instance
    if _integrated_translator_instance is None:
        logger.info("IntegratedNOTAMTranslator 초기화 중...")
        _integrated_translator_instance = IntegratedNOTAMTranslator()
        logger.info("IntegratedNOTAMTranslator 초기화 완료")
    return _integrated_translator_instance

def get_notam_comprehensive_analyzer():
    """Lazy initialization: 필요할 때만 NotamComprehensiveAnalyzer 인스턴스 생성"""
    global _notam_comprehensive_analyzer_instance
    if _notam_comprehensive_analyzer_instance is None:
        logger.info("NotamComprehensiveAnalyzer 초기화 중...")
        _notam_comprehensive_analyzer_instance = NotamComprehensiveAnalyzer()
        logger.info("NotamComprehensiveAnalyzer 초기화 완료")
    return _notam_comprehensive_analyzer_instance

# 최근 분석 결과 캐시 (메모리)
LAST_NOTAMS = []
LAST_NOTAMS_SOURCE = None  # 최근 소스 파일명
LAST_NOTAMS_INDEXED_BY_AIRPORT = {}  # { ICAO: [notam, ...] }
LAST_PACKAGE3_TEXT = None  # Package 3 원문 텍스트 캐시 (Cloud Run 호환성)

def get_last_package3_text():
    """Package 3 텍스트 캐시 반환 (순환 import 방지용)"""
    return LAST_PACKAGE3_TEXT

def _index_notams_by_airport(notams):
    indexed = {}
    try:
        for n in notams or []:
            # 명시적인 공항 리스트
            airports = n.get('airports', [])
            if isinstance(airports, list):
                for ac in airports:
                    if not ac:
                        continue
                    key = str(ac).strip().upper()
                    indexed.setdefault(key, []).append(n)
            # 단일 공항 코드
            ac2 = (n.get('airport_code') or '').strip().upper()
            if ac2:
                indexed.setdefault(ac2, []).append(n)
        return indexed
    except Exception:
        return {}

@app.route('/sw.js')
def service_worker():
    """Service Worker - 오프라인에서 저장된 분석 결과 확인 지원"""
    return send_from_directory(app.static_folder, 'sw.js', mimetype='application/javascript')


@app.route('/uploads/<path:filename>')
def serve_upload(filename):
    """uploads 폴더 파일 서빙 (차트 이미지 등)"""
    safe_dir = os.path.abspath(app.config['UPLOAD_FOLDER'])
    return send_from_directory(safe_dir, filename)


@app.route('/view-charts')
def view_charts():
    """OFP 기상 차트 뷰어 (새 창) — query params: sigwx1, asc, cross"""
    from flask import request as _req
    chart_images = {
        k: _req.args.get(k, '')
        for k in ('sigwx1', 'asc', 'cross')
        if _req.args.get(k)
    }
    return render_template('chart_viewer.html', chart_images=chart_images)


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/test_api.html')
def test_api():
    return render_template('test_api.html')

def convert_markdown_to_html(markdown_text: str) -> str:
    """
    마크다운 텍스트를 HTML로 변환하고 인라인 스타일로 스타일 강제 적용
    """
    import re
    
    if not markdown_text:
        return ""
    
    # 디버깅: 원본 텍스트 확인
    logger.info(f"마크다운 변환 시작, 길이: {len(markdown_text)}")
    logger.info(f"마크다운 처음 200자: {markdown_text[:200]}")
    
    html = markdown_text
    
    # h3 제목 공통 스타일 (중복 제거)
    h3_style = 'font-size: 20px !important; font-weight: 700 !important; border-bottom: 2px solid #0d6efd !important; padding-bottom: 6px !important; margin-top: 15px !important; margin-bottom: 0px !important; color: #0d6efd !important;'
    h3_template = f'<h3 style="{h3_style}"><i class="fas fa-exclamation-triangle me-2"></i>\\1</h3>'
    
    # 제목 변환 - **숫자. 형식의 제목을 먼저 처리 (### 변환보다 먼저)
    # **1. 주요 터뷸런스 예상 구간** → <h3>1. 주요 터뷸런스 예상 구간</h3>
    html = re.sub(r'^\*\*(\d+\.\s+.+?)\*\*$', h3_template, html, flags=re.MULTILINE)
    
    # 제목 변환 - 숫자. 형식의 제목 처리 (줄 시작에 숫자.가 있는 경우)
    # 1. 주요 터뷸런스 예상 구간 → <h3>1. 주요 터뷸런스 예상 구간</h3>
    html = re.sub(r'^(\d+\.\s+.+)$', h3_template, html, flags=re.MULTILINE)
    
    # 제목 변환 (### 제목 → <h3>제목</h3>) - 인라인 스타일 추가
    html = re.sub(r'^###\s+(.+)$', h3_template, html, flags=re.MULTILINE)
    html = re.sub(r'^##\s+(.+)$', r'<h2 style="font-size: 20px !important; font-weight: 600 !important; margin-top: 25px !important; margin-bottom: 15px !important; color: #0d6efd !important;">\1</h2>', html, flags=re.MULTILINE)
    html = re.sub(r'^#\s+(.+)$', r'<h1 style="font-size: 24px !important; font-weight: 700 !important; margin-top: 30px !important; margin-bottom: 20px !important; color: #0d6efd !important;">\1</h1>', html, flags=re.MULTILINE)
    
    # 마크다운 테이블을 HTML 테이블로 변환
    lines = html.split('\n')
    in_table = False
    table_html = []
    result_lines = []
    header_processed = False
    
    for i, line in enumerate(lines):
        # 테이블 시작 감지 (|로 시작하는 줄)
        if re.match(r'^\|.+\|$', line.strip()):
            if not in_table:
                in_table = True
                table_html = []
                header_processed = False
            
            # 헤더 구분선 제거 (|---|---|)
            if re.match(r'^\|[\s\-:]+\|', line.strip()):
                header_processed = True
                continue
            
            # 테이블 행 파싱
            cells = [cell.strip() for cell in line.strip().split('|')[1:-1]]
            if cells:
                if not header_processed:
                    # 헤더 행
                    # 반응형을 위해 colgroup 제거 (table-layout: auto 사용)
                    # colgroup은 table-layout: fixed일 때만 효과가 있음
                    table_html.append('<thead><tr>')
                    # 테이블 헤더 공통 스타일 (중복 제거)
                    th_base_style = "background: linear-gradient(135deg, #0d6efd 0%, #0a58ca 100%) !important; color: white !important; font-weight: 600 !important; font-size: 13px !important; padding: 10px 8px !important; text-align: center !important; vertical-align: middle !important; border: 1px solid #0a58ca !important; box-sizing: border-box !important;"
                    
                    for j, cell in enumerate(cells):
                        # 헤더 셀에서 :--- 형식 제거
                        cell_clean = re.sub(r':-+\s*$', '', cell).strip()
                        # 마지막 열(내용 및 근거)은 특별 처리
                        if j == len(cells) - 1:
                            th_style = th_base_style + " white-space: normal !important; width: 50% !important; min-width: 500px !important;"
                        else:
                            th_style = th_base_style + " white-space: nowrap !important;"
                        table_html.append(f'<th style="{th_style}">{cell_clean}</th>')
                    table_html.append('</tr></thead>')
                    header_processed = True
                else:
                    # 데이터 행
                    # 행의 심각도 판단 (내용 열에서 확인)
                    severity_class = ""
                    if len(cells) > 4:  # 내용 및 근거 열이 있는 경우
                        content_cell = cells[4] if len(cells) > 4 else ""
                        if 'SEV' in content_cell or 'Severe' in content_cell or '빨간색' in content_cell or 'red' in content_cell.lower():
                            severity_class = 'data-severity="severe"'
                        elif 'MODtoSEV' in content_cell or 'MODtoSEV' in content_cell or '노란색' in content_cell or 'yellow' in content_cell.lower():
                            severity_class = 'data-severity="modtosev"'
                        elif 'MOD' in content_cell or 'Moderate' in content_cell or '연한 파란색' in content_cell or 'light blue' in content_cell.lower():
                            severity_class = 'data-severity="moderate"'
                    
                    # 행 스타일 결정 (심각도에 따른 배경색)
                    row_style = ""
                    if severity_class == 'data-severity="severe"':
                        row_style = 'style="background-color: #fff5f5 !important; border-left: 4px solid #dc3545 !important;"'
                    elif severity_class == 'data-severity="modtosev"':
                        row_style = 'style="background-color: #fffbf0 !important; border-left: 4px solid #ffc107 !important;"'
                    elif severity_class == 'data-severity="moderate"':
                        row_style = 'style="background-color: #f0f8ff !important; border-left: 4px solid #0dcaf0 !important;"'
                    
                    table_html.append(f'<tr {severity_class} {row_style}>')
                    for j, cell in enumerate(cells):
                        # 터뷸런스 레벨에 따른 색상 적용
                        cell_html = cell
                        
                        # 마지막 열(내용 및 근거)인지 확인
                        is_content_cell = (j == len(cells) - 1)
                        
                        # "내용 및 근거" 열에서는 badge를 사용하지 않음 (긴 텍스트이므로)
                        # 다른 열에서만 badge 사용
                        if not is_content_cell:
                            # 배지 공통 스타일 (중복 제거) - if 블록 시작 부분에 정의
                            badge_base_style = "font-size: 0.9em !important; font-weight: 600 !important; padding: 5px 10px !important; border-radius: 4px !important;"
                            
                            # 구간 표시 형식 처리 (예: "22:48Z ~ 01:20Z", "KATCH ~ EEP1")
                            if ' ~ ' in cell:
                                # 구간 표시는 특별 스타일 적용
                                cell_html = f'<span style="color: #0d6efd !important; font-weight: 600 !important; font-size: 14px !important;">{cell}</span>'
                            # 시간 형식 강조 (예: 22:48Z, 03:45Z)
                            elif re.match(r'^\d{2}:\d{2}Z', cell.strip()):
                                cell_html = f'<span class="badge bg-secondary" style="font-family: \'Courier New\', monospace !important; {badge_base_style}">{cell}</span>'
                            # 숫자만 있는 경우 (예: 380, 360) - bold 적용
                            # 공백을 제거한 후 순수 숫자인지 확인 (시간 형식이 아닌 경우)
                            elif re.match(r'^\s*\d+\s*$', cell):
                                cell_html = f'<span style="font-weight: 700 !important;">{cell.strip()}</span>'
                            elif 'SR' in cell or 'Moderate' in cell or 'Severe' in cell or 'Light' in cell:
                                # 터뷸런스 레벨에 따른 색상 적용 (짧은 레이블만)
                                # SR 범위 파싱 (예: "SR 2-4", "SR 4-5", "SR 7")
                                sr_max = 0
                                sr_matches = re.findall(r'SR\s+(\d+)(?:\s*-\s*(\d+))?', cell, re.IGNORECASE)
                                for match in sr_matches:
                                    if match[1]:  # 범위인 경우 (예: "SR 2-4")
                                        sr_max = max(sr_max, int(match[0]), int(match[1]))
                                    else:  # 단일 값인 경우 (예: "SR 7")
                                        sr_max = max(sr_max, int(match[0]))
                                
                                # SR 기준에 따른 분류: SR 1-3: Light, SR 4: Moderate, SR 5-9: Moderate to Severe, SR 10+: Severe
                                if sr_max >= 10 or 'Severe' in cell or 'SEV' in cell:
                                    cell_html = f'<span class="badge bg-danger" style="{badge_base_style}">{cell}</span>'
                                elif sr_max >= 5 or 'Moderate to Severe' in cell or 'MODtoSEV' in cell:
                                    cell_html = f'<span class="badge bg-warning text-dark" style="{badge_base_style}">{cell}</span>'
                                elif sr_max >= 4 or ('Moderate' in cell and 'Light' not in cell and 'Severe' not in cell) or 'MOD' in cell:
                                    cell_html = f'<span class="badge bg-warning text-dark" style="{badge_base_style}">{cell}</span>'
                                elif sr_max >= 1 or 'Light' in cell or 'LGT' in cell:
                                    cell_html = f'<span class="badge bg-info" style="{badge_base_style}">{cell}</span>'
                                else:
                                    # SR 값이 없으면 텍스트 기반으로만 판단
                                    if 'Moderate to Severe' in cell or 'Severe' in cell or 'SEV' in cell:
                                        cell_html = f'<span class="badge bg-danger" style="{badge_base_style}">{cell}</span>'
                                    elif 'Moderate' in cell and 'Light' not in cell and 'Severe' not in cell:
                                        cell_html = f'<span class="badge bg-warning text-dark" style="{badge_base_style}">{cell}</span>'
                                    else:
                                        cell_html = f'<span class="badge bg-info" style="{badge_base_style}">{cell}</span>'
                        else:
                            # "내용 및 근거" 열: SR 값과 ASC 값을 구별해서 강조
                            # 1. SR 값 기준 터뷸런스 레벨 강조 (예: "Moderate Turbulence (SR 2-4)")
                            # 2. ASC 차트 값 강조 (예: "ASC Turbulence Chart 상 연한 파란색(MOD) 영역")
                            
                            # SR 값 기준 터뷸런스 레벨 패턴 (예: "Moderate Turbulence (SR 2-4)", "Severe Turbulence (SR 7)")
                            sr_turbulence_pattern = r'(Moderate|Severe|Light|Moderate to Severe)\s+Turbulence\s*\(SR\s+[\d\-]+\)'
                            if re.search(sr_turbulence_pattern, cell):
                                def highlight_sr_turbulence(match):
                                    level = match.group(1)
                                    # SR 값 추출하여 SR 기준에 따라 색상 결정
                                    sr_match = re.search(r'SR\s+(\d+)(?:\s*-\s*(\d+))?', match.group(0))
                                    sr_max = 0
                                    if sr_match:
                                        if sr_match.group(2):  # 범위인 경우
                                            sr_max = max(int(sr_match.group(1)), int(sr_match.group(2)))
                                        else:  # 단일 값
                                            sr_max = int(sr_match.group(1))
                                    
                                    # SR 기준: SR 1-3: Light, SR 4: Moderate, SR 5-9: Moderate to Severe, SR 10+: Severe
                                    if sr_max >= 10 or 'Severe' in level:
                                        color = '#dc3545'  # 빨간색
                                    elif sr_max >= 5 or 'Moderate to Severe' in level:
                                        color = '#ffc107'  # 노란색
                                    elif sr_max >= 4 or 'Moderate' in level:
                                        color = '#0dcaf0'  # 연한 파란색
                                    else:  # SR 1-3
                                        color = '#17a2b8'  # 파란색
                                    
                                    return f'<strong style="color: {color} !important; font-weight: 700 !important;">[SR 기준] {match.group(0)}</strong>'
                                cell_html = re.sub(sr_turbulence_pattern, highlight_sr_turbulence, cell)
                            
                            # ASC 차트 값 강조 (예: "ASC Turbulence Chart 상 연한 파란색(MOD) 영역", "빨간색(SEV) 영역")
                            # 중복 방지: "ASC Turbulence Chart 상" 포함 패턴을 먼저 처리하고, 이미 처리된 부분은 제외
                            # 1단계: "ASC Turbulence Chart 상" 포함 패턴 처리 (전체를 한 번에 강조)
                            asc_full_patterns = [
                                (r'ASC Turbulence Chart 상\s+빨간색\s*\(SEV\)', '#dc3545'),
                                (r'ASC Turbulence Chart 상\s+노란색\s*\(MODtoSEV\)', '#ffc107'),
                                (r'ASC Turbulence Chart 상\s+연한 파란색\s*\((MOD|LGT)\)', '#0dcaf0'),
                            ]
                            
                            for pattern, color in asc_full_patterns:
                                def highlight_full_asc(match):
                                    return f'<strong style="color: {color} !important; font-weight: 700 !important;">[ASC 차트] {match.group(0)}</strong>'
                                cell_html = re.sub(pattern, highlight_full_asc, cell_html)
                            
                            # 2단계: "ASC Turbulence Chart 상" 없이 색상만 있는 패턴 처리
                            # 이미 "[ASC 차트]" 태그가 없는 경우만 처리 (lookbehind 사용 안 함)
                            # "[ASC 차트]"가 이미 있으면 스킵 (이미 처리된 경우)
                            # 더 안전하게: "<strong" 태그로 감싸지 않은 색상 패턴만 찾기
                            if '[ASC 차트]' not in cell_html:
                                # 색상 패턴을 찾되, 이미 강조 태그 안에 있는 것은 제외
                                asc_color_patterns = [
                                    (r'빨간색\s*\(SEV\)', '#dc3545'),
                                    (r'노란색\s*\(MODtoSEV\)', '#ffc107'),
                                    (r'연한 파란색\s*\((MOD|LGT)\)', '#0dcaf0'),
                                ]
                                
                                for pattern, color in asc_color_patterns:
                                    # 모든 매칭을 찾아서, 이미 강조 태그 안에 있지 않은 것만 처리
                                    matches = list(re.finditer(pattern, cell_html))
                                    for match in reversed(matches):  # 뒤에서부터 처리하여 인덱스 변경 방지
                                        start, end = match.span()
                                        # 앞부분을 확인하여 이미 강조 태그 안에 있는지 체크
                                        before = cell_html[:start]
                                        # "<strong"가 있고 "</strong>"가 없으면 이미 강조 태그 안에 있음
                                        last_strong_start = before.rfind('<strong')
                                        last_strong_end = before.rfind('</strong>')
                                        if last_strong_start == -1 or (last_strong_end != -1 and last_strong_end > last_strong_start):
                                            # 강조 태그 밖에 있으면 처리
                                            replacement = f'<strong style="color: {color} !important; font-weight: 700 !important;">[ASC 차트] {match.group(0)}</strong>'
                                            cell_html = cell_html[:start] + replacement + cell_html[end:]
                        
                        # 모든 셀에 기본 인라인 스타일 적용
                        base_style = "padding: 6px 8px !important; vertical-align: top !important; border: 1px solid #dee2e6 !important; font-size: 13px !important; line-height: 1.0 !important; white-space: normal !important; word-wrap: break-word !important; word-break: break-word !important; overflow-wrap: break-word !important; overflow: visible !important; text-overflow: clip !important; box-sizing: border-box !important; max-width: 100% !important;"
                        
                        # 내용 및 근거 열은 더 넓게 (강제 줄바꿈)
                        # 반응형을 위해 고정 너비 제거
                        # base_style에 이미 line-height: 1.3이 있으므로 중복 제거
                        if is_content_cell:
                            cell_style = base_style + " hyphens: auto !important; -webkit-hyphens: auto !important; -moz-hyphens: auto !important; display: table-cell !important;"
                            table_html.append(f'<td class="content-cell" style="{cell_style}">{cell_html}</td>')
                        else:
                            # 다른 열들은 자동 너비 (table-layout: auto 사용)
                            table_html.append(f'<td style="{base_style} display: table-cell !important;">{cell_html}</td>')
                    table_html.append('</tr>')
        else:
            # 테이블 종료
            if in_table:
                # 테이블 컨테이너 공통 스타일 (중복 제거)
                table_container_style = 'overflow-x: auto !important; overflow-y: visible !important; width: 100% !important; max-width: 100% !important; display: block !important;'
                table_style = 'font-size: 14px !important; width: 100% !important; max-width: 100% !important; border-collapse: separate !important; border-spacing: 0 !important; table-layout: auto !important; border: 1px solid #dee2e6 !important; display: table !important; background-color: white !important;'
                result_lines.append(f'<div style="margin: 0px 0 !important; {table_container_style}"><table style="{table_style}">')
                result_lines.extend(table_html)
                result_lines.append('</table></div>')
                in_table = False
                table_html = []
                header_processed = False
            
            # 리스트 변환 (* 항목 → <li>항목</li>)
            if line.strip().startswith('*'):
                content = line.strip()[1:].strip()
                result_lines.append(f'<li class="mb-2">{content}</li>')
            elif line.strip().startswith('-'):
                content = line.strip()[1:].strip()
                result_lines.append(f'<li class="mb-2">{content}</li>')
            elif line.strip():
                result_lines.append(line)
            else:
                result_lines.append('<br>')
    
    # 마지막 테이블 처리
    if in_table:
        # 테이블 컨테이너 공통 스타일 (중복 제거)
        table_container_style = 'overflow-x: auto !important; overflow-y: visible !important; width: 100% !important; max-width: 100% !important; display: block !important;'
        table_style = 'font-size: 14px !important; width: 100% !important; max-width: 100% !important; border-collapse: separate !important; border-spacing: 0 !important; table-layout: auto !important; border: 1px solid #dee2e6 !important; display: table !important; background-color: white !important;'
        result_lines.append(f'<div style="margin: 0px 0 !important; {table_container_style}"><table style="{table_style}">')
        result_lines.extend(table_html)
        result_lines.append('</table></div>')
    
    html = '\n'.join(result_lines)
    
    # 리스트 래핑 (<li>가 연속으로 나오면 <ul>로 감싸기) - 인라인 스타일 추가
    html = re.sub(r'(<li[^>]*>.*?</li>(?:\s*<li[^>]*>.*?</li>)*)', r'<ul class="list-unstyled ms-3" style="padding-left: 25px !important; margin: 15px 0 !important;">\1</ul>', html, flags=re.DOTALL)
    
    # 리스트 항목 스타일 개선
    html = re.sub(r'<li class="mb-2">', r'<li class="mb-2" style="margin-bottom: 10px !important; font-size: 14px !important; line-height: 1.7 !important;">', html)
    
    # 강조 표시 (**텍스트** → <strong>텍스트</strong>) - 색상은 CSS에서 처리
    html = re.sub(r'\*\*(.+?)\*\*', r'<strong style="font-weight: 600 !important;">\1</strong>', html)
    
    # 시간 형식 강조 (예: 21:30Z, 08:26Z) - 인라인 스타일 추가
    html = re.sub(r'(\d{2}:\d{2}Z)', r'<span class="badge bg-secondary" style="font-family: \'Courier New\', monospace !important; font-weight: 600 !important; font-size: 0.9em !important; padding: 5px 10px !important; border-radius: 4px !important;">\1</span>', html)
    
    return html

@app.route('/ats_validator', methods=['GET', 'POST'])
def ats_validator():
    """ATS FPL Route Validator + 터뷸런스 분석 통합 버전"""
    from src.ats_route_extractor import (
        extract_ofp_route_from_page,
        extract_ats_fpl_route_from_page,
        compare_routes,
        is_valid_ofp_route,
        extract_route_from_docpack,
    )
    import pdfplumber
    import re
    import shutil
    
    if request.method == 'GET':
        return render_template('ats_validator.html')
    
    # POST 요청: 파일 업로드 처리
    if 'file' not in request.files:
        flash('파일이 선택되지 않았습니다.', 'error')
        return redirect(url_for('ats_validator'))
    
    file = request.files['file']
    if file.filename == '':
        flash('파일이 선택되지 않았습니다.', 'error')
        return redirect(url_for('ats_validator'))
    
    if not file.filename.lower().endswith('.pdf'):
        flash('PDF 파일만 업로드 가능합니다.', 'error')
        return redirect(url_for('ats_validator'))
    
    # 터뷸런스 분석 결과 변수
    turbulence_analysis = None
    flight_data = None
    etd_str = None
    takeoff_time_str = None
    eta_str = None
    
    try:
        # 업로드 파일 저장 (최신 3개 유지)
        ensure_files_cleaned()
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        request_id = str(uuid.uuid4())[:8]
        filename = f"{timestamp}_{request_id}_{filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        cleanup_files(app.config['UPLOAD_FOLDER'], max_files=3)
        
        try:
            # 1. 터뷸런스 분석 실행 (flightplanextractor.py)
            try:
                from flightplanextractor import extract_flight_data_from_pdf, analyze_turbulence_with_gemini
                
                logger.info("터뷸런스 분석 시작...")
                flight_data = extract_flight_data_from_pdf(filepath, save_temp=False)
                
                if flight_data:
                    # ETD, TAXI TIME, ETA 추출
                    import pdfplumber as pdfplumber_temp
                    departure_airport = None
                    arrival_airport = None
                    
                    with pdfplumber_temp.open(filepath) as pdf_temp:
                        full_text_temp = ""
                        for page in pdf_temp.pages:
                            page_text = page.extract_text()
                            if page_text:
                                full_text_temp += page_text + "\n"
                    
                    # ETD 추출 (공항 코드 포함)
                    etd_pattern = r'ETD\s+([A-Z]{4})\s+(\d{4})Z'
                    etd_match = re.search(etd_pattern, full_text_temp)
                    if etd_match:
                        departure_airport = etd_match.group(1)
                        etd_str = etd_match.group(2) + 'Z'
                    
                    # 이륙 시간 계산 (ETD + 20분)
                    if etd_str:
                        try:
                            etd_hour = int(etd_str[:2])
                            etd_minute = int(etd_str[2:4])
                            # 날짜는 오늘 날짜 사용 (시간 계산에만 사용되므로 날짜는 중요하지 않음)
                            today = datetime.now()
                            etd_time = datetime(today.year, today.month, today.day, etd_hour, etd_minute)
                            takeoff_time = etd_time + timedelta(minutes=20)
                            takeoff_time_str = takeoff_time.strftime('%H%M') + 'Z'
                        except Exception as e:
                            logger.warning(f"이륙 시간 계산 오류: {e}")
                    
                    # ETA 추출 (공항 코드 포함)
                    eta_pattern = r'ETA\s+([A-Z]{4})\s+(\d{4})Z'
                    eta_match = re.search(eta_pattern, full_text_temp)
                    if eta_match:
                        arrival_airport = eta_match.group(1)
                        eta_str = eta_match.group(2) + 'Z'
                    
                    # TURB/CB INFO 추출
                    turb_cb_info = []
                    if 'TURB/CB INFO' in full_text_temp.upper():
                        lines_text = full_text_temp.split('\n')
                        for i, line in enumerate(lines_text):
                            if 'TURB/CB INFO' in line.upper():
                                turb_cb_info.append(line.strip())
                                for j in range(i + 1, min(i + 10, len(lines_text))):
                                    next_line = lines_text[j].strip()
                                    if not next_line:
                                        if j + 1 < len(lines_text) and not lines_text[j + 1].strip():
                                            break
                                        continue
                                    if next_line.startswith(('6.', '7.', '8.', '9.', '---', '===')):
                                        break
                                    if any(keyword in next_line.upper() for keyword in ['CAUTION', 'CB', 'TURB', 'SIG WX', 'TURBULENCE', 'CHART']):
                                        turb_cb_info.append(next_line)
                                    elif len(turb_cb_info) <= 4:
                                        turb_cb_info.append(next_line)
                                break
                    
                    # TAF 데이터 추출
                    taf_data = {'departure': None, 'arrival': None, 'alternate': None}
                    if 'WEATHER BRIEFING' in full_text_temp.upper():
                        weather_briefing_match = re.search(r'WEATHER BRIEFING.*?(-{5,}\s*DEPARTURE WEATHER\s*-{5,}.*?)(?:-{5,}\s*ARRIVAL WEATHER\s*-{5,}.*?)(?:-{5,}\s*ALTERNATE WEATHER\s*-{5,}.*?)(?:-{5,}\s*END OF WEATHER BRIEFING|-{5,}\s*ROUTE TO ALTN|\Z)', full_text_temp, re.DOTALL)
                        if weather_briefing_match:
                            weather_briefing_section = weather_briefing_match.group(0)
                            dep_match = re.search(r'DEPARTURE WEATHER\s*-{5,}\s*(.*?)(?:-{5,}\s*ARRIVAL WEATHER|\Z)', weather_briefing_section, re.DOTALL)
                            if dep_match:
                                taf_data['departure'] = dep_match.group(1).strip()
                            arr_match = re.search(r'ARRIVAL WEATHER\s*-{5,}\s*(.*?)(?:-{5,}\s*ALTERNATE WEATHER|\Z)', weather_briefing_section, re.DOTALL)
                            if arr_match:
                                taf_data['arrival'] = arr_match.group(1).strip()
                            alt_match = re.search(r'ALTERNATE WEATHER\s*-{5,}\s*(.*?)(?:-{5,}\s*END OF WEATHER BRIEFING|-{5,}\s*ROUTE TO ALTN|\Z)', weather_briefing_section, re.DOTALL)
                            if alt_match:
                                taf_data['alternate'] = alt_match.group(1).strip()
                    
                    # Gemini API를 사용한 터뷸런스 분석
                    logger.info("Gemini API를 사용한 터뷸런스 분석 시작...")
                    turbulence_analysis = analyze_turbulence_with_gemini(
                        filepath, flight_data, etd_str, takeoff_time_str, eta_str, turb_cb_info, taf_data,
                        departure_airport, arrival_airport
                    )
                    logger.info("터뷸런스 분석 완료")
            except Exception as e:
                logger.warning(f"터뷸런스 분석 중 오류 발생 (계속 진행): {e}", exc_info=True)
                turbulence_analysis = None
            
            # 2. ATS FPL Route Validator 실행
            # PDF 파일 읽기 및 처리
            with pdfplumber.open(filepath) as pdf:
                total_pages = len(pdf.pages)
                
                # 전체 PDF 텍스트 추출
                all_text = ""
                page_texts = []
                for page in pdf.pages:
                    page_text = page.extract_text()
                    page_texts.append(page_text if page_text else "")
                    if page_text:
                        all_text += page_text + "\n"
                
                # OFP route 추출: Aviator OFP는 본경로가 항상 2페이지에 있음. ROUTE TO ALTN은 대체경로로 OFP가 아님.
                ofp_route = None
                ofp_page_num = None
                # 1) 2페이지 우선 (Aviator flight plan에서 OFP 본경로는 거의 항상 2페이지)
                if total_pages >= 2 and page_texts[1]:
                    ofp_route = extract_ofp_route_from_page(page_texts[1])
                    if ofp_route and is_valid_ofp_route(ofp_route):
                        ofp_page_num = 2
                # 2) 없으면 "DIST LATITUDE" / "DIST. LATITUDE" 있는 다른 페이지에서만 추출
                if not ofp_route:
                    flight_plan_page_indices = [i for i, pt in enumerate(page_texts) if pt and re.search(r'\bDIST\s*\.?\s*LATITUDE\b', pt or '', re.IGNORECASE) and i != 1]
                    for page_idx in flight_plan_page_indices[:3]:
                        page_text = page_texts[page_idx]
                        if page_text:
                            ofp_route = extract_ofp_route_from_page(page_text)
                            if ofp_route and is_valid_ofp_route(ofp_route):
                                ofp_page_num = page_idx + 1
                                break
                        ofp_route = None
                if not ofp_route:
                    ofp_route = extract_route_from_docpack(all_text)
                    if ofp_route:
                        ofp_page_num = "DocPack 전체"
                if not ofp_route:
                    max_pages_to_check = min(5, total_pages)
                    for page_idx in range(max_pages_to_check):
                        if page_idx == 1:
                            continue
                        page_text = page_texts[page_idx]
                        if page_text:
                            ofp_route = extract_ofp_route_from_page(page_text)
                            if ofp_route and is_valid_ofp_route(ofp_route):
                                ofp_page_num = page_idx + 1
                                break
                # 마지막 폴백: app의 extract_route_from_page2 (여러 페이지·DIST 유연 패턴 시도)
                if not ofp_route:
                    ofp_route = extract_route_from_page2(filepath)
                    if ofp_route and is_valid_ofp_route(ofp_route):
                        ofp_page_num = "PDF 다중페이지 추출"
                
                # OFP 추출 실패 시 사유 (사용자 안내용)
                ofp_route_fail_reason = None
                if not ofp_route and total_pages > 0:
                    has_dist = any(re.search(r'\bDIST\s*\.?\s*LATITUDE\b', pt or '', re.IGNORECASE) for pt in page_texts)
                    has_text = any((pt or '').strip() for pt in page_texts)
                    if not has_text:
                        ofp_route_fail_reason = "PDF에서 텍스트를 추출할 수 없습니다(이미지/스캔본일 수 있음)."
                    elif not has_dist and total_pages == 1:
                        ofp_route_fail_reason = "단일 페이지 PDF이며, 비행계획 테이블(DIST LATITUDE) 형식을 찾지 못했습니다."
                    elif not has_dist:
                        ofp_route_fail_reason = "어떤 페이지에서도 비행계획 테이블(DIST LATITUDE) 또는 공항코드+항로 패턴을 찾지 못했습니다."
                    else:
                        ofp_route_fail_reason = "항로 블록 형식이 일반 OFP와 다르거나, ROUTE TO ALTN 이전에 본경로가 없습니다."
                
                # ATS FPL route 추출
                ats_route = None
                ats_page_num = None
                for i, page_text in enumerate(page_texts):
                    if page_text and ('COPY OF ATS FPL' in page_text.upper() or 'ATS FPL' in page_text.upper()):
                        ats_route = extract_ats_fpl_route_from_page(page_text)
                        if ats_route:
                            ats_page_num = i + 1
                            break
                
                # 비교 결과
                comparison = None
                if ofp_route and ats_route:
                    comparison = compare_routes(ofp_route, ats_route)
                
                # 터뷸런스 분석 결과를 HTML로 변환 (마크다운 → HTML)
                turbulence_analysis_html = None
                if turbulence_analysis:
                    logger.info(f"터뷸런스 분석 원본 (처음 500자): {turbulence_analysis[:500] if len(turbulence_analysis) > 500 else turbulence_analysis}")
                    turbulence_analysis_html = convert_markdown_to_html(turbulence_analysis)
                    logger.info(f"터뷸런스 분석 HTML 변환 완료 (처음 500자): {turbulence_analysis_html[:500] if len(turbulence_analysis_html) > 500 else turbulence_analysis_html}")
                    logger.info(f"인라인 스타일 개수: {turbulence_analysis_html.count('style=') if turbulence_analysis_html else 0}")
                    # HTML 태그가 포함되어 있는지 확인
                    if turbulence_analysis_html and ('<h3>' in turbulence_analysis_html or '<table>' in turbulence_analysis_html):
                        logger.info("✅ HTML 변환 성공: HTML 태그가 포함되어 있습니다.")
                    else:
                        logger.warning("⚠️ HTML 변환 실패: HTML 태그가 없습니다. 원본 텍스트가 반환되었을 수 있습니다.")
                        # HTML 태그가 없으면 원본을 그대로 사용 (마크다운으로 표시)
                        turbulence_analysis_html = turbulence_analysis_html or turbulence_analysis
                
                return render_template('ats_validator.html',
                                 total_pages=total_pages,
                                 ofp_route=ofp_route,
                                 ofp_page_num=ofp_page_num,
                                 ofp_route_fail_reason=ofp_route_fail_reason,
                                 ats_route=ats_route,
                                 ats_page_num=ats_page_num,
                                 comparison=comparison,
                                 page_texts=page_texts[:5] if not ofp_route or not ats_route else None,
                                 turbulence_analysis=turbulence_analysis_html,
                                 flight_data=flight_data,
                                 etd_str=etd_str,
                                 takeoff_time_str=takeoff_time_str,
                                 eta_str=eta_str)
        finally:
            pass
        
    except Exception as e:
        logger.error(f"ATS Validator 오류: {e}", exc_info=True)
        flash(f'오류가 발생했습니다: {str(e)}', 'error')
        return redirect(url_for('ats_validator'))


@app.route('/validate_ats_fpl', methods=['GET', 'POST'])
def validate_ats_fpl():
    """ATS FPL Validator (레거시 호환 - Flask 통합 버전으로 리다이렉트)"""
    # 새 Flask 통합 버전으로 리다이렉트
    if request.method == 'POST':
        from flask import jsonify
        return jsonify({
            'status': 'success',
            'url': url_for('ats_validator', _external=True),
            'is_local': True
        }), 200
    
    return redirect(url_for('ats_validator'))

# ================== 지도용 NOTAM 캐시 주입(분석 결과 재사용) ==================
# _index_notams_by_airport 함수는 위에서 이미 정의됨 (중복 제거)

@app.route('/api/airport-notams/override', methods=['POST'])
def override_airport_notams():
    """
    분석 결과에서 생성한 구조화 NOTAM을 지도 API에서 재사용할 수 있도록
    서버 캐시에 주입하는 엔드포인트.
    Body(JSON):
      {
        "notams": [ {...}, ... ],
        "source": "20251116_xxx.pdf"   // 선택
      }
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
        notams = data.get('notams') or []
        if not isinstance(notams, list) or not notams:
            return jsonify({'error': 'notams 배열이 비었습니다.'}), 400
        source = data.get('source') or 'override'
        # 전역 캐시 갱신
        global LAST_NOTAMS, LAST_NOTAMS_SOURCE, LAST_NOTAMS_INDEXED_BY_AIRPORT
        LAST_NOTAMS = notams
        LAST_NOTAMS_SOURCE = source
        LAST_NOTAMS_INDEXED_BY_AIRPORT = _index_notams_by_airport(LAST_NOTAMS)
        return jsonify({
            'ok': True,
            'cached': len(LAST_NOTAMS),
            'airports_indexed': len(LAST_NOTAMS_INDEXED_BY_AIRPORT),
            'source': LAST_NOTAMS_SOURCE
        })
    except Exception as e:
        return jsonify({'error': f'캐시 주입 실패: {str(e)}'}), 500

@app.route('/upload', methods=['GET'])
def upload_redirect():
    """GET /upload 시 메인 페이지로 이동 (브라우저가 /upload로 리다이렉트된 경우·새로고침 시 로딩 루프 방지)"""
    return redirect(url_for('index'))


@app.route('/upload', methods=['POST'])
def upload_file():
    global _processing_locks
    
    # 세션 ID 가져오기 (없으면 생성)
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
    session_id = session['session_id']
    
    # 세션별 락 정보 가져오기
    lock_info = _processing_locks.get(session_id, {'locked': False, 'lock_time': None})
    
    # 타임아웃 체크: 락이 설정된 지 일정 시간이 지났으면 자동 해제
    if lock_info['locked'] and lock_info['lock_time']:
        elapsed = (datetime.now() - lock_info['lock_time']).total_seconds()
        if elapsed > PROCESSING_LOCK_TIMEOUT:
            logger.warning(f"세션 {session_id[:8]}의 처리 락이 타임아웃되었습니다 ({elapsed:.1f}초 경과). 자동 해제합니다.")
            lock_info['locked'] = False
            lock_info['lock_time'] = None
            _processing_locks[session_id] = lock_info
    
    # 중복 요청 방지 (해당 세션에 대해서만)
    if lock_info['locked']:
        elapsed = (datetime.now() - lock_info['lock_time']).total_seconds() if lock_info['lock_time'] else 0
        logger.warning(f"세션 {session_id[:8]}에서 이미 처리 중인 요청이 있습니다. 새 요청을 거부합니다. (경과 시간: {elapsed:.1f}초)")
        flash('이미 처리 중인 요청이 있습니다. 잠시 후 다시 시도해주세요.')
        return redirect(url_for('index'))
    
    # 처리 시작 (해당 세션에 락 설정)
    lock_info['locked'] = True
    lock_info['lock_time'] = datetime.now()
    _processing_locks[session_id] = lock_info
    
    try:
        # 파일 정리 (첫 요청 시에만)
        ensure_files_cleaned()
        
        # 전체 처리 시간 측정 시작
        total_start_time = datetime.now()
        processing_times = {}
        if 'file' not in request.files:
            flash('파일이 선택되지 않았습니다.')
            return redirect(url_for('index'))
        
        file = request.files['file']
        if file.filename == '':
            flash('파일이 선택되지 않았습니다.')
            return redirect(url_for('index'))
        
        if file and file.filename and allowed_file(file.filename):
            # 파일 저장 시간 측정
            file_save_start = datetime.now()
            filename = secure_filename(file.filename)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            # 고유 요청 ID 생성 (파일 충돌 방지)
            request_id = str(uuid.uuid4())[:8]  # 짧은 고유 ID
            filename = f"{timestamp}_{request_id}_{filename}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            # 업로드 직후 파일 크기 확인 (빈 파일 또는 업로드 실패 방지)
            if os.path.getsize(filepath) < 100:
                logger.error(f"업로드된 파일 크기가 비정상적으로 작음: {filepath}, size={os.path.getsize(filepath)}")
                flash('업로드된 파일이 비어 있거나 손상된 것 같습니다. 다시 업로드해 주세요.')
                return redirect(url_for('index'))
            
            # 업로드 파일 정리 (최신 3개만 유지 - 용량 절감 + 이전 파일 확인 가능)
            cleanup_files(app.config['UPLOAD_FOLDER'], max_files=3)
            
            processing_times['file_save'] = (datetime.now() - file_save_start).total_seconds()
            
            # PDF 텍스트 변환 시간 측정
            pdf_conversion_start = datetime.now()
            
            # 일반 NOTAM PDF 처리
            text = pdf_converter.convert_pdf_to_text(filepath)
            
            # 두 번째 페이지에서 route 추출 시도
            extracted_route = extract_route_from_page2(filepath)
            if extracted_route:
                logger.info(f"두 번째 페이지에서 route 추출: {extracted_route[:100]}...")
            else:
                logger.debug("두 번째 페이지에서 route를 찾을 수 없음 (skip)")
            
            # Flight plan waypoint 좌표는 아래에서 text 기준으로 추출 (PDF 재오픈 없이 처리 시간 절감)
            
            # split 파일명 생성
            base_name = os.path.splitext(os.path.basename(filepath))[0]
            split_filename = f"{base_name}_split.txt"
            
            processing_times['pdf_conversion'] = (datetime.now() - pdf_conversion_start).total_seconds()
            
            logger.debug(f"PDF 변환 완료: {len(text)} 문자, {processing_times['pdf_conversion']:.2f}초")
            
            if not text.strip():
                logger.error("PDF에서 추출된 텍스트가 비어있습니다.")
                flash('PDF에서 텍스트를 추출할 수 없습니다.')
                return redirect(url_for('index'))
            
            # Flight plan waypoint 좌표 추출 (이미 있는 text만 사용, PDF 재오픈 없음 → 처리 시간 절감)
            flight_plan_waypoints = []
            try:
                from flightplanextractor import extract_flight_plan_waypoints_from_text
                waypoint_rows = extract_flight_plan_waypoints_from_text(text)
                for row in waypoint_rows:
                    entry = {
                        "ident": (row.get("Waypoint") or "").strip().upper(),
                        "lat":   float(row["lat"]),
                        "lon":   float(row["lon"]),
                    }
                    if row.get("fl") is not None:
                        entry["fl"] = int(row["fl"])
                    if row.get("actm") is not None:
                        entry["actm"] = str(row["actm"])
                    flight_plan_waypoints.append(entry)
                if flight_plan_waypoints:
                    logger.info(f"Flight plan waypoint 좌표 추출: {len(flight_plan_waypoints)}개")
            except Exception as e:
                logger.warning(f"Flight plan 좌표 추출 실패: {e}")
            
            # Flight plan 요약 분석 (Callsign, PAX, MEL/CDL, 연료, 중량, ETD/ETA 등)
            flight_plan_summary_items = []
            flight_plan_summary_items_before = []
            flight_plan_summary_items_after = []
            flight_plan_fuel_time_table = []
            flight_plan_weight_table = []
            flight_plan_report_ko = ""
            try:
                from src.flight_plan_analyzer import (
                    extract_flight_plan_summary,
                    get_flight_plan_summary_display_items,
                    get_fuel_time_table,
                    get_weight_table,
                )
                summary = extract_flight_plan_summary(text)
                flight_plan_summary_items = get_flight_plan_summary_display_items(summary)
                # 연료/무게 테이블 이전에 올 항목 (Callsign ~ 평균 WIND/TEMP)
                _fp_before_keys = {
                    "flight_plan_number", "callsign_line", "pax_line", "mel_cdl",
                    "trip_fuel_increase_2000lbs", "dispatch_note", "turb_cb",
                    "route_fuel_consumption", "cost_index_value", "apms", "avg_wind_temp",
                }
                flight_plan_summary_items_before = [i for i in flight_plan_summary_items if i.get("key") in _fp_before_keys]
                flight_plan_summary_items_after = [i for i in flight_plan_summary_items if i.get("key") not in _fp_before_keys]
                flight_plan_fuel_time_table = get_fuel_time_table(summary)
                flight_plan_weight_table = get_weight_table(summary)
                if any(item.get("value") and item["value"] != "—" for item in flight_plan_summary_items):
                    logger.info(f"Flight plan 요약 추출: {len([i for i in flight_plan_summary_items if i.get('value') and i['value'] != '—'])}개 항목")
            except Exception as e:
                logger.warning(f"Flight plan 요약 추출 실패: {e}")
            
            # split 파일명은 convert_pdf_to_text에서 자동 생성됨
            
            # NOTAM 필터링 (한 번만 실행)
            filtering_start = datetime.now()
            notams = notam_filter.filter_korean_air_notams(text)
            takeoff_infos = notam_filter.extract_takeoff_performance_info(text)
            processing_times['notam_filtering'] = (datetime.now() - filtering_start).total_seconds()
            logger.debug(f"NOTAM 필터링: {len(notams)}개, {processing_times['notam_filtering']:.2f}초")
            if not notams and text.strip():
                logger.warning(
                    "NOTAM이 0건 추출됨(텍스트는 있음). PDF 형식 또는 인코딩 확인 필요. "
                    "텍스트 앞 500자: %s", text[:500].replace('\n', ' ')
                )
            
            # 최근 NOTAM 캐시 저장 (split 파일명으로 저장하여 정확한 매칭)
            try:
                global LAST_NOTAMS, LAST_NOTAMS_SOURCE, LAST_NOTAMS_INDEXED_BY_AIRPORT, LAST_PACKAGE3_TEXT
                LAST_NOTAMS = notams or []
                # split 파일명이 있으면 사용 (docpack과 일반 PDF 모두)
                if 'split_filename' in locals() and split_filename:
                    LAST_NOTAMS_SOURCE = split_filename
                else:
                    # 폴백: 원본 파일명 사용
                    LAST_NOTAMS_SOURCE = os.path.basename(filepath)
                LAST_NOTAMS_INDEXED_BY_AIRPORT = _index_notams_by_airport(LAST_NOTAMS)
                
                # Package 3 텍스트 추출 및 캐시 저장 (Cloud Run 호환성)
                try:
                    from src.package3_parser import _extract_package3_text
                    LAST_PACKAGE3_TEXT = _extract_package3_text(text)
                    if LAST_PACKAGE3_TEXT:
                        logger.info(f"Package 3 텍스트 캐시 저장: {len(LAST_PACKAGE3_TEXT)} 문자")
                    else:
                        logger.debug("Package 3 텍스트 없음 (캐시 저장 안 함)")
                except Exception as e:
                    logger.warning(f"Package 3 텍스트 추출 실패: {e}")
                    LAST_PACKAGE3_TEXT = None
                
                logger.info(f"최근 NOTAM 캐시 저장: {len(LAST_NOTAMS)}개, source={LAST_NOTAMS_SOURCE}, 공항수={len(LAST_NOTAMS_INDEXED_BY_AIRPORT)}")
            except Exception as e:
                logger.warning(f"최근 NOTAM 캐시 저장 실패: {e}")
            
            # 공항 코드 추출
            all_airports = set()
            for notam in notams:
                airport_code = notam.get('airport_code', '')
                if airport_code:
                    all_airports.add(airport_code)
            
            # Package 정보 추출하여 동적 순서로 업데이트
            package_extraction_text = text
            logger.debug(f"패키지 정보 추출용 텍스트 길이: {len(package_extraction_text)} 문자")
            if False:  # docpack 검증 로직 제거됨
                # 디버깅: 원본 텍스트에서 DEP/DEST/ALTN 패턴 확인
                import re
                dep_match = re.search(r'DEP:\s*([A-Z]{4})', package_extraction_text)
                dest_match = re.search(r'DEST:\s*([A-Z]{4})', package_extraction_text)
                altn_match = re.search(r'ALTN:\s*([A-Z\s]+?)(?=\n|SECY|$)', package_extraction_text)
                logger.info(f"원본 텍스트에서 패턴 확인 - DEP: {dep_match.group(1) if dep_match else '없음'}, DEST: {dest_match.group(1) if dest_match else '없음'}, ALTN: {altn_match.group(1) if altn_match else '없음'}")
            filtered_package_airports = notam_filter.extract_package_airports(package_extraction_text, all_airports)
            
            # Package 1 출발/도착 공항 추출 (항로 정보 자동 생성용)
            package1_route_info = None
            if 'package1' in filtered_package_airports:
                package1_airports = filtered_package_airports['package1']
                if len(package1_airports) >= 2:
                    dep_icao = package1_airports[0]
                    dest_icao = package1_airports[1]
                    
                    # airports.csv에서 ICAO → IATA 변환
                    def load_icao_to_iata_mapping():
                        """airports.csv 파일에서 ICAO → IATA 매핑 로드"""
                        icao_to_iata = {}
                        try:
                            csv_path = os.path.join(os.path.dirname(__file__), 'src', 'airports.csv')
                            if os.path.exists(csv_path):
                                import csv
                                with open(csv_path, 'r', encoding='utf-8-sig') as f:
                                    reader = csv.DictReader(f)
                                    for row in reader:
                                        ident = (row.get('ident') or '').strip().upper()
                                        iata_code = (row.get('iata_code') or '').strip().upper()
                                        if ident and iata_code and iata_code != 'NULL':
                                            icao_to_iata[ident] = iata_code
                                logger.debug(f"ICAO → IATA 매핑 로드 완료: {len(icao_to_iata)}개 공항")
                        except Exception as e:
                            logger.warning(f"airports.csv 로드 실패: {e}")
                        return icao_to_iata
                    
                    icao_to_iata = load_icao_to_iata_mapping()
                    
                    # IATA 코드 변환 (매핑이 없으면 폴백: ICAO의 마지막 3자리)
                    dep_iata = icao_to_iata.get(dep_icao, dep_icao[1:4] if len(dep_icao) == 4 else dep_icao)
                    dest_iata = icao_to_iata.get(dest_icao, dest_icao[1:4] if len(dest_icao) == 4 else dest_icao)
                    
                    package1_route_info = {
                        'dep': dep_icao,
                        'dest': dest_icao,
                        'depIata': dep_iata,
                        'destIata': dest_iata,
                        'routePair': f'{dep_iata}/{dest_iata}',
                        'reversePair': f'{dest_iata}/{dep_iata}'
                    }
                    logger.info(f"Package 1 항로 정보 자동 추출: {package1_route_info}")
            logger.info(f"추출된 패키지 공항: {filtered_package_airports}")
            
            # 시간대 워밍업: 패키지 및 탐지된 공항 전체에 대해 1회만 타임존 해석
            warmup_airports = set(all_airports)
            for airports in filtered_package_airports.values():
                warmup_airports.update(airports)
            # 표본 시각: 현재 시각과 파일명 타임스탬프 근사치 (선택)
            sample_times = [datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')]
            try:
                warmup_result = notam_filter.warmup_airport_timezones(warmup_airports, sample_times_utc=sample_times)
                logger.debug(f"타임존 워밍업: {len([k for k,v in warmup_result.items() if v])}/{len(warmup_result)} 성공")
            except Exception as e:
                logger.warning(f"타임존 워밍업 중 오류: {e}")
            
            # 정렬 적용 (패키지 타입인 경우)
            if 'KOREAN AIR NOTAM PACKAGE' in text.upper():
                # 패키지 타입 감지
                if 'KOREAN AIR NOTAM PACKAGE 1' in text.upper():
                    package_type = 'package1'
                elif 'KOREAN AIR NOTAM PACKAGE 2' in text.upper():
                    package_type = 'package2'
                elif 'KOREAN AIR NOTAM PACKAGE 3' in text.upper():
                    package_type = 'package3'
                else:
                    package_type = None
                
                if package_type and package_type in notam_filter.package_airport_order:
                    # 공항 순서에 따라 정렬
                    order_list = notam_filter.package_airport_order[package_type]
                    notams.sort(key=lambda x: order_list.index(x.get('airport_code', '')) if x.get('airport_code') in order_list else 999)
                    logger.debug(f"패키지별 공항 순서로 정렬 완료: {package_type}")
            
            # 공항 필터링 처리 시간 측정 (선택사항)
            airport_filter_start = datetime.now()
            airport_filter_data = request.form.get('airport_filter')
            if airport_filter_data:
                try:
                    airport_filter = json.loads(airport_filter_data)
                    selected_airports = airport_filter.get('selected_airports', [])
                    
                    if selected_airports:
                        logger.debug(f"공항 필터 적용: {selected_airports}")
                        # 선택된 공항과 관련된 NOTAM만 필터링 (원본 순서 유지)
                        filtered_notams = []
                        # 비교 용이성을 위해 대문자/공백 제거
                        selected_upper = {str(code).strip().upper() for code in selected_airports if str(code).strip()}
                        for i, notam in enumerate(notams):
                            notam_airport = (notam.get('airport_code', '') or '').strip().upper()
                            notam_airports_list = []
                            try:
                                if isinstance(notam.get('airports'), list):
                                    notam_airports_list = [str(a).strip().upper() for a in notam.get('airports') if str(a).strip()]
                            except Exception:
                                pass
                            # 선택된 공항과 일치하면 포함
                            if notam_airport in selected_upper or any(a in selected_upper for a in notam_airports_list):
                                filtered_notams.append(notam)
                        
                        notams = filtered_notams
                        # Takeoff Performance 정보도 동일하게 필터링
                        filtered_takeoff_infos = []
                        for info in takeoff_infos:
                            info_airport = (info.get('airport_code') or '').strip().upper()
                            # selected_upper를 사용하여 대소문자 구분 없이 필터링
                            if info_airport and info_airport in selected_upper:
                                filtered_takeoff_infos.append(info)
                        takeoff_infos = filtered_takeoff_infos
                        logger.debug(f"공항 필터링 후: NOTAM {len(notams)}개, Takeoff Performance 정보 {len(takeoff_infos)}개")
                        
                except Exception as e:
                    logger.error(f"공항 필터 파싱 오류: {str(e)}")
            processing_times['airport_filtering'] = (datetime.now() - airport_filter_start).total_seconds()
            
            # NOTAM 시간을 로컬 시간으로 변환 시간 측정 (성능 최적화: 병렬 처리)
            time_conversion_start = datetime.now()
            
            def convert_time_for_notam(args):
                """단일 NOTAM의 시간 변환 함수 (병렬 처리용)"""
                notam, notam_filter_instance = args
                airport_code = notam.get('airport_code', 'RKSI')  # 기본값: 인천공항
                effective_time = notam.get('effective_time', '')
                expiry_time = notam.get('expiry_time', '')
                
                # 로컬 시간으로 변환된 시간 문자열 생성
                if effective_time:
                    local_time_str = notam_filter_instance.format_notam_time_with_local(
                        effective_time, expiry_time, airport_code, notam
                    )
                    notam['local_time_display'] = local_time_str
                return notam
            
            # 10개 이상일 때만 병렬 처리 (작은 경우 오버헤드 방지)
            if len(notams) > 10:
                max_workers = min(8, len(notams))  # 최대 8개 워커
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    notams = list(executor.map(
                        convert_time_for_notam,
                        [(notam, notam_filter) for notam in notams]
                    ))
            else:
                # 소량은 순차 처리 (병렬화 오버헤드 회피)
                for notam in notams:
                    airport_code = notam.get('airport_code', 'RKSI')
                    effective_time = notam.get('effective_time', '')
                    expiry_time = notam.get('expiry_time', '')
                    if effective_time:
                        local_time_str = notam_filter.format_notam_time_with_local(
                            effective_time, expiry_time, airport_code, notam
                        )
                        notam['local_time_display'] = local_time_str
            
            processing_times['time_conversion'] = (datetime.now() - time_conversion_start).total_seconds()
            
            if not notams:
                flash(
                    '필터링된 NOTAM이 없습니다. '
                    'PDF가 "KOREAN AIR NOTAM PACKAGE" 형식인지 확인하거나, 다른 오류 메시지가 있었다면 터미널 로그를 확인해 주세요.'
                )
                return redirect(url_for('index'))
            
            # NOTAM 번역 및 요약 시간 측정 (병렬 번역기 사용)
            translation_start = datetime.now()
            logger.info(f"번역 시작: {len(notams)}개 NOTAM (워커 수: {get_integrated_translator().max_workers})")
            
            # 통합 번역기 사용 (개별 처리로 변경) - Lazy initialization
            translated_notams = get_integrated_translator().process_notams_individual(notams)
            processing_times['translation'] = (datetime.now() - translation_start).total_seconds()
            
            logger.debug(f"번역 완료: {len(translated_notams)}개, {processing_times['translation']:.2f}초")

            # 결과를 원래 notams 리스트에 반영
            notams = translated_notams
            
            # 전체 처리 시간 계산
            total_processing_time = (datetime.now() - total_start_time).total_seconds()
            processing_times['total'] = total_processing_time
            
            # 전체 처리 시간 로깅 (성능 모니터링)
            logger.info(
                f"처리 완료: 총 {processing_times['total']:.2f}초 | "
                f"PDF: {processing_times['pdf_conversion']:.2f}s | "
                f"필터: {processing_times['notam_filtering']:.2f}s | "
                f"공항필터: {processing_times.get('airport_filtering', 0):.2f}s | "
                f"시간변환: {processing_times.get('time_conversion', 0):.2f}s | "
                f"번역: {processing_times['translation']:.2f}s ({len(notams)}개, 평균 {processing_times['translation']/len(notams):.2f}s/개)"
            )
            
            # ── PDF에서 기상 차트(sigwx/asc/cross) JPG 추출 ─────────────────
            chart_images = {}   # {"sigwx1": "/uploads/XXX_sigwx1.jpg", ...}
            try:
                from find_and_analyze_cross_section import (
                    find_weather_chart_pages_before_notam,
                    export_cross_chart_page_to_jpg,
                )
                _base = os.path.splitext(os.path.basename(filepath))[0]
                _pages = find_weather_chart_pages_before_notam(filepath)
                for _label in ("sigwx1", "asc", "cross"):
                    if _label not in _pages:
                        continue
                    _out = os.path.join(app.config['UPLOAD_FOLDER'],
                                        f"{_base}_{_label}.jpg")
                    _path = export_cross_chart_page_to_jpg(
                        filepath, _pages[_label], output_path=_out)
                    if _path and os.path.exists(_path):
                        # 웹 URL 경로로 변환 (/uploads/파일명)
                        chart_images[_label] = "/" + _path.replace("\\", "/")
                        logger.info(f"차트 추출: {_label} → {_path}")
            except Exception as e:
                logger.warning(f"기상 차트 추출 실패: {e}")

            # 주요 터뷸런스 예상 구간 테이블 (OFP PDF에서 SR 5+ 구간 추출)
            major_turbulence_table = []
            flight_data = []
            try:
                from flightplanextractor import extract_flight_data_from_pdf, build_major_turbulence_table
                flight_data = extract_flight_data_from_pdf(filepath, save_temp=False)
                if flight_data:
                    major_turbulence_table = build_major_turbulence_table(flight_data)
                    if major_turbulence_table:
                        logger.info(f"주요 터뷸런스 예상 구간: {len(major_turbulence_table)}개 구간")
            except Exception as e:
                logger.warning(f"주요 터뷸런스 테이블 생성 실패: {e}")

            # ISIGMET + G-AIRMET 실시간 경로 분석 (aviationweather.gov)
            sigmet_route_table = []
            sigmet_checked = False   # API 호출 성공 여부
            try:
                from src.sigwx_analyzer import fetch_and_match_sigmet_for_route
                from datetime import datetime as _dt, timezone as _tz
                import re as _re
                if flight_data:
                    # OFP 날짜 파싱 (PDF 텍스트에서 "06/MAR/26" 형식 추출)
                    ofp_date = None
                    try:
                        _month_map = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,
                                      'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
                        _dm = _re.search(r'(\d{2})/([A-Z]{3})/(\d{2,4})', text[:5000])
                        if _dm:
                            _day = int(_dm.group(1))
                            _mon = _month_map.get(_dm.group(2), 1)
                            _yr_raw = _dm.group(3)
                            _yr = int(_yr_raw) if len(_yr_raw) == 4 else 2000 + int(_yr_raw)
                            ofp_date = _dt(_yr, _mon, _day, 0, 0, 0, tzinfo=_tz.utc)
                            logger.info(f"OFP 날짜 파싱: {ofp_date.date()}")
                    except Exception as _e:
                        logger.warning(f"OFP 날짜 파싱 실패: {_e}")

                    sigmet_route_table = fetch_and_match_sigmet_for_route(
                        flight_data, ofp_date=ofp_date)
                    sigmet_checked = True
                    logger.info(f"SIGMET 경로 영향 구간: {len(sigmet_route_table)}개")
            except Exception as e:
                logger.warning(f"SIGMET 경로 분석 실패: {e}")

            # GFS(Ellrod) CAT 분석 비활성화 — 정확도 이슈로 결과 화면에서 제외
            wafs_turb_table = []
            wafs_turb_warn  = None
            wafs_cat_disabled = True

            # 공항별 기상(TAF) 분석 테이블 (DEP/DEST/ALTN/REFILE/EDTO/ERA) — ERA는 공항 필터 Package 2와 동일 소스 사용
            airport_weather_table = []
            try:
                from src.flight_plan_analyzer import build_airport_weather_table
                airport_weather_table = build_airport_weather_table(
                    text,
                    package_airports=filtered_package_airports if filtered_package_airports else None,
                )
                if airport_weather_table:
                    logger.info(f"공항별 기상 분석: {len(airport_weather_table)}개 공항")
            except Exception as e:
                logger.warning(f"공항별 기상 분석 테이블 생성 실패: {e}")

            # REFILE 연료 요약 — 원문 PDF → text → temp split 파일 순으로 시도 (다른 단계 실패와 무관)
            refile_fuel_table = []
            try:
                from src.flight_plan_analyzer import extract_refile_fuel_summaries
                # 1) 원문 PDF 전체
                if filepath:
                    try:
                        refile_text = pdf_converter.get_raw_pdf_text(filepath)
                        refile_fuel_table = extract_refile_fuel_summaries(refile_text) if refile_text else []
                    except Exception as _e:
                        logger.debug(f"REFILE raw PDF 추출 스킵: {_e}")
                # 2) 변환된 text (패키지 시 NOTAM 블록 join본)
                if not refile_fuel_table and text and "REFILE FLT PLAN" in text.upper():
                    refile_fuel_table = extract_refile_fuel_summaries(text)
                # 3) temp에 저장된 split 파일 (pdf_converter와 동일 경로: 앱 루트 기준)
                if not refile_fuel_table and filepath:
                    _temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), app.config.get("TEMP_FOLDER", "temp"))
                    _base = os.path.splitext(os.path.basename(filepath))[0]
                    _split_path = os.path.join(_temp_dir, _base + "_split.txt")
                    if os.path.isfile(_split_path):
                        with open(_split_path, "r", encoding="utf-8") as _f:
                            _split_content = _f.read()
                        refile_fuel_table = extract_refile_fuel_summaries(_split_content)
                        if refile_fuel_table:
                            logger.info("REFILE 연료 요약: temp split 파일에서 추출")
                if refile_fuel_table:
                    logger.info(f"REFILE 연료 요약: {len(refile_fuel_table)}개")
            except Exception as e:
                logger.warning(f"REFILE 연료 요약 추출 실패: {e}")

            # High Terrain 구간 테이블 (MSA > 10,000ft), ETP 요약, Wind/Temp 기반 shear/역전 분석
            high_terrain_table = []
            etp_summary_table = []
            wind_shear_table = []
            try:
                from src.flight_plan_analyzer import (
                    extract_high_terrain_waypoints,
                    extract_all_airports_from_text,
                    extract_etp_summaries,
                    build_wind_shear_inversion_table_for_route,
                )
                _airports_info = extract_all_airports_from_text(text)
                _etd = _airports_info.get("etd_time") or ""

                high_terrain_table = extract_high_terrain_waypoints(text, etd_hhmm=_etd)
                if high_terrain_table:
                    logger.info(f"High Terrain 구간: {len(high_terrain_table)}개")

                etp_summary_table = extract_etp_summaries(text, etd_hhmm=_etd)
                if etp_summary_table:
                    logger.info(f"ETP 요약: {len(etp_summary_table)}개")

                # Wind/Temp 요약: 실제 운항 waypoint+FL 기준으로 분석
                try:
                    wind_shear_table = build_wind_shear_inversion_table_for_route(text, flight_data or [])
                except NameError:
                    # flight_data가 정의되지 않은 경우(추출 실패 등)에는 스킵
                    wind_shear_table = []
                if wind_shear_table:
                    logger.info(f"Wind/Temp 역전·shear 구간: {len(wind_shear_table)}개")
            except Exception as e:
                logger.warning(f"High Terrain / ETP / Wind 분석 실패: {e}")
            
            # Q Route 비교 결과 (OFP vs ATS FPL) — 2nd plan 행 아래에 표시
            route_comparison = None
            try:
                import pdfplumber
                from src.ats_route_extractor import (
                    extract_ats_fpl_route_from_page,
                    compare_routes,
                    normalize_route,
                )
                if extracted_route and extracted_route.strip():
                    ofp_normalized = normalize_route(extracted_route)
                    ats_route = None
                    ats_full_text = None
                    try:
                        with pdfplumber.open(filepath) as pdf:
                            page_texts = [(p.extract_text() or "") for p in pdf.pages]
                        # (FPL- 블록이 페이지를 넘어갈 수 있으므로 전체 텍스트에서 괄호 균형으로 추출
                        full_pdf_text = "\n".join(page_texts)
                        idx = full_pdf_text.find("(FPL-")
                        if idx >= 0:
                            start = idx
                            depth = 0
                            for i in range(start, len(full_pdf_text)):
                                if full_pdf_text[i] == "(":
                                    depth += 1
                                elif full_pdf_text[i] == ")":
                                    depth -= 1
                                    if depth == 0:
                                        ats_full_text = "\n".join(
                                            line.strip() for line in full_pdf_text[start : i + 1].splitlines() if line.strip()
                                        )
                                        break
                        # 경로 추출은 (FPL-) 블록 또는 각 페이지에서 시도
                        for page_text in page_texts:
                            if not page_text:
                                continue
                            up = page_text.upper()
                            if "COPY OF ATS FPL" in up or "ATS FPL" in up or "(FPL-" in page_text:
                                ats_route = extract_ats_fpl_route_from_page(page_text)
                                if ats_route:
                                    break
                        if not ats_route and ats_full_text:
                            ats_route = extract_ats_fpl_route_from_page(ats_full_text)
                    except Exception as e2:
                        logger.warning(f"ATS FPL 페이지 스캔 실패: {e2}")
                    if ats_route:
                        route_comparison = compare_routes(extracted_route, ats_route)
                        route_comparison["ats_full_text"] = ats_full_text
                        logger.info(f"Route 비교: 일치={route_comparison.get('match')}")
                    else:
                        # OFP만 있어도 블록 표시 (ATS 미추출 시 메시지로 안내)
                        route_comparison = {
                            "ofp_normalized": ofp_normalized,
                            "ats_normalized": None,
                            "match": False,
                            "ats_not_found": True,
                            "ats_full_text": ats_full_text,
                        }
            except Exception as e:
                logger.warning(f"Q Route 비교 생성 실패: {e}")
            
            # 템플릿에 공항 정보 및 항로 정보 전달
            return render_template('results.html', 
                                 notams=notams, 
                                 takeoff_infos=takeoff_infos,
                                 current_date=datetime.now().strftime('%Y-%m-%d'),
                                 all_airports=sorted(list(all_airports)),
                                 package_airports=filtered_package_airports,
                                 package1_route_info=package1_route_info,  # Package 1 항로 정보 추가
                                 extracted_route=extracted_route if extracted_route else '',
                                 is_docpack=bool(extracted_route),
                                 flight_plan_waypoints=flight_plan_waypoints,
                                 flight_plan_summary_items_before=flight_plan_summary_items_before,
                                 flight_plan_summary_items_after=flight_plan_summary_items_after,
                                 flight_plan_fuel_time_table=flight_plan_fuel_time_table,
                                 flight_plan_weight_table=flight_plan_weight_table,
                                 major_turbulence_table=major_turbulence_table,
                                 sigmet_route_table=sigmet_route_table,
                                 sigmet_checked=sigmet_checked,
                                 wafs_turb_table=wafs_turb_table,
                                 wafs_turb_warn=wafs_turb_warn,
                                 wafs_cat_disabled=wafs_cat_disabled,
                                 chart_images=chart_images,
                                 route_comparison=route_comparison,
                                 airport_weather_table=airport_weather_table,
                                 high_terrain_table=high_terrain_table,
                                 etp_summary_table=etp_summary_table,
                                 refile_fuel_table=refile_fuel_table,
                                 wind_shear_table=wind_shear_table)
        
        else:
            flash('허용되지 않는 파일 형식입니다. PDF 파일만 업로드 가능합니다.')
            return redirect(url_for('index'))
    
    except Exception as e:
        logger.error(f"업로드 처리 중 오류: {str(e)}", exc_info=True)
        flash(f'파일 처리 중 오류가 발생했습니다: {str(e)}')
        return redirect(url_for('index'))
    finally:
        # 처리 완료 후 해당 세션의 락 해제
        if 'session_id' in session:
            session_id = session['session_id']
            if session_id in _processing_locks:
                _processing_locks[session_id]['locked'] = False
                _processing_locks[session_id]['lock_time'] = None
                logger.debug(f"세션 {session_id[:8]}의 처리 락을 해제했습니다.")

# 중복된 health check 엔드포인트 제거

@app.route('/api/analyze_route', methods=['POST'])
def analyze_route():
    """GEMINI를 사용한 AI 기반 루트 분석 API (Package 3 공항 필터링)"""
    try:
        # 파일 업로드 및 폼 데이터 지원
        if request.content_type and request.content_type.startswith('multipart/form-data'):
            route = request.form.get('route', '').strip()
            notam_file = request.files.get('notam_file')
            notam_data = []
            if notam_file:
                # 파일 내용을 읽어서 lines로 변환
                file_content = notam_file.read().decode('utf-8', errors='ignore')
                # 간단한 NOTAM 파싱 (여기서는 줄 단위로 리스트로 전달)
                notam_data = file_content.splitlines()
            package_scope = request.form.get('package_scope', '')
            # 추가적으로 필요한 파싱 로직이 있으면 여기에 구현
            data = {'route': route, 'notam_data': notam_data, 'package_scope': package_scope}
        else:
            # application/json 요청만 처리
            if request.is_json:
                data = request.get_json()
                route = data.get('route', '').strip()
                package_scope = data.get('package_scope', '')
                notam_data = data.get('notam_data', [])
            else:
                logger.error(f"지원하지 않는 Content-Type: {request.content_type}")
                return jsonify({'error': f'지원하지 않는 Content-Type: {request.content_type}'}), 415
        if not route:
            logger.warning("항로가 입력되지 않음")
            return jsonify({'error': '항로를 입력해주세요.'}), 400
        logger.debug(f"분석: {route}, Scope: {package_scope}")

        # Package 3 공항 필터링
        if package_scope == 'package3':
            try:
                logger.debug("Package 3 원문 추출")
                
                # split.txt 파일에서 Package 3 원문 직접 읽기
                package3_text_list = []  # 문자열 리스트로 Package 3 원문 저장
                fir_order = []
                try:
                    temp_dir = app.config.get('TEMP_FOLDER', 'temp')
                    split_files = glob.glob(os.path.join(temp_dir, '*_split.txt'))
                    if split_files:
                        latest_split = max(split_files, key=os.path.getmtime)
                        logger.debug(f"최신 split: {latest_split}")
                        
                        # Package 3 섹션 추출
                        with open(latest_split, 'r', encoding='utf-8', errors='ignore') as f:
                            full_text = f.read()
                        
                        package3_start = full_text.find("KOREAN AIR NOTAM PACKAGE 3")
                        if package3_start != -1:
                            package3_end = full_text.find("END OF KOREAN AIR NOTAM PACKAGE 3", package3_start)
                            if package3_end == -1:
                                package3_text = full_text[package3_start:]
                            else:
                                package3_end += len("END OF KOREAN AIR NOTAM PACKAGE 3")
                                package3_text = full_text[package3_start:package3_end]
                            
                            # 줄 단위로 리스트로 변환 (ai_route_analyzer에서 문자열 리스트를 기대)
                            package3_text_list = package3_text.splitlines()
                            logger.debug(f"Package 3: {len(package3_text_list)}줄")
                        
                        # FIR 순서 추출 (Package 3 텍스트 우선, multi-line 지원)
                        try:
                            source_lines = []
                            if package3_text_list:
                                # 이미 추출한 Package 3 텍스트에서 직접 파싱
                                source_lines = package3_text_list
                            else:
                                with open(latest_split, 'r', encoding='utf-8', errors='ignore') as f:
                                    source_lines = f.readlines()
                            # 'FIR:' 시작 라인 찾기
                            start_idx = -1
                            for i, line in enumerate(source_lines):
                                if str(line).strip().startswith('FIR:'):
                                    start_idx = i
                                    break
                            if start_idx != -1:
                                collected = []
                                # 최대 10줄까지 블록 스캔
                                for j in range(start_idx, min(start_idx + 10, len(source_lines))):
                                    raw = source_lines[j]
                                    line = str(raw).rstrip('\n\r')  # 줄바꿈 제거
                                    if j == start_idx:
                                        # 'FIR:' 접두어 제거
                                        line = re.sub(r'^\s*FIR:\s*', '', line, flags=re.IGNORECASE).strip()
                                        logger.debug(f"  라인 {j+1} (첫 줄): '{line[:120]}'")
                                    else:
                                        line = line.strip()
                                        logger.debug(f"  라인 {j+1}: '{line[:120]}'")
                                    if not line or line.startswith('==='):
                                        if j == start_idx:
                                            break
                                        else:
                                            logger.debug(f"  라인 {j+1}이 비어있거나 구분선 - 블록 종료")
                                            break
                                    codes = re.findall(r'\b[A-Z]{4}\b', line.upper())
                                    if codes:
                                        collected.extend(codes)
                                    else:
                                        if j > start_idx:
                                            logger.debug(f"  라인 {j+1}에 FIR 코드 없음 - 블록 종료")
                                            break
                                seen = set()
                                for c in collected:
                                    if len(c) == 4 and c.isalpha() and c not in seen:
                                        seen.add(c)
                                        fir_order.append(c)
                                logger.debug(f"FIR 순서 추출: {len(fir_order)}개")
                            else:
                                logger.debug("FIR: 라인을 찾을 수 없음")
                        except Exception as _e_parse:
                            logger.debug(f"FIR 파싱 경고: {_e_parse}")
                        
                        if not fir_order:
                            logger.debug("FIR 순서가 비어있음")
                    else:
                        logger.debug("split.txt 파일 없음")
                        # 폴백: 프런트엔드가 보낸 데이터 사용
                        notam_data = data.get('notam_data', [])
                        if isinstance(notam_data, list) and len(notam_data) > 0:
                            if isinstance(notam_data[0], str):
                                package3_text_list = notam_data
                            else:
                                # 딕셔너리 리스트인 경우 텍스트만 추출
                                package3_text_list = [item.get('text', '') for item in notam_data if isinstance(item, dict)]
                                package3_text_list = [line for text in package3_text_list for line in text.splitlines() if text]
                    if not fir_order or len(fir_order) < 2:
                        logger.debug(f"FIR 순서 부족: {len(fir_order)}개")
                except Exception as e:
                    logger.warning(f"Package 3 원문 추출 실패(무시하고 진행): {e}")
                    import traceback
                    logger.debug(traceback.format_exc())
                    # 폴백: 프런트엔드가 보낸 데이터 사용
                    notam_data = data.get('notam_data', [])
                    if isinstance(notam_data, list) and len(notam_data) > 0:
                        if isinstance(notam_data[0], str):
                            package3_text_list = notam_data
                        else:
                            package3_text_list = [item.get('text', '') for item in notam_data if isinstance(item, dict)]
                            package3_text_list = [line for text in package3_text_list for line in text.splitlines() if text]
                # 입력값 검증 및 방어적 analyze_route_with_gemini 호출
                try:
                    gemini_analysis = None
                    if not isinstance(package3_text_list, list):
                        logger.error(f"❌ package3_text_list가 리스트가 아님: {package3_text_list}")
                        package3_text_list = []
                    if not isinstance(fir_order, list):
                        logger.error(f"❌ fir_order가 리스트가 아님: {fir_order}")
                        fir_order = []
                    
                    if not package3_text_list:
                        logger.warning("⚠️ Package 3 원문이 없습니다. 프런트엔드 데이터로 폴백")
                        notam_data = data.get('notam_data', [])
                        if isinstance(notam_data, list) and len(notam_data) > 0:
                            if isinstance(notam_data[0], str):
                                package3_text_list = notam_data
                            else:
                                package3_text_list = [item.get('text', '') for item in notam_data if isinstance(item, dict)]
                                package3_text_list = [line for text in package3_text_list for line in text.splitlines() if text]
                    
                    logger.debug(f"Gemini 분석 시작: route={route}, fir={len(fir_order)}개, lines={len(package3_text_list)}")
                    gemini_analysis = analyze_route_with_gemini(
                        route=route,
                        notam_data=package3_text_list,  # Package 3 원문 문자열 리스트 전달
                        fir_order=fir_order,
                        **{k: v for k, v in data.items() if k not in ['route', 'notam_data', 'use_package3_extraction', 'package_scope']}
                    )
                except Exception as e:
                    logger.error(f"Gemini 분석 오류: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    gemini_analysis = {'error': f'analyze_route_with_gemini 오류: {str(e)}'}
                return jsonify({
                    'route': route,
                    'gemini_analysis': gemini_analysis,
                    'package3_notam_count': len(package3_text_list),
                    'fir_order': fir_order,
                    'timestamp': datetime.now().isoformat()
                })
            except Exception as e:
                logger.error(f"Package 3 필터링 실패: {str(e)}")
                logger.exception("상세 오류:")
                return jsonify({'error': f'Package 3 필터링 중 오류: {str(e)}'}), 500
        
        # 일반 모드 (전체 NOTAM 사용)
        else:
            notam_data = data.get('notam_data', [])
            logger.debug(f"전체 NOTAM: {len(notam_data)}개")
            
            # AI 분석기로 위임
            gemini_analysis = analyze_route_with_gemini(
                route=route,
                notam_data=notam_data,
                **{k: v for k, v in data.items() if k not in ['route', 'notam_data']}
            )
            
            return jsonify({
                'route': route,
                'gemini_analysis': gemini_analysis,
                'timestamp': datetime.now().isoformat()
            })
        
    except Exception as e:
        logger.error(f"루트 분석 오류: {str(e)}")
        logger.exception("상세 오류:")
        return jsonify({
            'error': f'루트 분석 중 오류가 발생했습니다: {str(e)}',
            'traceback': str(e)
        }), 500

@app.route('/api/analyze_airports_comprehensive', methods=['POST'])
def analyze_airports_comprehensive():
    """GEMINI AI를 활용한 공항별 NOTAM 종합 분석 API"""
    try:
        data = request.get_json()
        notam_data = data.get('notam_data', [])
        
        # 공항 정보 추출 - 두 가지 방식 지원
        # 1. 직접 공항 코드가 있는 경우 (dep/dest 폼)
        dep = data.get('dep', '').strip().upper()
        dest = data.get('dest', '').strip().upper()
        altn = data.get('altn', '').strip().upper() if data.get('altn') else None
        edto = data.get('edto', '').strip().upper() if data.get('edto') else None
        
        # 2. 공항 필터에서 선택한 경우 (airports 딕셔너리)
        airports_dict = data.get('airports', {})
        
        # 공항 정보 처리
        airports = {}
        
        if dep and dest:
            # 폼에서 입력한 경우
            airports['DEP'] = dep
            airports['DEST'] = dest
            if altn:
                airports['ALTN'] = altn
            if edto:
                edto_airports = edto.split()
                for i, airport_code in enumerate(edto_airports):
                    if airport_code.strip():
                        airports[f'EDTO_{i+1}'] = airport_code.strip()
            logger.debug(f"공항 분석: {dep}/{dest}, ALT:{altn}, EDT:{edto}")
        elif airports_dict:
            # 공항 필터에서 선택한 경우
            for airport_type, airport_data in airports_dict.items():
                if isinstance(airport_data, dict):
                    airport_code = airport_data.get('airport_code', '')
                else:
                    airport_code = str(airport_data)
                
                if airport_code:
                    airports[airport_type] = airport_code.strip().upper()
            logger.debug(f"공항 필터: {list(airports.values())}")
        else:
            return jsonify({'error': '공항 정보를 입력해주세요.'}), 400
        
        logger.debug(f"NOTAM: {len(notam_data)}개")
        
        # 각 공항별 필터링 및 분석
        analysis_result = {}
        total_notams_count = 0
        
        for airport_type, airport_code in airports.items():
            # 해당 공항의 NOTAM 필터링
            airport_notams = []
            for notam in notam_data:
                notam_airports = notam.get('airports', [])
                if isinstance(notam_airports, list) and airport_code in notam_airports:
                    airport_notams.append(notam)
                    continue
                if notam.get('airport_code') == airport_code:
                    airport_notams.append(notam)
                    continue
                # text/description에서 확인
                text = notam.get('text', '').upper()
                description = notam.get('description', '').upper()
                if airport_code in text or airport_code in description:
                    airport_notams.append(notam)
            
            total_notams_count += len(airport_notams)
            
            logger.debug(f"{airport_type}({airport_code}): {len(airport_notams)}개")
            
            # GEMINI AI를 활용한 종합 분석 - Lazy initialization
            airport_analysis = get_notam_comprehensive_analyzer().analyze_airport_notams_comprehensive(
                airport_code, airport_notams
            )
            
            # total_notams 필드 추가 (프론트엔드 호환성)
            airport_analysis['total_notams'] = len(airport_notams)
            airport_analysis['notams'] = airport_notams[:10]  # 상위 10개만 저장
            
            analysis_result[airport_type] = airport_analysis
        
        # 분석 타입 결정 (GEMINI 사용 시 comprehensive) - Lazy initialization
        analyzer = get_notam_comprehensive_analyzer()
        analysis_type = 'comprehensive' if analyzer.model else 'basic'
        
        return jsonify({
            'analysis_result': {
                'airports': analysis_result,
                'summary': {
                    'total_airports': len(airports),
                    'total_notams': total_notams_count,
                    'analysis_type': analysis_type
                }
            },
            'summary': {
                'total_airports': len(airports),
                'total_notams': total_notams_count,
                'analysis_type': analysis_type
            },
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"공항별 NOTAM 분석 중 오류: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({'error': f'공항별 NOTAM 분석 중 오류가 발생했습니다: {str(e)}'}), 500

@app.route('/api/analyze_single_airport', methods=['POST'])
def analyze_single_airport():
    """단순화된 개별 공항 NOTAM 분석 API"""
    try:
        data = request.get_json()
        airport_code = data.get('airport_code', '').strip().upper()
        notam_data = data.get('notam_data', [])
        
        if not airport_code:
            return jsonify({'error': '공항 코드를 입력해주세요.'}), 400
        
        logger.debug(f"개별 공항 분석: {airport_code}, {len(notam_data)}개")
        
        # 해당 공항의 NOTAM 필터링
        airport_notams = [
            notam for notam in notam_data 
            if airport_code in notam.get('airports', []) or 
               airport_code == notam.get('airport_code', '')
        ]
        
        analysis_result = {
            'airport_code': airport_code,
            'total_notams': len(airport_notams),
            'notams': airport_notams,
            'summary': f"{airport_code} 공항 관련 NOTAM {len(airport_notams)}건 발견"
        }
        
        return jsonify({
            'airport_code': airport_code,
            'analysis_result': analysis_result,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"개별 공항 NOTAM 분석 중 오류: {str(e)}")
        return jsonify({'error': f'개별 공항 NOTAM 분석 중 오류가 발생했습니다: {str(e)}'}), 500

@app.route('/api/extract_flight_info', methods=['POST'])
def extract_flight_info():
    """NOTAM에서 항공편 정보 자동 추출 API"""
    try:
        # temp 폴더에서 가장 최근 txt 파일 찾기
        temp_folder = 'temp'
        if not os.path.exists(temp_folder):
            return jsonify({'error': 'temp 폴더를 찾을 수 없습니다.'}), 404
        
        # 가장 최근 txt 파일 찾기
        txt_files = [f for f in os.listdir(temp_folder) if f.endswith('_split.txt')]
        if not txt_files:
            return jsonify({'error': 'NOTAM txt 파일을 찾을 수 없습니다.'}), 404
        
        # 가장 최근 파일 선택 (파일명 기준)
        latest_file = max(txt_files)
        txt_path = os.path.join(temp_folder, latest_file)
        
        
        # 원본 txt 파일에서 직접 읽기
        with open(txt_path, 'r', encoding='utf-8') as f:
            notam_text = f.read()
        
        logger.debug(f"txt 읽기: {len(notam_text)} 문자")
        
        # NOTAM에서 항공편 정보 추출
        flight_info = extract_flight_info_from_notams(notam_text)
        
        return jsonify({
            'flight_info': flight_info,
            'source_file': latest_file,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        # Windows 인코딩 문제 방지를 위해 오류 메시지 안전 처리
        try:
            error_msg = str(e)
            logger.error(f"항공편 정보 추출 중 오류: {error_msg}")
        except UnicodeEncodeError:
            # 인코딩 오류 발생 시 ASCII로 변환
            error_msg = str(e).encode('ascii', 'ignore').decode('ascii')
            logger.error(f"항공편 정보 추출 중 오류: {error_msg}")
        
        # JSON 응답은 UTF-8로 안전하게 전송
        try:
            error_response = f'항공편 정보 추출 중 오류가 발생했습니다: {str(e)}'
        except UnicodeEncodeError:
            error_response = '항공편 정보 추출 중 오류가 발생했습니다.'
        
        return jsonify({'error': error_response}), 500

# AI 항로 분석 관련 코드는 src/ai_route_analyzer.py로 이동

@app.route('/api/submit_improvement', methods=['POST'])
def submit_improvement():
    """개선요청 제출 API"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'success': False, 'error': '데이터가 없습니다.'}), 400
        
        feedback_type = data.get('feedback_type', 'improvement')
        title = data.get('title', '')
        content = data.get('content', '')
        email = data.get('email', '')
        
        if not title or not content:
            return jsonify({'success': False, 'error': '제목과 내용을 입력해주세요.'}), 400
        
        # Supabase에 개선요청 저장
        result = feedback_db.submit_feedback(
            original_text=f"[개선요청] {title}\n\n{content}",
            feedback_type=feedback_type,
            feedback_comment=content,
            user_email=email if email else None,
            user_id=request.remote_addr,  # IP 주소를 사용자 ID로 사용
            session_id=request.headers.get('X-Session-ID', '')
        )
        
        if result.get('success'):
            logger.info(f"개선요청 제출 성공: {result.get('id')}")
            return jsonify({
                'success': True,
                'message': '개선요청이 성공적으로 제출되었습니다.',
                'id': result.get('id')
            })
        else:
            logger.error(f"개선요청 제출 실패: {result.get('error')}")
            return jsonify({
                'success': False,
                'error': result.get('error', '개선요청 제출에 실패했습니다.')
            }), 500
            
    except Exception as e:
        logger.error(f"개선요청 제출 오류: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'개선요청 제출 중 오류가 발생했습니다: {str(e)}'
        }), 500

@app.route('/api/extract_airports', methods=['POST'])
def extract_airports():
    """PDF에서 공항 코드를 추출하는 API"""
    try:
        
        if 'file' not in request.files:
            logger.error("파일이 요청에 포함되지 않음")
            return jsonify({'error': '파일이 선택되지 않았습니다.'}), 400
        
        file = request.files['file']
        
        if file.filename == '' or not allowed_file(file.filename):
            logger.error(f"유효하지 않은 파일: {file.filename}")
            return jsonify({'error': '유효하지 않은 파일입니다.'}), 400
        
        # 임시 파일 저장 (고유 ID 추가로 파일 충돌 방지)
        filename = secure_filename(file.filename or 'unknown.pdf')
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        request_id = str(uuid.uuid4())[:8]  # 짧은 고유 ID
        temp_filename = f"temp_{timestamp}_{request_id}_{filename}"
        temp_filepath = os.path.join(app.config['TEMP_FOLDER'], temp_filename)
        file.save(temp_filepath)
        
        # 임시 파일 정리 (최신 2개만 유지 - 용량 절감 + 이전 파일 확인 가능)
        cleanup_files(app.config['TEMP_FOLDER'], max_files=2)
        
        try:
            # PDF 텍스트 변환 (임시 파일 저장 비활성화)
            text = pdf_converter.convert_pdf_to_text(temp_filepath, save_temp=False)
            logger.debug(f"PDF 변환: {len(text)} 문자")
            
            if not text.strip():
                logger.error("PDF에서 텍스트 추출 실패")
                return jsonify({'error': 'PDF에서 텍스트를 추출할 수 없습니다.'}), 400
            
            # NOTAM 필터링하여 공항 코드 추출
            notams = notam_filter.filter_korean_air_notams(text)
            logger.debug(f"NOTAM 필터링: {len(notams)}개")
            
            # ai_route_analyzer의 공항 추출 함수 사용
            from src.ai_route_analyzer import AIRouteAnalyzer
            analyzer = AIRouteAnalyzer()
            all_airports = analyzer._extract_airports_from_notams(notams)
            
            logger.debug(f"공항 추출: {len(all_airports)}개")
            
            return jsonify({
                'airports': all_airports,
                'notam_count': len(notams)
            })
            
        finally:
            # 임시 파일 삭제
            if os.path.exists(temp_filepath):
                os.remove(temp_filepath)
    
    except Exception as e:
        # Windows 인코딩 문제 방지를 위해 오류 메시지 안전 처리
        try:
            error_msg = str(e)
            logger.error(f"공항 추출 중 오류: {error_msg}")
        except UnicodeEncodeError:
            # 인코딩 오류 발생 시 ASCII로 변환
            error_msg = str(e).encode('ascii', 'ignore').decode('ascii')
            logger.error(f"공항 추출 중 오류: {error_msg}")
        
        # JSON 응답은 UTF-8로 안전하게 전송
        try:
            error_response = f'공항 추출 중 오류가 발생했습니다: {str(e)}'
        except UnicodeEncodeError:
            error_response = '공항 추출 중 오류가 발생했습니다.'
        
        return jsonify({'error': error_response}), 500

@app.route('/google_maps')
def google_maps():
    """구글지도 페이지"""
    # Google Maps API 키 가져오기 (보안상 Maps 전용 키만 노출)
    maps_api_key = os.getenv('GOOGLE_MAPS_API_KEY')
    if not maps_api_key:
        logger.warning("GOOGLE_MAPS_API_KEY is not set; Google Maps page may fail to load.")
    return render_template('google_maps.html', maps_api_key=maps_api_key or '')

@app.route('/api/airport-notams')
def api_airport_notams():
    """
    현재 temp 폴더의 최신 *_split.txt에서 NOTAM을 읽어
    지정 공항(ICAO)의 NOTAM을 시간 필터로 반환
    Query:
      - icao: 공항 코드 (필수)
      - from: ISO8601 (선택)
      - to: ISO8601 (선택)
    """
    try:
        # icao가 없으면 airport 파라미터를 대체 입력으로 사용 (IATA/ICAO 모두 허용)
        icao = request.args.get('icao', '').strip().upper()
        if not icao:
            alt = request.args.get('airport', '').strip().upper()
            if alt:
                icao = alt
        if not icao:
            return jsonify({'error': 'icao 파라미터가 필요합니다.'}), 400
        # IATA(3자) → ICAO(4자) 매핑 시도
        if len(icao) == 3:
            try:
                # src/airports.csv 사용 (헤더: icao,iata,name,lat,lon 등 가정)
                csv_path = os.path.join(os.path.dirname(__file__), 'src', 'airports.csv')
                if os.path.exists(csv_path):
                    import csv
                    with open(csv_path, newline='', encoding='utf-8-sig') as cf:
                        reader = csv.DictReader(cf)
                        mapped = None
                        for row in reader:
                            # 파일 헤더: ident(ICAO), iata_code
                            iata = (row.get('iata_code') or row.get('iata') or '').strip().upper()
                            icao_val = (row.get('ident') or row.get('icao') or '').strip().upper()
                            if iata == icao and len(icao_val) == 4:
                                mapped = icao_val
                                break
                        if mapped:
                            icao = mapped
                        else:
                            # 추가 폴백(자주 쓰는 공항)
                            fallback_map = {
                                'GMP': 'RKSS', 'ICN': 'RKSI', 'PUS': 'RKPK', 'CJU': 'RKPC',
                                'HND': 'RJTT', 'NRT': 'RJAA', 'KIX': 'RJBB', 'CTS': 'RJCC'
                            }
                            if icao in fallback_map:
                                icao = fallback_map[icao]
            except Exception as _:
                pass
        # 1) 캐시 우선: 최근 분석 결과가 있으면 그 데이터에서 바로 공항 필터
        global LAST_NOTAMS, LAST_NOTAMS_INDEXED_BY_AIRPORT, LAST_NOTAMS_SOURCE
        cached = []
        
        # temp 폴더의 최신 파일 확인
        temp_folder = app.config.get('TEMP_FOLDER', 'temp')
        latest_file_in_folder = None
        latest_file_mtime = 0
        if os.path.exists(temp_folder):
            txt_files = [f for f in os.listdir(temp_folder) if f.endswith('_split.txt')]
            if txt_files:
                # 파일 수정 시간 기준으로 최신 파일 선택
                for f in txt_files:
                    file_path = os.path.join(temp_folder, f)
                    try:
                        mtime = os.path.getmtime(file_path)
                        if mtime > latest_file_mtime:
                            latest_file_mtime = mtime
                            latest_file_in_folder = f
                    except Exception:
                        pass
                # 파일명 기준 폴백 (타임스탬프 형식인 경우)
                if not latest_file_in_folder:
                    latest_file_in_folder = max(txt_files)
        
        # 메모리 캐시가 있고, 최신 파일과 일치하는 경우에만 사용
        use_cache = False
        if LAST_NOTAMS_SOURCE and latest_file_in_folder:
            # 캐시된 파일이 최신 파일과 일치하는지 확인
            if LAST_NOTAMS_SOURCE == latest_file_in_folder:
                use_cache = True
        
        try:
            if use_cache and LAST_NOTAMS_INDEXED_BY_AIRPORT and icao in LAST_NOTAMS_INDEXED_BY_AIRPORT:
                cached = LAST_NOTAMS_INDEXED_BY_AIRPORT.get(icao, [])
            elif use_cache and LAST_NOTAMS:
                analyzer = AirportNotamAnalyzer()
                cached = analyzer._filter_airport_notams(icao, LAST_NOTAMS)
        except Exception:
            cached = []
        # 하위 헬퍼: 제한 사항 키워드 확인 (확장됨)
        # 정규식을 모듈 레벨에서 한 번만 컴파일 (성능 최적화)
        import re
        _NOTAM_CLOSED_KEYWORDS_PATTERN = re.compile(
            r'\b(CLSD|CLOSED|NOT\s+AVAILABLE|NOT\s+AVAIL|UNAVAILABLE|RESTRICTED|PROHIBITED|FORBIDDEN|NOT\s+AUTHORIZED|OUT\s+OF\s+SERVICE|OUT\s+OF\s+SERV)\b',
            re.IGNORECASE
        )
        _NOTAM_HTML_TAG_PATTERN = re.compile(r'<[^>]+>')
        
        def _is_closed_notam(n):
            t = (n.get('text') or '') + ' ' + (n.get('description') or '')
            # HTML 태그 제거 (description 필드에 HTML이 포함될 수 있음)
            t = _NOTAM_HTML_TAG_PATTERN.sub('', t)  # 모든 HTML 태그 제거
            tu = t.upper()
            # 제한 사항 키워드: CLSD, CLOSED, RESTRICTED, PROHIBITED, FORBIDDEN, UNAVAILABLE 등 (U/S 제외)
            # 단어 경계를 사용하여 정확한 매칭 (예: "CLOSED"는 단어로 인식, "CLOSEDOWN"은 제외)
            return bool(_NOTAM_CLOSED_KEYWORDS_PATTERN.search(tu))

        if cached:
            # CLSD/폐쇄 계열만 선별
            cached = [n for n in cached if _is_closed_notam(n)]
            from_iso = request.args.get('from'); to_iso = request.args.get('to')
            from_local = request.args.get('from_local'); to_local = request.args.get('to_local')
            airport_for_local = icao  # 타임존 기준은 최종 ICAO로 고정
            def parse_iso(value):
                try:
                    if not value:
                        return None
                    return datetime.fromisoformat(value.replace('Z', '+00:00'))
                except Exception:
                    return None
            from_dt = parse_iso(from_iso); to_dt = parse_iso(to_iso)
            # 로컬 시간 필터가 있으면 우선 적용 (공항 현지시각)
            def in_local_window(n):
                if not from_local and not to_local:
                    return True
                # 사용자 로컬 입력/오프셋 공통 준비
                def parse_local_dt(s):
                    v = s.replace(' ', 'T')
                    return datetime.fromisoformat(v)
                user_from_local = parse_local_dt(from_local) if from_local else None
                user_to_local = parse_local_dt(to_local) if to_local else None
                tz_offset = notam_filter.get_timezone(airport_for_local)  # "+09:00"
                sign = 1 if tz_offset.startswith('+') else -1
                hh = int(tz_offset[1:3]); mm = int(tz_offset[4:6])
                delta = timedelta(hours=sign*hh, minutes=sign*mm)
                # local → UTC: local - offset
                user_from_utc = (user_from_local - delta) if user_from_local else None
                user_to_utc = (user_to_local - delta) if user_to_local else None
                # 0) 유효기간(현지시각 변환) 기준 1차 필터: 사용자 로컬 창과 겹치지 않으면 즉시 제외
                try:
                    eff = n.get('effective_time'); exp = n.get('expiry_time')
                    if eff:
                        eff_dt_utc = datetime.fromisoformat(eff.replace('Z', '+00:00'))
                        exp_dt_utc = None
                        if exp and exp not in ('UFN','PERM'):
                            exp_dt_utc = datetime.fromisoformat(exp.replace('Z', '+00:00'))
                        eff_local = eff_dt_utc + delta
                        exp_local = (exp_dt_utc + delta) if exp_dt_utc else None
                        if user_from_local or user_to_local:
                            if user_from_local and exp_local and exp_local < user_from_local:
                                return False
                            if user_to_local and eff_local and eff_local > user_to_local:
                                return False
                except Exception:
                    pass
                # notam의 로컬 시간 범위를 계산
                try:
                    # D) 필드 기반 로컬 범위 계산 (즉시 반환하지 말고 폴백으로 사용)
                    gen = notam_filter._generate_local_time_display(n)
                    d_local_ranges = None
                    if isinstance(gen, tuple) and len(gen) == 2:
                        local_time_str, d_local_ranges = gen
                    elif isinstance(gen, str):
                        local_time_str = gen
                    # 사용자 윈도우(UTC) 준비
                    user_from_utc = (user_from_local - delta) if user_from_local else None
                    user_to_utc = (user_to_local - delta) if user_to_local else None
                except Exception:
                    d_local_ranges = None
                # 1.4) local_time_display 내 HHMM-HHMM을 일일 로컬 구간으로 간주하여 겹침 확인
                try:
                    ltd = n.get('local_time_display') or ''
                    import re
                    m = re.search(r'(\d{3,4})\s*[-/]\s*(\d{3,4})', ltd)
                    if m and (user_from_local or user_to_local):
                        def to_minutes(hhmm):
                            s = hhmm.zfill(4)
                            return int(s[:2]) * 60 + int(s[2:])
                        d_start = to_minutes(m.group(1))
                        d_end = to_minutes(m.group(2))
                        uf = user_from_local.time() if user_from_local else None
                        ut = user_to_local.time() if user_to_local else None
                        ufm = (uf.hour*60 + uf.minute) if uf else None
                        utm = (ut.hour*60 + ut.minute) if ut else None
                        def overlap_daily(a1, a2, b1, b2):
                            def expand(s, e):
                                return [(s, e)] if s <= e else [(s, 24*60), (0, e)]
                            A = expand(a1, a2); B = expand(b1, b2)
                            for x1, x2 in A:
                                for y1, y2 in B:
                                    if max(x1, y1) < min(x2, y2):
                                        return True
                            return False
                        if ufm is not None and utm is not None:
                            return overlap_daily(d_start, d_end, ufm, utm)
                        elif ufm is not None:
                            return overlap_daily(d_start, d_end, ufm, ufm+1)
                        else:
                            return overlap_daily(d_start, d_end, utm, utm+1)
                except Exception:
                    pass
                # 1.5) description 내 HHMM-HHMM 패턴을 일일 로컬 구간으로 간주하여 겹침 확인 (캐시 데이터 보강)
                try:
                    desc = (n.get('description') or '') + ' ' + (n.get('text') or '')
                    import re
                    m = re.search(r'\b(\d{3,4})\s*[-/]\s*(\d{3,4})\b', desc)
                    if m and (user_from_local or user_to_local):
                        def to_minutes(hhmm):
                            s = hhmm.zfill(4)
                            return int(s[:2]) * 60 + int(s[2:])
                        d_start = to_minutes(m.group(1))
                        d_end = to_minutes(m.group(2))

                        # 사용자 로컬 윈도우(분)
                        uf = user_from_local.time() if user_from_local else None
                        ut = user_to_local.time() if user_to_local else None
                        ufm = (uf.hour * 60 + uf.minute) if uf else None
                        utm = (ut.hour * 60 + ut.minute) if ut else None
                        if ufm is None and utm is None:
                            return True

                        # 구간 겹침(자정 넘김 처리)
                        def overlap_daily(a1, a2, b1, b2):
                            def expand(s, e):
                                return [(s, e)] if s <= e else [(s, 24*60), (0, e)]
                            A = expand(a1, a2)
                            B = expand(b1, b2)
                            for x1, x2 in A:
                                for y1, y2 in B:
                                    if max(x1, y1) < min(x2, y2):
                                        return True
                            return False

                        # 사용자 구간이 한쪽만 있을 수 있음 → 점 시각으로 처리
                        if ufm is not None and utm is not None:
                            return overlap_daily(d_start, d_end, ufm, utm)
                        elif ufm is not None:
                            return overlap_daily(d_start, d_end, ufm, ufm + 1)
                        else:
                            return overlap_daily(d_start, d_end, utm, utm + 1)
                except Exception:
                    # 정규식/시간 파싱 실패 시 무시하고 다음 단계로 진행
                    pass
                # 1.6) 위에서 일일 HHMM이 없을 때만 D) 범위(UTC)로 폴백 겹침 확인
                try:
                    if d_local_ranges:
                        def overlaps_range(r):
                            try:
                                r_start = datetime.fromisoformat(r['start_utc'].replace('Z', '+00:00'))
                                r_end = datetime.fromisoformat(r['end_utc'].replace('Z', '+00:00'))
                                if not user_from_utc and not user_to_utc:
                                    return True
                                if user_from_utc and r_end and r_end < user_from_utc:
                                    return False
                                if user_to_utc and r_start and r_start > user_to_utc:
                                    return False
                                return True
                            except Exception:
                                return True
                        return any(overlaps_range(r) for r in d_local_ranges)
                except Exception:
                    pass
                # 2) 로컬 범위가 없으면 전체 유효기간을 공항 현지시각으로 변환해 비교
                try:
                    eff = n.get('effective_time'); exp = n.get('expiry_time')
                    if not eff:
                        return True
                    eff_dt_utc = datetime.fromisoformat(eff.replace('Z', '+00:00'))
                    exp_dt_utc = None
                    if exp and exp not in ('UFN','PERM'):
                        exp_dt_utc = datetime.fromisoformat(exp.replace('Z', '+00:00'))
                    # 공항 현지 오프셋(+HH:MM)
                    tz_offset = notam_filter.get_timezone(airport_for_local)
                    sign = 1 if tz_offset.startswith('+') else -1
                    hh = int(tz_offset[1:3]); mm = int(tz_offset[4:6])
                    delta = timedelta(hours=sign*hh, minutes=sign*mm)
                    eff_local = eff_dt_utc + delta
                    exp_local = (exp_dt_utc + delta) if exp_dt_utc else None
                    def parse_local_dt2(s):
                        return datetime.fromisoformat(s.replace(' ', 'T')) if s else None
                    user_from = parse_local_dt2(from_local)
                    user_to = parse_local_dt2(to_local)
                    if not user_from and not user_to:
                        return True
                    if user_from and exp_local and exp_local < user_from:
                        return False
                    if user_to and eff_local and eff_local > user_to:
                        return False
                    return True
                except Exception:
                    return True
            def overlaps_cached(n):
                eff = n.get('effective_time'); exp = n.get('expiry_time')
                try:
                    eff_dt = datetime.fromisoformat(eff.replace('Z', '+00:00')) if eff else None
                except Exception:
                    eff_dt = None
                if exp in ('UFN', 'PERM'):
                    exp_dt = None
                else:
                    try:
                        exp_dt = datetime.fromisoformat(exp.replace('Z', '+00:00')) if exp else None
                    except Exception:
                        exp_dt = None
                if not from_dt and not to_dt:
                    return True
                if from_dt and exp_dt and exp_dt < from_dt:
                    return False
                if to_dt and eff_dt and eff_dt > to_dt:
                    return False
                return True
            # 로컬 윈도우가 있으면 우선 로컬 기준 필터, 없으면 UTC 필터
            if from_local or to_local:
                cached = [n for n in cached if in_local_window(n)]
            elif from_dt or to_dt:
                cached = [n for n in cached if overlaps_cached(n)]
            result = []
            for n in cached:
                # 로컬 시간대 표시 및 일일 윈도우 보강 정보 (단계별 안전 처리)
                eff = n.get('effective_time'); exp = n.get('expiry_time')
                ac = (n.get('airport_code') or icao)
                local_time_str = None
                local_ranges = None
                # 1) 표준 포맷 생성 (실패해도 무시)
                try:
                    if eff:
                        local_time_str = notam_filter.format_notam_time_with_local(eff, exp, ac, n)
                except Exception:
                    pass
                # 2) D) 필드 기반 로컬 범위 (반환형 유연 처리)
                try:
                    gen = notam_filter._generate_local_time_display(n)
                    # 함수가 문자열만 반환하거나 (str), (str, ranges) 튜플을 반환할 수 있다고 가정
                    if isinstance(gen, tuple) and len(gen) == 2:
                        lt, lr = gen
                        local_ranges = lr
                        if not local_time_str and lt:
                            local_time_str = lt
                    elif isinstance(gen, str):
                        if not local_time_str and gen:
                            local_time_str = gen
                except Exception:
                    pass
                # 3) 최종 폴백: 유효시간(UTC) → 현지시각 간단 포맷
                if not local_time_str and eff:
                    try:
                        tz_offset = notam_filter.get_timezone(ac)  # "+09:00"
                        sign = 1 if tz_offset.startswith('+') else -1
                        hh = int(tz_offset[1:3]); mm = int(tz_offset[4:6])
                        delta = timedelta(hours=sign*hh, minutes=sign*mm)
                        eff_dt_utc = datetime.fromisoformat(eff.replace('Z', '+00:00'))
                        exp_dt_utc = datetime.fromisoformat(exp.replace('Z', '+00:00')) if exp and exp not in ('UFN','PERM') else None
                        eff_local = eff_dt_utc + delta
                        exp_local = (exp_dt_utc + delta) if exp_dt_utc else None
                        def fmt(dt):
                            return dt.strftime('%y/%m/%d %H:%M')
                        if exp_local:
                            local_time_str = f"유효시간 {fmt(eff_local)} - {fmt(exp_local)} ({tz_offset})"
                        else:
                            local_time_str = f"유효시간 {fmt(eff_local)} - UFN ({tz_offset})"
                    except Exception:
                        # 타임존 실패 시 UTC 그대로라도 표시
                        try:
                            if exp and exp not in ('UFN','PERM'):
                                local_time_str = f"유효시간 {eff} - {exp} (UTC)"
                            else:
                                local_time_str = f"유효시간 {eff} - UFN (UTC)"
                        except Exception:
                            pass
                hhmm_window = None
                try:
                    _desc = (n.get('description') or '') + ' ' + (n.get('text') or '')
                    import re as _re
                    _m = _re.search(r'\b(\d{3,4})\s*[-/]\s*(\d{3,4})\b', _desc)
                    if _m:
                        hhmm_window = f"{_m.group(1).zfill(4)}-{_m.group(2).zfill(4)}"
                except Exception:
                    pass
                result.append({
                    'id': n.get('id') or n.get('notam_id') or n.get('number') or '',
                    'airport_code': n.get('airport_code') or icao,
                    'text': n.get('text') or '',
                    'description': n.get('description') or '',
                    'effective_time': n.get('effective_time'),
                    'expiry_time': n.get('expiry_time'),
                    'local_time_display': local_time_str,
                    'local_ranges': local_ranges,
                    'daily_window_hhmm': hhmm_window,
                })
            return jsonify({
                'notams': result,
                'source': LAST_NOTAMS_SOURCE or 'cache',
                'filtered_count': len(result),
                'debug': {
                    'icao': icao,
                    'airport_for_local': airport_for_local,
                    'from_local': from_local,
                    'to_local': to_local,
                    'from': from_iso,
                    'to': to_iso
                }
            })

        # 2) 캐시가 없으면 기존 폴백: temp 최신 txt 재파싱
        # 최신 split txt 찾기 (파일 수정 시간 기준)
        temp_folder = app.config.get('TEMP_FOLDER', 'temp')
        if not os.path.exists(temp_folder):
            return jsonify({'notams': [], 'source': None})
        txt_files = [f for f in os.listdir(temp_folder) if f.endswith('_split.txt')]
        if not txt_files:
            return jsonify({'notams': [], 'source': None})
        
        # 파일 수정 시간 기준으로 최신 파일 선택
        latest_file = None
        latest_file_mtime = 0
        for f in txt_files:
            file_path = os.path.join(temp_folder, f)
            try:
                mtime = os.path.getmtime(file_path)
                if mtime > latest_file_mtime:
                    latest_file_mtime = mtime
                    latest_file = f
            except Exception:
                pass
        
        # 파일명 기준 폴백 (타임스탬프 형식인 경우)
        if not latest_file:
            latest_file = max(txt_files)
        
        txt_path = os.path.join(temp_folder, latest_file)
        with open(txt_path, 'r', encoding='utf-8') as f:
            notam_text = f.read()
        # 전체 NOTAM 파싱
        all_notams = notam_filter.filter_korean_air_notams(notam_text) or []
        # 공항별 필터
        analyzer = AirportNotamAnalyzer()
        airport_notams = analyzer._filter_airport_notams(icao, all_notams)
        # CLSD/폐쇄 계열만 선별
        airport_notams = [n for n in airport_notams if _is_closed_notam(n)]
        # 시간 필터
        from_iso = request.args.get('from')
        to_iso = request.args.get('to')
        from_local = request.args.get('from_local')
        to_local = request.args.get('to_local')
        airport_for_local = icao
        from_dt = None
        to_dt = None
        def parse_iso(value):
            try:
                if not value:
                    return None
                # Z 없으면 그대로, 있으면 python 파싱
                return datetime.fromisoformat(value.replace('Z', '+00:00'))
            except Exception:
                return None
        from_dt = parse_iso(from_iso)
        to_dt = parse_iso(to_iso)
        # 로컬 윈도우 판단 함수 (폴백 경로)
        def in_local_window_fb(n):
            if not from_local and not to_local:
                return True
            try:
                # 사용자 로컬시간 준비 및 오프셋 계산
                def parse_local_dt(s):
                    return datetime.fromisoformat(s.replace(' ', 'T'))
                user_from_local = parse_local_dt(from_local) if from_local else None
                user_to_local = parse_local_dt(to_local) if to_local else None
                tz_offset = notam_filter.get_timezone(airport_for_local)
                sign = 1 if tz_offset.startswith('+') else -1
                hh = int(tz_offset[1:3]); mm = int(tz_offset[4:6])
                delta = timedelta(hours=sign*hh, minutes=sign*mm)
                # 0) 유효기간(현지시각) 1차 필터: 겹치지 않으면 즉시 제외
                try:
                    eff = n.get('effective_time'); exp = n.get('expiry_time')
                    if eff:
                        eff_dt_utc = datetime.fromisoformat(eff.replace('Z', '+00:00'))
                        exp_dt_utc = None
                        if exp and exp not in ('UFN','PERM'):
                            exp_dt_utc = datetime.fromisoformat(exp.replace('Z', '+00:00'))
                        eff_local = eff_dt_utc + delta
                        exp_local = (exp_dt_utc + delta) if exp_dt_utc else None
                        if user_from_local or user_to_local:
                            if user_from_local and exp_local and exp_local < user_from_local:
                                return False
                            if user_to_local and eff_local and eff_local > user_to_local:
                                return False
                except Exception:
                    pass
                # 1) local_time_display 내 HHMM-HHMM 일일 구간 우선 검사
                try:
                    ltd = n.get('local_time_display') or ''
                    import re
                    m = re.search(r'(\d{3,4})\s*[-/]\s*(\d{3,4})', ltd)
                    if m and (from_local or to_local):
                        def to_minutes(hhmm):
                            s = hhmm.zfill(4)
                            return int(s[:2]) * 60 + int(s[2:])
                        d_start = to_minutes(m.group(1)); d_end = to_minutes(m.group(2))
                        uf = user_from_local.time() if user_from_local else None
                        ut = user_to_local.time() if user_to_local else None
                        ufm = (uf.hour*60 + uf.minute) if uf else None
                        utm = (ut.hour*60 + ut.minute) if ut else None
                        def overlap_daily(a1, a2, b1, b2):
                            def expand(s, e):
                                return [(s, e)] if s <= e else [(s, 24*60), (0, e)]
                            A = expand(a1, a2); B = expand(b1, b2)
                            for x1, x2 in A:
                                for y1, y2 in B:
                                    if max(x1, y1) < min(x2, y2):
                                        return True
                            return False
                        if ufm is not None and utm is not None:
                            return overlap_daily(d_start, d_end, ufm, utm)
                        elif ufm is not None:
                            return overlap_daily(d_start, d_end, ufm, ufm+1)
                        else:
                            return overlap_daily(d_start, d_end, utm, utm+1)
                except Exception:
                    pass
                # 2) description/text 내 HHMM-HHMM 보강
                desc = (n.get('description') or '') + ' ' + (n.get('text') or '')
                import re
                m = re.search(r'\b(\d{3,4})\s*[-/]\s*(\d{3,4})\b', desc)
                if m and (from_local or to_local):
                    def to_minutes(hhmm):
                        s = hhmm.zfill(4)
                        return int(s[:2]) * 60 + int(s[2:])
                    d_start = to_minutes(m.group(1))
                    d_end = to_minutes(m.group(2))
                    uf = user_from_local.time() if user_from_local else None
                    ut = user_to_local.time() if user_to_local else None
                    ufm = (uf.hour*60 + uf.minute) if uf else None
                    utm = (ut.hour*60 + ut.minute) if ut else None
                    def overlap_daily(a1, a2, b1, b2):
                        def expand(s, e):
                            return [(s, e)] if s <= e else [(s, 24*60), (0, e)]
                        A = expand(a1, a2)
                        B = expand(b1, b2)
                        for x1, x2 in A:
                            for y1, y2 in B:
                                if max(x1, y1) < min(x2, y2):
                                    return True
                        return False
                    if ufm is not None and utm is not None:
                        return overlap_daily(d_start, d_end, ufm, utm)
                    elif ufm is not None:
                        return overlap_daily(d_start, d_end, ufm, ufm+1)
                    else:
                        return overlap_daily(d_start, d_end, utm, utm+1)
                # 3) 마지막으로 D) 필드 기반 로컬 범위(UTC) 검사
                try:
                    local_time_str, local_ranges = notam_filter._generate_local_time_display(n)
                    if local_ranges:
                        user_from_utc = (user_from_local - delta) if user_from_local else None
                        user_to_utc = (user_to_local - delta) if user_to_local else None
                        def overlaps_range(r):
                            try:
                                r_start = datetime.fromisoformat(r['start_utc'].replace('Z', '+00:00'))
                                r_end = datetime.fromisoformat(r['end_utc'].replace('Z', '+00:00'))
                                if not user_from_utc and not user_to_utc:
                                    return True
                                if user_from_utc and r_end and r_end < user_from_utc:
                                    return False
                                if user_to_utc and r_start and r_start > user_to_utc:
                                    return False
                                return True
                            except Exception:
                                return True
                        return any(overlaps_range(r) for r in local_ranges)
                except Exception:
                    pass
            except Exception:
                pass
            # D) 없으면 유효기간을 현지시각으로 변환 후 비교
            try:
                eff = n.get('effective_time'); exp = n.get('expiry_time')
                if not eff:
                    return True
                eff_dt_utc = datetime.fromisoformat(eff.replace('Z', '+00:00'))
                exp_dt_utc = None
                if exp and exp not in ('UFN','PERM'):
                    exp_dt_utc = datetime.fromisoformat(exp.replace('Z', '+00:00'))
                tz_offset = notam_filter.get_timezone(airport_for_local)
                sign = 1 if tz_offset.startswith('+') else -1
                hh = int(tz_offset[1:3]); mm = int(tz_offset[4:6])
                delta = timedelta(hours=sign*hh, minutes=sign*mm)
                eff_local = eff_dt_utc + delta
                exp_local = (exp_dt_utc + delta) if exp_dt_utc else None
                def parse_local_dt2(s):
                    return datetime.fromisoformat(s.replace(' ', 'T')) if s else None
                user_from = parse_local_dt2(from_local)
                user_to = parse_local_dt2(to_local)
                if not user_from and not user_to:
                    return True
                if user_from and exp_local and exp_local < user_from:
                    return False
                if user_to and eff_local and eff_local > user_to:
                    return False
                return True
            except Exception:
                return True
        def overlaps(n):
            # effective_time/expiry_time 사용, 없으면 통과
            eff = n.get('effective_time')
            exp = n.get('expiry_time')
            try:
                eff_dt = datetime.fromisoformat(eff.replace('Z', '+00:00')) if eff else None
            except Exception:
                eff_dt = None
            if exp in ('UFN', 'PERM'):
                exp_dt = None  # 무기한
            else:
                try:
                    exp_dt = datetime.fromisoformat(exp.replace('Z', '+00:00')) if exp else None
                except Exception:
                    exp_dt = None
            # 필터가 없으면 통과
            if not from_dt and not to_dt:
                return True
            # 구간 겹침 판정 (무기한은 넓게 인정)
            start = eff_dt
            end = exp_dt
            if from_dt and end and end < from_dt:
                return False
            if to_dt and start and start > to_dt:
                return False
            return True
        # 로컬 필터 우선, 없으면 UTC 필터
        if from_local or to_local:
            airport_notams = [n for n in airport_notams if in_local_window_fb(n)]
        elif from_dt or to_dt:
            airport_notams = [n for n in airport_notams if overlaps(n)]
        # 최소 필드만 반환
        result = []
        for n in airport_notams:
            # 로컬 시간대 표시 및 일일 윈도우 보강 정보 (단계별 안전 처리)
            eff = n.get('effective_time'); exp = n.get('expiry_time')
            ac = (n.get('airport_code') or icao)
            local_time_str = None
            local_ranges = None
            # 1) 표준 포맷 생성
            try:
                if eff:
                    local_time_str = notam_filter.format_notam_time_with_local(eff, exp, ac, n)
            except Exception:
                pass
            # 2) D) 필드 기반 (반환형 유연)
            try:
                gen = notam_filter._generate_local_time_display(n)
                if isinstance(gen, tuple) and len(gen) == 2:
                    lt, lr = gen
                    local_ranges = lr
                    if not local_time_str and lt:
                        local_time_str = lt
                elif isinstance(gen, str):
                    if not local_time_str and gen:
                        local_time_str = gen
            except Exception:
                pass
            # 3) 폴백
            if not local_time_str and eff:
                try:
                    tz_offset = notam_filter.get_timezone(ac)
                    sign = 1 if tz_offset.startswith('+') else -1
                    hh = int(tz_offset[1:3]); mm = int(tz_offset[4:6])
                    delta = timedelta(hours=sign*hh, minutes=sign*mm)
                    eff_dt_utc = datetime.fromisoformat(eff.replace('Z', '+00:00'))
                    exp_dt_utc = datetime.fromisoformat(exp.replace('Z', '+00:00')) if exp and exp not in ('UFN','PERM') else None
                    eff_local = eff_dt_utc + delta
                    exp_local = (exp_dt_utc + delta) if exp_dt_utc else None
                    def fmt(dt):
                        return dt.strftime('%y/%m/%d %H:%M')
                    if exp_local:
                        local_time_str = f"유효시간 {fmt(eff_local)} - {fmt(exp_local)} ({tz_offset})"
                    else:
                        local_time_str = f"유효시간 {fmt(eff_local)} - UFN ({tz_offset})"
                except Exception:
                    # 타임존 실패 시 UTC 그대로라도 표시
                    try:
                        if exp and exp not in ('UFN','PERM'):
                            local_time_str = f"유효시간 {eff} - {exp} (UTC)"
                        else:
                            local_time_str = f"유효시간 {eff} - UFN (UTC)"
                    except Exception:
                        pass
            hhmm_window = None
            try:
                _desc = (n.get('description') or '') + ' ' + (n.get('text') or '')
                import re as _re
                _m = _re.search(r'\b(\d{3,4})\s*[-/]\s*(\d{3,4})\b', _desc)
                if _m:
                    hhmm_window = f"{_m.group(1).zfill(4)}-{_m.group(2).zfill(4)}"
            except Exception:
                pass
            result.append({
                'id': n.get('id') or n.get('notam_id') or n.get('number') or '',
                'airport_code': n.get('airport_code') or icao,
                'text': n.get('text') or '',
                'description': n.get('description') or '',
                'effective_time': n.get('effective_time'),
                'expiry_time': n.get('expiry_time'),
                'local_time_display': local_time_str,
                'local_ranges': local_ranges,
                'daily_window_hhmm': hhmm_window,
            })
        return jsonify({
            'notams': result,
            'source': latest_file,
            'filtered_count': len(result),
            'debug': {
                'icao': icao,
                'airport_for_local': airport_for_local,
                'from_local': from_local,
                'to_local': to_local,
                'from': from_iso,
                'to': to_iso
            }
        })
    except Exception as e:
        logger.error(f"/api/airport-notams 오류: {e}")
        return jsonify({'error': f'공항 NOTAM 조회 중 오류: {str(e)}'}), 500

@app.route('/geojson/<path:filename>')
def serve_geojson(filename):
    """repo의 geojson 폴더에서 GeoJSON 파일 제공"""
    base_dir = os.path.join(os.path.dirname(__file__), 'geojson')
    # 경로 역참조 방지
    safe_dir = os.path.abspath(base_dir)
    safe_path = os.path.abspath(os.path.join(base_dir, filename))
    if not safe_path.startswith(safe_dir):
        return jsonify({'error': 'Invalid path'}), 400
    if not os.path.exists(safe_path):
        return jsonify({'error': 'File not found'}), 404
    return send_from_directory(safe_dir, filename, mimetype='application/geo+json')

@app.route('/api/airports')
def get_airports():
    """공항 목록을 JSON으로 반환 (airports.csv 기반)"""
    try:
        import csv
        csv_path = os.path.join(os.path.dirname(__file__), 'src', 'airports.csv')
        
        airports = {}
        with open(csv_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            header = next(reader)  # 헤더 읽기
            
            # 헤더 인덱스 찾기
            try:
                ident_idx = header.index('ident')
                lat_idx = header.index('latitude_deg')
                lng_idx = header.index('longitude_deg')
                # iata_code가 헤더에 있으면 인덱스 가져오기, 없으면 -1
                iata_idx = header.index('iata_code') if 'iata_code' in header else -1
            except ValueError as e:
                logger.error(f"CSV 헤더 형식 오류: {e}, 헤더: {header}")
                return jsonify({'error': f'CSV 헤더 형식 오류: {e}'}), 500
            
            for row_num, row in enumerate(reader, start=2):
                if len(row) < 3:
                    continue
                    
                try:
                    ident = row[ident_idx].strip().upper() if ident_idx < len(row) else ''
                    if not ident:
                        continue
                    
                    # IATA 코드 추출
                    iata = None
                    
                    if iata_idx >= 0 and iata_idx < len(row):
                        # 케이스 1: 헤더에 iata_code 컬럼이 있는 경우
                        iata_raw = row[iata_idx].strip() if row[iata_idx] else ''
                        iata = iata_raw.upper() if iata_raw and iata_raw.lower() not in ['null', '', 'none'] else None
                        lat = float(row[lat_idx])
                        lng = float(row[lng_idx])
                    elif len(row) == 4:
                        # 케이스 2: 헤더는 3개지만 데이터에 4개 필드가 있는 경우
                        # ident, iata_code, lat, lng 순서로 가정
                        potential_iata = row[1].strip() if len(row) > 1 else ''
                        # 3자리 알파벳이면 IATA 코드로 간주
                        if potential_iata and len(potential_iata) == 3 and potential_iata.isalpha() and not potential_iata[0].isdigit():
                            iata = potential_iata.upper()
                            lat = float(row[2]) if len(row) > 2 else float(row[lat_idx])
                            lng = float(row[3]) if len(row) > 3 else float(row[lng_idx])
                        else:
                            lat = float(row[lat_idx])
                            lng = float(row[lng_idx])
                    else:
                        # 케이스 3: 헤더 구조대로 파싱
                        lat = float(row[lat_idx])
                        lng = float(row[lng_idx])
                    
                    # ICAO 코드로 추가
                    airports[ident] = {
                        'lat': lat,
                        'lng': lng,
                        'name': ident,
                        'iata': iata,
                        'iata_code': iata  # results.html에서 사용하는 필드명
                    }
                    
                    # IATA 코드로도 추가 (있을 경우)
                    if iata:
                        airports[iata] = {
                            'lat': lat,
                            'lng': lng,
                            'name': f"{ident} ({iata})",
                            'iata': iata
                        }
                        
                except (ValueError, IndexError) as e:
                    logger.warning(f"공항 데이터 파싱 오류 (라인 {row_num}): {row}, {e}")
                    continue
        
        logger.debug(f"공항 로드: {len(airports)}개")
        return jsonify(airports)
    except Exception as e:
        logger.error(f"공항 목록 로드 중 오류: {str(e)}")
        return jsonify({'error': f'공항 목록을 불러올 수 없습니다: {str(e)}'}), 500

@app.route('/geojson')
def list_geojson_files():
    """repo의 geojson 폴더 내 .geojson 파일 목록 반환"""
    base_dir = os.path.join(os.path.dirname(__file__), 'geojson')
    safe_dir = os.path.abspath(base_dir)
    if not os.path.exists(safe_dir):
        return jsonify({'files': []})
    try:
        files = [f for f in os.listdir(safe_dir) if f.lower().endswith('.geojson')]
        files.sort()
        return jsonify({'files': files})
    except Exception as e:
        logger.error(f"geojson 파일 목록 조회 실패: {e}")
        return jsonify({'files': []})

def cleanup_old_saved_results(keep_count=2):
    """saved_results 디렉토리에서 최근 파일만 유지하고 나머지 삭제 (용량 절감: 5개 → 2개)"""
    try:
        save_dir = os.path.join(os.path.dirname(__file__), 'saved_results')
        if not os.path.exists(save_dir):
            return
        
        # HTML 파일 목록 가져오기
        html_files = [f for f in os.listdir(save_dir) if f.lower().endswith('.html')]
        
        if len(html_files) <= keep_count:
            return
        
        # 파일 경로와 수정 시간을 튜플로 저장
        file_times = []
        for filename in html_files:
            file_path = os.path.join(save_dir, filename)
            mtime = os.path.getmtime(file_path)
            file_times.append((file_path, mtime))
        
        # 수정 시간 기준으로 정렬 (최신이 마지막)
        file_times.sort(key=lambda x: x[1])
        
        # 오래된 파일들 삭제 (최근 keep_count개 제외)
        files_to_delete = file_times[:-keep_count]
        for file_path, _ in files_to_delete:
            try:
                os.remove(file_path)
                logger.debug(f"오래된 파일 삭제: {os.path.basename(file_path)}")
            except Exception as e:
                logger.warning(f"파일 삭제 실패 {os.path.basename(file_path)}: {str(e)}")
                
    except Exception as e:
        logger.error(f"saved_results 정리 중 오류: {str(e)}")

@app.route('/save_html', methods=['POST'])
def save_html():
    """현재 페이지를 그대로 HTML 파일로 저장"""
    try:
        # 현재 페이지의 HTML을 그대로 가져오기
        from flask import request
        
        # 클라이언트에서 현재 페이지의 HTML을 전송받음
        html_content = request.get_json().get('html_content', '')
        
        if not html_content:
            return jsonify({'error': 'HTML 내용이 없습니다.'}), 400
        
        # HTML 파일명 생성
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'NOTAM_Results_{timestamp}.html'
        
        # 저장할 디렉토리 생성
        save_dir = os.path.join(os.path.dirname(__file__), 'saved_results')
        os.makedirs(save_dir, exist_ok=True)
        
        # HTML 파일 경로
        file_path = os.path.join(save_dir, filename)
        
        # 외부 리소스를 로컬로 변환
        processed_html = process_html_for_offline(html_content)
        
        # 파일 저장
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(processed_html)
        
        logger.debug(f"HTML 저장: {filename}")
        
        # 오래된 파일 정리 (최근 2개만 유지 - 용량 절감)
        cleanup_old_saved_results(keep_count=2)
        
        return jsonify({
            'success': True,
            'filename': filename,
            'message': f'HTML 파일이 저장되었습니다: {filename}'
        })
        
    except Exception as e:
        logger.error(f"HTML 저장 중 오류: {str(e)}")
        return jsonify({'error': f'HTML 저장 중 오류가 발생했습니다: {str(e)}'}), 500

def process_html_for_offline(html_content):
    """HTML을 오프라인에서 볼 수 있도록 처리"""
    
    # Bootstrap CSS를 로컬로 다운로드하거나 인라인으로 포함
    bootstrap_css = """
    <style>
        /* Bootstrap 5.3.3 CSS (간소화된 버전) */
        *,*::before,*::after{box-sizing:border-box}
        :root{--bs-font-sans-serif:'Noto Sans KR',-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,"Noto Sans",sans-serif,"Apple Color Emoji","Segoe UI Emoji","Segoe UI Symbol","Noto Color Emoji"}
        body{margin:0;font-size:1rem;font-weight:400;line-height:1.5;color:#212529;background-color:#fff;-webkit-text-size-adjust:100%;-webkit-tap-highlight-color:transparent}
        .container{width:100%;padding-right:var(--bs-gutter-x,.75rem);padding-left:var(--bs-gutter-x,.75rem);margin-right:auto;margin-left:auto}
        .row{--bs-gutter-x:1.5rem;--bs-gutter-y:0;display:flex;flex-wrap:wrap;margin-top:calc(-1 * var(--bs-gutter-y));margin-right:calc(-.5 * var(--bs-gutter-x));margin-left:calc(-.5 * var(--bs-gutter-x))}
        .col{flex:1 0 0%}
        .col-md-12{flex:0 0 auto;width:100%}
        .btn{display:inline-block;font-weight:400;line-height:1.5;color:#212529;text-align:center;text-decoration:none;vertical-align:middle;cursor:pointer;-webkit-user-select:none;-moz-user-select:none;user-select:none;background-color:transparent;border:1px solid transparent;padding:.375rem .75rem;font-size:1rem;border-radius:.375rem;transition:color .15s ease-in-out,background-color .15s ease-in-out,border-color .15s ease-in-out,box-shadow .15s ease-in-out}
        .btn-primary{color:#fff;background-color:#0d6efd;border-color:#0d6efd}
        .btn-success{color:#fff;background-color:#198754;border-color:#198754}
        .btn-info{color:#000;background-color:#0dcaf0;border-color:#0dcaf0}
        .card{position:relative;display:flex;flex-direction:column;min-width:0;word-wrap:break-word;background-color:#fff;background-clip:border-box;border:1px solid rgba(0,0,0,.125);border-radius:.375rem}
        .card-header{padding:.5rem 1rem;margin-bottom:0;background-color:rgba(0,0,0,.03);border-bottom:1px solid rgba(0,0,0,.125)}
        .card-body{flex:1 1 auto;padding:1rem 1rem}
        .table{width:100%;margin-bottom:1rem;color:#212529;vertical-align:top;border-color:#dee2e6}
        .table>tbody{vertical-align:inherit}
        .table>thead{vertical-align:bottom}
        .table>:not(caption)>*>*{padding:.5rem .5rem;background-color:var(--bs-table-bg);border-bottom-width:1px}
        .badge{display:inline-block;padding:.35em .65em;font-size:.75em;font-weight:700;line-height:1;color:#fff;text-align:center;white-space:nowrap;vertical-align:baseline;border-radius:.375rem}
        .bg-info{background-color:#0dcaf0!important}
        .bg-success{background-color:#198754!important}
        .bg-warning{background-color:#ffc107!important}
        .bg-danger{background-color:#dc3545!important}
        .text-muted{color:#6c757d!important}
        .d-flex{display:flex!important}
        .justify-content-between{justify-content:space-between!important}
        .align-items-center{align-items:center!important}
        .mb-4{margin-bottom:1.5rem!important}
        .gap-2{gap:.5rem!important}
        .me-2{margin-right:.5rem!important}
        .fas{font-family:"Font Awesome 6 Free";font-weight:900}
        .fa-download:before{content:"\\f019"}
        .fa-spinner:before{content:"\\f110"}
        .fa-spin{animation:fa-spin 2s infinite linear}
        @keyframes fa-spin{0%{transform:rotate(0deg)}100%{transform:rotate(360deg)}}
        .alert{padding:.75rem 1.25rem;margin-bottom:1rem;border:1px solid transparent;border-radius:.375rem}
        .alert-success{color:#0f5132;background-color:#d1e7dd;border-color:#badbcc}
        .alert-danger{color:#842029;background-color:#f8d7da;border-color:#f5c2c7}
        .alert-dismissible{padding-right:4rem}
        .btn-close{padding:.25em .25em;margin:.25rem -.25rem -.25rem auto;background:transparent;border:0;border-radius:.375rem;opacity:.5}
        .btn-close:hover{color:#000;text-decoration:none;opacity:.75}
        .btn-close:focus{outline:0;box-shadow:0 0 0 .25rem rgba(13,110,253,.25);opacity:1}
        .btn-close:disabled{pointer-events:none;-webkit-user-select:none;-moz-user-select:none;user-select:none;opacity:.25}
        .btn-close::before{content:"\\00d7"}
        .fade{transition:opacity .15s linear}
        .show{opacity:1}
        .table-responsive{overflow-x:auto;-webkit-overflow-scrolling:touch}
        .border-primary{border-color:#0d6efd!important}
        .bg-primary{background-color:#0d6efd!important}
        .text-white{color:#fff!important}
        .form-check{display:block;min-height:1.5rem;padding-left:1.5em}
        .form-check-input{width:1em;height:1em;margin-top:.25em;vertical-align:top;background-color:#fff;background-repeat:no-repeat;background-position:center;background-size:contain;border:1px solid rgba(0,0,0,.25);-webkit-appearance:none;-moz-appearance:none;appearance:none}
        .form-check-input:checked{background-color:#0d6efd;border-color:#0d6efd}
        .form-check-input[type=checkbox]{border-radius:.25em}
        .form-check-inline{display:inline-block;margin-right:1rem}
        .flex-wrap{flex-wrap:wrap!important}
        .translation-text{white-space:normal;font-size:.95rem;line-height:1.6;text-align:left;word-wrap:break-word;padding:10px;background-color:#f8f9fa;border-radius:.25rem;margin:.5rem 0}
        .notam-text{font-family:'Courier New',monospace;background-color:#f8f9fa;padding:.5rem;border-radius:.25rem;margin:.5rem 0}
        .airport-badges{margin:.5rem 0}
        .airport-badges .badge{margin-right:.25rem;margin-bottom:.25rem}
        .time-info{font-size:.875rem;color:#6c757d}
        .notam-item{border-bottom:1px solid #dee2e6;padding:1rem 0}
        .notam-item:last-child{border-bottom:none}
        .small{font-size:.875em}
        .text-center{text-align:center!important}
        .fw-bold{font-weight:700!important}
        .mb-0{margin-bottom:0!important}
        .mb-1{margin-bottom:.25rem!important}
        .mb-2{margin-bottom:.5rem!important}
        .mb-3{margin-bottom:1rem!important}
        .mt-3{margin-top:1rem!important}
        .p-2{padding:.5rem!important}
        .px-2{padding-right:.5rem!important;padding-left:.5rem!important}
        .py-1{padding-top:.25rem!important;padding-bottom:.25rem!important}
        .border{border:1px solid #dee2e6!important}
        .border-top{border-top:1px solid #dee2e6!important}
        .border-bottom{border-bottom:1px solid #dee2e6!important}
        .rounded{border-radius:.375rem!important}
        .shadow{box-shadow:0 .5rem 1rem rgba(0,0,0,.15)!important}
        .w-100{width:100%!important}
        .h-100{height:100%!important}
        .position-relative{position:relative!important}
        .position-absolute{position:absolute!important}
        .position-fixed{position:fixed!important}
        .top-0{top:0!important}
        .end-0{right:0!important}
        .start-0{left:0!important}
        .translate-middle{transform:translate(-50%,-50%)!important}
        .z-3{z-index:3!important}
        .overflow-hidden{overflow:hidden!important}
        .opacity-75{opacity:.75!important}
        .opacity-50{opacity:.5!important}
        .opacity-25{opacity:.25!important}
        .opacity-0{opacity:0!important}
        .visually-hidden{position:absolute!important;width:1px!important;height:1px!important;padding:0!important;margin:-1px!important;overflow:hidden!important;clip:rect(0,0,0,0)!important;white-space:nowrap!important;border:0!important}
        .stretched-link::after{position:absolute;top:0;right:0;bottom:0;left:0;z-index:1;content:""}
        .text-truncate{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
        .align-baseline{vertical-align:baseline!important}
        .align-top{vertical-align:top!important}
        .align-middle{vertical-align:middle!important}
        .align-bottom{vertical-align:bottom!important}
        .align-text-bottom{vertical-align:text-bottom!important}
        .align-text-top{vertical-align:text-top!important}
        .float-start{float:left!important}
        .float-end{float:right!important}
        .float-none{float:none!important}
        .user-select-all{-webkit-user-select:all!important;-moz-user-select:all!important;user-select:all!important}
        .user-select-auto{-webkit-user-select:auto!important;-moz-user-select:auto!important;user-select:auto!important}
        .user-select-none{-webkit-user-select:none!important;-moz-user-select:none!important;user-select:none!important}
        .pe-none{pointer-events:none!important}
        .pe-auto{pointer-events:auto!important}
        .rounded-circle{border-radius:50%!important}
        .rounded-pill{border-radius:50rem!important}
        .rounded-0{border-radius:0!important}
        .rounded-1{border-radius:.2rem!important}
        .rounded-2{border-radius:.375rem!important}
        .rounded-3{border-radius:.5rem!important}
        .visible{visibility:visible!important}
        .invisible{visibility:hidden!important}
        @media (max-width:768px){
            .container{padding:0 10px}
            .table{font-size:.875rem}
            .card-body{padding:.75rem}
            .btn{padding:.25rem .5rem;font-size:.875rem}
        }
    </style>
    """
    
    # Font Awesome 아이콘을 위한 CSS 추가
    fontawesome_css = """
    <style>
        @font-face{font-family:"Font Awesome 6 Free";font-style:normal;font-weight:400;font-display:block;src:url("data:font/woff2;base64,") format("woff2")}
        .fas{font-family:"Font Awesome 6 Free";font-weight:900}
        .fa-download:before{content:"\\f019"}
        .fa-spinner:before{content:"\\f110"}
        .fa-map-marked-alt:before{content:"\\f5fa"}
        .fa-spin{animation:fa-spin 2s infinite linear}
        @keyframes fa-spin{0%{transform:rotate(0deg)}100%{transform:rotate(360deg)}}
    </style>
    """
    
    # 외부 링크를 제거하고 로컬 스타일로 대체
    processed_html = html_content
    
    # Bootstrap CDN 링크 제거
    processed_html = processed_html.replace(
        '<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">',
        bootstrap_css
    )
    
    # Font Awesome CDN 링크 제거
    processed_html = processed_html.replace(
        '<link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">',
        fontawesome_css
    )
    
    # Bootstrap JS CDN 링크 제거 (기본 기능만 유지)
    processed_html = processed_html.replace(
        '<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>',
        '<script>/* Bootstrap JS functionality removed for offline use */</script>'
    )
    
    # HTML 저장 버튼 비활성화 (오프라인에서는 불필요)
    processed_html = processed_html.replace(
        'onclick="saveAsHTML(this)"',
        'onclick="alert(\'오프라인 모드에서는 사용할 수 없습니다.\')"'
    )
    
    # 원본 HTML의 body 스타일에 font-family가 있으면 보존하도록 보장
    # </style> 태그 뒤에 원본 body 스타일을 강제로 추가하여 우선순위 보장
    if '<style>' in processed_html and 'font-family' in processed_html:
        # 원본 body 스타일이 있으면 보존되도록 추가 스타일 삽입
        font_preservation_style = """
    <style>
        /* 원본 글꼴 스타일 보존 */
        body {
            font-family: 'Noto Sans KR', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans", sans-serif !important;
        }
        * {
            font-family: inherit;
        }
    </style>
    """
        # </head> 태그 앞에 추가하여 원본 스타일보다 나중에 로드되도록 함
        if '</head>' in processed_html:
            processed_html = processed_html.replace('</head>', font_preservation_style + '</head>', 1)
    
    return processed_html

@app.route('/download_html/<filename>')
def download_html(filename):
    """저장된 HTML 파일 다운로드"""
    try:
        save_dir = os.path.join(os.path.dirname(__file__), 'saved_results')
        file_path = os.path.join(save_dir, filename)
        
        if not os.path.exists(file_path):
            return jsonify({'error': '파일을 찾을 수 없습니다.'}), 404
        
        return send_file(file_path, as_attachment=True, download_name=filename)
        
    except Exception as e:
        logger.error(f"HTML 다운로드 중 오류: {str(e)}")
        return jsonify({'error': f'HTML 다운로드 중 오류가 발생했습니다: {str(e)}'}), 500


# 마지막 health check는 유지 (앱 종료 전에 필요)

if __name__ == '__main__':
    # PID 파일 경로
    PID_FILE = '.smartbrief.pid'
    
    # 종료 시 정리 함수
    def cleanup():
        print('\n🛑 애플리케이션을 종료합니다...')
        # PID 파일 삭제
        if os.path.exists(PID_FILE):
            try:
                os.remove(PID_FILE)
            except:
                pass
    
    # atexit로 정리 함수 등록 (정상 종료 시)
    atexit.register(cleanup)
    
    # 시그널 핸들러 설정 (Flask의 종료를 방해하지 않도록 KeyboardInterrupt 재발생)
    def signal_handler(sig, frame):
        """시그널 핸들러: KeyboardInterrupt를 재발생시켜 Flask가 처리하도록 함"""
        print('\n\n🛑 종료 신호를 받았습니다...')
        # KeyboardInterrupt를 재발생시켜 Flask의 기본 처리 메커니즘이 작동하도록 함
        raise KeyboardInterrupt
    
    # SIGINT (Ctrl+C)와 SIGTERM 시그널 핸들러 등록
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # PID 파일에 현재 프로세스 ID 저장
    try:
        with open(PID_FILE, 'w') as f:
            f.write(str(os.getpid()))
        print(f"📝 프로세스 ID가 저장되었습니다: {os.getpid()}")
        print(f"💡 종료하려면: ./stop_app.sh 또는 Ctrl+C (여러 번 눌러보세요)")
    except Exception as e:
        logger.warning(f"PID 파일 저장 실패: {e}")
    
    # Cloud Run에서는 PORT 환경변수를 사용, 로컬에서는 5005 사용
    port = int(os.environ.get('PORT', 5005))
    
    # 환경 변수로 개발/프로덕션 구분
    environment = os.environ.get('FLASK_ENV', os.environ.get('ENVIRONMENT', 'development'))
    is_production = environment.lower() == 'production'
    
    # Werkzeug의 개발 서버 경고 메시지 억제 (상업적 사용을 위해)
    import warnings
    import logging
    
    # Flask/Werkzeug 경고 메시지 억제를 위한 환경 변수 설정
    # use_reloader=False일 때는 WERKZEUG_RUN_MAIN을 설정하지 않음
    # (설정하면 is_running_from_reloader()가 True를 반환하여 WERKZEUG_SERVER_FD를 확인함)
    # use_reloader=True일 때만 설정하여 중복 메시지 방지
    # 주석: use_reloader=False이므로 WERKZEUG_RUN_MAIN을 설정하지 않음
    
    # WERKZEUG_SERVER_FD 환경 변수 처리 (MacBook 등에서 이전 세션의 유효하지 않은 값 제거)
    # 이 환경 변수는 Flask reloader가 사용하는데, 유효하지 않으면 KeyError 발생
    # use_reloader=False를 사용하므로 이 환경 변수는 필요 없음
    if 'WERKZEUG_SERVER_FD' in os.environ:
        try:
            # 유효한 파일 디스크립터인지 확인
            fd = int(os.environ['WERKZEUG_SERVER_FD'])
            # 파일 디스크립터가 유효한지 확인 (0 이상이어야 함)
            if fd < 0:
                del os.environ['WERKZEUG_SERVER_FD']
            else:
                # 파일 디스크립터가 실제로 열려있는지 확인
                import fcntl
                try:
                    fcntl.fcntl(fd, fcntl.F_GETFD)
                except (OSError, ValueError):
                    # 파일 디스크립터가 유효하지 않으면 삭제
                    del os.environ['WERKZEUG_SERVER_FD']
        except (ValueError, OSError, ImportError, NameError):
            # 유효하지 않은 값이거나 fcntl을 사용할 수 없으면 삭제
            # (Windows나 일부 환경에서는 fcntl이 없을 수 있음)
            if 'WERKZEUG_SERVER_FD' in os.environ:
                del os.environ['WERKZEUG_SERVER_FD']
    
    # Werkzeug의 run_simple과 ThreadedWSGIServer가 WERKZEUG_SERVER_FD를 안전하게 처리하도록 패치
    # use_reloader=False일 때는 WERKZEUG_SERVER_FD가 필요 없으므로 제거
    try:
        import werkzeug.serving
        
        # run_simple 함수 패치: use_reloader=False일 때 WERKZEUG_SERVER_FD 제거 및 안전 처리
        original_run_simple = werkzeug.serving.run_simple
        
        def patched_run_simple(*args, **kwargs):
            # use_reloader가 False일 때는 WERKZEUG_SERVER_FD가 필요 없음
            use_reloader = kwargs.get('use_reloader', True)
            
            if not use_reloader:
                # use_reloader=False일 때는 WERKZEUG_SERVER_FD를 제거
                # WERKZEUG_RUN_MAIN을 설정하지 않았으므로 is_running_from_reloader()가 False를 반환
                # 따라서 Werkzeug가 WERKZEUG_SERVER_FD를 확인하지 않음
                had_werkzeug_fd = 'WERKZEUG_SERVER_FD' in os.environ
                
                if had_werkzeug_fd:
                    # 기존 값 제거 (use_reloader=False이므로 불필요)
                    del os.environ['WERKZEUG_SERVER_FD']
                
                # WERKZEUG_RUN_MAIN도 제거하여 is_running_from_reloader()가 False를 반환하도록 함
                had_run_main = 'WERKZEUG_RUN_MAIN' in os.environ
                if had_run_main:
                    del os.environ['WERKZEUG_RUN_MAIN']
                
                try:
                    result = original_run_simple(*args, **kwargs)
                finally:
                    # 정리 (복원하지 않음, use_reloader=False이므로 불필요)
                    pass
                
                return result
            else:
                # use_reloader=True일 때는 WERKZEUG_RUN_MAIN을 설정하여 중복 메시지 방지
                if 'WERKZEUG_RUN_MAIN' not in os.environ:
                    os.environ['WERKZEUG_RUN_MAIN'] = 'true'
                return original_run_simple(*args, **kwargs)
        
        werkzeug.serving.run_simple = patched_run_simple
        
        # ThreadedWSGIServer의 원본 __init__ 메서드 저장
        original_threaded_init = werkzeug.serving.ThreadedWSGIServer.__init__
        
        def patched_threaded_init(self, host, port, app, *args, **kwargs):
            # WERKZEUG_SERVER_FD가 있지만 유효하지 않은 경우 제거
            if 'WERKZEUG_SERVER_FD' in os.environ:
                try:
                    fd = int(os.environ['WERKZEUG_SERVER_FD'])
                    # 유효한 파일 디스크립터인지 확인 (0 이상이어야 함)
                    if fd < 0:
                        del os.environ['WERKZEUG_SERVER_FD']
                    else:
                        # Unix/Linux에서만 fcntl 사용 가능
                        try:
                            import fcntl
                            fcntl.fcntl(fd, fcntl.F_GETFD)
                        except (OSError, ValueError, ImportError):
                            # 파일 디스크립터가 유효하지 않거나 fcntl을 사용할 수 없음
                            # (Windows에서는 fcntl이 없을 수 있음)
                            del os.environ['WERKZEUG_SERVER_FD']
                except (ValueError, OSError):
                    # 변환 실패 또는 유효하지 않은 값
                    if 'WERKZEUG_SERVER_FD' in os.environ:
                        del os.environ['WERKZEUG_SERVER_FD']
            
            # 원본 __init__ 호출
            # 이제 WERKZEUG_SERVER_FD가 없거나 유효한 값만 있으므로 안전함
            return original_threaded_init(self, host, port, app, *args, **kwargs)
        
        werkzeug.serving.ThreadedWSGIServer.__init__ = patched_threaded_init
    except (ImportError, AttributeError, Exception):
        # Werkzeug 패치 실패 시 무시 (다른 방법으로 처리)
        pass
    
    # Werkzeug 로거의 경고 레벨 조정
    werkzeug_logger = logging.getLogger('werkzeug')
    werkzeug_logger.setLevel(logging.ERROR)  # WARNING 이상만 표시하지 않도록
    
    # Flask CLI 로거도 조정
    flask_logger = logging.getLogger('flask')
    flask_logger.setLevel(logging.ERROR)
    
    # Python warnings 억제
    warnings.filterwarnings('ignore', category=UserWarning, module='werkzeug')
    warnings.filterwarnings('ignore', message='.*development server.*')
    warnings.filterwarnings('ignore', message='.*Do not use.*production.*')
    
    # 로컬 주소 출력
    print("\n" + "="*60)
    print(f"🚀 SmartBrief (Smart Briefing System)이 시작되었습니다!")
    print(f"📍 로컬 주소: http://localhost:{port}")
    print(f"📍 네트워크 주소: http://127.0.0.1:{port}")
    print("="*60)
    print(f"⏹️  종료 방법:")
    print(f"   1. Ctrl+C (기본 방법)")
    print(f"   2. 다른 터미널에서: ./stop_app.sh")
    print(f"   3. 포트 종료: lsof -ti :{port} | xargs kill -9")
    print("="*60 + "\n")
    
    # 크롬 브라우저 자동 열기
    url = f"http://localhost:{port}"
    try:
        if platform.system() == "Darwin":  # macOS
            # macOS에서 크롬을 명시적으로 열기
            subprocess.Popen(['open', '-a', 'Google Chrome', url])
        elif platform.system() == "Windows":  # Windows
            # Windows에서 크롬 경로 찾기
            chrome_paths = [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe")
            ]
            chrome_path = None
            for path in chrome_paths:
                if os.path.exists(path):
                    chrome_path = path
                    break
            
            if chrome_path:
                subprocess.Popen([chrome_path, url])
            else:
                # 크롬을 찾지 못하면 기본 브라우저 열기
                webbrowser.open(url)
        else:  # Linux
            # Linux에서 크롬 열기 시도
            try:
                subprocess.Popen(['google-chrome', url])
            except FileNotFoundError:
                try:
                    subprocess.Popen(['chromium-browser', url])
                except FileNotFoundError:
                    webbrowser.open(url)
        print(f"🌐 크롬 브라우저를 열었습니다: {url}")
    except Exception as e:
        logger.warning(f"브라우저 자동 열기 실패: {e}")
        print(f"⚠️  브라우저를 수동으로 열어주세요: {url}")
    
    # 포트가 이미 사용 중인지 확인하고 처리
    def is_port_in_use(port):
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(('localhost', port)) == 0
    
    # 포트가 사용 중이면 이전 프로세스 종료 시도
    if is_port_in_use(port):
        print(f"⚠️  포트 {port}가 이미 사용 중입니다.")
        try:
            # macOS/Linux에서 포트를 사용하는 프로세스 찾기 및 종료
            if platform.system() in ['Darwin', 'Linux']:
                result = subprocess.run(
                    ['lsof', '-ti', f':{port}'],
                    capture_output=True,
                    text=True
                )
                if result.returncode == 0 and result.stdout.strip():
                    pids = result.stdout.strip().split('\n')
                    for pid in pids:
                        if pid:
                            print(f"🛑 이전 프로세스(PID: {pid})를 종료합니다...")
                            subprocess.run(['kill', '-9', pid], check=False)
                            import time
                            time.sleep(1)  # 프로세스 종료 대기
                    print(f"✅ 포트 {port}를 정리했습니다.")
        except Exception as e:
            print(f"⚠️  이전 프로세스 종료 실패: {e}")
            print(f"💡 다른 포트를 사용하거나 수동으로 프로세스를 종료해주세요.")
    
    try:
        if is_production:
            # 프로덕션에서는 debug=False
            app.run(debug=False, host='0.0.0.0', port=port, use_reloader=False)
        else:
            # 개발 환경에서는 debug=True (개발 편의를 위해 reloader는 비활성화)
            app.run(debug=True, host='0.0.0.0', port=port, use_reloader=False)
    except KeyboardInterrupt:
        # Flask의 기본 KeyboardInterrupt 처리가 작동함
        print('\n\n🛑 Ctrl+C를 눌러 애플리케이션을 종료합니다...')
        cleanup()
        sys.exit(0)
    except OSError as e:
        if 'Address already in use' in str(e) or '포트' in str(e):
            print(f"\n❌ 포트 {port}가 이미 사용 중입니다.")
            print(f"💡 다음 명령어로 포트를 사용하는 프로세스를 확인하고 종료하세요:")
            if platform.system() in ['Darwin', 'Linux']:
                print(f"   lsof -ti :{port} | xargs kill -9")
            else:
                print(f"   netstat -ano | findstr :{port}")
        else:
            print(f"\n❌ 서버 시작 오류: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 예상치 못한 오류가 발생했습니다: {e}")
        sys.exit(1)