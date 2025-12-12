# Package 3 추출 및 분석 - 빠른 참조 카드

## ⚡ 빠른 시작 (3단계)

### 1️⃣ 테스트 실행
```bash
python test_package3_analysis.py
```

### 2️⃣ Python 코드에서 사용
```python
from src.package3_extractor import extract_and_analyze_package3

result = extract_and_analyze_package3(
    route="RKSI OSPOT Y782 TGU RJAA",
    dep='RKSI',
    dest='RJAA'
)
print(result['analysis_result'])
```

### 3️⃣ API 호출
```bash
curl -X POST http://localhost:5000/api/analyze_route \
  -H "Content-Type: application/json" \
  -d '{"route": "RKSI OSPOT Y782 TGU RJAA", "use_package3_extraction": true}'
```

## 📋 주요 함수

| 함수 | 설명 | 예시 |
|------|------|------|
| `get_latest_split_file()` | 최신 split.txt 찾기 | `get_latest_split_file('temp')` |
| `extract_package3_from_file()` | Package 3 추출 | `extract_package3_from_file(split_file)` |
| `extract_and_analyze_package3()` | 추출 + AI 분석 | `extract_and_analyze_package3(route, ...)` |

## 🔌 API 엔드포인트

### Package 3 추출만
```
POST /api/extract_package3
```

### Package 3 추출 + AI 분석
```
POST /api/analyze_route
Body: {
  "route": "RKSI ... RJAA",
  "use_package3_extraction": true
}
```

## 📁 파일 구조

```
temp/
├── 20251027_172500_Notam-20251027_split.txt      ← 원본
└── 20251027_172500_Notam-20251027_package3.txt   ← 추출됨 ✅
```

## ✅ 확인 사항

- [x] temp 디렉토리에 *_split.txt 파일 존재
- [x] split.txt에 "KOREAN AIR NOTAM PACKAGE 3" 포함
- [x] GEMINI_API_KEY 환경 변수 설정
- [x] Python 가상환경 활성화

## 🎯 예상 결과

### Package 3 파일
- 파일 크기: ~15-25KB
- FIR 개수: 2개 (RKRR, RJJJ)
- NOTAM 형식: Z1140/25, CHINA SUP 16/21 등

### AI 분석 결과
```markdown
# NOTAM 브리핑 자료

## 1. 인천 FIR (RKRR)

**Z1140/25**: GPS 신호 불안정...
**CHINA SUP 16/21**: AKARA-FUKUE 회랑 관제...

## 2. 후쿠오카 FIR (RJJJ)
...
```

## 🐛 문제 해결

| 문제 | 해결 |
|------|------|
| FileNotFoundError | temp 디렉토리에 split.txt 확인 |
| "Package 3 섹션을 찾을 수 없습니다" | split.txt 내용 확인 |
| API 키 오류 | `.env`에 GEMINI_API_KEY 설정 |

## 📖 상세 문서

- 📘 [README_PACKAGE3.md](README_PACKAGE3.md) - 완전한 가이드
- 📗 [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md) - 구현 상세 정보
- 📙 [src/package3_extractor.py](src/package3_extractor.py) - 소스 코드

## 💡 팁

- 자동으로 최신 split.txt 사용됨 (경로 지정 불필요)
- Package 3 파일은 재사용 가능 (한 번 추출하면 캐시처럼 사용)
- `use_package3_extraction: false`로 기존 방식도 사용 가능
