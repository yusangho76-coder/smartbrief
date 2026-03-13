#!/usr/bin/env python3
"""
4개 PDF로 루트 추출 테스트: extract_route_from_page2 + ats_route_extractor
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import extract_route_from_page2
from src.ats_route_extractor import extract_ofp_route_from_page
import pdfplumber

PDFS = [
    "uploads/ImportantFile 13.pdf",
    "uploads/20260226_192557_5121ad2a_ImportantFile_12.pdf",
    "uploads/20260228_003610_979ab882_ImportantFile_13.pdf",
    "uploads/20260228_004431_52a04512_ImportantFile_13.pdf",
]

def main():
    base = os.path.dirname(os.path.abspath(__file__))
    for rel in PDFS:
        path = os.path.join(base, rel)
        name = os.path.basename(path)
        print("=" * 60)
        print(f"PDF: {name}")
        print("=" * 60)
        if not os.path.isfile(path):
            print("  [SKIP] 파일 없음\n")
            continue

        # 1) app.extract_route_from_page2 (여러 페이지, 2ND-$/DEP.. ..DEST 등)
        route_app = extract_route_from_page2(path)
        print(f"  extract_route_from_page2: {'OK' if route_app else 'FAIL (empty)'}")
        if route_app:
            print(f"    길이: {len(route_app)}")
            print(f"    처음 80자: {route_app[:80]}...")
            print(f"    끝   80자: ...{route_app[-80:]}")
        else:
            # 2페이지 텍스트만 확인 (디버깅)
            try:
                with pdfplumber.open(path) as pdf:
                    n = len(pdf.pages)
                    print(f"    PDF 페이지 수: {n}")
                    if n >= 2:
                        t = pdf.pages[1].extract_text() or ""
                        print(f"    2페이지 텍스트 길이: {len(t)}")
                        if t:
                            snippet = (t[:400] + "..." if len(t) > 400 else t)
                            print(f"    2페이지 앞 400자:\n{snippet}")
            except Exception as e:
                print(f"    pdfplumber 오류: {e}")

        # 2) ats_route_extractor (2페이지 텍스트만 넣었을 때)
        try:
            with pdfplumber.open(path) as pdf:
                page2_text = pdf.pages[1].extract_text() if len(pdf.pages) >= 2 else (pdf.pages[0].extract_text() if pdf.pages else "")
            route_ats = extract_ofp_route_from_page(page2_text or "") if page2_text else None
        except Exception as e:
            route_ats = None
            print(f"  ats_route_extractor (2페이지): 오류 - {e}")
        print(f"  extract_ofp_route_from_page(2페이지): {'OK' if route_ats else 'FAIL (empty)'}")
        if route_ats:
            print(f"    길이: {len(route_ats)}, 처음 60자: {route_ats[:60]}...")
        print()
    print("테스트 완료.")

if __name__ == "__main__":
    main()
