#!/bin/bash
# 세 가지 방법 비교 테스트를 위한 라이브러리 설치 스크립트

echo "=========================================="
echo "ASC 차트 색상 추출 방법 비교 테스트 설정"
echo "=========================================="

# 방법 1: OpenCV + OCR
echo ""
echo "[방법 1] OpenCV + OCR 라이브러리 설치..."
echo "필요한 라이브러리:"
echo "  - opencv-python"
echo "  - pytesseract 또는 easyocr"
echo ""
read -p "방법 1을 설치하시겠습니까? (y/n): " install_method1
if [ "$install_method1" = "y" ]; then
    pip3 install opencv-python
    echo "OCR 라이브러리 선택:"
    echo "  1. pytesseract (빠름, 영어 위주)"
    echo "  2. easyocr (정확도 높음, 다국어 지원)"
    read -p "선택 (1 또는 2): " ocr_choice
    if [ "$ocr_choice" = "1" ]; then
        pip3 install pytesseract
        echo "⚠️  Tesseract OCR 엔진도 설치해야 합니다:"
        echo "   macOS: brew install tesseract"
        echo "   Linux: sudo apt-get install tesseract-ocr"
    elif [ "$ocr_choice" = "2" ]; then
        pip3 install easyocr
    fi
fi

# 방법 2: Google Cloud Vision API
echo ""
echo "[방법 2] Google Cloud Vision API 설정..."
echo "필요한 작업:"
echo "  1. Google Cloud 프로젝트 생성"
echo "  2. Vision API 활성화"
echo "  3. 서비스 계정 키 생성"
echo "  4. 환경 변수 설정: export GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json"
echo ""
read -p "방법 2를 설정하시겠습니까? (y/n): " setup_method2
if [ "$setup_method2" = "y" ]; then
    pip3 install google-cloud-vision
    echo "✅ google-cloud-vision 설치 완료"
    echo "⚠️  Google Cloud 설정이 필요합니다 (위 안내 참조)"
fi

# 방법 3: Gemini API (이미 설정되어 있을 수 있음)
echo ""
echo "[방법 3] Gemini API 확인..."
if [ -f ".env" ] && grep -q "GEMINI_API_KEY\|GOOGLE_API_KEY" .env; then
    echo "✅ Gemini API 키가 설정되어 있습니다"
else
    echo "⚠️  Gemini API 키가 설정되지 않았습니다"
    echo "   .env 파일에 GEMINI_API_KEY 또는 GOOGLE_API_KEY를 추가하세요"
fi

echo ""
echo "=========================================="
echo "설정 완료!"
echo "=========================================="
echo ""
echo "테스트 실행:"
echo "  python3 test_asc_colors_comparison.py"

