# SIGWX 차트 분석 개선 테스트 가이드

## 실제 코드 변경 사항

### ✅ 실제 코드 변경됨 (테스트 코드만이 아님)

1. **`src/sigwx_analyzer.py`** (새 파일 생성)
   - SIGWX 차트 분석을 위한 새로운 모듈
   - 하이브리드 접근법 구현

2. **`flightplanextractor.py`** (실제 코드 수정)
   - `analyze_turbulence_with_gemini()` 함수 수정
   - SIGWX 차트 분석을 자동으로 통합
   - 기존 코드와 호환되도록 설계됨

3. **`test_enhanced_sigwx.py`** (테스트 스크립트)
   - 테스트용 스크립트 (선택사항)

## 테스트 방법

### 방법 1: 실제 웹 애플리케이션에서 테스트 (권장)

**DocPack PDF를 업로드하여 실제로 테스트할 수 있습니다.**

1. 웹 애플리케이션 실행:
```bash
python app.py
```

2. 브라우저에서 `/ats_validator` 페이지 접속

3. DocPack PDF 파일 업로드

4. 자동으로 SIGWX 차트 분석이 포함된 터뷸런스 분석 결과 확인

**변경 사항:**
- 기존과 동일하게 PDF를 업로드하면 됩니다
- `analyze_turbulence_with_gemini()` 함수가 자동으로 SIGWX 차트를 찾아서 분석합니다
- SIGWX 차트가 없어도 기존 방식으로 작동합니다 (하위 호환성 유지)

### 방법 2: 테스트 스크립트로 직접 테스트

```bash
# uploads 폴더의 최신 PDF 사용
python test_enhanced_sigwx.py

# 또는 특정 PDF 파일 지정
python test_enhanced_sigwx.py uploads/your_docpack.pdf
```

## 작동 방식

### 자동 통합 프로세스:

1. **PDF 업로드** → `app.py`의 `/ats_validator` 엔드포인트

2. **Flight Plan 데이터 추출** → `extract_flight_data_from_pdf()`

3. **터뷸런스 분석 호출** → `analyze_turbulence_with_gemini()`
   - 이 함수 내부에서 자동으로:
     - SIGWX 차트 페이지 찾기 (`find_sigwx_pages()`)
     - SIGWX 차트 분석 (`analyze_sigwx_chart_enhanced()`)
     - 분석 결과를 Gemini 프롬프트에 포함

4. **결과 표시** → 웹 페이지에 표시

## 확인 방법

### 로그에서 확인:

터뷸런스 분석 중 다음 로그가 나타나면 SIGWX 분석이 작동한 것입니다:

```
✅ SIGWX 차트 분석 완료: X개 waypoint 분석됨
```

또는 SIGWX 차트가 없으면:

```
⚠️ SIGWX 차트 분석 중 오류 (계속 진행): ...
```

(오류가 나도 기존 방식으로 계속 진행됩니다)

### 분석 결과에서 확인:

터뷸런스 분석 결과에 다음이 포함되면 SIGWX 분석이 적용된 것입니다:

```
**SIGWX 차트 분석 결과 (이미지 처리 + 좌표 기반 매핑):**
- KATCH (0332Z): MOD Turbulence, CB Clouds
- EEP1 (0420Z): SEV Turbulence
...
```

## 하위 호환성

- **SIGWX 차트가 없는 PDF**: 기존 방식으로 작동 (오류 없음)
- **OpenCV가 설치되지 않은 경우**: 이미지 처리는 건너뛰고 Gemini Vision만 사용
- **NavData가 없는 경우**: 좌표 기반 매핑은 건너뛰고 기존 방식 사용

모든 경우에 기존 기능은 정상 작동합니다.

## 문제 해결

### SIGWX 분석이 작동하지 않는 경우:

1. **필수 패키지 확인:**
```bash
pip install pdf2image pillow opencv-python numpy
```

2. **NavData 확인:**
   - `NavData/` 폴더에 navdata 파일이 있는지 확인
   - waypoint 좌표 조회에 필요

3. **로그 확인:**
   - 터미널에서 오류 메시지 확인
   - `⚠️ SIGWX 차트 분석 중 오류` 메시지 확인

### SIGWX 차트를 찾지 못하는 경우:

- PDF에 "SIGWX" 키워드가 있는 페이지가 있어야 함
- 페이지 텍스트에서 "SIGWX"를 검색하여 찾음

## 요약

- ✅ **실제 코드 변경됨** (테스트 코드만 아님)
- ✅ **자동으로 작동** (별도 설정 불필요)
- ✅ **하위 호환성 유지** (기존 기능 정상 작동)
- ✅ **DocPack 업로드로 바로 테스트 가능**

