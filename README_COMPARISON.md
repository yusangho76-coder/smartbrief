# ASC 차트 색상 추출 방법 비교

세 가지 방법을 구현하여 가장 정확한 방법을 선별합니다.

## 구현된 방법

### 방법 1: OpenCV + OCR
- **장점**: 정확한 RGB 값 추출, 무료, 로컬 처리
- **단점**: OCR 라이브러리 설치 필요, waypoint 위치 찾기 복잡
- **필요 라이브러리**: 
  - `opencv-python`
  - `pytesseract` 또는 `easyocr`
  - Tesseract OCR 엔진 (pytesseract 사용 시)

### 방법 2: Google Cloud Vision API
- **장점**: 정확한 RGB 값, 구조화된 데이터, Google의 검증된 API
- **단점**: 비용 발생 가능, Google Cloud 설정 필요
- **필요 작업**:
  1. Google Cloud 프로젝트 생성
  2. Vision API 활성화
  3. 서비스 계정 키 생성
  4. 환경 변수 설정: `export GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json`
  5. `google-cloud-vision` 설치

### 방법 3: Gemini API (개선된 프롬프트)
- **장점**: 이미 설정되어 있음, 빠른 적용 가능
- **단점**: LLM의 색상 구분 한계
- **필요**: `GEMINI_API_KEY` 또는 `GOOGLE_API_KEY` 환경 변수

## 설치 방법

### 빠른 설치
```bash
./setup_comparison_test.sh
```

### 수동 설치

#### 방법 1: OpenCV + OCR
```bash
# OpenCV 설치
pip3 install opencv-python

# OCR 선택 (둘 중 하나)
# 옵션 1: pytesseract (빠름)
pip3 install pytesseract
brew install tesseract  # macOS

# 옵션 2: easyocr (정확도 높음)
pip3 install easyocr
```

#### 방법 2: Google Cloud Vision API
```bash
# 라이브러리 설치
pip3 install google-cloud-vision

# Google Cloud 설정
# 1. 프로젝트 생성 및 Vision API 활성화
# 2. 서비스 계정 키 생성
# 3. 환경 변수 설정
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json
```

#### 방법 3: Gemini API
```bash
# 이미 설치되어 있을 수 있음
# .env 파일에 API 키 확인
```

## 테스트 실행

```bash
python3 test_asc_colors_comparison.py
```

## 결과 해석

테스트 결과는 다음을 보여줍니다:
- 각 방법별 waypoint 색상 추출 결과
- 세 방법 간 일치도
- 각 방법별 통계 (빨간색/노란색/파란색 비율)

## 권장 사항

1. **방법 1 (OpenCV + OCR)**: 가장 정확하지만 설정이 복잡
2. **방법 2 (Vision API)**: 정확하고 안정적이지만 비용 발생
3. **방법 3 (Gemini)**: 빠르지만 색상 구분 정확도가 낮을 수 있음

테스트 결과를 보고 가장 적합한 방법을 선택하세요.

