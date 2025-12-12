# Package 3 자동 추출 및 AI 항로 분석 가이드

## 📋 개요

`split.txt` 파일에서 **KOREAN AIR NOTAM PACKAGE 3** 섹션만 자동으로 추출하여 AI 항로 분석에 사용하는 기능입니다.

## 🎯 주요 기능

### 1. Package 3 자동 추출
- `temp/` 디렉토리에서 가장 최근 `*_split.txt` 파일을 자동으로 찾습니다
- "KOREAN AIR NOTAM PACKAGE 3"부터 "END OF KOREAN AIR NOTAM PACKAGE 3"까지 추출
- 추출된 내용을 `*_package3.txt` 파일로 저장

### 2. AI 항로 분석
- 추출된 Package 3 데이터를 AI 항로 분석기로 전달
- FIR별 NOTAM 자동 분류 및 항로 관련 NOTAM 필터링
- 조종사 브리핑 자료 형식으로 결과 생성

## 📁 파일 구조

```
src/
├── package3_extractor.py    # Package 3 추출 모듈
├── ai_route_analyzer.py      # AI 항로 분석 모듈
└── ...

temp/
├── 20251027_172500_Notam-20251027_split.txt      # 원본 split.txt
└── 20251027_172500_Notam-20251027_package3.txt   # 추출된 Package 3

test_package3_analysis.py     # 테스트 스크립트
app.py                        # Flask 웹 서버 (API 엔드포인트 포함)
```

## 🚀 사용 방법

### 방법 1: Python 스크립트 직접 실행

```python
from src.package3_extractor import extract_and_analyze_package3

# 항로 분석 (자동으로 최근 split.txt 찾기)
result = extract_and_analyze_package3(
    route="RKSI OSPOT Y782 TGU RJAA",
    dep='RKSI',
    dest='RJAA',
    flight_details='KE 0703 ICN/NRT'
)

print(result['analysis_result'])
```

### 방법 2: Flask API 사용

#### 2-1. Package 3 추출만 수행

```bash
curl -X POST http://localhost:5000/api/extract_package3 \
  -H "Content-Type: application/json" \
  -d '{}'
```

**응답 예시:**
```json
{
  "success": true,
  "split_file": "temp/20251027_172500_Notam-20251027_split.txt",
  "package3_file": "temp/20251027_172500_Notam-20251027_package3.txt",
  "content_length": 45632,
  "preview": "KOREAN AIR NOTAM PACKAGE 3...",
  "timestamp": "2025-10-27T17:25:00"
}
```

#### 2-2. Package 3 추출 + AI 항로 분석 (통합)

```bash
curl -X POST http://localhost:5000/api/analyze_route \
  -H "Content-Type: application/json" \
  -d '{
    "route": "RKSI OSPOT Y782 TGU RJAA",
    "use_package3_extraction": true,
    "dep": "RKSI",
    "dest": "RJAA",
    "flight_details": "KE 0703 ICN/NRT"
  }'
```

**응답 예시:**
```json
{
  "route": "RKSI OSPOT Y782 TGU RJAA",
  "gemini_analysis": "# NOTAM 브리핑 자료\n\n## 1. 인천 FIR (RKRR)\n\n**Z1140/25**: GPS 신호 불안정...",
  "package3_file": "temp/20251027_172500_Notam-20251027_package3.txt",
  "split_file": "temp/20251027_172500_Notam-20251027_split.txt",
  "timestamp": "2025-10-27T17:30:00"
}
```

#### 2-3. 기존 방식 사용 (notam_data 직접 전달)

```bash
curl -X POST http://localhost:5000/api/analyze_route \
  -H "Content-Type: application/json" \
  -d '{
    "route": "RKSI OSPOT Y782 TGU RJAA",
    "use_package3_extraction": false,
    "notam_data": ["NOTAM 텍스트..."],
    "dep": "RKSI",
    "dest": "RJAA"
  }'
```

### 방법 3: 테스트 스크립트 실행

```bash
# 가상환경 활성화
.venv\Scripts\Activate.ps1

# 테스트 실행
python test_package3_analysis.py
```

**테스트 스크립트 기능:**
1. 자동으로 최근 split.txt 파일 찾기
2. Package 3 추출 및 검증
3. AI 항로 분석 수행 (사용자 확인 후)
4. 결과 출력

## 📚 모듈 설명

### `src/package3_extractor.py`

주요 함수:

#### `extract_package3_from_file(input_file_path, output_dir=None)`
split.txt에서 Package 3 추출

**Parameters:**
- `input_file_path` (str): 입력 파일 경로
- `output_dir` (str, optional): 출력 디렉토리 (기본값: 입력 파일과 동일)

**Returns:**
- `str`: 생성된 package3 파일 경로

#### `get_latest_split_file(temp_dir='temp')`
가장 최근 split.txt 파일 자동 찾기

**Parameters:**
- `temp_dir` (str): temp 디렉토리 경로

**Returns:**
- `str`: 가장 최근 split.txt 파일 경로

#### `extract_and_analyze_package3(route, split_file_path=None, **kwargs)`
Package 3 추출 + AI 항로 분석 통합 실행

**Parameters:**
- `route` (str): 분석할 항로
- `split_file_path` (str, optional): split.txt 파일 경로 (None이면 자동 검색)
- `**kwargs`: AI 분석 옵션 (dep, dest, flight_details 등)

**Returns:**
- `dict`: 분석 결과 딕셔너리
  ```python
  {
      'analysis_result': '분석 결과 텍스트',
      'package3_file': 'package3 파일 경로',
      'split_file': 'split 파일 경로'
  }
  ```

## 🔍 동작 원리

```
┌─────────────────────┐
│  split.txt 파일     │
│  (전체 NOTAM)       │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────────────────────┐
│ 1. "KOREAN AIR NOTAM PACKAGE 3"     │
│    텍스트 패턴 검색                  │
└──────────┬──────────────────────────┘
           │
           ▼
┌─────────────────────────────────────┐
│ 2. Package 3 섹션 추출              │
│    (시작 ~ 끝 마커)                 │
└──────────┬──────────────────────────┘
           │
           ▼
┌─────────────────────────────────────┐
│ 3. *_package3.txt 파일 생성         │
└──────────┬──────────────────────────┘
           │
           ▼
┌─────────────────────────────────────┐
│ 4. AI 항로 분석기로 전달            │
│    (ai_route_analyzer.py)           │
└──────────┬──────────────────────────┘
           │
           ▼
┌─────────────────────────────────────┐
│ 5. FIR별 분류 및 필터링             │
│    - RKRR (인천 FIR)                │
│    - RJJJ (후쿠오카 FIR)            │
└──────────┬──────────────────────────┘
           │
           ▼
┌─────────────────────────────────────┐
│ 6. NOTAM 번호 추출                  │
│    예: Z1140/25, CHINA SUP 16/21    │
└──────────┬──────────────────────────┘
           │
           ▼
┌─────────────────────────────────────┐
│ 7. 조종사 브리핑 자료 생성          │
│    (Markdown 형식)                  │
└─────────────────────────────────────┘
```

## ⚙️ 설정 및 옵션

### API 파라미터

**`/api/analyze_route` 엔드포인트:**

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|---------|------|------|--------|------|
| `route` | string | ✅ | - | 분석할 항로 |
| `use_package3_extraction` | boolean | ❌ | `true` | Package 3 자동 추출 사용 여부 |
| `dep` | string | ❌ | - | 출발 공항 ICAO 코드 |
| `dest` | string | ❌ | - | 도착 공항 ICAO 코드 |
| `altn` | string | ❌ | - | 교체 공항 ICAO 코드 |
| `flight_details` | string | ❌ | - | 항공편 정보 (예: KE 0703) |
| `notam_data` | array | ❌ | - | NOTAM 데이터 (use_package3_extraction=false일 때 사용) |

## 📝 예제 코드

### 예제 1: 기본 사용

```python
from src.package3_extractor import extract_and_analyze_package3

# RKSI → RJAA 항로 분석
result = extract_and_analyze_package3(
    route="RKSI OSPOT Y782 TGU Y781 BESNA RJAA",
    dep='RKSI',
    dest='RJAA'
)

print(result['analysis_result'])
```

### 예제 2: 특정 파일 지정

```python
from src.package3_extractor import extract_and_analyze_package3

# 특정 split.txt 파일 사용
result = extract_and_analyze_package3(
    route="RKSI OSPOT Y782 TGU RJAA",
    split_file_path="temp/20251027_172500_Notam-20251027_split.txt",
    dep='RKSI',
    dest='RJAA',
    flight_details='KE 0703 ICN/NRT'
)
```

### 예제 3: Package 3만 추출

```python
from src.package3_extractor import extract_package3_from_file, get_latest_split_file

# 최근 파일 찾기
split_file = get_latest_split_file('temp')
print(f"사용할 파일: {split_file}")

# Package 3 추출
package3_file = extract_package3_from_file(split_file)
print(f"생성된 파일: {package3_file}")

# 내용 확인
with open(package3_file, 'r', encoding='utf-8') as f:
    content = f.read()
    print(f"파일 크기: {len(content)} 문자")
```

## 🐛 문제 해결

### 문제: "split.txt 파일을 찾을 수 없습니다"

**해결 방법:**
1. `temp/` 디렉토리에 `*_split.txt` 파일이 있는지 확인
2. 파일이 없다면 NOTAM PDF → split.txt 변환 먼저 수행

### 문제: "Package 3 섹션을 찾을 수 없습니다"

**해결 방법:**
1. split.txt 파일에 "KOREAN AIR NOTAM PACKAGE 3" 텍스트가 있는지 확인
2. NOTAM 파일이 올바르게 파싱되었는지 검증

### 문제: AI 분석 결과에 잘못된 NOTAM 번호 표시

**해결 방법:**
1. Package 3 파일에서 NOTAM 번호 형식 확인 (예: Z1140/25, CHINA SUP 16/21)
2. `ai_route_analyzer.py`의 NOTAM 번호 추출 로직 확인

## 📊 성능 정보

- Package 3 추출: ~0.1초 (50KB 파일 기준)
- AI 항로 분석: ~5-10초 (Gemini API 응답 시간)
- 총 처리 시간: ~5-10초

## 🔐 보안 고려사항

- API 키는 환경 변수로 관리 (`GEMINI_API_KEY` 또는 `GOOGLE_API_KEY`)
- temp 디렉토리 권한 확인 (읽기/쓰기)
- 프로덕션 환경에서는 파일 경로 검증 강화 권장

## 📖 참고 자료

- [ai_route_analyzer.py](src/ai_route_analyzer.py) - AI 항로 분석 로직
- [package3_extractor.py](src/package3_extractor.py) - Package 3 추출 로직
- [app.py](app.py) - Flask API 엔드포인트

## 🎉 업데이트 내역

### 2025-10-27
- ✨ Package 3 자동 추출 기능 추가
- ✨ `/api/extract_package3` API 엔드포인트 추가
- ✨ `/api/analyze_route` 엔드포인트에 자동 추출 옵션 통합
- ✨ `test_package3_analysis.py` 테스트 스크립트 추가
- 📝 README_PACKAGE3.md 문서 작성
