#!/usr/bin/env python3
"""
NOTAM 텍스트에서 항공편 정보 추출기
DEP, DEST, ALTN, EDTO 공항을 자동으로 추출
"""

import re
from typing import Dict, List, Optional, Any

class FlightInfoExtractor:
    """NOTAM 텍스트에서 항공편 정보 추출기"""
    
    def __init__(self):
        """초기화"""
        # 공항 코드 패턴 (3-4자리 알파벳)
        self.airport_pattern = r'\b[A-Z]{4}\b'
        
        # 항공편 정보 키워드
        self.flight_keywords = {
            'dep': ['DEP', 'DEPARTURE', 'FROM', 'ORIGIN'],
            'dest': ['DEST', 'DESTINATION', 'TO', 'ARRIVAL'],
            'altn': ['ALTN', 'ALTERNATE', 'ALT', 'ALTERNATIVE'],
            'refile': ['REFILE', 'REF', 'REFILING'],
            'edto': ['EDTO', 'EDT', 'EXTENDED DIVERSION', 'DIVERSION'],
            'route': ['ROUTE', 'RT', 'ROUTING', 'FLIGHT PATH']
        }
        
        # 일반적인 공항 코드 (필터링용)
        self.common_airports = {
            # 한국
            'RKSI', 'RKSS', 'RKPC', 'RKPK', 'RKJB', 'RKNY', 'RKJJ', 'RKPU',
            # 미국
            'KSEA', 'KPDX', 'KLAX', 'KSFO', 'KJFK', 'KORD', 'KDFW', 'KATL',
            'KPHX', 'KLAS', 'KDTW', 'KMSP', 'KIAH', 'KEWR', 'KBOS', 'KMIA',
            # 일본
            'RJTT', 'RJCC', 'RJAA', 'RJGG', 'RJFK', 'RJFF', 'RJOO', 'RJBB',
            # 캐나다
            'CYVR', 'CYYZ', 'CYUL', 'CYHZ', 'CYOW', 'CYWG', 'CYEG', 'CYQR',
            # 기타
            'PANC', 'PAED', 'PASY', 'PAKN', 'PACD', 'PAZA', 'KZAK', 'RJJJ'
        }
    
    def extract_flight_info(self, notam_text: str) -> Dict[str, Any]:
        """
        NOTAM 텍스트에서 항공편 정보 추출
        
        Args:
            notam_text: NOTAM 텍스트
            
        Returns:
            Dict[str, Any]: 추출된 항공편 정보
        """
        # 텍스트 정리
        cleaned_text = self._clean_text(notam_text)
        
        # PACKAGE별로 정보 추출 (원본 텍스트 사용)
        package_info = self._extract_by_packages(notam_text)
        
        # 각 항목별 추출 (PACKAGE 정보만 사용, 백업 추출 비활성화)
        result = {
            'dep': package_info.get('dep'),
            'dest': package_info.get('dest'),
            'altn': package_info.get('altn'),
            'refile': package_info.get('refile'),
            'edto': package_info.get('edto'),
            'route': self._extract_route(cleaned_text),
            'all_airports': self._extract_all_airports(cleaned_text),
            'confidence': self._calculate_confidence(cleaned_text)
        }
        
        return result
    
    def _extract_by_packages(self, text: str) -> Dict[str, str]:
        """PACKAGE별로 정보 추출 (유연한 구분)"""
        # 원본 텍스트 사용 (대문자 변환 전)
        original_lines = text.split('\n')
        package_info = {}
        
        # 디버깅: 처음 10줄 출력
        print(f"=== _extract_by_packages 디버깅 ===")
        print(f"전체 텍스트 길이: {len(text)} 문자")
        print(f"총 줄 수: {len(original_lines)}")
        print("처음 4줄:")
        for i, line in enumerate(original_lines[:4]):
            print(f"  줄 {i+1}: '{line}'")
        
        # DEP, DEST, ALTN 추출 (3번째 줄에서 정확한 패턴 우선)
        # 3번째 줄: "DEP: RKSI DEST: KSEA ALTN: KPDX SECY"
        
        # 3번째 줄에서 정확한 패턴 추출 시도
        if len(original_lines) >= 3:
            line3 = original_lines[2].upper().strip()  # 3번째 줄 (0-based index)
            print(f"3번째 줄 분석: '{line3}'")
            
            # DEP: RKSI DEST: KSEA ALTN: KPDX 패턴 매칭
            dep_match = re.search(r'DEP:\s*([A-Z]{4})\s+DEST:', line3)
            dest_match = re.search(r'DEST:\s*([A-Z]{4})\s+ALTN:', line3)
            altn_match = re.search(r'ALTN:\s*([A-Z]{4})', line3)
            
            if dep_match:
                dep_code = dep_match.group(1)
                if self._is_valid_airport(dep_code):
                    package_info['dep'] = dep_code
                    print(f"DEP 추출 (3번째 줄): {dep_code}")
            
            if dest_match:
                dest_code = dest_match.group(1)
                if self._is_valid_airport(dest_code):
                    package_info['dest'] = dest_code
                    print(f"DEST 추출 (3번째 줄): {dest_code}")
            
            if altn_match:
                altn_code = altn_match.group(1)
                if self._is_valid_airport(altn_code):
                    package_info['altn'] = altn_code
                    print(f"ALTN 추출 (3번째 줄): {altn_code}")
        
        # 3번째 줄에서 추출 실패 시 다른 패턴 시도
        if not package_info.get('dep') or not package_info.get('dest'):
            print("3번째 줄에서 추출 실패, 다른 패턴 시도...")
            
            # 전체 텍스트에서 DEP/DEST/ALTN 패턴 검색
            for i, line in enumerate(original_lines):
                line_upper = line.upper().strip()
                
                # DEP: RKSI DEST: KSEA ALTN: KPDX 형태 찾기
                if 'DEP:' in line_upper and 'DEST:' in line_upper and 'ALTN:' in line_upper:
                    print(f"패턴 발견 (라인 {i+1}): '{line}'")
                    
                    dep_match = re.search(r'DEP:\s*([A-Z]{4})\s+DEST:', line_upper)
                    dest_match = re.search(r'DEST:\s*([A-Z]{4})\s+ALTN:', line_upper)
                    altn_match = re.search(r'ALTN:\s*([A-Z]{4})', line_upper)
                    
                    if dep_match and not package_info.get('dep'):
                        dep_code = dep_match.group(1)
                        if self._is_valid_airport(dep_code):
                            package_info['dep'] = dep_code
                            print(f"DEP 추출 (라인 {i+1}): {dep_code}")
                    
                    if dest_match and not package_info.get('dest'):
                        dest_code = dest_match.group(1)
                        if self._is_valid_airport(dest_code):
                            package_info['dest'] = dest_code
                            print(f"DEST 추출 (라인 {i+1}): {dest_code}")
                    
                    if altn_match and not package_info.get('altn'):
                        altn_code = altn_match.group(1)
                        if self._is_valid_airport(altn_code):
                            package_info['altn'] = altn_code
                            print(f"ALTN 추출 (라인 {i+1}): {altn_code}")
                    break
        
        print(f"추출된 package_info: {package_info}")
        print("=== 디버깅 완료 ===")
        
        # REFILE과 EDTO 추출 (DEP/DEST와 동일한 방식)
        # REFILE: PANC PAED 형태에서 추출
        # EDTO: RJCC PACD CYVR 형태에서 추출
        for i, line in enumerate(original_lines):
            line_upper = line.upper().strip()
            
            # REFILE: PANC PAED 형태에서 추출 (DEP/DEST와 동일한 방식)
            if 'REFILE:' in line_upper and 'refile' not in package_info:
                print(f"REFILE 라인 발견 (라인 {i+1}): '{line}'")
                # DEP/DEST와 동일한 패턴으로 추출
                refile_match = re.search(r'REFILE:\s*([A-Z\s]+)', line_upper)
                if refile_match:
                    airports_text = refile_match.group(1).strip()
                    airports = re.findall(self.airport_pattern, airports_text)
                    valid_airports = [airport for airport in airports if self._is_valid_airport(airport)]
                    if valid_airports:
                        package_info['refile'] = ' '.join(valid_airports)
                        print(f"REFILE 추출 (라인 {i+1}): {package_info['refile']}")
            
            # EDTO: RJCC PACD CYVR 형태에서 추출 (모든 공항 포함)
            if 'EDTO:' in line_upper and 'edto' not in package_info:
                print(f"EDTO 라인 발견 (라인 {i+1}): '{line}'")
                # EDTO 패턴으로 추출
                edto_match = re.search(r'EDTO:\s*([A-Z\s]+)', line_upper)
                if edto_match:
                    airports_text = edto_match.group(1).strip()
                    airports = re.findall(self.airport_pattern, airports_text)
                    valid_airports = [airport for airport in airports if self._is_valid_airport(airport)]
                    if valid_airports:
                        # EDTO는 모든 공항을 공백으로 구분하여 저장
                        package_info['edto'] = ' '.join(valid_airports)
                        print(f"EDTO 추출 (라인 {i+1}): {package_info['edto']} (개별: {valid_airports})")
        
        return package_info
    
    def _split_by_packages(self, lines: List[str]) -> Dict[str, List[str]]:
        """PACKAGE별로 라인 분리"""
        package_sections = {}
        current_package = None
        current_lines = []
        
        for i, line in enumerate(lines):
            line_upper = line.upper().strip()
            
            # PACKAGE 헤더 감지
            if 'PACKAGE' in line_upper and ('PACKAGE 1' in line_upper or 'PACKAGE 2' in line_upper or 'PACKAGE 3' in line_upper):
                # 이전 PACKAGE 저장
                if current_package and current_lines:
                    package_sections[current_package] = current_lines
                
                # 새 PACKAGE 시작
                if 'PACKAGE 1' in line_upper:
                    current_package = 'PACKAGE 1'
                elif 'PACKAGE 2' in line_upper:
                    current_package = 'PACKAGE 2'
                elif 'PACKAGE 3' in line_upper:
                    current_package = 'PACKAGE 3'
                else:
                    current_package = None
                
                current_lines = []
                # PACKAGE 헤더 자체는 포함하지 않음
                continue
            
            # PACKAGE 1 끝 감지 (END OF KOREAN AIR NOTAM PACKAGE 1)
            if 'END OF KOREAN AIR NOTAM PACKAGE 1' in line_upper:
                # PACKAGE 1 저장
                if current_package == 'PACKAGE 1' and current_lines:
                    package_sections[current_package] = current_lines
                current_package = None
                current_lines = []
                continue
            
            # PACKAGE 내 라인 추가
            if current_package:
                current_lines.append(line)
        
        # 마지막 PACKAGE 저장
        if current_package and current_lines:
            package_sections[current_package] = current_lines
        
        return package_sections
    
    def _clean_text(self, text: str) -> str:
        """텍스트 정리"""
        # 대문자 변환
        text = text.upper()
        
        # 불필요한 문자 제거
        text = re.sub(r'[^\w\s\.\-]', ' ', text)
        
        # 연속 공백 제거
        text = re.sub(r'\s+', ' ', text)
        
        return text.strip()
    
    def _extract_airport_by_keyword(self, text: str, airport_type: str) -> Optional[str]:
        """키워드 기반 공항 추출"""
        keywords = self.flight_keywords[airport_type]
        
        # 여러 PACKAGE에서 검색 (PACKAGE 1, 2, 3 등)
        lines = text.split('\n')
        
        # PACKAGE별로 검색
        for i, line in enumerate(lines):
            line_upper = line.upper()
            
            # PACKAGE 헤더 라인인지 확인
            if 'PACKAGE' in line_upper and i + 1 < len(lines):
                # 다음 줄도 확인 (KE0041 / ICN / SEA 형태)
                next_line = lines[i + 1].upper()
                
                for keyword in keywords:
                    # 현재 줄에서 검색
                    pattern = rf'{keyword}[:\s]+({self.airport_pattern})'
                    match = re.search(pattern, line_upper)
                    if match:
                        airport_code = match.group(1)
                        if self._is_valid_airport(airport_code):
                            return airport_code
                    
                    # 다음 줄에서 검색
                    match = re.search(pattern, next_line)
                    if match:
                        airport_code = match.group(1)
                        if self._is_valid_airport(airport_code):
                            return airport_code
        
        # PACKAGE에서 찾지 못한 경우 전체 텍스트에서 검색 (더 정확한 패턴)
        for keyword in keywords:
            # 더 정확한 패턴: 키워드 뒤에 공항 코드만 오도록
            pattern = rf'{keyword}[:\s]+({self.airport_pattern})(?:\s|$|[^\w])'
            match = re.search(pattern, text)
            
            if match:
                airport_code = match.group(1)
                if self._is_valid_airport(airport_code):
                    return airport_code
        
        # EDTO의 경우 여러 공항이 있을 수 있으므로 특별 처리
        if airport_type == 'edto':
            return self._extract_edto_airports(text)
        
        return None
    
    def _extract_edto_airports(self, text: str) -> Optional[str]:
        """EDTO 공항 추출 (여러 공항 중 첫 번째)"""
        # EDTO: RJCC PANC CYVR 형태에서 첫 번째 공항 추출
        pattern = r'EDTO[:\s]+([A-Z]{3,4})'
        match = re.search(pattern, text)
        
        if match:
            airport_code = match.group(1)
            if self._is_valid_airport(airport_code):
                return airport_code
        
        return None
    
    def _extract_multiple_airports_by_keyword(self, text: str, airport_type: str) -> Optional[str]:
        """키워드 기반 여러 공항 추출 (REFILE, EDTO용)"""
        keywords = self.flight_keywords[airport_type]
        
        # PACKAGE별로 검색하여 첫 번째로 찾은 것만 사용
        lines = text.split('\n')
        
        for i, line in enumerate(lines):
            line_upper = line.upper()
            
            # PACKAGE 헤더 라인인지 확인
            if 'PACKAGE' in line_upper:
                # PACKAGE 섹션에서 검색
                for j in range(i, min(i + 10, len(lines))):  # PACKAGE 다음 10줄까지 검색
                    package_line = lines[j].upper()
                    
                    for keyword in keywords:
                        pattern = rf'{keyword}[:\s]+((?:{self.airport_pattern}\s*)+)'
                        match = re.search(pattern, package_line)
                        
                        if match:
                            airports_text = match.group(1).strip()
                            airports = re.findall(self.airport_pattern, airports_text)
                            
                            # 유효한 공항만 필터링
                            valid_airports = []
                            for airport in airports:
                                if self._is_valid_airport(airport):
                                    valid_airports.append(airport)
                            
                            if valid_airports:
                                return ' '.join(valid_airports)
        
        # PACKAGE에서 찾지 못한 경우 전체 텍스트에서 검색
        for keyword in keywords:
            pattern = rf'{keyword}[:\s]+((?:{self.airport_pattern}\s*)+)'
            match = re.search(pattern, text)
            
            if match:
                airports_text = match.group(1).strip()
                airports = re.findall(self.airport_pattern, airports_text)
                
                # 유효한 공항만 필터링
                valid_airports = []
                for airport in airports:
                    if self._is_valid_airport(airport):
                        valid_airports.append(airport)
                
                if valid_airports:
                    return ' '.join(valid_airports)
        
        return None
    
    def _extract_route(self, text: str) -> Optional[str]:
        """항로 정보 추출"""
        keywords = self.flight_keywords['route']
        
        for keyword in keywords:
            # 키워드 뒤의 항로 정보 찾기
            pattern = rf'{keyword}[:\s]+([A-Z0-9\.\s\-]+?)(?:\n|$)'
            match = re.search(pattern, text)
            
            if match:
                route = match.group(1).strip()
                if len(route) > 10:  # 의미있는 길이
                    return route
        
        return None
    
    def _extract_all_airports(self, text: str) -> List[str]:
        """모든 공항 코드 추출"""
        airports = re.findall(self.airport_pattern, text)
        
        # 유효한 공항만 필터링
        valid_airports = []
        for airport in airports:
            if self._is_valid_airport(airport):
                valid_airports.append(airport)
        
        # 중복 제거
        return list(set(valid_airports))
    
    def _is_valid_airport(self, code: str) -> bool:
        """유효한 공항 코드인지 확인"""
        # 길이 확인 (4자리만 허용)
        if len(code) != 4:
            return False
        
        # 알파벳만 포함
        if not code.isalpha():
            return False
        
        # 일반적인 공항 코드인지 확인
        if code in self.common_airports:
            return True
        
        # 패턴 기반 확인
        # ICAO 코드 패턴 (첫 글자로 지역 구분)
        if code[0] in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
            return True
        
        return False
    
    def _calculate_confidence(self, text: str) -> Dict[str, float]:
        """추출 신뢰도 계산"""
        confidence = {
            'dep': 0.0,
            'dest': 0.0,
            'altn': 0.0,
            'refile': 0.0,
            'edto': 0.0,
            'overall': 0.0
        }
        
        # 키워드 존재 여부로 신뢰도 계산
        for airport_type in ['dep', 'dest', 'altn', 'refile', 'edto']:
            keywords = self.flight_keywords[airport_type]
            for keyword in keywords:
                if keyword in text:
                    confidence[airport_type] += 0.3
            
            # 최대 1.0으로 제한
            confidence[airport_type] = min(confidence[airport_type], 1.0)
        
        # 전체 신뢰도
        confidence['overall'] = sum([confidence[key] for key in ['dep', 'dest', 'altn', 'refile', 'edto']]) / 5
        
        return confidence
    
    def extract_from_notam_data(self, notams_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        NOTAM 데이터 리스트에서 항공편 정보 추출
        
        Args:
            notams_data: NOTAM 데이터 리스트
            
        Returns:
            Dict[str, Any]: 추출된 항공편 정보
        """
        # 모든 NOTAM 텍스트 결합
        all_text = ""
        for notam in notams_data:
            text = notam.get('text', '')
            description = notam.get('description', '')
            all_text += f" {text} {description}"
        
        # 항공편 정보 추출
        flight_info = self.extract_flight_info(all_text)
        
        # NOTAM별 상세 정보 추가
        flight_info['notam_details'] = []
        for notam in notams_data:
            notam_text = f"{notam.get('text', '')} {notam.get('description', '')}"
            notam_flight_info = self.extract_flight_info(notam_text)
            
            if any(notam_flight_info[key] for key in ['dep', 'dest', 'altn', 'edto']):
                flight_info['notam_details'].append({
                    'notam_id': notam.get('notam_number', ''),
                    'airports': notam.get('airports', []),
                    'flight_info': notam_flight_info
                })
        
        return flight_info

def extract_flight_info_from_notams(notams_data) -> Dict[str, Any]:
    """
    NOTAM 데이터에서 항공편 정보 추출 (편의 함수)
    
    Args:
        notams_data: NOTAM 데이터 리스트 또는 NOTAM 텍스트
        
    Returns:
        Dict[str, Any]: 추출된 항공편 정보
    """
    extractor = FlightInfoExtractor()
    
    # 텍스트인 경우 직접 추출
    if isinstance(notams_data, str):
        return extractor.extract_flight_info(notams_data)
    return extractor.extract_from_notam_data(notams_data)
