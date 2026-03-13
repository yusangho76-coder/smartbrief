#!/usr/bin/env python3
"""
PDF에서 'KOREAN AIR NOTAM PACKAGE 1' 이전에 나오는 sigwx1, asc, cross
라벨 페이지를 찾아 각각 JPG로 저장합니다.
"""
import os
import sys

try:
    from find_and_analyze_cross_section import (
        find_weather_chart_pages_before_notam,
        export_cross_chart_page_to_jpg,
    )
except ImportError:
    find_weather_chart_pages_before_notam = None
    export_cross_chart_page_to_jpg = None


def main():
    if len(sys.argv) < 2:
        print("사용법: python3 extract_weather_charts_images.py <PDF경로> [출력디렉터리]")
        print("  출력디렉터리 생략 시 PDF와 같은 디렉터리에 저장.")
        print("  생성 파일: {PDF이름}_sigwx1.jpg, {PDF이름}_asc.jpg, {PDF이름}_cross.jpg")
        sys.exit(1)

    pdf_path = sys.argv[1]
    out_dir = sys.argv[2] if len(sys.argv) > 2 else None

    if not os.path.exists(pdf_path):
        print(f"파일을 찾을 수 없습니다: {pdf_path}")
        sys.exit(1)

    if not find_weather_chart_pages_before_notam or not export_cross_chart_page_to_jpg:
        print("find_and_analyze_cross_section 모듈을 불러올 수 없습니다.")
        sys.exit(1)

    base_name = os.path.splitext(os.path.basename(pdf_path))[0]
    if out_dir is None:
        out_dir = os.path.dirname(os.path.abspath(pdf_path))
    os.makedirs(out_dir, exist_ok=True)

    pages = find_weather_chart_pages_before_notam(pdf_path)
    if not pages:
        print("sigwx1, asc, cross 페이지를 찾지 못했습니다. (KOREAN AIR NOTAM PACKAGE 1 이전)")
        sys.exit(1)

    saved = []
    for label in ("sigwx1", "asc", "cross"):
        if label not in pages:
            print(f"  '{label}' 페이지 없음, 건너뜀.")
            continue
        page_index = pages[label]
        output_path = os.path.join(out_dir, f"{base_name}_{label}.jpg")
        path = export_cross_chart_page_to_jpg(pdf_path, page_index, output_path=output_path)
        if path:
            saved.append((label, page_index + 1, path))
            print(f"  {label} (페이지 {page_index + 1}) → {path}")

    if not saved:
        print("JPG로 저장된 파일이 없습니다.")
        sys.exit(1)
    print(f"\n총 {len(saved)}개 JPG 저장 완료.")


if __name__ == "__main__":
    main()
