import pdfplumber
import re
import os
import time
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
import io

# pdf2image 사용
try:
    from pdf2image import convert_from_path
    from PIL import Image
    import numpy as np
    PDF2IMAGE_AVAILABLE = True
except ImportError:
    PDF2IMAGE_AVAILABLE = False
    Image = None
    np = None

# OpenCV 사용 (정확한 색상 추출용)
try:
    import cv2
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False
    cv2 = None

# Gemini API 사용
try:
    import google.generativeai as genai
    from dotenv import load_dotenv
    load_dotenv()
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    genai = None

def extract_flight_plan_waypoints_from_text(full_text: str) -> List[Dict[str, object]]:
    """
    이미 추출된 전체 텍스트에서 Flight Plan waypoint + 좌표만 추출 (PDF 미개방, 경량).
    업로드 플로우에서 convert_pdf_to_text() 결과로 호출해 중복 PDF 읽기 방지.
    Returns: [ {"Waypoint": str, "lat": float, "lon": float}, ... ]
    """
    if not (full_text and full_text.strip()):
        return []
    lines = full_text.split("\n")
    # OFP 테이블 시작: "DIST LATITUDE" 또는 "DIST. LATITUDE" 등
    start_ok = re.compile(r"DIST\s*\.?\s*LATITUDE", re.IGNORECASE)
    end_marker = "ROUTE TO ALTN"
    in_flight_plan = False
    flight_plan_lines = []
    for line in lines:
        stripped = line.strip()
        if start_ok.search(line) and not in_flight_plan:
            in_flight_plan = True
            continue
        if stripped.startswith(end_marker):
            break
        if in_flight_plan and stripped:
            flight_plan_lines.append(re.sub(r" +", " ", stripped))
    if not flight_plan_lines:
        return []

    def _lat(parts: List[str]) -> Optional[float]:
        for j in range(len(parts) - 1):
            tok = parts[j]
            if re.match(r"^[NS]\d{2}$", tok) and re.match(r"^\d+\.?\d*$", parts[j + 1]):
                try:
                    deg = int(tok[1:])
                    mins = float(parts[j + 1])
                    return round((1 if tok[0] == "N" else -1) * (deg + mins / 60.0), 6)
                except (ValueError, IndexError):
                    pass
        return None

    def _lon(parts: List[str]) -> Optional[float]:
        for j in range(len(parts) - 1):
            tok = parts[j]
            if re.match(r"^[EW]\d{2,3}$", tok) and re.match(r"^\d+\.?\d*$", parts[j + 1]):
                try:
                    deg = int(tok[1:])
                    mins = float(parts[j + 1])
                    return round((1 if tok[0] == "E" else -1) * (deg + mins / 60.0), 6)
                except (ValueError, IndexError):
                    pass
        return None

    invalid_keywords = {"Page", "TO", "TC", "FIR", "/", "---", "CLB", "DSC", "ANCHORAGE", "OCEANIC", "INCHEON", "SENDAI", "NIIGATA", "YECHEON", "POHANG", "FUKUOKA"}
    result = []
    i = 0
    while i < len(flight_plan_lines):
        parts = flight_plan_lines[i].split()
        if not parts or not parts[0].isdigit() or len(parts) <= 7:
            i += 1
            continue
        if i + 1 >= len(flight_plan_lines):
            i += 1
            continue
        next_parts = flight_plan_lines[i + 1].split()
        if not next_parts:
            i += 1
            continue
        wp = next_parts[0]
        if wp in invalid_keywords or len(wp) < 2:
            i += 1
            continue
        if not (re.match(r"^\d{2}N\d{2}", wp) or re.match(r"^[A-Z]+\d+", wp) or (wp.isalpha() and len(wp) >= 2)):
            i += 1
            continue
        lat, lon = _lat(parts), _lon(next_parts)
        if lat is not None and lon is not None:
            result.append({"Waypoint": wp, "lat": lat, "lon": lon})
        i += 2
    return result


def extract_flight_data_from_pdf(pdf_path: str, save_temp: bool = True) -> List[Dict[str, str]]:
    """
    PDF 파일에서 Flight Plan 테이블을 추출하고, 'SR' 및 'ACTM' 데이터를 추출합니다.
    
    Args:
        pdf_path: PDF 파일 경로
        save_temp: True인 경우 temp 폴더에 텍스트 파일로 저장 (기본값: True)
        
    Returns:
        추출된 Flight Plan 데이터 리스트 (Waypoint, SR, ACTM 포함)
    """
    full_text = ""
    
    # pdfplumber를 사용하여 PDF 텍스트 추출
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    full_text += page_text + "\n"
    except Exception as e:
        print(f"PDF 파일을 읽는 중 오류가 발생했습니다: {e}")
        return []

    if not full_text.strip():
        print("PDF에서 텍스트를 추출할 수 없습니다.")
        return []

    # ETD (Estimated Time of Departure) 및 TAXI TIME 추출
    etd_time = None
    taxi_minutes = 20  # 기본값: 20분 (사용자 요구사항)
    departure_airport = None
    arrival_airport = None
    
    # ETD 찾기: "ETD CYVR 2100Z" 형식
    etd_pattern = r'ETD\s+([A-Z]{4})\s+(\d{4})Z'
    etd_match = re.search(etd_pattern, full_text)
    if etd_match:
        departure_airport = etd_match.group(1)
        etd_str = etd_match.group(2)
        try:
            # "2100"을 시간과 분으로 변환
            etd_hour = int(etd_str[:2])
            etd_minute = int(etd_str[2:])
            # 날짜는 오늘 날짜 사용 (시간 계산에만 사용되므로 날짜는 중요하지 않음)
            today = datetime.now()
            etd_time = datetime(today.year, today.month, today.day, etd_hour, etd_minute)
            print(f"ETD 추출: {departure_airport} {etd_str}Z")
        except Exception as e:
            print(f"ETD 시간 파싱 오류: {e}")
    
    # TAXI TIME 찾기: "TAXI 0012" 형식
    taxi_pattern = r'TAXI\s+(\d{4})'
    taxi_match = re.search(taxi_pattern, full_text)
    if taxi_match:
        taxi_time_str = taxi_match.group(1)
        try:
            # "0012"를 분으로 변환 (0012 = 12분)
            # PDF에서 추출한 값을 사용하되, 기본값은 20분
            taxi_hours = int(taxi_time_str[:2])
            taxi_mins = int(taxi_time_str[2:])
            extracted_taxi_minutes = taxi_hours * 60 + taxi_mins
            # 사용자 요구사항에 따라 20분 사용 (필요시 extracted_taxi_minutes 사용 가능)
            taxi_minutes = 20  # 사용자 요구사항: 20분
            print(f"TAXI TIME 추출: {taxi_time_str} (PDF: {extracted_taxi_minutes}분), 사용: {taxi_minutes}분 (요구사항)")
        except Exception as e:
            print(f"TAXI TIME 파싱 오류: {e}")
    
    # 이륙 시간 계산: ETD + TAXI TIME
    takeoff_time = None
    if etd_time:
        takeoff_time = etd_time + timedelta(minutes=taxi_minutes)
        print(f"이륙 시간 계산: {etd_time.strftime('%H%M')}Z + {taxi_minutes}분 = {takeoff_time.strftime('%H%M')}Z")
    
    # ETA (Estimated Time of Arrival) 추출
    eta_str = None
    eta_pattern = r'ETA\s+([A-Z]{4})\s+(\d{4})Z'
    eta_match = re.search(eta_pattern, full_text)
    if eta_match:
        arrival_airport = eta_match.group(1)
        eta_str = eta_match.group(2) + 'Z'
        print(f"ETA 추출: {arrival_airport} {eta_str}")

    # TURB/CB INFO 섹션 추출
    turb_cb_info = []
    if 'TURB/CB INFO' in full_text.upper():
        lines_text = full_text.split('\n')
        in_turb_section = False
        
        for i, line in enumerate(lines_text):
            if 'TURB/CB INFO' in line.upper():
                in_turb_section = True
                turb_cb_info.append(line.strip())
                # 다음 몇 줄도 포함 (빈 줄이나 다음 섹션 시작 전까지)
                for j in range(i + 1, min(i + 10, len(lines_text))):
                    next_line = lines_text[j].strip()
                    if not next_line:
                        # 빈 줄이 2개 연속이면 종료
                        if j + 1 < len(lines_text) and not lines_text[j + 1].strip():
                            break
                        continue
                    # 다음 섹션 시작 (숫자로 시작하는 항목 등)이면 종료
                    if next_line.startswith(('6.', '7.', '8.', '9.', '---', '===')):
                        break
                    # TURB/CB INFO 관련 내용만 추가
                    if any(keyword in next_line.upper() for keyword in ['CAUTION', 'CB', 'TURB', 'SIG WX', 'TURBULENCE', 'CHART']):
                        turb_cb_info.append(next_line)
                    elif len(turb_cb_info) <= 4:  # 처음 몇 줄만 포함
                        turb_cb_info.append(next_line)
                break
        
        if turb_cb_info:
            print(f"TURB/CB INFO 추출: {len(turb_cb_info)}줄")
    
    # WEATHER BRIEFING (TAF) 섹션 추출
    taf_data = {
        'departure': None,  # CYVR
        'arrival': None,    # RKSI
        'alternate': None  # RKSS, RJTT 등
    }
    
    if 'WEATHER BRIEFING' in full_text.upper():
        lines_text = full_text.split('\n')
        in_weather = False
        weather_lines = []
        
        for i, line in enumerate(lines_text):
            if 'WEATHER BRIEFING' in line.upper():
                in_weather = True
                continue
            
            if in_weather:
                # 섹션 종료 조건
                if 'END OF JEPPESEN' in line.upper() or 'ROUTE TO ALTN' in line.upper():
                    break
                if line.strip().startswith('---') and len(line.strip()) > 20:
                    # 다음 섹션 시작 확인
                    if i + 1 < len(lines_text) and ('END OF' in lines_text[i+1].upper() or 'ROUTE TO' in lines_text[i+1].upper()):
                        break
                
                weather_lines.append(line)
                if len(weather_lines) > 100:  # 최대 100줄까지만
                    break
        
        if weather_lines:
            weather_text = '\n'.join(weather_lines)
            
            # DEPARTURE WEATHER 추출
            dep_match = re.search(r'DEPARTURE WEATHER\s*\n(.*?)(?=ARRIVAL WEATHER|ALTERNATE WEATHER|$)', weather_text, re.DOTALL | re.IGNORECASE)
            if dep_match:
                taf_data['departure'] = dep_match.group(1).strip()
            
            # ARRIVAL WEATHER 추출
            arr_match = re.search(r'ARRIVAL WEATHER\s*\n(.*?)(?=ALTERNATE WEATHER|$)', weather_text, re.DOTALL | re.IGNORECASE)
            if arr_match:
                taf_data['arrival'] = arr_match.group(1).strip()
            
            # ALTERNATE WEATHER 추출
            alt_match = re.search(r'ALTERNATE WEATHER\s*\n(.*?)(?=$)', weather_text, re.DOTALL | re.IGNORECASE)
            if alt_match:
                taf_data['alternate'] = alt_match.group(1).strip()
            
            if taf_data['departure'] or taf_data['arrival'] or taf_data['alternate']:
                print(f"TAF 데이터 추출 완료: 출발={taf_data['departure'] is not None}, 도착={taf_data['arrival'] is not None}, 교체={taf_data['alternate'] is not None}")

    # Flight Plan 테이블 영역 찾기
    lines = full_text.split('\n')
    start_marker = "DIST LATITUDE MC FL ETO/MSA R/F OT WIND/COMP SR TAS ZT B/O"

    def _parse_lat_from_parts(parts: List[str]) -> Optional[float]:
        """첫 행에서 위도 추출. 예: N37 42.0 -> 37 + 42.0/60"""
        for j in range(len(parts) - 1):
            tok = parts[j]
            if re.match(r'^[NS]\d{2}$', tok) and re.match(r'^\d+\.?\d*$', parts[j + 1]):
                try:
                    deg = int(tok[1:])
                    mins = float(parts[j + 1])
                    sign = 1 if tok[0] == 'N' else -1
                    return round(sign * (deg + mins / 60.0), 6)
                except (ValueError, IndexError):
                    pass
        return None

    def _parse_lon_from_parts(parts: List[str]) -> Optional[float]:
        """두 번째 행에서 경도 추출. 예: E128 45.2 -> 128 + 45.2/60"""
        for j in range(len(parts) - 1):
            tok = parts[j]
            if re.match(r'^[EW]\d{2,3}$', tok) and re.match(r'^\d+\.?\d*$', parts[j + 1]):
                try:
                    deg = int(tok[1:])
                    mins = float(parts[j + 1])
                    sign = 1 if tok[0] == 'E' else -1
                    return round(sign * (deg + mins / 60.0), 6)
                except (ValueError, IndexError):
                    pass
        return None
    end_marker = "ROUTE TO ALTN"

    in_flight_plan = False
    flight_plan_lines = []

    # Flight Plan 테이블 영역 추출
    for line in lines:
        stripped_line = line.strip()

        # 테이블 헤더 찾기
        if start_marker in line and not in_flight_plan:
            in_flight_plan = True
            continue

        # 테이블 종료 마커 찾기
        if stripped_line.startswith(end_marker):
            break

        # Flight Plan 테이블 내의 데이터 행 수집
        if in_flight_plan and stripped_line:
            # 여러 공백을 하나로 정리
            cleaned_line = re.sub(r' +', ' ', stripped_line)
            flight_plan_lines.append(cleaned_line)
            
    if not flight_plan_lines:
        print("Flight Plan 테이블을 찾을 수 없습니다.")
        return []

    # 데이터 추출 및 정리
    # 테이블 구조:
    # - 첫 번째 행: DIST, 좌표, 숫자들... (SR 값이 여기 있음, 인덱스 7)
    # - 두 번째 행: 웨이포인트 이름, 좌표, ... (ACTM 값이 여기 있음, "00.10" 형식)
    # - 세 번째 행: 추가 정보 (선택적)
    
    extracted_data = []
    
    i = 0
    while i < len(flight_plan_lines):
        current_line = flight_plan_lines[i]
        parts = current_line.split()

        if not parts:
            i += 1
            continue
        
        # 첫 번째 행: DIST로 시작하는 행 (SR 값이 여기 있음)
        if parts[0].isdigit() and len(parts) > 7:
            # CLB (Climb) 중인지 확인 - CLB 중에는 SR이 없음
            is_climb = 'CLB' in parts
            
            # 다음 행을 확인하여 웨이포인트 이름 찾기
            if i + 1 < len(flight_plan_lines):
                next_line = flight_plan_lines[i + 1]
                next_parts = next_line.split()
                
                if next_parts:
                    # 웨이포인트 이름 확인
                    waypoint_candidate = next_parts[0]
                    
                    # 웨이포인트 판별:
                    # 1. 좌표 형식: 57N60, 57N70 등 (숫자+N+숫자)
                    # 2. 알파벳+숫자: EEP1, EXP1, ETP1, EEP2, EXP2 등
                    # 3. 알파벳만: TREEL, UQQ, KATCH 등
                    # 제외: Page, TO, TC, FIR, /, ---, CLB, DSC 등
                    invalid_keywords = ['Page', 'TO', 'TC', 'FIR', '/', '---', 'CLB', 'DSC', 'ANCHORAGE', 'OCEANIC', 'INCHEON', 'SENDAI', 'NIIGATA', 'YECHEON', 'POHANG', 'FUKUOKA']
                    
                    # 좌표 형식 체크 (57N60, 57N70 등)
                    is_coordinate = re.match(r'^\d{2}N\d{2}', waypoint_candidate)
                    # 알파벳+숫자 형식 체크 (EEP1, EXP1, ETP1 등)
                    is_alphanumeric = re.match(r'^[A-Z]+\d+', waypoint_candidate)
                    # 알파벳만 체크 (TREEL, UQQ, NATES, NIKLL 등 - N으로 시작해도 허용)
                    is_alpha_only = waypoint_candidate.isalpha() and len(waypoint_candidate) >= 2
                    
                    # N으로 시작하는 좌표 형식이 아닌 경우도 허용 (NATES, NIKLL 등)
                    # 단, 'N' 단독이나 좌표처럼 보이는 것은 제외
                    is_valid_waypoint = (
                        (is_coordinate or is_alphanumeric or is_alpha_only) and
                        waypoint_candidate not in invalid_keywords and
                        len(waypoint_candidate) >= 2
                    )
                    
                    if is_valid_waypoint:
                        
                        waypoint = waypoint_candidate
                        
                        # FL (Flight Level) 추출: 헤더 구조상 FL은 4번째 열이지만,
                        # 실제 데이터에서 LATITUDE가 여러 필드로 분리되어 있어서 인덱스를 조정해야 함
                        # 예: "0077 N57 06.9 277 360" -> parts[0]=0077, parts[1]=N57, parts[2]=06.9, parts[3]=277, parts[4]=360
                        # 헤더: DIST LATITUDE MC FL ETO/MSA R/F OT WIND/COMP SR TAS ZT B/O
                        # 실제: 0    1-2       3  4  5        6  7  8          9  10  11 12
                        # FL은 인덱스 4에 있음 (MC 다음, ETO/MSA 이전)
                        fl = "N/A"
                        if len(parts) > 4:
                            fl_candidate = parts[4].strip()
                            # FL은 숫자 (예: "273", "380", "360")
                            if fl_candidate.isdigit():
                                fl = fl_candidate
                            elif fl_candidate == "CLB":
                                # CLB 중에는 FL이 없음
                                fl = "N/A"
                        
                        # MSA (Minimum Safe Altitude) 추출: 현재 행의 5번째 요소 (인덱스 5)
                        # 형식: "---/113" 또는 "---/010" (슬래시 뒤의 숫자가 MSA)
                        msa = "N/A"
                        if len(parts) > 5:
                            eto_msa_raw = parts[5].strip()
                            if '/' in eto_msa_raw:
                                # "---/113" 형식에서 113 추출
                                msa_value = eto_msa_raw.split('/')[1]
                                if msa_value.isdigit():
                                    msa = msa_value
                        
                        # SR (Shear Rate) 추출: 현재 행의 9번째 요소 (인덱스 9)
                        # 헤더: DIST LATITUDE MC FL ETO/MSA R/F OT WIND/COMP SR TAS ZT B/O
                        # 인덱스: 0    1         2  3  4        5   6  7          8  9   10 11
                        # 실제로는 WIND/COMP가 여러 열에 걸쳐 있을 수 있으므로 SR은 인덱스 9
                        sr = "N/A"
                        if is_climb:
                            # CLB 중에는 SR이 없음
                            sr = "N/A"
                        elif len(parts) > 9:
                            # 인덱스 9에 SR 값이 있음
                            sr_candidate = parts[9].strip()
                            # SR은 보통 2자리 숫자 (예: "04", "02")
                            if re.match(r'^\d{1,2}$', sr_candidate):
                                sr = sr_candidate
                            else:
                                sr = "N/A"

                        # ACTM (Accumulated Time) 추출: 다음 행의 7번째 요소 (인덱스 7)
                        # 형식: "00.10" 또는 "00.10 0059/" (다음 요소에 0059/가 있을 수 있음)
                        actm = "N/A"
                        if len(next_parts) > 7:
                            actm_raw = next_parts[7].strip()
                            # "00.10" 형식인지 확인
                            if re.match(r'\d{2}\.\d{2}', actm_raw):
                                actm = actm_raw
                            # "00.10/0059/" 형식인 경우
                            elif '/' in actm_raw and '.' in actm_raw:
                                actm = actm_raw.split('/')[0]
                            else:
                                actm = actm_raw
                        
                        # 통과 시간 계산: 이륙 시간 + ACTM
                        estimated_time = "N/A"
                        if takeoff_time and actm != "N/A":
                            try:
                                # ACTM을 분으로 변환 (예: "00.10" = 10분, "01.28" = 88분)
                                actm_parts = actm.split('.')
                                if len(actm_parts) == 2:
                                    hours = int(actm_parts[0])
                                    minutes = int(actm_parts[1])
                                    total_minutes = hours * 60 + minutes
                                    
                                    # 이륙 시간에 ACTM 추가
                                    waypoint_time = takeoff_time + timedelta(minutes=total_minutes)
                                    estimated_time = waypoint_time.strftime('%H%M') + 'Z'
                            except:
                                pass
                        
                        # Flight plan 행에서 위도/경도 추출 (첫 행: N37 42.0, 둘째 행: KAE E128 45.2)
                        lat = _parse_lat_from_parts(parts)
                        lon = _parse_lon_from_parts(next_parts)
                        
                        # 최종 데이터 추가
                        row = {
                            "Waypoint": waypoint,
                            "FL (Flight Level)": fl,
                            "MSA": msa,
                            "SR (Shear Rate)": sr,
                            "ACTM (Accumulated Time)": actm,
                            "Estimated Time (Z)": estimated_time
                        }
                        if lat is not None:
                            row["lat"] = lat
                        if lon is not None:
                            row["lon"] = lon
                        extracted_data.append(row)
                        
                        # 웨이포인트 행을 건너뛰기
                        i += 2
                        continue
        
        i += 1

    # 텍스트 파일로 저장 (save_temp가 True인 경우)
    if save_temp and extracted_data:
        try:
            # temp 폴더 경로 생성 (프로젝트 루트의 temp 폴더)
            base_name = os.path.splitext(os.path.basename(pdf_path))[0]
            # 현재 파일의 디렉토리를 기준으로 프로젝트 루트 찾기
            current_dir = os.path.dirname(os.path.abspath(__file__))
            temp_dir = os.path.join(current_dir, 'temp')
            os.makedirs(temp_dir, exist_ok=True)
            out_path = os.path.join(temp_dir, base_name + "_flightplan.txt")
            
            # 텍스트 파일로 저장
            with open(out_path, "w", encoding="utf-8") as f:
                # 헤더 작성
                f.write("=" * 70 + "\n")
                f.write("Flight Plan Data Extracted from PDF\n")
                f.write(f"Source: {os.path.basename(pdf_path)}\n")
                f.write(f"Total Waypoints: {len(extracted_data)}\n")
                f.write("=" * 70 + "\n\n")
                
                # ETD 및 이륙 시간 정보 작성
                if etd_time and takeoff_time:
                    f.write(f"ETD: {etd_time.strftime('%H%M')}Z\n")
                    f.write(f"TAXI TIME: {taxi_minutes}분\n")
                    f.write(f"이륙 시간: {takeoff_time.strftime('%H%M')}Z\n")
                    if eta_str:
                        f.write(f"착륙 시간 (ETA): {eta_str}\n")
                    
                    # TURB/CB INFO 추가 (7-9줄 뒤, 즉 10줄 위치)
                    if turb_cb_info:
                        f.write("\n")
                        f.write("=" * 70 + "\n")
                        f.write("TURB/CB INFO\n")
                        f.write("=" * 70 + "\n")
                        for line in turb_cb_info:
                            if line and line.strip():  # 빈 줄이 아닌 경우만
                                # "- TURB/CB INFO" 제목은 제외하고 내용만 추가
                                if 'TURB/CB INFO' in line.upper() and line.strip().startswith('-'):
                                    continue
                                f.write(line + "\n")
                        f.write("=" * 70 + "\n")
                    
                    f.write("\n")
                
                # 테이블 헤더
                f.write(f"{'Waypoint':<15}{'MSA':<10}{'SR (Shear Rate)':<20}{'ACTM (Accumulated Time)':<20}{'Estimated Time (Z)':<20}\n")
                f.write("-" * 100 + "\n")
                
                # 데이터 행 작성
                for row in extracted_data:
                    f.write(f"{row['Waypoint']:<15}{row['MSA']:<10}{row['SR (Shear Rate)']:<20}{row['ACTM (Accumulated Time)']:<20}{row['Estimated Time (Z)']:<20}\n")
                
                f.write("\n" + "=" * 70 + "\n")
                
                # Gemini API를 사용한 터뷸런스 분석 추가
                if GEMINI_AVAILABLE:
                    try:
                        etd_str = etd_time.strftime('%H%M') + 'Z' if etd_time else None
                        takeoff_time_str = takeoff_time.strftime('%H%M') + 'Z' if takeoff_time else None
                        
                        print("🤖 Gemini API를 사용한 터뷸런스 분석 시작...")
                        analysis_result = analyze_turbulence_with_gemini(
                            pdf_path, extracted_data, etd_str, takeoff_time_str, eta_str, turb_cb_info, taf_data,
                            departure_airport, arrival_airport
                        )
                        
                        if analysis_result and not analysis_result.startswith("⚠️"):
                            f.write("\n" + "=" * 70 + "\n")
                            f.write("터뷸런스 및 기상 회피 분석 (Gemini AI)\n")
                            f.write("=" * 70 + "\n\n")
                            f.write(analysis_result)
                            f.write("\n\n" + "=" * 70 + "\n")
                            print("✅ 터뷸런스 분석 완료")
                        else:
                            print(f"⚠️ 터뷸런스 분석 실패: {analysis_result}")
                    except Exception as e:
                        print(f"⚠️ 터뷸런스 분석 중 오류: {e}")
            
            print(f"✅ Flight Plan 데이터가 저장되었습니다: {out_path}")
        except Exception as e:
            print(f"⚠️  텍스트 파일 저장 중 오류 발생: {e}")

    return extracted_data


def build_major_turbulence_table(flight_data: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    Flight data(OFP PDF 추출 결과)에서 SR 5 이상 구간만 추려 '주요 터뷸런스 예상 구간' 테이블 행 목록을 만듭니다.
    NOTAM 결과 페이지에서 TURB/CB 아래 테이블로 표시할 때 사용합니다.
    
    Args:
        flight_data: extract_flight_data_from_pdf() 반환값 (Waypoint, FL, SR, ACTM, Estimated Time (Z) 등)
    
    Returns:
        [{"time_utc": "05:34Z ~ 06:04Z", "waypoint": "EKORO ~ ENLAB", "actm": "01.29 ~ 01.59", "fl": "381", "content": "..."}, ...]
        구간이 없으면 빈 리스트.
    """
    if not flight_data:
        return []

    waypoint_table = []
    for row in flight_data:
        waypoint_table.append({
            'Waypoint': row.get('Waypoint', ''),
            'FL': row.get('FL (Flight Level)', 'N/A'),
            'MSA': row.get('MSA', 'N/A'),
            'SR': row.get('SR (Shear Rate)', 'N/A'),
            'ACTM': row.get('ACTM (Accumulated Time)', 'N/A'),
            'Estimated Time (Z)': row.get('Estimated Time (Z)', 'N/A')
        })

    def get_sr_group(sr_str):
        if sr_str == "N/A" or not sr_str:
            return None
        try:
            sr_value = int(sr_str)
            if sr_value <= 4:
                return None
            elif 5 <= sr_value <= 8:
                return "Moderate"
            else:
                return "Severe"
        except Exception:
            return None

    turbulence_segments = []
    current_segment = None

    for i, wp in enumerate(waypoint_table):
        sr_group = get_sr_group(wp['SR'])
        if sr_group is None:
            if current_segment:
                turbulence_segments.append(current_segment)
                current_segment = None
            continue
        if current_segment is None:
            current_segment = {
                'category': sr_group,
                'start_waypoint': wp['Waypoint'],
                'start_time': wp['Estimated Time (Z)'],
                'start_actm': wp['ACTM'],
                'start_fl': wp['FL'],
                'sr_values': [wp['SR']],
                'end_waypoint': wp['Waypoint'],
                'end_time': wp['Estimated Time (Z)'],
                'end_actm': wp['ACTM'],
                'end_fl': wp['FL']
            }
        elif current_segment['category'] == sr_group:
            current_segment['end_waypoint'] = wp['Waypoint']
            current_segment['end_time'] = wp['Estimated Time (Z)']
            current_segment['end_actm'] = wp['ACTM']
            current_segment['end_fl'] = wp['FL']
            current_segment['sr_values'].append(wp['SR'])
        else:
            turbulence_segments.append(current_segment)
            current_segment = {
                'category': sr_group,
                'start_waypoint': wp['Waypoint'],
                'start_time': wp['Estimated Time (Z)'],
                'start_actm': wp['ACTM'],
                'start_fl': wp['FL'],
                'sr_values': [wp['SR']],
                'end_waypoint': wp['Waypoint'],
                'end_time': wp['Estimated Time (Z)'],
                'end_actm': wp['ACTM'],
                'end_fl': wp['FL']
            }
    if current_segment:
        turbulence_segments.append(current_segment)

    def _fmt_time(t):
        if t and t != "N/A" and len(str(t)) == 5:
            s = str(t)
            return f"{s[:2]}:{s[2:4]}Z"
        return t or "N/A"

    def _is_valid_fl(fl_str):
        if fl_str == "N/A" or not fl_str:
            return False
        try:
            int(fl_str)
            return True
        except Exception:
            return False

    rows = []
    for seg in turbulence_segments:
        sr_values_int = [int(sr) for sr in seg['sr_values'] if sr != "N/A"]
        if not sr_values_int:
            continue
        sr_min_val = min(sr_values_int)
        sr_max_val = max(sr_values_int)
        sr_range = f"{sr_min_val}-{sr_max_val}" if sr_min_val != sr_max_val else str(sr_min_val)

        start_t = _fmt_time(seg['start_time'])
        end_t = _fmt_time(seg['end_time'])
        time_display = f"{start_t} ~ {end_t}" if start_t != end_t else start_t
        wp_display = f"{seg['start_waypoint']} ~ {seg['end_waypoint']}" if seg['start_waypoint'] != seg['end_waypoint'] else seg['start_waypoint']
        actm_display = f"{seg['start_actm']} ~ {seg['end_actm']}" if seg['start_actm'] != seg['end_actm'] else seg['start_actm']

        start_fl_val = seg['start_fl']
        end_fl_val = seg['end_fl']
        if _is_valid_fl(start_fl_val) and _is_valid_fl(end_fl_val):
            fl_display = start_fl_val if start_fl_val == end_fl_val else f"{start_fl_val} ~ {end_fl_val}"
        elif _is_valid_fl(start_fl_val):
            fl_display = start_fl_val
        elif _is_valid_fl(end_fl_val):
            fl_display = end_fl_val
        else:
            fl_display = "N/A"

        category = seg['category']
        if category == "Moderate":
            content = f"[SR 기준] Moderate Turbulence (SR {sr_range}) - SR 기반."
        elif category == "Severe":
            content = f"[SR 기준] Severe Turbulence (SR {sr_range}) - SR 기반."
        else:
            content = f"[SR 기준] {category} Turbulence (SR {sr_range}) - SR 기반."

        rows.append({
            "time_utc": time_display,
            "waypoint": wp_display,
            "actm": actm_display,
            "fl": fl_display,
            "content": content
        })
    return rows


def merge_consecutive_turbulence_segments(text: str) -> str:
    """
    연속된 동일한 터뷸런스 레벨의 구간을 하나로 병합합니다.
    
    예:
    19:07Z ~ 19:23Z	BUDOP ~ EVKAM	...	Moderate to Severe Turbulence (SR 4-5)
    19:23Z ~ 19:31Z	EVKAM ~ KARDE	...	Moderate to Severe Turbulence (SR 4-5)
    ->
    19:07Z ~ 19:31Z	BUDOP ~ KARDE	...	Moderate to Severe Turbulence (SR 4-5)
    """
    import re
    
    lines = text.split('\n')
    result_lines = []
    i = 0
    
    while i < len(lines):
        line = lines[i].strip()
        
        # 터뷸런스 구간 라인인지 확인 (탭으로 구분된 형식)
        if '\t' in line and ('Z ~' in line or 'Z\t' in line):
            # 현재 구간 파싱
            parts = line.split('\t')
            if len(parts) >= 5:
                time_range = parts[0].strip()
                waypoint_range = parts[1].strip()
                actm_range = parts[2].strip()
                fl_range = parts[3].strip()
                content = parts[4].strip()
                
                # 터뷸런스 레벨 추출 (SR 값과 카테고리 조합)
                # 예: "Moderate to Severe Turbulence (SR 4-5)" 또는 "Severe Turbulence (SR 7)"
                turb_level_match = re.search(r'((?:Moderate(?:\s+to\s+Severe)?|Severe|Light)\s+Turbulence)\s*\(SR\s*(\d+(?:[-~]\d+)?)\)', content, re.IGNORECASE)
                if turb_level_match:
                    # 카테고리와 SR 값을 조합하여 고유한 키 생성
                    category = turb_level_match.group(1).strip()
                    sr_value = turb_level_match.group(2).strip()
                    turb_level = f"{category} (SR {sr_value})"
                else:
                    # SR 값만 있는 경우도 처리
                    sr_only_match = re.search(r'SR\s*(\d+(?:[-~]\d+)?)', content, re.IGNORECASE)
                    if sr_only_match:
                        turb_level = f"SR {sr_only_match.group(1)}"
                    else:
                        turb_level = None
                
                if turb_level:
                    
                    # 연속된 동일한 터뷸런스 레벨 찾기
                    merged_segments = [{
                        'time_start': time_range.split(' ~ ')[0] if ' ~ ' in time_range else time_range,
                        'time_end': time_range.split(' ~ ')[1] if ' ~ ' in time_range else time_range,
                        'waypoint_start': waypoint_range.split(' ~ ')[0] if ' ~ ' in waypoint_range else waypoint_range,
                        'waypoint_end': waypoint_range.split(' ~ ')[1] if ' ~ ' in waypoint_range else waypoint_range,
                        'actm_start': actm_range.split(' ~ ')[0] if ' ~ ' in actm_range else actm_range,
                        'actm_end': actm_range.split(' ~ ')[1] if ' ~ ' in actm_range else actm_range,
                        'fl_start': fl_range.split(' ~ ')[0] if ' ~ ' in fl_range else fl_range,
                        'fl_end': fl_range.split(' ~ ')[1] if ' ~ ' in fl_range else fl_range,
                        'content': content
                    }]
                    
                    # 다음 라인들을 확인하여 동일한 터뷸런스 레벨인지 확인
                    j = i + 1
                    while j < len(lines):
                        next_line = lines[j].strip()
                        if not next_line or not ('\t' in next_line and ('Z ~' in next_line or 'Z\t' in next_line)):
                            break
                        
                        next_parts = next_line.split('\t')
                        if len(next_parts) >= 5:
                            next_time_range = next_parts[0].strip()
                            next_waypoint_range = next_parts[1].strip()
                            next_content = next_parts[4].strip()
                            
                            # 다음 구간의 터뷸런스 레벨 확인
                            next_turb_level_match = re.search(r'((?:Moderate(?:\s+to\s+Severe)?|Severe|Light)\s+Turbulence)\s*\(SR\s*(\d+(?:[-~]\d+)?)\)', next_content, re.IGNORECASE)
                            if next_turb_level_match:
                                next_category = next_turb_level_match.group(1).strip()
                                next_sr_value = next_turb_level_match.group(2).strip()
                                next_turb_level = f"{next_category} (SR {next_sr_value})"
                            else:
                                # SR 값만 있는 경우도 처리
                                next_sr_only_match = re.search(r'SR\s*(\d+(?:[-~]\d+)?)', next_content, re.IGNORECASE)
                                if next_sr_only_match:
                                    next_turb_level = f"SR {next_sr_only_match.group(1)}"
                                else:
                                    next_turb_level = None
                            
                            if next_turb_level:
                                
                                # 동일한 터뷸런스 레벨이고, waypoint가 연속된 경우 병합
                                if next_turb_level == turb_level:
                                    # waypoint 연속성 확인 (이전 구간의 종료 waypoint가 다음 구간의 시작 waypoint와 일치)
                                    current_end_wp = merged_segments[-1]['waypoint_end']
                                    next_start_wp = next_waypoint_range.split(' ~ ')[0] if ' ~ ' in next_waypoint_range else next_waypoint_range
                                    
                                    if current_end_wp == next_start_wp:
                                        # 병합
                                        merged_segments.append({
                                            'time_start': next_time_range.split(' ~ ')[0] if ' ~ ' in next_time_range else next_time_range,
                                            'time_end': next_time_range.split(' ~ ')[1] if ' ~ ' in next_time_range else next_time_range,
                                            'waypoint_start': next_start_wp,
                                            'waypoint_end': next_waypoint_range.split(' ~ ')[1] if ' ~ ' in next_waypoint_range else next_waypoint_range,
                                            'actm_start': next_parts[2].strip().split(' ~ ')[0] if ' ~ ' in next_parts[2].strip() else next_parts[2].strip(),
                                            'actm_end': next_parts[2].strip().split(' ~ ')[1] if ' ~ ' in next_parts[2].strip() else next_parts[2].strip(),
                                            'fl_start': next_parts[3].strip().split(' ~ ')[0] if ' ~ ' in next_parts[3].strip() else next_parts[3].strip(),
                                            'fl_end': next_parts[3].strip().split(' ~ ')[1] if ' ~ ' in next_parts[3].strip() else next_parts[3].strip(),
                                            'content': next_content
                                        })
                                        j += 1
                                        continue
                        
                        break
                    
                    # 병합된 구간이 2개 이상이면 하나로 합치기
                    if len(merged_segments) > 1:
                        first = merged_segments[0]
                        last = merged_segments[-1]
                        
                        # FL 범위 계산 (시작과 종료가 다를 경우)
                        fl_display = first['fl_start']
                        if first['fl_start'] != last['fl_end']:
                            fl_display = f"{first['fl_start']} ~ {last['fl_end']}"
                        elif first['fl_start'] == first['fl_end']:
                            fl_display = first['fl_start']
                        
                        merged_line = f"{first['time_start']} ~ {last['time_end']}\t{first['waypoint_start']} ~ {last['waypoint_end']}\t{first['actm_start']} ~ {last['actm_end']}\t{fl_display}\t{first['content']}"
                        result_lines.append(merged_line)
                        i = j  # 병합된 라인 수만큼 건너뛰기
                        continue
        
        result_lines.append(line)
        i += 1
    
    return '\n'.join(result_lines)


def _split_range(value: str) -> Tuple[str, str]:
    if ' ~ ' in value:
        start, end = [s.strip() for s in value.split(' ~ ', 1)]
        return start, end
    return value.strip(), value.strip()


def _format_range(start: str, end: str) -> str:
    return start if start == end else f"{start} ~ {end}"


def _parse_turbulence_row(line: str) -> Optional[Dict[str, str]]:
    import re

    stripped = line.strip()
    if not stripped:
        return None
    parts = None
    if '\t' in stripped:
        parts = [p.strip() for p in stripped.split('\t')]
    elif stripped.startswith('|') and stripped.endswith('|'):
        parts = [p.strip() for p in stripped.strip('|').split('|')]
    if not parts or len(parts) < 4:
        return None
    time_range = parts[0]
    if not re.search(r'\d{2}:\d{2}Z', time_range):
        return None
    return {
        'time_range': time_range,
        'wp_range': parts[1] if len(parts) > 1 else "",
        'actm_range': parts[2] if len(parts) > 2 else "",
        'fl_range': parts[3] if len(parts) > 3 else "",
        'content': parts[4] if len(parts) > 4 else "",
    }


def merge_consecutive_turbulence_segments_table(text: str) -> str:
    """
    마크다운 테이블 형식의 연속된 동일한 터뷸런스 레벨 구간을 병합합니다.
    """
    import re

    lines = text.split('\n')
    result_lines = []
    i = 0

    while i < len(lines):
        line = lines[i].strip()
        parsed = _parse_turbulence_row(line)
        if parsed and line.startswith('|') and line.endswith('|'):
            content = parsed['content']
            turb_level_match = re.search(
                r'((?:Moderate(?:\s+to\s+Severe)?|Severe|Light)\s+Turbulence)\s*\(SR\s*(\d+(?:[-~]\d+)?)\)',
                content,
                re.IGNORECASE
            )
            if turb_level_match:
                category = turb_level_match.group(1).strip()
                sr_value = turb_level_match.group(2).strip()
                turb_level = f"{category} (SR {sr_value})"
            else:
                sr_only_match = re.search(r'SR\s*(\d+(?:[-~]\d+)?)', content, re.IGNORECASE)
                turb_level = f"SR {sr_only_match.group(1)}" if sr_only_match else None

            if turb_level:
                t_start, t_end = _split_range(parsed['time_range'])
                w_start, w_end = _split_range(parsed['wp_range'])
                a_start, a_end = _split_range(parsed['actm_range'])
                f_start, f_end = _split_range(parsed['fl_range'])

                j = i + 1
                while j < len(lines):
                    next_line = lines[j].strip()
                    next_parsed = _parse_turbulence_row(next_line)
                    if not next_parsed or not (next_line.startswith('|') and next_line.endswith('|')):
                        break
                    next_content = next_parsed['content']
                    next_match = re.search(
                        r'((?:Moderate(?:\s+to\s+Severe)?|Severe|Light)\s+Turbulence)\s*\(SR\s*(\d+(?:[-~]\d+)?)\)',
                        next_content,
                        re.IGNORECASE
                    )
                    if next_match:
                        next_category = next_match.group(1).strip()
                        next_sr_value = next_match.group(2).strip()
                        next_turb_level = f"{next_category} (SR {next_sr_value})"
                    else:
                        next_sr_only = re.search(r'SR\s*(\d+(?:[-~]\d+)?)', next_content, re.IGNORECASE)
                        next_turb_level = f"SR {next_sr_only.group(1)}" if next_sr_only else None

                    if next_turb_level != turb_level:
                        break

                    nt_start, nt_end = _split_range(next_parsed['time_range'])
                    nw_start, nw_end = _split_range(next_parsed['wp_range'])
                    na_start, na_end = _split_range(next_parsed['actm_range'])
                    nf_start, nf_end = _split_range(next_parsed['fl_range'])

                    if w_end == nw_start:
                        t_end = nt_end
                        w_end = nw_end
                        a_end = na_end
                        f_end = nf_end
                        j += 1
                        continue
                    break

                merged_line = (
                    f"| {_format_range(t_start, t_end)} | {_format_range(w_start, w_end)} | "
                    f"{_format_range(a_start, a_end)} | {_format_range(f_start, f_end)} | {content} |"
                )
                result_lines.append(merged_line)
                i = j
                continue

        result_lines.append(lines[i])
        i += 1

    return '\n'.join(result_lines)


def filter_major_turbulence_rows(text: str, min_sr: int = 5) -> str:
    """
    Gemini 출력에서 SR 기준 주요 터뷸런스 표의 데이터 행 중
    SR 값이 min_sr 미만인 행을 제거합니다.
    """
    import re

    lines = text.split('\n')
    filtered = []
    for line in lines:
        parsed = _parse_turbulence_row(line)
        if parsed:
            # SR 값 파싱: (SR 4), (SR 5-7), (SR 9+)
            match = re.search(r'\(SR\s*(\d+)(?:\s*[-~]\s*(\d+))?\+?\)', line, re.IGNORECASE)
            if match:
                sr_start = int(match.group(1))
                sr_end = int(match.group(2)) if match.group(2) else sr_start
                sr_min = min(sr_start, sr_end)
                if sr_min < min_sr:
                    continue
        filtered.append(line)
    return '\n'.join(filtered)


def _actm_to_minutes(actm: str) -> float:
    """ACTM 값(예: '01.38')을 분 단위 숫자로 변환"""
    try:
        parts = actm.strip().split('.')
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
    except:
        pass
    return -1


def filter_contained_rows(text: str) -> str:
    """
    시간/ACTM 범위가 다른 행에 완전히 포함된 세부 구간을 제거합니다.
    예: ISMAD~CANAI (01.02~01.38)이 있으면,
        KAGYA~MIMOD (01.03~01.13)은 완전히 포함되므로 제거.
    """
    lines = text.split('\n')
    parsed_rows = []
    for idx, line in enumerate(lines):
        parsed = _parse_turbulence_row(line)
        if parsed:
            a_start_str, a_end_str = _split_range(parsed['actm_range'])
            a_start = _actm_to_minutes(a_start_str)
            a_end = _actm_to_minutes(a_end_str)
            parsed_rows.append({
                'idx': idx,
                'a_start': a_start,
                'a_end': a_end,
                'line': line
            })

    drop_indices = set()
    for row in parsed_rows:
        if row['a_start'] < 0 or row['a_end'] < 0:
            continue
        for other in parsed_rows:
            if other is row:
                continue
            if other['a_start'] < 0 or other['a_end'] < 0:
                continue
            # other가 row보다 넓은 범위이고, row가 other 안에 완전히 포함되는 경우
            other_span = other['a_end'] - other['a_start']
            row_span = row['a_end'] - row['a_start']
            if other_span > row_span and other['a_start'] <= row['a_start'] and other['a_end'] >= row['a_end']:
                drop_indices.add(row['idx'])
                break

    result = []
    for i, line in enumerate(lines):
        if i in drop_indices:
            continue
        result.append(line)
    return '\n'.join(result)




def classify_color_from_rgb(r: int, g: int, b: int) -> Dict[str, bool]:
    """
    RGB 값을 기반으로 터뷸런스 색상 분류 (정확한 수치 기반 판단)
    
    Args:
        r, g, b: RGB 값 (0-255)
        
    Returns:
        {'has_red': bool, 'has_yellow': bool, 'has_light_blue': bool}
    """
    result = {
        'has_red': False,
        'has_yellow': False,
        'has_light_blue': False
    }
    
    # 빨간색 판단: Red가 높고, Green과 Blue가 상대적으로 낮음
    # 빨간색: R > 200, R > G*1.3, R > B*1.3
    if r > 200 and r > g * 1.3 and r > b * 1.3:
        result['has_red'] = True
    
    # 노란색 판단: Red와 Green이 모두 높고, Blue가 낮음
    # 노란색: R > 180, G > 180, B < 150, |R-G| < 50
    if r > 180 and g > 180 and b < 150 and abs(r - g) < 50:
        result['has_yellow'] = True
    
    # 연한 파란색 판단: Blue가 높고, Red와 Green도 어느 정도 있음
    # 연한 파란색: B > 150, R > 100, G > 100, B > R*0.8, B > G*0.8
    if b > 150 and r > 100 and g > 100 and b > r * 0.8 and b > g * 0.8:
        result['has_light_blue'] = True
    
    return result


def find_sigwx_pages(pdf_path: str) -> List[int]:
    """
    PDF에서 SIGWX 차트가 있는 페이지 번호를 찾습니다.
    
    Args:
        pdf_path: PDF 파일 경로
        
    Returns:
        SIGWX 차트가 있는 페이지 번호 리스트 (0-based index)
    """
    sigwx_pages = []
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                page_text = page.extract_text()
                if page_text:
                    # SIGWX 키워드 찾기
                    if re.search(r'SIGWX', page_text, re.IGNORECASE):
                        sigwx_pages.append(i)
    except Exception as e:
        print(f"PDF 파일을 읽는 중 오류가 발생했습니다: {e}")
    
    return sigwx_pages


def analyze_turbulence_with_gemini(pdf_path: str, flight_data: List[Dict[str, str]], 
                                   etd_str: str, takeoff_time_str: str, eta_str: str,
                                   turb_cb_info: List[str], taf_data: Dict[str, Optional[str]] = None,
                                   departure_airport: Optional[str] = None, arrival_airport: Optional[str] = None) -> str:
    """
    Gemini API를 사용하여 터뷸런스 및 기상 회피 정보 분석
    SIGWX 차트 분석을 통합하여 정확도 향상
    
    Args:
        pdf_path: PDF 파일 경로
        flight_data: 추출된 Flight Plan 데이터
        etd_str: ETD (예: "2100Z")
        takeoff_time_str: 이륙 시간 (예: "2120Z")
        eta_str: ETA (예: "0826Z")
        turb_cb_info: TURB/CB INFO 내용 리스트
        
    Returns:
        분석 결과 문자열
    """
    if not GEMINI_AVAILABLE:
        return "⚠️ Gemini API를 사용할 수 없습니다. google-generativeai 패키지가 설치되어 있는지 확인하세요."
    
    api_key = os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
    if not api_key:
        return "⚠️ Gemini API 키가 설정되지 않았습니다. GEMINI_API_KEY 환경 변수를 설정하세요."
    
    # SIGWX 차트 분석 시도 (개선된 방법)
    sigwx_analysis = {}
    try:
        from src.sigwx_analyzer import analyze_sigwx_chart_enhanced, find_sigwx_pages
        
        sigwx_pages = find_sigwx_pages(pdf_path)
        if sigwx_pages:
            # 첫 번째 SIGWX 페이지 분석
            sigwx_analysis = analyze_sigwx_chart_enhanced(
                pdf_path, flight_data, sigwx_pages[0]
            )
            print(f"✅ SIGWX 차트 분석 완료: {len(sigwx_analysis)}개 waypoint 분석됨")
        else:
            print("ℹ️ SIGWX 차트를 찾을 수 없습니다. 기존 방식으로 분석을 계속합니다.")
    except ImportError as e:
        print(f"⚠️ SIGWX 분석 모듈을 불러올 수 없습니다 (계속 진행): {e}")
    except Exception as e:
        print(f"⚠️ SIGWX 차트 분석 중 오류 (계속 진행): {e}")
        import traceback
        traceback.print_exc()
    
    # ISIGMET API 데이터 가져오기 (실시간 기상 경보)
    isigmet_data = []
    isigmet_matches = {}
    try:
        from src.sigwx_analyzer import get_waypoint_coordinates_with_timing, match_sigmet_to_waypoints
        import requests
        from datetime import datetime
        
        # Waypoint 좌표 추출
        waypoints_with_coords = get_waypoint_coordinates_with_timing(flight_data)
        
        if waypoints_with_coords:
            # 비행 경로의 경계 상자(bounding box) 계산
            lats = [wp['lat'] for wp in waypoints_with_coords if wp.get('lat')]
            lons = [wp['lon'] for wp in waypoints_with_coords if wp.get('lon')]
            
            if lats and lons:
                min_lat, max_lat = min(lats), max(lats)
                min_lon, max_lon = min(lons), max(lons)
                # ±1도 여유를 두어 bbox 생성
                bbox = f"{min_lat-1},{min_lon-1},{max_lat+1},{max_lon+1}"
                
                # ISIGMET API 호출 (터뷸런스 관련만)
                try:
                    from datetime import datetime
                    # 현재 시간을 명시적으로 지정하여 최신 데이터 가져오기
                    current_time = datetime.now().strftime('%Y%m%d%H%M')
                    
                    isigmet_url = f"https://aviationweather.gov/api/data/isigmet?format=json&bbox={bbox}&hazard=turb&date={current_time}"
                    # 비행 고도에 맞춰 level 파라미터 추가 (기본 FL370 기준)
                    avg_fl = 37000  # 기본값
                    fl_values = []
                    for wp in waypoints_with_coords:
                        fl_str = wp.get('fl', '')
                        if fl_str and fl_str != 'N/A':
                            try:
                                fl_values.append(int(fl_str) * 100)  # FL370 -> 37000ft
                            except:
                                pass
                    if fl_values:
                        avg_fl = int(sum(fl_values) / len(fl_values))
                    
                    isigmet_url += f"&level={avg_fl}"
                    
                    print(f"📡 ISIGMET API 호출: bbox={bbox}, level={avg_fl}ft, date={current_time} (최신 데이터)")
                    isigmet_response = requests.get(isigmet_url, timeout=10)
                    
                    if isigmet_response.status_code == 200:
                        isigmet_json = isigmet_response.json()
                        if isinstance(isigmet_json, list):
                            isigmet_data = isigmet_json
                            print(f"✅ ISIGMET 데이터 수신: {len(isigmet_data)}개")
                            
                            # Waypoint와 SIGMET 매칭 (waypoint 형식 변환)
                            waypoints_for_matching = []
                            for wp in waypoints_with_coords:
                                waypoints_for_matching.append({
                                    'name': wp['waypoint'],
                                    'lat': wp['lat'],
                                    'lon': wp['lon']
                                })
                            
                            isigmet_matches = match_sigmet_to_waypoints(isigmet_data, waypoints_for_matching)
                            
                            if isigmet_matches:
                                matched_count = sum(1 for matches in isigmet_matches.values() if matches)
                                print(f"✅ {matched_count}개 waypoint에서 ISIGMET 매칭됨")
                except Exception as e:
                    print(f"⚠️ ISIGMET API 호출 실패 (계속 진행): {e}")
    except ImportError as e:
        print(f"ℹ️ ISIGMET 매칭 모듈을 불러올 수 없습니다 (계속 진행): {e}")
    except Exception as e:
        print(f"⚠️ ISIGMET 데이터 가져오기 중 오류 (계속 진행): {e}")
    
    try:
        genai.configure(api_key=api_key)
        # 일관된 결과를 위해 temperature=0으로 설정
        # 딕셔너리 형식으로 generation_config 생성 (더 호환성 좋음)
        generation_config = {
            'temperature': 0,  # 0으로 설정하여 가장 결정적인 결과 생성
            'top_p': 0.95,     # nucleus sampling
            'top_k': 40,       # top-k sampling
        }
        model = genai.GenerativeModel(
            'gemini-2.5-flash-lite',
            generation_config=generation_config
        )
        
        # Flight Plan 데이터 포맷팅
        waypoint_table = []
        for row in flight_data:
            waypoint_table.append({
                'Waypoint': row['Waypoint'],
                'FL': row.get('FL (Flight Level)', 'N/A'),
                'MSA': row['MSA'],
                'SR': row['SR (Shear Rate)'],
                'ACTM': row['ACTM (Accumulated Time)'],
                'Estimated Time (Z)': row['Estimated Time (Z)']
            })
        
        # SR 값 기반으로 구간 그룹화 (정규식으로 처리)
        def get_sr_group(sr_str):
            """SR 값을 그룹으로 변환: SR 1-4: Light/Null (표시하지 않음), SR 5-8: Moderate, SR 9+: Severe"""
            if sr_str == "N/A" or not sr_str:
                return None
            try:
                sr_value = int(sr_str)
                if sr_value <= 4:
                    # SR 1-4는 Light/Null로 표시하지 않음
                    return None
                elif 5 <= sr_value <= 8:
                    return "Moderate"
                else:  # sr_value >= 9
                    return "Severe"
            except:
                return None
        
        # SR 값 기반 구간 그룹화
        turbulence_segments = []
        current_segment = None
        
        for i, wp in enumerate(waypoint_table):
            sr_group = get_sr_group(wp['SR'])
            
            if sr_group is None:
                # SR이 없는 경우 (CLB 등) - 이전 구간 종료
                if current_segment:
                    turbulence_segments.append(current_segment)
                    current_segment = None
                continue
            
            if current_segment is None:
                # 새 구간 시작
                current_segment = {
                    'category': sr_group,
                    'start_waypoint': wp['Waypoint'],
                    'start_time': wp['Estimated Time (Z)'],
                    'start_actm': wp['ACTM'],
                    'start_fl': wp['FL'],
                    'sr_values': [wp['SR']],
                    'waypoints': [wp['Waypoint']],
                    'end_waypoint': wp['Waypoint'],
                    'end_time': wp['Estimated Time (Z)'],
                    'end_actm': wp['ACTM'],
                    'end_fl': wp['FL']
                }
            elif current_segment['category'] == sr_group:
                # 같은 그룹 - 구간 확장
                current_segment['end_waypoint'] = wp['Waypoint']
                current_segment['end_time'] = wp['Estimated Time (Z)']
                current_segment['end_actm'] = wp['ACTM']
                current_segment['end_fl'] = wp['FL']
                current_segment['sr_values'].append(wp['SR'])
                current_segment['waypoints'].append(wp['Waypoint'])
            else:
                # 그룹 변경 - 이전 구간 종료, 새 구간 시작
                turbulence_segments.append(current_segment)
                current_segment = {
                    'category': sr_group,
                    'start_waypoint': wp['Waypoint'],
                    'start_time': wp['Estimated Time (Z)'],
                    'start_actm': wp['ACTM'],
                    'start_fl': wp['FL'],
                    'sr_values': [wp['SR']],
                    'waypoints': [wp['Waypoint']],
                    'end_waypoint': wp['Waypoint'],
                    'end_time': wp['Estimated Time (Z)'],
                    'end_actm': wp['ACTM'],
                    'end_fl': wp['FL']
                }
        
        # 마지막 구간 추가
        if current_segment:
            turbulence_segments.append(current_segment)
        
        # 주요 터뷸런스 구간 필터링: SR 값이 5 이상인 구간만 포함 (SR 1-4는 제외)
        major_turbulence_segments = []
        for seg in turbulence_segments:
            # SR 값이 5 이상인 구간만 포함 (SR 1-4는 Light/Null로 표시하지 않음)
            sr_values_int = [int(sr) for sr in seg['sr_values'] if sr != "N/A"]
            if sr_values_int:
                sr_max = max(sr_values_int)
                if sr_max >= 5:  # SR 5 이상인 구간만 포함
                    major_turbulence_segments.append(seg)
        
        # 필터링된 구간을 turbulence_segments로 교체
        turbulence_segments = major_turbulence_segments

        # 동일 시작 waypoint의 단일 구간이 연속으로 중복되는 경우 제거
        # (예: ISMAD~ISMAD 다음에 ISMAD~CANAI가 이어지는 케이스)
        cleaned_segments = []
        i = 0
        while i < len(turbulence_segments):
            seg = turbulence_segments[i]
            is_single_point = (
                seg.get('start_waypoint') == seg.get('end_waypoint')
                and seg.get('start_time') == seg.get('end_time')
                and seg.get('start_actm') == seg.get('end_actm')
                and seg.get('start_fl') == seg.get('end_fl')
            )
            if is_single_point and i + 1 < len(turbulence_segments):
                nxt = turbulence_segments[i + 1]
                same_start = (
                    nxt.get('category') == seg.get('category')
                    and nxt.get('start_waypoint') == seg.get('start_waypoint')
                    and nxt.get('start_time') == seg.get('start_time')
                    and nxt.get('start_actm') == seg.get('start_actm')
                )
                if same_start:
                    i += 1
                    continue
            cleaned_segments.append(seg)
            i += 1
        turbulence_segments = cleaned_segments
        
        
        # TURB/CB INFO 포맷팅
        turb_cb_text = '\n'.join(turb_cb_info) if turb_cb_info else "없음"
        
        # TAF 데이터 포맷팅 (공항 코드 동적 추출)
        taf_text = ""
        if taf_data:
            if taf_data.get('departure'):
                airport_label = f" ({departure_airport})" if departure_airport else ""
                taf_text += f"DEPARTURE WEATHER{airport_label}:\n{taf_data['departure']}\n\n"
            if taf_data.get('arrival'):
                airport_label = f" ({arrival_airport})" if arrival_airport else ""
                taf_text += f"ARRIVAL WEATHER{airport_label}:\n{taf_data['arrival']}\n\n"
            if taf_data.get('alternate'):
                taf_text += f"ALTERNATE WEATHER:\n{taf_data['alternate']}\n\n"
        
        if not taf_text:
            taf_text = "TAF 데이터가 제공되지 않았습니다."
        
        # SIGWX 차트 분석 결과 포맷팅
        sigwx_text = ""
        if sigwx_analysis:
            sigwx_text = "\n**SIGWX 차트 분석 결과 (이미지 처리 + 좌표 기반 매핑):**\n"
            for wp_name, wp_data in sigwx_analysis.items():
                sigwx_info = []
                if wp_data.get('mod_turbulence'):
                    sigwx_info.append("MOD Turbulence")
                if wp_data.get('sev_turbulence'):
                    sigwx_info.append("SEV Turbulence")
                if wp_data.get('cb_clouds'):
                    sigwx_info.append(f"CB Clouds ({len(wp_data['cb_clouds'])}개)")
                if wp_data.get('jet_streams'):
                    sigwx_info.append(f"Jet Streams ({len(wp_data['jet_streams'])}개)")
                
                if sigwx_info:
                    sigwx_text += f"- {wp_name} ({wp_data.get('estimated_time', 'N/A')}): {', '.join(sigwx_info)}\n"
            
            if sigwx_text == "\n**SIGWX 차트 분석 결과 (이미지 처리 + 좌표 기반 매핑):**\n":
                sigwx_text += "기상 현상이 발견되지 않았습니다.\n"
        else:
            sigwx_text = "SIGWX 차트 분석 결과가 없습니다.\n"
        sigwx_available = bool(sigwx_analysis)
        
        # ISIGMET API 데이터 포맷팅 (실시간 기상 경보)
        # ISIGMET 유효 시간/고도(FL) 기준 필터링을 위한 waypoint 시간/고도 계산
        from datetime import datetime, timedelta

        def _parse_hhmmz(hhmmz: str):
            if not hhmmz or hhmmz == "N/A":
                return None
            s = hhmmz.strip().replace("Z", "")
            if len(s) != 4 or not s.isdigit():
                return None
            return int(s[:2]), int(s[2:4])

        base_date = datetime.utcnow().date()
        etd_time_dt = None
        etd_parsed = _parse_hhmmz(etd_str)
        if etd_parsed:
            etd_time_dt = datetime.combine(base_date, datetime.min.time()).replace(
                hour=etd_parsed[0], minute=etd_parsed[1]
            )

        waypoint_time_epoch = {}
        waypoint_time_dt = {}
        waypoint_alt_ft = {}
        waypoint_fl_map = {}
        prev_dt = etd_time_dt

        for wp in waypoint_table:
            wp_name = wp.get('Waypoint')
            wp_time = _parse_hhmmz(wp.get('Estimated Time (Z)', ''))
            wp_fl = wp.get('FL', '')

            # 고도(ft) 계산
            alt_ft = None
            if wp_fl and wp_fl != "N/A":
                try:
                    alt_ft = int(wp_fl) * 100
                except Exception:
                    alt_ft = None
            if wp_name:
                waypoint_alt_ft[wp_name] = alt_ft
                try:
                    waypoint_fl_map[wp_name] = int(wp_fl) if wp_fl and wp_fl != "N/A" else None
                except Exception:
                    waypoint_fl_map[wp_name] = None

            if wp_name and wp_time:
                wp_dt = datetime.combine(base_date, datetime.min.time()).replace(
                    hour=wp_time[0], minute=wp_time[1]
                )
                if prev_dt and wp_dt < prev_dt:
                    wp_dt = wp_dt + timedelta(days=1)
                prev_dt = wp_dt
                waypoint_time_epoch[wp_name] = int(wp_dt.timestamp())
                waypoint_time_dt[wp_name] = wp_dt

        def _sigmet_time_ok(sigmet: dict, wp_epoch: int) -> bool:
            valid_from = sigmet.get('validTimeFrom', 0)
            valid_to = sigmet.get('validTimeTo', 0)
            if not wp_epoch:
                return True
            if valid_from and valid_to:
                return valid_from <= wp_epoch <= valid_to
            return True

        def _sigmet_alt_ok(sigmet: dict, wp_alt: int) -> bool:
            if wp_alt is None:
                return True
            base_ft = sigmet.get('base', None)
            top_ft = sigmet.get('top', None)
            if isinstance(base_ft, int) and isinstance(top_ft, int):
                return base_ft <= wp_alt <= top_ft
            return True

        # 유효 시간/고도 기준으로 필터링된 매칭
        filtered_isigmet_matches = {}
        if isigmet_matches:
            for wp_name, matches in isigmet_matches.items():
                if not matches:
                    continue
                wp_epoch = waypoint_time_epoch.get(wp_name)
                wp_alt = waypoint_alt_ft.get(wp_name)
                filtered = []
                for match_info in matches:
                    sigmet = match_info.get('sigmet', {})
                    if _sigmet_time_ok(sigmet, wp_epoch) and _sigmet_alt_ok(sigmet, wp_alt):
                        filtered.append(match_info)
                if filtered:
                    filtered_isigmet_matches[wp_name] = filtered

        isigmet_text = ""
        if filtered_isigmet_matches:
            isigmet_text = "\n**ISIGMET (International SIGMET) 실시간 기상 경보:**\n"
            for wp_name, matches in filtered_isigmet_matches.items():
                for match_info in matches:
                    sigmet = match_info.get('sigmet', {})
                    fir_name = sigmet.get('firName', 'Unknown')
                    hazard = sigmet.get('hazard', 'N/A')
                    qualifier = sigmet.get('qualifier', 'N/A')
                    base_ft = sigmet.get('base', 'N/A')
                    top_ft = sigmet.get('top', 'N/A')

                    # 유효 시간
                    valid_from = sigmet.get('validTimeFrom', 0)
                    valid_to = sigmet.get('validTimeTo', 0)
                    if valid_from and valid_to:
                        valid_from_str = datetime.fromtimestamp(valid_from).strftime('%Y-%m-%d %H:%MZ')
                        valid_to_str = datetime.fromtimestamp(valid_to).strftime('%Y-%m-%d %H:%MZ')
                        valid_time = f"{valid_from_str} ~ {valid_to_str}"
                    else:
                        valid_time = "N/A"

                    location = "영역 내부" if match_info.get('inside') else "영역 근처"
                    isigmet_text += f"- {wp_name}: {fir_name} FIR, {qualifier} {hazard}, FL{base_ft//1000 if isinstance(base_ft, int) else 'N/A'}-{top_ft//1000 if isinstance(top_ft, int) else 'N/A'}, 유효: {valid_time}, {location}\n"

            if isigmet_text == "\n**ISIGMET (International SIGMET) 실시간 기상 경보:**\n":
                isigmet_text += "기상 경보가 없습니다.\n"
        elif isigmet_data:
            isigmet_text = "\n**ISIGMET 데이터 수신: 경로/시간/고도 조건에 맞는 경보가 없습니다.**\n"
        else:
            isigmet_text = "ISIGMET 실시간 기상 경보 데이터가 없습니다.\n"

        # GFS 기반 파생지표 요약 (Herbie) — 당분간 비활성화 (다운로드 지연 방지)
        # 켜려면 환경변수: ENABLE_GFS_ANALYSIS=true
        gfs_summary_markdown = ""
        gfs_status = ""
        if os.getenv("ENABLE_GFS_ANALYSIS", "false").lower() == "true":
            try:
                from src.gfs_weather_analyzer import build_gfs_summary_markdown, GfsWaypoint
                from src.sigwx_analyzer import get_waypoint_coordinates_with_timing

                waypoints_with_coords = get_waypoint_coordinates_with_timing(flight_data)
                coords_map = {wp.get('waypoint'): wp for wp in waypoints_with_coords if wp.get('waypoint')}

                candidate_names = []
                for seg in turbulence_segments:
                    if seg.get('start_waypoint'):
                        candidate_names.append(seg['start_waypoint'])
                    if seg.get('end_waypoint'):
                        candidate_names.append(seg['end_waypoint'])
                if not candidate_names:
                    candidate_names = list(waypoint_time_dt.keys())[:10]

                seen = set()
                unique_names = []
                for name in candidate_names:
                    if name and name not in seen:
                        seen.add(name)
                        unique_names.append(name)

                gfs_waypoints = []
                for name in unique_names:
                    coord = coords_map.get(name)
                    if not coord:
                        continue
                    fl_value = waypoint_fl_map.get(name)
                    if fl_value is None:
                        continue
                    gfs_waypoints.append(GfsWaypoint(
                        name=name,
                        lat=coord.get('lat'),
                        lon=coord.get('lon'),
                        fl=fl_value,
                        eta_dt=waypoint_time_dt.get(name)
                    ))

                if not gfs_waypoints:
                    for name, fl_value in waypoint_fl_map.items():
                        if fl_value is None:
                            continue
                        coord = coords_map.get(name)
                        if not coord:
                            continue
                        gfs_waypoints.append(GfsWaypoint(
                            name=name,
                            lat=coord.get('lat'),
                            lon=coord.get('lon'),
                            fl=fl_value,
                            eta_dt=waypoint_time_dt.get(name)
                        ))
                        if len(gfs_waypoints) >= 10:
                            break

                gfs_summary_markdown, gfs_status = build_gfs_summary_markdown(gfs_waypoints)
            except Exception as e:
                gfs_summary_markdown = ""
                gfs_status = f"오류: {str(e)}"
        else:
            gfs_status = "GFS 분석 비활성화 (ENABLE_GFS_ANALYSIS=true 로 활성화 가능)"
            print("ℹ️ GFS 분석 스킵 (다운로드 없음). 켜려면 ENABLE_GFS_ANALYSIS=true 설정")

        # ISIGMET 요약을 waypoint 기준으로 정리 (구간별 표시용)
        isigmet_summary_by_waypoint = {}
        if filtered_isigmet_matches:
            from datetime import datetime
            for wp_name, matches in filtered_isigmet_matches.items():
                if not matches:
                    continue
                summaries = []
                for match_info in matches:
                    sigmet = match_info.get('sigmet', {})
                    fir_name = sigmet.get('firName', 'Unknown')
                    hazard = sigmet.get('hazard', 'N/A')
                    qualifier = sigmet.get('qualifier', 'N/A')
                    base_ft = sigmet.get('base', 'N/A')
                    top_ft = sigmet.get('top', 'N/A')

                    valid_from = sigmet.get('validTimeFrom', 0)
                    valid_to = sigmet.get('validTimeTo', 0)
                    if valid_from and valid_to:
                        valid_from_str = datetime.fromtimestamp(valid_from).strftime('%Y-%m-%d %H:%MZ')
                        valid_to_str = datetime.fromtimestamp(valid_to).strftime('%Y-%m-%d %H:%MZ')
                        valid_time = f"{valid_from_str} ~ {valid_to_str}"
                    else:
                        valid_time = "N/A"

                    location = "영역 내부" if match_info.get('inside') else "영역 근처"
                    base_fl = base_ft // 1000 if isinstance(base_ft, int) else 'N/A'
                    top_fl = top_ft // 1000 if isinstance(top_ft, int) else 'N/A'
                    summary = f"{qualifier} {hazard}, FL{base_fl}-{top_fl}, 유효: {valid_time}, {fir_name} FIR, {location}"
                    summaries.append(summary)

                if summaries:
                    # 중복 제거 (순서 유지)
                    deduped = list(dict.fromkeys(summaries))
                    isigmet_summary_by_waypoint[wp_name] = deduped
        
        # 프롬프트 생성
        sigwx_status_text = "있음" if sigwx_available else "없음"

        prompt = f"""최종 분석 지침 (System Instruction Modification)
목표:
조종사가 비행 중 예상되는 위험 요소를 신속하게 파악할 수 있도록 '터뷸런스(Turbulence)'와 '기상 회피(Weather Deviation)' 정보를 시간, 위치 위주로 정리합니다.

분석 지침:
OFP(Operational Flight Plan): Waypoint 별 예상 통과 시간(UTC)을 기준으로 잡으십시오.
SIGWX Chart & Vertical Cross Section: 해당 차트의 난기류, 적란운(CB), 제트기류 정보를 OFP의 경로 및 시간과 매핑하십시오.
ISIGMET: 경로상에 매칭된 경보가 있으면 반드시 포함하고, 유효 시간을 명확히 표시하십시오.
TAF (공항 예보): 이륙, 착륙, 교체 공항의 기상 악화(Gust, TSRA 등) 시간대를 확인하십시오. **중요: TAF는 "기상 회피 기동" 섹션이 아닌 "공항 주의 사항" 섹션에만 사용하세요.**
Dispatcher Remarks: 운항 관리사가 작성한 주의 사항 중 기상 관련 사항만 확인하십시오.

**시간 정보 사용 지침 (매우 중요 - 반드시 준수):**
- Flight Plan Waypoint 데이터에 제공된 "예상 통과 시간"은 이미 정확히 계산된 값입니다.
- **절대 시간을 계산하지 마세요.** 제공된 "예상 통과 시간" 값을 그대로 정확히 사용하세요.
- 구간 표시 시: 시작 Waypoint의 "예상 통과 시간" ~ 종료 Waypoint의 "예상 통과 시간" 형식으로 표시하세요.
- **예시**: Waypoint 데이터에 "예상 통과 시간=0332Z"로 제공되면, 반드시 "03:32Z" 또는 "0332Z"로 표시하세요. 다른 시간으로 변경하거나 계산하지 마세요.
- **예시**: Waypoint 데이터에 "예상 통과 시간=0846Z"로 제공되면, 반드시 "08:46Z" 또는 "0846Z"로 표시하세요.

SR 분류: SR 1-4: Light/Null (표시하지 않음), SR 5-8: Moderate Turbulence, SR 9+: Severe Turbulence

**중요: 모든 Waypoint를 반드시 포함하세요. 마지막 Waypoint까지 누락 없이 모든 구간을 분석하세요.**

특히 SR 값이 5 이상인 Waypoint 구간에 초점을 맞추고, SR 값을 근거로 명시하십시오.

제약 사항 (중요):
결과 출력 시, 정보의 출처가 되는 문서의 페이지 번호(예: Page 12, P.24, 5 of 8 등)는 절대 표기하지 마십시오. 오직 분석된 내용과 근거만 명시하십시오.
'FMS/Waypoint 데이터 불일치'와 같은 기상/항행 외의 행정적 주의 사항은 출력하지 마십시오.

=== 입력 데이터 ===

ETD (Pushback Time): {etd_str}
이륙 시간 (Takeoff Time): {takeoff_time_str} (ETD + 20분)
착륙 시간 (ETA): {eta_str}

TURB/CB INFO:
{turb_cb_text}

TAF (Terminal Aerodrome Forecast) 데이터:
{taf_text}

{sigwx_text}
SIGWX 사용 가능 여부: {sigwx_status_text}

{isigmet_text}

GFS 파생지표 요약:
{gfs_summary_markdown if gfs_summary_markdown else f"GFS 파생지표 데이터를 사용할 수 없습니다. ({gfs_status or 'N/A'})"}

Flight Plan Waypoint 데이터:
"""
        
        # Waypoint 데이터 추가 (참고용)
        prompt += "Flight Plan Waypoint 데이터 (참고용):\n"
        for wp in waypoint_table:
            prompt += f"- {wp['Waypoint']}: FL={wp['FL']}, MSA={wp['MSA']}, SR={wp['SR']}, ACTM={wp['ACTM']}, 예상 통과 시간={wp['Estimated Time (Z)']}\n"
        
        # ── Section 1 테이블을 코드에서 직접 생성 ──
        def _fmt_time(t):
            if t and t != "N/A" and len(t) == 5:
                return f"{t[:2]}:{t[2:4]}Z"
            return t

        def _is_valid_fl(fl_str):
            if fl_str == "N/A" or not fl_str:
                return False
            try:
                int(fl_str)
                return True
            except:
                return False

        section1_rows = []
        for seg in turbulence_segments:
            sr_values_int = [int(sr) for sr in seg['sr_values'] if sr != "N/A"]
            if not sr_values_int:
                continue
            sr_min_val = min(sr_values_int)
            sr_max_val = max(sr_values_int)
            sr_range = f"{sr_min_val}-{sr_max_val}" if sr_min_val != sr_max_val else str(sr_min_val)

            start_t = _fmt_time(seg['start_time'])
            end_t = _fmt_time(seg['end_time'])
            time_display = f"{start_t} ~ {end_t}" if start_t != end_t else start_t
            wp_display = f"{seg['start_waypoint']} ~ {seg['end_waypoint']}" if seg['start_waypoint'] != seg['end_waypoint'] else seg['start_waypoint']
            actm_display = f"{seg['start_actm']} ~ {seg['end_actm']}" if seg['start_actm'] != seg['end_actm'] else seg['start_actm']

            start_fl_val = seg['start_fl']
            end_fl_val = seg['end_fl']
            if _is_valid_fl(start_fl_val) and _is_valid_fl(end_fl_val):
                fl_display = start_fl_val if start_fl_val == end_fl_val else f"{start_fl_val} ~ {end_fl_val}"
            elif _is_valid_fl(start_fl_val):
                fl_display = start_fl_val
            elif _is_valid_fl(end_fl_val):
                fl_display = end_fl_val
            else:
                fl_display = "N/A"

            category = seg['category']
            if category == "Moderate":
                content = f"[SR 기준] Moderate Turbulence (SR {sr_range}) - SR 기반."
            elif category == "Severe":
                content = f"[SR 기준] Severe Turbulence (SR {sr_range}) - SR 기반."
            else:
                content = f"[SR 기준] {category} Turbulence (SR {sr_range}) - SR 기반."

            # ISIGMET 정보 추가
            isigmet_segment_summaries = []
            for wp_name in seg.get('waypoints', []):
                wp_summaries = isigmet_summary_by_waypoint.get(wp_name, [])
                if wp_summaries:
                    isigmet_segment_summaries.extend(wp_summaries)
            if isigmet_segment_summaries:
                isigmet_text_seg = " / ".join(list(dict.fromkeys(isigmet_segment_summaries)))
                content += f" ISIGMET: {isigmet_text_seg}"

            section1_rows.append(f"| {time_display} | {wp_display} | {actm_display} | {fl_display} | {content} |")

        # Section 1 마크다운 테이블 생성
        section1_table = "## 1. 주요 터뷸런스 예상 구간\n\n"
        if section1_rows:
            section1_table += "| 예상 시간 (UTC) | 위치 (Waypoint) | ACTM | 고도 (FL) | 내용 및 근거 |\n"
            section1_table += "|---|---|---|---|---|\n"
            for row in section1_rows:
                section1_table += row + "\n"
        else:
            section1_table += "SR 5 이상의 주요 터뷸런스 구간이 없습니다.\n"

        # 프롬프트에 Section 1 데이터 참조용으로 추가
        prompt += "\n**SR 값 기반 주요 터뷸런스 구간 (코드에서 이미 생성됨 - 참고용):**\n"
        for row in section1_rows:
            prompt += row + "\n"

        prompt += """

출력 형식:
**중요: "1. 주요 터뷸런스 예상 구간" 섹션은 코드에서 이미 생성했으므로, 출력에 포함하지 마세요.**
**Section 2부터 시작하세요.**

2. 기상 회피 기동 (Weather Deviation) 예상 구간
**매우 중요: 이 섹션은 "주요 터뷸런스 예상 구간"과 완전히 다른 섹션입니다.**

**기상 회피 기동이 필요한 조건 (다음 중 하나 이상에 해당해야 함):**
- SIGWX 차트에서 적란운(CB Clouds)이 경로와 직접 교차하는 구간 (Cloud top 정보 포함)
- ISIGMET에서 Severe 터뷸런스 경보가 waypoint와 매칭된 구간 (SR 9 이상)
- Satellite 정보에서 경로상에 심각한 기상 현상(적란운, 폭풍 등)이 있는 구간

**절대 포함하지 말 것:**
- TAF 데이터는 공항 예보이므로 이 섹션에 포함하지 마세요. TAF는 "공항 주의 사항" 섹션에만 사용하세요.
- SR 1-8의 터뷸런스만으로는 기상 회피가 필요하지 않습니다. CB Clouds나 적란운 정보가 없으면 포함하지 마세요.
- "주요 터뷸런스 예상 구간"에 이미 포함된 구간을 이 섹션에 중복으로 포함하지 마세요.

**필수 정보:**
- CB Clouds가 경로와 교차하는 경우: Cloud top 고도 정보를 반드시 포함하세요.
- ISIGMET 경보가 있는 경우: FIR, 위험 유형, 고도 범위, 유효 시간을 포함하세요.

**해당 구간이 없으면:**
"기상 회피 기동이 필요한 구간이 없습니다."라고만 표시하세요.

예상 시간 (UTC)	위치 (Waypoint)	ACTM	고도 (FL)	내용 및 근거
(예: 21:20Z)	(예: CYVR)	(예: DEP)	(예: DEP)	(분석 내용)

3. 공항 주의 사항
**이 섹션에는 TAF 데이터를 기반으로 한 이륙/착륙/교체 공항의 기상 정보를 포함하세요.**
- **시간 칼럼은 반드시 Flight Plan의 ETD/ETA를 사용하세요.**
  - 출발 공항: ETD (Pushback Time)
  - 도착/교체 공항: ETA
  - TAF 유효 시간(예: 0406/0512)은 "내용 및 근거"에만 표기하세요. 시간 칼럼에 쓰지 마세요.
- TAF 데이터에서 추출한 공항별 기상 악화 시간대 (Gust, TSRA, 시정 저하 등)
- 이륙 시점의 기상 조건
- 도착 시점의 기상 조건 (시정, 강우, 구름 등)
- 교체 공항의 기상 조건

예상 시간 (UTC)	위치	ACTM	내용 및 근거
...	...	...	...

4. 조종사를 위한 제언
(핵심 조언만 기상 및 비행 운영에 초점을 맞추어 간결하게 작성)

5. GFS 기반 파생지표 요약
- 위에 제공된 "GFS 파생지표 요약" 표가 있으면 그대로 표시하세요.
- 표가 없거나 "사용할 수 없습니다"로 제공되면, 그 문구를 그대로 표시하세요.

위 데이터를 분석하여 위 형식대로 출력하세요. 페이지 번호는 절대 표기하지 마세요.
**매우 중요: "1. 주요 터뷸런스 예상 구간" 섹션은 출력하지 마세요. 코드에서 이미 생성했습니다. Section 2부터 출력하세요.**"""
        
        # Gemini API 호출 (타임아웃 및 재시도 로직 포함)
        max_retries = 3
        timeout_seconds = 60  # 60초 타임아웃
        retry_delay = 5  # 재시도 전 5초 대기
        
        for attempt in range(max_retries):
            try:
                # ThreadPoolExecutor를 사용하여 타임아웃 제어
                with ThreadPoolExecutor(max_workers=1) as executor:
                    # generation_config를 명시적으로 전달하여 일관된 결과 보장
                    future = executor.submit(
                        model.generate_content, 
                        prompt,
                        generation_config=generation_config
                    )
                    try:
                        response = future.result(timeout=timeout_seconds)
                        result = response.text.strip()
                        # Section 1 (코드 생성) + Gemini 결과 (Section 2~) 합치기
                        result = section1_table + "\n" + result
                        return result
                    except FutureTimeoutError:
                        if attempt < max_retries - 1:
                            print(f"⚠️ Gemini API 타임아웃 (시도 {attempt + 1}/{max_retries}). {retry_delay}초 후 재시도...")
                            time.sleep(retry_delay)
                            continue
                        else:
                            return f"⚠️ Gemini API 타임아웃: 요청이 {timeout_seconds}초를 초과했습니다. 프롬프트가 너무 길거나 네트워크가 불안정할 수 있습니다."
                    except Exception as e:
                        error_str = str(e)
                        # 504 타임아웃 오류인 경우 재시도
                        if "504" in error_str or "timeout" in error_str.lower() or "timed out" in error_str.lower():
                            if attempt < max_retries - 1:
                                print(f"⚠️ Gemini API 타임아웃 오류 (시도 {attempt + 1}/{max_retries}): {error_str}. {retry_delay}초 후 재시도...")
                                time.sleep(retry_delay)
                                continue
                            else:
                                return f"⚠️ Gemini API 타임아웃: 서버 응답 시간 초과 (504). 여러 번 재시도했지만 실패했습니다. 프롬프트를 단순화하거나 나중에 다시 시도해주세요."
                        # 429 Rate Limit 오류인 경우 재시도
                        elif "429" in error_str or "Quota exceeded" in error_str or "rate limit" in error_str.lower():
                            if attempt < max_retries - 1:
                                wait_time = retry_delay * (attempt + 1)  # 점진적 대기 시간 증가
                                print(f"⚠️ Gemini API Rate Limit (시도 {attempt + 1}/{max_retries}). {wait_time}초 후 재시도...")
                                time.sleep(wait_time)
                                continue
                            else:
                                return f"⚠️ Gemini API Rate Limit: API 호출 한도를 초과했습니다. 잠시 후 다시 시도해주세요."
                        else:
                            # 다른 오류는 즉시 반환
                            raise
            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"⚠️ Gemini API 오류 (시도 {attempt + 1}/{max_retries}): {str(e)}. {retry_delay}초 후 재시도...")
                    time.sleep(retry_delay)
                    continue
                else:
                    return f"⚠️ Gemini API 분석 중 오류 발생: {str(e)}"
        
        return "⚠️ Gemini API 분석 실패: 최대 재시도 횟수를 초과했습니다."
        
    except Exception as e:
        return f"⚠️ Gemini API 분석 중 오류 발생: {str(e)}"


# 사용 예시 (로컬에서 파일 경로를 입력받습니다)
# file_path = input("PDF 파일 경로를 입력하세요: ")
# flight_data = extract_flight_data_from_pdf(file_path)

# # 결과 출력
# print("\n### 📊 추출된 Flight Data (Waypoint, SR, ACTM)")
# if flight_data:
#     print(f"{'Waypoint':<15}{'SR (Shear Rate)':<20}{'ACTM (Accumulated Time)':<25}")
#     print("-" * 60)
#     for row in flight_data:
#         print(f"{row['Waypoint']:<15}{row['SR (Shear Rate)']:<20}{row['ACTM (Accumulated Time)']:<25}")
# else:
#     print("Flight Plan 데이터 추출에 실패했거나 파일 경로가 올바르지 않습니다.")