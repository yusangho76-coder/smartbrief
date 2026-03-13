# OFP 기상 차트 분석 재검토 (Vision 대체 방안)

**최종:** OpenCV 색상·경로 분석 및 Google Vision 모두 실패 이력으로 **차트 이미지 자동 분석은 비활성화**되어 있습니다. OFP 차트(SigWx/ASC/Cross)는 **참고용 표시만** 하며, 터뷸런스·기상은 **SIGMET/G-AIRMET 및 WAFS API 분석 결과**만 사용합니다.

## 현재 구조 요약

| 차트 | Georeferencing | 경로 추출 | 기상 현상 추출 | 보조 검증 |
|------|----------------|-----------|----------------|-----------|
| **SigWx** | PDF 텍스트 regex (N40, E150) | OpenCV 검은 점선 → **실패 시 좌표 기반 선분** | OpenCV 색상 마스크 (핑크/빨강/초록/파랑) | Gemini Vision (선택) |
| **ASC** | Google Cloud Vision OCR → **대안: pdfplumber** | OpenCV 경로 색상 | OpenCV 터뷸런스 색상 | — |
| **Cross** | 동일 (Vision / pdfplumber) | 동일 | 동일 | — |

- **Google Cloud Vision**: `georeference_chart.py`의 `find_grid_labels(image)`에서 **그리드 라벨(위/경도)** 추출용으로만 사용. 차트가 복잡하거나 글자 크기가 작으면 인식률이 떨어짐.
- **Gemini Vision**: `src/sigwx_analyzer.py`의 SigWx 분석에서 **보조**로 사용. waypoint별 터뷸런스/CB/제트 판단을 이미지 처리 결과 위에 덧붙임. 차트 해상도·레이아웃에 따라 결과가 들쭉날쭉할 수 있음.

---

## 적용한 개선 사항

### 1. SigWx: Vision/이미지 경로에 덜 의존

- **문제**: 이미지에서 비행 경로(검은 점선) 추출이 실패하면 `flight_path_points`가 비어 있고, 기존 로직은 “경로 근처” 체크 때문에 **교차 결과가 0건**이 됨.
- **조치**:
  - **좌표 기반 경로**: waypoint의 (lat, lon) → 이미지 (x, y) 변환으로 만든 선분을 구간당 40점 정도로 샘플링해 `flight_path_points`를 생성.
  - 이미지에서 추출한 경로 점이 **20개 미만**이면 위 좌표 기반 경로로 자동 대체.
  - `find_weather_intersections`에서 **경로가 비어 있을 때**는 “waypoint–기상 현상” 거리만으로 교차 여부 판단 (경로 거리 조건 생략).

→ 이미지 경로 추출이 잘 안 되어도, **OFP waypoint 좌표만 있으면** 터뷸런스/CB/제트 매칭이 동작하도록 정리됨.

### 2. ASC/Cross: Vision 없이 그리드 라벨 쓰기

- **문제**: `find_grid_labels(image)`가 Google Cloud Vision에 의존하고, 차트 품질에 따라 인식이 불안정함.
- **조치**:
  - **`find_grid_labels_from_pdf(pdf_path, page_index, image_size)`** 추가 (Vision 없음).
  - 해당 PDF 페이지를 **pdfplumber**로 열고 `extract_words()`로 단어 bbox를 구한 뒤, `N20`, `E150` 등 패턴으로 위/경도 라벨만 추출.
  - PDF 좌표(포인트)를 이미지 픽셀으로 변환할 때 `페이지 크기 vs image_size` 비율로 스케일.
  - **`georeference_chart(image, waypoints, pdf_path=None, page_index=None)`** 에서 `pdf_path`와 `page_index`가 주어지면 **먼저** `find_grid_labels_from_pdf`를 호출하고, 라벨이 충분히 나오면 그걸 사용. 부족하면 기존 Vision `find_grid_labels(image)`로 폴백.

→ ASC/Cross 분석을 다시 켤 때, **같은 페이지를 가리키는 pdf_path + page_index**만 넘기면 Vision 없이 그리드를 쓸 수 있음.

---

## 추가로 고려할 수 있는 방안

1. **Gemini Vision 의존도 낮추기**
   - SigWx에서 Gemini는 “이미지 처리 결과 보정” 용도. 환경 변수(예: `DISABLE_GEMINI_CHART_ANALYSIS=1`)로 끄면, 순수 OpenCV + 좌표 기반 경로만 사용 가능.
   - 또는 프롬프트를 단순화해 “경로 상 MOD/SEV 터뷸런스 구역이 있으면 yes/no만” 답하도록 바꿔, JSON 파싱 실패·환각을 줄일 수 있음.

2. **색상 범위 자동화**
   - 회사별/PDF별로 차트 색상이 조금씩 다를 수 있음. 차트 이미지에서 “배경이 아닌 픽셀”을 샘플링해 클러스터링한 뒤, 터뷸런스/제트 등 색상 범위를 자동으로 잡는 방식으로 확장 가능.

3. **ASC 분석 재활성화 시**
   - `analyze_chart_with_coordinates(pdf_path, chart_image, chart_page_index=None)` 형태로 **chart_page_index**를 받아서, `georeference_chart(..., pdf_path=pdf_path, page_index=chart_page_index)`에 넘기면 Vision 없이 그리드 사용 가능.
   - 현재는 “오류가 많아 비활성화” 상태이므로, 재활성화할 때 위 인자만 추가해 주면 됨.

4. **차트 분석 결과의 역할**
   - 실시간 **SIGMET/G-AIRMET**, **WAFS 터뷸런스** 등은 이미 API로 제공되므로, OFP 차트 이미지 분석은 “참고용·보조”로 두고, API 결과를 메인으로 두는 구성이 안정적임.

---

## 차트 이미지 자동 분석 비활성화 (OpenCV 실패 반영)

- **flightplanextractor.py**: `analyze_turbulence_with_gemini` 내부에서 **`analyze_sigwx_chart_enhanced` 호출 제거**. SigWx/ASC/Cross 차트에 대한 OpenCV 색상·경로 분석을 실행하지 않음.
- **결과 화면**: OFP 기상 차트 영역에 "참고용 표시입니다. 차트 내 터뷸런스·기상 자동 분석은 수행하지 않습니다." 안내 추가.
- 터뷸런스·기상 분석은 **OFP SR 테이블, SIGMET/G-AIRMET API, WAFS(Ellrod)** 만 사용.

## 파일별 변경 요약

| 파일 | 변경 내용 |
|------|-----------|
| `flightplanextractor.py` | SigWx 차트 이미지 분석 호출 제거, Gemini용 안내 문구 수정 |
| `templates/results.html` | OFP 기상 차트 영역에 참고용 안내 문구 추가 |
| `src/sigwx_analyzer.py` | (이전) 좌표 기반 경로·교차 로직 추가 — 현재는 차트 분석 비활성화로 호출 안 함 |
| `georeference_chart.py` | Vision 제거, PDF 그리드 또는 waypoint 기본 변환만 사용 |
| `md/OFP_기상차트_분석_재검토.md` | 본 재검토 문서 |

차트는 **참고용 이미지로만** 제공되고, **기상 분석은 전부 API 기반**으로만 수행됨.
