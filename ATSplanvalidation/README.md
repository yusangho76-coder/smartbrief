# DocPack Route Validator

비행 문서(DocPack) PDF에서 ATS Flight Plan과 OFP(Operation Flight Plan) route를 자동으로 추출하고 비교하는 웹 애플리케이션입니다.

## 기능

- 📄 PDF 파일에서 자동으로 route 추출
  - 2페이지에서 OFP route 추출
  - "COPY OF ATS FPL" 페이지에서 ATS Flight Plan route 추출
- 🔍 Route 정규화 및 비교
  - TAS/고도 정보 제거
  - 시간 정보 제거
  - 속도/고도 제약 제거
  - Waypoint 추출 및 순서 비교
- ✅ 차이점 자동 감지
  - OFP에만 있는 waypoint/airway
  - ATS FPL에만 있는 waypoint/airway
  - Route 요소 순서 불일치

## 설치 방법

1. 필요한 패키지 설치:
```bash
pip install -r requirements.txt
```

## 실행 방법

### 방법 1: 실행 스크립트 사용 (권장)

**macOS/Linux:**
```bash
./run.sh
```

또는 Python 스크립트:
```bash
python3 run.py
```

**Windows:**
```bash
python run.py
```

### 방법 2: 직접 실행

```bash
source .venv/bin/activate  # 가상환경 활성화
streamlit run app.py
```

브라우저에서 자동으로 앱이 열립니다.

## 사용법

1. **PDF 파일 업로드**: DocPack PDF 파일을 선택합니다.
2. **자동 추출**: 앱이 자동으로 다음을 수행합니다:
   - 2페이지에서 OFP route 추출
   - "COPY OF ATS FPL" 페이지에서 ATS Flight Plan route 추출
3. **비교 결과 확인**: 두 route를 비교하여 차이점을 확인합니다.

## Route 형식

### OFP Route 예시
```
RKSI..NOPIK Y697 AGAVO A591 IKEKA W4 HCH W200 DOVIV W55 PAMRU W34
LADIX B339 ASILA A575 UPREK W28 ATBUG W66 NUKTI B215 KABDO W119
GOBOK A343 RULAD M610 ARBOL Z621 TRK N147 OTBOR A480 TIMGA B476
METKA L88 RASAM N199 LUSAL M11 REBLO UM11 CRM UL746 ODERO..LUGEB..
DEGET..BALUX..TORNO..NATEX..LOWW
```

### ATS FPL Route 예시
```
RKSI0255 -N0495F320 DCT NOPIK Y697 AGAVO/K0917S0980 A591 IKEKA W4
SEBLI/K0907S1040 W4 HCH W200 DOVIV W55 PAMRU W34 LADIX B339 ASILA
A575 UPREK W28 ATBUG W66 BUVTA/K0895S1100 W66 NUKTI B215 KABDO
W119 GOBOK A343 RULAD/N0485F360 M610 ARBOL Z621 TRK N147 OTBOR
A480 TIMGA B476 METKA L88 RASAM N199 LUSAL M11 REBLO UM11 CRM
UL746 ODERO DCT LUGEB DCT DEGET DCT BALUX DCT TORNO DCT NATEX DCT
-LOWW1225
```

앱은 자동으로 route를 정규화하여 비교합니다:
- 시간 정보 제거 (RKSI0255 → RKSI)
- TAS/고도 정보 제거 (N0495F320)
- 속도/고도 제약 제거 (/K0917S0980)
- DCT 제거
- ..를 공백으로 변환

## 파일 구조

```
ATSplanvalidation/
├── app.py                 # Streamlit 메인 앱
├── route_extractor.py     # Route 추출 및 비교 로직
├── run.sh                 # 실행 스크립트 (macOS/Linux)
├── run.py                 # 실행 스크립트 (모든 OS)
├── requirements.txt       # 필요한 패키지 목록
└── README.md             # 이 파일
```

## 기술 스택

- **Streamlit**: 웹 애플리케이션 프레임워크
- **pdfplumber**: PDF 텍스트 추출
- **Python 3.7+**

## 주의사항

- PDF 파일이 올바른 형식이어야 합니다.
- 2페이지에 OFP route가 있어야 합니다.
- "COPY OF ATS FPL"로 시작하는 페이지가 있어야 합니다.

