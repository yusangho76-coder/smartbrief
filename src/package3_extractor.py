"""
Package 3 NOTAM 추출 모듈

split.txt 파일에서 "KOREAN AIR NOTAM PACKAGE 3" 섹션만 추출하여
새로운 파일로 저장하는 기능을 제공합니다.
"""

import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


from typing import Optional

def extract_package3_from_file(input_file_path: str, output_dir: Optional[str] = None) -> str:
    """
    split.txt 파일에서 Package 3 섹션만 추출하여 새로운 파일로 저장
    
    Args:
        input_file_path: 입력 파일 경로 (예: temp/20251027_172500_Notam-20251027_split.txt)
        output_dir: 출력 디렉토리 (기본값: temp)
    
    Returns:
        생성된 파일의 경로
    """
    try:
        # 입력 파일 읽기
        if not os.path.exists(input_file_path):
            raise FileNotFoundError(f"입력 파일을 찾을 수 없습니다: {input_file_path}")
        
        with open(input_file_path, 'r', encoding='utf-8') as f:
            full_text = f.read()
        
        logger.info(f"📄 입력 파일 읽기 완료: {len(full_text)} 문자")
        
        # Package 3 섹션 찾기
        package3_start = full_text.find("KOREAN AIR NOTAM PACKAGE 3")
        if package3_start == -1:
            raise ValueError("Package 3 섹션을 찾을 수 없습니다.")
        
        package3_end = full_text.find("END OF KOREAN AIR NOTAM PACKAGE 3", package3_start)
        if package3_end == -1:
            logger.warning("Package 3 섹션의 끝을 찾을 수 없습니다. 파일 끝까지 추출합니다.")
            package3_text = full_text[package3_start:]
        else:
            package3_end += len("END OF KOREAN AIR NOTAM PACKAGE 3")
            package3_text = full_text[package3_start:package3_end]
        
        logger.info(f"✅ Package 3 추출 완료: {len(package3_text)} 문자")
        
        # 출력 파일 경로 생성
        if output_dir is None:
            output_dir = os.path.dirname(input_file_path) or 'temp'
        
        os.makedirs(output_dir, exist_ok=True)
        
        # 출력 파일명 생성 (원본 파일명 기반)
        input_filename = os.path.basename(input_file_path)
        base_name = input_filename.replace('_split.txt', '').replace('.txt', '')
        output_filename = f"{base_name}_package3.txt"
        output_path = os.path.join(output_dir, output_filename)
        
        # Package 3 텍스트 저장
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(package3_text)
        
        logger.info(f"💾 Package 3 파일 저장 완료: {output_path}")
        
        return output_path
        
    except Exception as e:
        logger.error(f"❌ Package 3 추출 중 오류: {str(e)}")
        raise


def read_package3_file(file_path: str) -> str:
    """
    Package 3 파일을 읽어서 문자열로 반환
    
    Args:
        file_path: Package 3 파일 경로
    
    Returns:
        Package 3 텍스트 내용
    """
    try:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"파일을 찾을 수 없습니다: {file_path}")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        logger.info(f"📄 Package 3 파일 읽기 완료: {len(content)} 문자")
        return content
        
    except Exception as e:
        logger.error(f"❌ Package 3 파일 읽기 중 오류: {str(e)}")
        raise


def get_latest_split_file(temp_dir: str = 'temp') -> str:
    """
    temp 디렉토리에서 가장 최근의 split.txt 파일 찾기
    
    Args:
        temp_dir: temp 디렉토리 경로
    
    Returns:
        가장 최근 split.txt 파일의 경로
    """
    try:
        if not os.path.exists(temp_dir):
            raise FileNotFoundError(f"temp 디렉토리를 찾을 수 없습니다: {temp_dir}")
        
        # split.txt로 끝나는 파일들 찾기
        split_files = [f for f in os.listdir(temp_dir) if f.endswith('_split.txt')]
        
        if not split_files:
            raise FileNotFoundError("split.txt 파일을 찾을 수 없습니다.")
        
        # 파일 수정 시간 기준으로 정렬
        split_files_with_time = []
        for filename in split_files:
            file_path = os.path.join(temp_dir, filename)
            mtime = os.path.getmtime(file_path)
            split_files_with_time.append((mtime, file_path))
        
        # 가장 최근 파일 선택
        split_files_with_time.sort(reverse=True)
        latest_file = split_files_with_time[0][1]
        
        logger.info(f"🔍 가장 최근 split.txt 파일: {latest_file}")
        return latest_file
        
    except Exception as e:
        logger.error(f"❌ split.txt 파일 찾기 중 오류: {str(e)}")
        raise


def extract_and_analyze_package3(route: str, split_file_path: Optional[str] = None, **kwargs):
    """
    split.txt에서 Package 3를 추출하고 AI 항로 분석 수행
    
    Args:
        route: 분석할 항로
        split_file_path: split.txt 파일 경로 (None이면 자동으로 최근 파일 찾기)
        **kwargs: AI 분석에 필요한 추가 파라미터
    
    Returns:
        AI 분석 결과 문자열
    """
    from src.ai_route_analyzer import analyze_route_with_gemini
    
    try:
        # split.txt 파일 찾기
        if split_file_path is None:
            split_file_path = get_latest_split_file()
            logger.info(f"📂 자동 선택된 파일: {split_file_path}")
        
        # Package 3 추출
        package3_file_path = extract_package3_from_file(split_file_path)
        
        # Package 3 파일 읽기
        package3_content = read_package3_file(package3_file_path)
        
        # AI 항로 분석 수행 (Package 3 텍스트를 리스트로 전달)
        notam_data = [package3_content]
        
        logger.info(f"🚀 AI 항로 분석 시작 - 경로: {route}")
        analysis_result = analyze_route_with_gemini(
            route=route,
            notam_data=notam_data,
            **kwargs
        )
        
        logger.info(f"✅ AI 항로 분석 완료")
        
        return {
            'analysis_result': analysis_result,
            'package3_file': package3_file_path,
            'split_file': split_file_path
        }
        
    except Exception as e:
        logger.error(f"❌ Package 3 추출 및 분석 중 오류: {str(e)}")
        raise


# 테스트용 메인 함수
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 테스트: 가장 최근 split.txt에서 Package 3 추출
    try:
        latest_split = get_latest_split_file('temp')
        print(f"\n가장 최근 파일: {latest_split}")
        
        package3_path = extract_package3_from_file(latest_split)
        print(f"\nPackage 3 추출 완료: {package3_path}")
        
        # Package 3 내용 미리보기
        with open(package3_path, 'r', encoding='utf-8') as f:
            content = f.read()
            print(f"\nPackage 3 내용 미리보기 (처음 500자):")
            print("-" * 80)
            print(content[:500])
            print("-" * 80)
            
    except Exception as e:
        print(f"\n오류 발생: {str(e)}")
