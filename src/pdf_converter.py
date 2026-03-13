import os
import re
import pdfplumber
import logging
from typing import List, Dict, Any

class PDFConverter:
    """PDF를 텍스트로 변환하고 NOTAM을 분리하는 클래스"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def _extract_text_from_pdf(self, pdf_path: str) -> str:
        """PDF에서 텍스트 추출"""
        all_text = ""
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    all_text += page_text + "\n"
        
        # 인코딩 문제 패턴 제거
        all_text = self._clean_encoding_issues(all_text)
        return all_text
    
    def _clean_encoding_issues(self, text: str) -> str:
        """인코딩 문제 패턴들을 제거"""
        # 인코딩 문제 패턴들
        encoding_patterns = [
            r'â—A¼IR WAY',
            r'â—A¼IR SPACE', 
            r'â—C¼O MPANY',
            r'â—C¼O MMUNICATION',
            r'â—[A-Z]¼[A-Z] [A-Z]+',  # 일반적인 패턴
        ]
        
        for pattern in encoding_patterns:
            text = re.sub(pattern, '', text)
        
        return text
    
    def _detect_notam_type(self, text: str) -> str:
        """NOTAM 유형 감지 (pdf_to_txt_auto.py 기반)"""
        if 'KOREAN AIR NOTAM PACKAGE' in text.upper():
            return 'package'
        return 'airport'
    
    def _process_airport_notam(self, pdf_path: str, save_temp=True) -> str:
        """공항 NOTAM 처리 (pdf_to_txt_test_airport.py 기반)"""
        all_text = self._extract_text_from_pdf(pdf_path)
        
        def split_notams(text):
            """NOTAM 분리 함수 (pdf_to_txt_test_airport.py 기반)"""
            lines = text.split('\n')
            notams = []
            current_notam = []
            
            # robust pattern: 날짜-날짜, 날짜-UFN, 날짜-PERM 모두 허용
            # COAD 형식도 포함 (예: 27FEB25 00:00 - UFN KSEA COAD01/25)
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
                    continue  # 첫 NOTAM 시작 전까지는 무시
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
            """불필요한 키워드가 포함된 줄 제거 (pdf_to_txt_test_airport.py 기반)"""
            # COAD 형식은 보존하고, OCR 오류 패턴만 제거
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
                import re
                if re.search(r'^[◼■]\s*[A-Z\s/]+$', line.strip()):
                    continue
                cleaned_lines.append(line)
            return '\n'.join(cleaned_lines)

        split_notams_list = split_notams(all_text)
        # 필터링을 NOTAM 분리 후에 적용 (pdf_to_txt_test_airport.py와 동일)
        split_notams_list_cleaned = [remove_unwanted_lines_from_notam(notam) for notam in split_notams_list]

        if save_temp:
            base_name = os.path.splitext(os.path.basename(pdf_path))[0]
            out_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'temp', base_name + "_split.txt")
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            
            with open(out_path, "w", encoding="utf-8") as f:
                for notam in split_notams_list_cleaned:
                    f.write(notam + "\n" + ("="*60) + "\n")

        return '\n\n'.join(split_notams_list_cleaned) + '\n'
    
    def _process_package_notam(self, pdf_path: str, save_temp=True) -> str:
        """패키지 NOTAM 처리 (pdf_to_txt_test_package.py 기반)"""
        all_text = self._extract_text_from_pdf(pdf_path)

        def merge_notam_lines(text):
            """NOTAM 라인 병합 (pdf_to_txt_test_package.py 기반)"""
            lines = text.split('\n')
            # 삭제할 키워드 목록
            unwanted_keywords = [
                'â—R¼A MP', 'â—O¼B STRUCTION', 'â—G¼P S', 'â—R¼U NWAY', 'â—A¼PP ROACH', 'â—T¼A XIWAY',
                'â—N¼A VAID', 'â—D¼E PARTURE', 'â—R¼U NWAY LIGHT', 'â—A¼IP', 'â—O¼T HER'
            ]
            # 불필요한 키워드가 포함된 줄 삭제
            filtered_lines = [line for line in lines if not any(keyword in line for keyword in unwanted_keywords)]
            merged_lines = []
            i = 0
            
            # 더 정확한 패턴들
            notam_id_pattern = r'^[A-Z]{4}(?:\s+[A-Z]+(?:\s+[A-Z]+)*)?\s+\d{1,3}/\d{2}$|^[A-Z]{4}\s+[A-Z]\d{4}/\d{2}$'
            coad_pattern = r'^[A-Z]{4}\s+COAD\d{2}/\d{2}$'  # COAD 패턴 추가
            date_line_pattern = r'^(?:\d+\.\s+)?\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*-'  # "1. " 패턴 포함
            
            while i < len(filtered_lines):
                line = filtered_lines[i].strip()
                
                # COAD NOTAM ID 패턴 체크
                if re.match(coad_pattern, line):
                    # 다음 줄이 날짜 패턴이면 합침
                    if i + 1 < len(filtered_lines) and re.match(date_line_pattern, filtered_lines[i+1].strip()):
                        next_line = filtered_lines[i+1].strip()
                        # "1. " 같은 번호 접두사 제거
                        cleaned_date_line = re.sub(r'^\d+\.\s+', '', next_line)
                        merged_lines.append(f"{cleaned_date_line} {line}")
                        i += 2
                        continue
                
                # 일반 NOTAM ID 패턴 체크
                elif re.match(notam_id_pattern, line):
                    # 다음 줄이 날짜 패턴이면 합침
                    if i + 1 < len(filtered_lines) and re.match(date_line_pattern, filtered_lines[i+1].strip()):
                        next_line = filtered_lines[i+1].strip()
                        # "1. " 같은 번호 접두사 제거
                        cleaned_date_line = re.sub(r'^\d+\.\s+', '', next_line)
                        merged_lines.append(f"{cleaned_date_line} {line}")
                        i += 2
                        continue
                
                merged_lines.append(line)
                i += 1
            return '\n'.join(merged_lines)

        merged_text = merge_notam_lines(all_text)

        def split_notams(text):
            """NOTAM 분리 함수 (pdf_to_txt_test_package.py 기반)"""
            lines = text.split('\n')
            notams = []
            current_notam = []
            # 패턴 정의
            notam_start_pattern = r'^\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*-'
            section_start_pattern = r'^\[.*\]'
            notam_id_pattern = r'^[A-Z]{4}(?:\s+[A-Z]+)?\s*\d{1,3}/\d{2}$|^[A-Z]{4}\s+[A-Z]\d{4}/\d{2}$|^[A-Z]{4}\s+COAD\d{2}/\d{2}$'
            end_phrase_pattern = r'ANY CHANGE WILL BE NOTIFIED BY NOTAM\.'
            # COAD 항목 분리를 위한 패턴 (예: "1. 20FEB25 00:00 - UFN RKSI COAD01/25")
            coad_item_pattern = r'^\d+\.\s+\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*-.*COAD\d{2}/\d{2}'

            for line in lines:
                # 다음 NOTAM 시작, 섹션 시작, NOTAM ID 등장, COAD 항목 시작 시 끊기
                if (re.match(notam_start_pattern, line) or 
                    re.match(section_start_pattern, line) or 
                    re.match(notam_id_pattern, line) or
                    re.match(coad_item_pattern, line)):
                    if current_notam:
                        notams.append('\n'.join(current_notam).strip())
                        current_notam = []
                current_notam.append(line)
                # 끝 문구 등장 시 강제 끊기
                if re.search(end_phrase_pattern, line):
                    notams.append('\n'.join(current_notam).strip())
                    current_notam = []
            if current_notam:
                notams.append('\n'.join(current_notam).strip())
            return notams

        split_notams_list = split_notams(merged_text)
        # 분리된 NOTAM에서 불필요한 키워드 줄 제거
        unwanted_keywords = [
            'â—R¼A MP', 'â—O¼B STRUCTION', 'â—G¼P S', 'â—R¼U NWAY', 'â—A¼PP ROACH', 'â—T¼A XIWAY',
            'â—N¼A VAID', 'â—D¼E PARTURE', 'â—R¼U NWAY LIGHT', 'â—A¼IP', 'â—O¼T HER', 'â—A¼IR PORT'
        ]
        def remove_unwanted_lines_from_notam(notam):
            lines = notam.split('\n')
            cleaned_lines = []
            import re
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

        if save_temp:
            base_name = os.path.splitext(os.path.basename(pdf_path))[0]
            out_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'temp', base_name + "_split.txt")
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            
            with open(out_path, "w", encoding="utf-8") as f:
                for notam in split_notams_list_cleaned:
                    f.write(notam + "\n" + ("="*60) + "\n")

        return '\n\n'.join(split_notams_list_cleaned) + '\n'
    
    def get_raw_pdf_text(self, pdf_path: str) -> str:
        """
        NOTAM 분리/가공 없이 PDF 전체 페이지를 순서대로 추출한 원문.
        REFILE·OFP 등 블록 경계와 무관하게 분석할 때 사용.
        """
        return self._extract_text_from_pdf(pdf_path)

    def convert_pdf_to_text(self, pdf_path: str, save_temp=True) -> str:
        """
        PDF 파일을 텍스트로 변환하고, 유형을 자동 감지하여 적절한 처리 적용
        """
        try:
            self.logger.info(f"PDF 파일에서 텍스트 추출 시작: {pdf_path}")
            all_text = self._extract_text_from_pdf(pdf_path)
            self.logger.info(f"원본 텍스트 추출 완료: {len(all_text)} 문자")
            
            if not all_text.strip():
                self.logger.warning("추출된 텍스트가 비어있습니다.")
                return ""
            
            notam_type = self._detect_notam_type(all_text)
            self.logger.info(f"NOTAM 유형 감지: {notam_type}")
            
            if notam_type == 'package':
                self.logger.info("패키지 NOTAM 처리 시작")
                result = self._process_package_notam(pdf_path, save_temp=save_temp)
            else:
                self.logger.info("공항 NOTAM 처리 시작")
                result = self._process_airport_notam(pdf_path, save_temp=save_temp)
            
            self.logger.info(f"NOTAM 처리 완료: {len(result)} 문자")
            return result
            
        except Exception as e:
            self.logger.error(f"PDF 변환 중 오류 발생: {str(e)}")
            import traceback
            self.logger.error(f"상세 오류: {traceback.format_exc()}")
            raise Exception(f"PDF 변환 중 오류가 발생했습니다: {str(e)}")
