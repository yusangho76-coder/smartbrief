#!/usr/bin/env python3
"""
PDF에서 크로스 차트 페이지(상단 우측에 Wind Isotach Isotherm VWS 범례가 있는 페이지)를
찾아 해당 페이지만 JPG 이미지로 추출합니다.
"""
import os
import sys

# find_and_analyze_cross_section에서 함수 사용
try:
    from find_and_analyze_cross_section import (
        find_cross_chart_page_by_legend,
        find_cross_chart_page_by_label,
        export_cross_chart_page_to_jpg,
    )
except ImportError:
    find_cross_chart_page_by_legend = None
    find_cross_chart_page_by_label = None
    export_cross_chart_page_to_jpg = None


def main():
    if len(sys.argv) < 2:
        print("사용법: python3 extract_cross_chart_image.py <PDF경로> [출력JPG경로] [페이지번호]")
        print("  페이지번호: 생략 시 'Wind Isotach Isotherm VWS' 범례로 자동 검색. 차트가 이미지일 경우 1부터 시작하는 페이지 번호 지정.")
        print("예: python3 extract_cross_chart_image.py uploads/ImportantFile_14.pdf")
        print("예: python3 extract_cross_chart_image.py uploads/ImportantFile_14.pdf output/cross_chart.jpg")
        print("예: python3 extract_cross_chart_image.py uploads/ImportantFile_14.pdf '' 21   # 21페이지를 JPG로 저장")
        sys.exit(1)

    pdf_path = sys.argv[1]
    output_path = None
    page_one_based = None
    if len(sys.argv) >= 4:
        output_path = sys.argv[2] or None
        try:
            page_one_based = int(sys.argv[3])
        except ValueError:
            pass
    elif len(sys.argv) == 3:
        if sys.argv[2].strip().isdigit():
            page_one_based = int(sys.argv[2])
        else:
            output_path = sys.argv[2] or None

    if not os.path.exists(pdf_path):
        print(f"파일을 찾을 수 없습니다: {pdf_path}")
        sys.exit(1)

    if not export_cross_chart_page_to_jpg:
        print("find_and_analyze_cross_section 모듈을 불러올 수 없습니다.")
        sys.exit(1)

    page_index = None
    if page_one_based is not None:
        page_index = page_one_based - 1
        if page_index < 0:
            print("페이지 번호는 1 이상이어야 합니다.")
            sys.exit(1)
        print(f"지정한 페이지 {page_one_based}를 JPG로 추출합니다.")
    else:
        # 1) 범례(Wind Isotach Isotherm VWS)로 검색
        pages = find_cross_chart_page_by_legend(pdf_path) if find_cross_chart_page_by_legend else []
        if not pages and find_cross_chart_page_by_label:
            # 2) split.txt에 나오는 'cross' 라벨 페이지로 검색
            pages = find_cross_chart_page_by_label(pdf_path)
            if pages:
                print("'cross' 라벨 페이지로 크로스 차트를 찾았습니다.")
        if not pages:
            print("크로스 차트 페이지를 찾지 못했습니다.")
            print("  - 범례(Wind Isotach Isotherm VWS) 또는 텍스트 'cross' 로 검색했습니다.")
            print("  - 차트가 이미지로만 되어 있으면, 페이지 번호를 직접 지정하세요.")
            print("예: python3 extract_cross_chart_image.py \"{}\" 21".format(pdf_path))
            sys.exit(1)
        page_index = pages[0]

    saved = export_cross_chart_page_to_jpg(pdf_path, page_index, output_path)
    if saved:
        print(f"크로스 차트 페이지 {page_index + 1} → 저장됨: {saved}")
    else:
        print("JPG 저장에 실패했습니다.")
        sys.exit(1)


if __name__ == "__main__":
    main()
