# 위성/구름 기반 운정고도 및 CB·ST 검토 (경로 적용)

비행 경로 상 **운정고도**(구름 밑/위), **경로 고도에 구름 걸림 여부**, **CB vs ST 구분**(회피 필요 여부)을 알 수 있는 **무료·제한적 무료** 데이터 소스와 적용 방안을 정리합니다.

---

## 1. 요구사항 정리

| 항목 | 설명 |
|------|------|
| 운정고도 | 구름 밑(cloud base) / 구름 위(cloud top) 고도(ft 또는 m) |
| 경로 구름 걸림 | OFP waypoint + FL과 비교해 해당 고도에 구름이 있는지 |
| CB vs ST | 층운(ST) vs 적란운(CB) 구분 — CB는 회피 필요 |

---

## 2. 무료·제한적 무료 데이터 소스 검토

### 2.1 Open-Meteo (무료, API 키 불필요)

- **제공**: `cloud_cover`, `cloud_cover_low`(0~3km), `cloud_cover_mid`(3~8km), `cloud_cover_high`(8km~), `freezing_level_height`, `cape`(대류에너지).
- **운정고도**: **직접 제공 안 함**. 구름층을 **고도대(저/중/고)** 로만 구분.
- **CB/ST**: **직접 구분 없음**. `cape`(Convective Available Potential Energy)로 대류 활발도 추정 가능 — CAPE 높으면 CB 가능성 참고용.
- **경로 적용**: waypoint별 lat/lon + 예상 시각으로 호출하면, 해당 지점의 저/중/고 cloud cover %와 CAPE를 얻을 수 있음. **FL을 고도대에 매핑**해 "해당 FL에 구름 걸림/안 걸림" 판단 가능.

**정리**:  
- **구름 걸림 여부**: FL ↔ 저(0~3km)/중(3~8km)/고(8km~) 매핑으로 "경로 고도에 구름 있음" 판단 가능.  
- **CB/ST**: CAPE로 "대류 활발(CB 가능성)"만 참고 가능.

---

### 2.2 Aviation Weather (METAR/TAF) — 이미 사용 중

- **제공**: 공항 기준 METAR/TAF. METAR에 **운고(ceiling)**·일부 **구름층** 정보 포함. cloud group에 **CB** 표기 있는 경우 있음(예: `BKN030CB`).
- **운정고도**: **공항 부근**의 cloud base/ceiling만 (지점 제한).
- **CB/ST**: METAR cloud group에서 **CB** 문자열 파싱하면 해당 공항 근처 CB 유무는 알 수 있음. **경로 상 임의 지점**에는 사용 불가.
- **경로 적용**: DEP/DEST/ALTN 등 **공항**에서만 운고·CB 참고. 경로 중간 waypoint에는 "가장 가까운 공항 METAR"로 근사하는 방식만 가능(정확도 제한).

---

### 2.3 위성/이미지 기반 (구름 유형·CB)

| 소스 | 운정고도 | CB/ST 구분 | 비용 | 비고 |
|------|----------|------------|------|------|
| **CloudAerias** | 이미지 기반 추정 가능 | CB 등 구름 유형 제공 | 무료 체험/유료 | API, 위성·이미지 기반 |
| **Meteomatics** | cloud_type 등 | 구름 유형 파라미터 있음 | API 키, 유료 옵션 | 위성·NWP 결합 |
| **Sentinel Hub (s2cloudless)** | — | 구름 마스크/확률만 | 할당량 내 무료 | CB/ST 구분 없음 |
| **CIMSS/SSEC (GOES Convective Mask)** | — | 대류성(CB 등) 구름 탐지 | 공개 데이터 | 별도 처리·API화 필요 |

- **위성만으로 "경로 상 모든 구간의 운정고도 + CB/ST"**를 **무료 API 한 번에** 주는 서비스는 찾기 어렵고, **Open-Meteo 고도대 + CAPE** 조합이 현실적인 무료 선택지.

---

## 3. 경로 적용 방안

### 3.1 "경로 고도에 구름 걸림 여부"

- **데이터**: Open-Meteo `hourly` — `cloud_cover_low`, `cloud_cover_mid`, `cloud_cover_high` (고도대별 %).
- **규칙**:
  - FL → 고도 대략 변환: FL330 ≈ 10km, FL350 ≈ 10.6km, FL390 ≈ 11.9km 등.
  - 저층(0~3km), 중층(3~8km), 고층(8km~) 중 **비행 FL이 속한 구간**의 cloud_cover가 임계값(예: ≥ 50%)이면 "해당 구간에서 구름 걸림"으로 판단.
- **적용**:  
  - waypoint별 (lat, lon) + **예상 통과 시각**(ETD 기반)으로 Open-Meteo 1회 호출(또는 소수 waypoint 샘플링).  
  - 각 waypoint에 "구름 걸림 / 안 걸림" 플래그 부여 → 결과 테이블·지도에 표시.

### 3.2 "CB 회피 필요" 참고

- **데이터**  
  - **Open-Meteo**: `cape` — 구간별 CAPE가 높으면(예: > 1000 J/kg) "대류 활발, CB 가능성" 참고.  
  - **METAR**: DEP/DEST/ALTN 등 공항 METAR에서 `CB` 문자열 파싱 → 해당 공항 인근 CB 유무.  
  - **SIGMET**: 이미 사용 중이면 대류성 SIGMET 영역과 경로 교차 여부로 "CB 구역 회피" 보강.
- **적용**:  
  - CAPE 기반: "대류 활발(CB 가능성)" 구간을 테이블/지도에 참고용으로 표시.  
  - METAR CB: 공항별 기상 블록에 "CB" 표기.  
  - SIGMET: 경로와 겹치는 대류 영역을 "회피 권고"로 표시.

### 3.3 ST vs CB "구분"

- **무료 API만으로** 경로 전 구간에 대해 **위성/관측 기반 ST vs CB**를 정확히 구분하는 서비스는 제한적.
- **가능한 조합**:  
  - Open-Meteo: 고도대별 구름 + CAPE(대류 가능성).  
  - METAR: 공항에서 CB 표기.  
  - SIGMET/차트: 대류성 영역·CB 언급 활용.  
→ "CB 확실"은 SIGMET·METAR, "CB 가능성"은 CAPE로 보완하는 방식이 현실적.

---

## 4. 구현 제안 (요약)

1. **Open-Meteo 경로 연동**
   - waypoint (또는 구간 대표점)의 lat, lon + 예상 시각으로 `hourly` 요청.
   - 변수: `cloud_cover_low`, `cloud_cover_mid`, `cloud_cover_high`, `cape`, 필요 시 `freezing_level_height`.
   - FL을 고도( m )로 변환 후, 해당 고도대 cloud cover로 "구름 걸림/안 걸림" 판단.
2. **결과 표시**
   - 기존 결과 화면(`results.html`) 또는 지도에 "경로 구간별 구름 걸림" 및 "대류 활발(CB 가능성)" 컬럼/뱃지 추가.
3. **METAR CB 파싱**
   - 공항별 METAR raw 텍스트에서 cloud group `CB` 파싱해 공항 기상 테이블에 "CB" 표시.
4. **선택**
   - SIGMET 대류 영역과 경로 교차 시 "CB 구역 회피" 문구/스타일 강화.

이렇게 하면 **위성 전용 무료 API 없이도**  
- 경로 상 **고도대별 구름 유무**(구름 걸림 여부),  
- **대류 활발도(CB 가능성)** 참고,  
- **공항·SIGMET 기반 CB/회피**  
까지 일관되게 적용할 수 있습니다.

---

## 5. 참고

- Open-Meteo 문서: [https://open-meteo.com/en/docs](https://open-meteo.com/en/docs)  
  - `cloud_cover_low`: up to 3km  
  - `cloud_cover_mid`: 3–8km  
  - `cloud_cover_high`: 8km+  
  - `cape`: J/kg  
- METAR cloud group: `FEW/SCT/BKN/OVC` + 높이(100ft 단위) + 선택 `CB`/`TCU`.

---

## 6. FL ↔ 고도대 매핑 (Open-Meteo용)

| FL 구간 | 대략 고도 (m) | Open-Meteo 층 |
|---------|----------------|----------------|
| FL100–300 | 3,000–9,100 m | mid (3–8km) + high (8km+) |
| FL310–400 | 9,400–12,200 m | high |
| FL250 이하 | ~7,600 m 이하 | low + mid |

- 판단 예: 비행 FL350 → 고층(8km~) 사용. `cloud_cover_high` ≥ 50%이면 "해당 구간에서 고도에 구름 걸림"으로 표시.

---

## 7. 구현 시 참고 (코드 위치)

- **경로 waypoint + FL**: `app.py`에서 `flight_data` (waypoint, lat, lon, fl), `flight_plan_waypoints` 사용. WAFS/SIGMET 분석과 동일하게 ETD(`ofp_date`) 기반 예상 시각 계산.
- **Open-Meteo 호출**: 새 모듈(예: `src/route_cloud_analyzer.py`)에서 waypoint별 또는 샘플링된 좌표 + 시간으로 `api.open-meteo.com/v1/forecast` 호출 후, 고도대·CAPE 판단 결과를 리스트로 반환.
- **결과 표시**: `flight_plan_analyzer`의 `wind_shear_table`/`wafs_turb_table`과 유사하게 테이블로 만들어 `results.html`에 전달하거나, 지도 오버레이로 구름 걸림/대류 활발 구간 표시.

---

## 8. 구체 코드 설계 및 함수 시그니처

### 8.1 모듈: `src/route_cloud_analyzer.py`

역할: 경로 waypoint별 Open-Meteo 호출 후 구름 걸림 여부 + CAPE(대류/CB 가능성) 판단하여 테이블용 리스트 반환.

#### 8.1.1 FL ↔ 고도대 매핑 (내부 상수)

- FL → 고도(m): `fl_to_altitude_m(fl) = fl * 100 * 0.3048`
- 고도대: **low** 0~3,000 m → `cloud_cover_low` / **mid** 3,000~8,000 m → `cloud_cover_mid` / **high** 8,000 m~ → `cloud_cover_high`
- 구름 걸림 임계값: 해당 층 `cloud_cover` ≥ 50%
- CAPE "대류 활발" 임계값: `cape` > 1000 J/kg (참고: 500~1000 보통, >1000 뇌우 가능성)

#### 8.1.2 함수 시그니처

```python
def fl_to_altitude_m(fl: int) -> float: ...
def altitude_to_layer(altitude_m: float) -> str: ...  # "low"|"mid"|"high"

def _interpret_hourly(fl, cloud_low, cloud_mid, cloud_high, cape, *,
    cloud_threshold=50.0, cape_threshold=1000.0) -> dict: ...

def fetch_route_cloud_cape(flight_data: List[Dict], etd_utc: Optional[datetime] = None, *,
    cloud_threshold=50.0, cape_threshold=1000.0, max_waypoints=50) -> List[Dict]: ...
```

#### 8.1.3 flight_data 입력 형식 (기존 OFP 추출과 동일)

- `List[Dict]`: 각 항목에 `lat`, `lon`(또는 `lng`), `fl`(또는 `"FL (Flight Level)"` 등), `actm`(또는 `"ACTM (Accumulated Time)"`), waypoint 이름(`Waypoint` 또는 `ident`) 포함.

#### 8.1.4 fetch_route_cloud_cape 반환 형식 (테이블용)

| 키 | 타입 | 설명 |
|----|------|------|
| waypoint | str | Waypoint 이름 |
| lat, lon | float | 좌표 |
| fl | int \| None | Flight Level |
| fl_label | str | 예: FL350 |
| actm | str | ACTM |
| cloud_on_route | bool | 해당 FL 고도대에 구름 걸림 여부 |
| cloud_layer | str | low / mid / high |
| cloud_cover_pct | int \| None | 해당 층 cloud cover % |
| cape | float \| None | CAPE (J/kg) |
| cb_risk | str | 높음 / 보통 / 낮음 / — |
| source | str | Open-Meteo |
| valid_utc | str | 사용한 예보 시각(UTC) 설명 |

- API 실패 시: `[{"_warning_row": True, "warn_msg": "..."}]` (WAFS와 동일 패턴).

#### 8.1.5 예상 통과 시각

- `etd_utc`: OFP ETD (UTC). 없으면 `datetime.now(timezone.utc)`.
- waypoint별 ETA가 없으면 첫 WP = ETD, 같은 UTC hour로 요청해도 됨 (Open-Meteo hourly 단위).

### 8.2 app.py 연동 위치

- WAFS 터뷸런스 분석 직후, wind_shear_table 생성 블록 근처.
- 입력: flight_data, ofp_date. 반환: route_cloud_table (list), route_cloud_warn (str \| None).

```python
route_cloud_table = []
route_cloud_warn = None
try:
    from src.route_cloud_analyzer import fetch_route_cloud_cape
    if flight_data:
        rows = fetch_route_cloud_cape(flight_data, etd_utc=ofp_date)
        for row in rows:
            if row.get("_warning_row"):
                route_cloud_warn = row.get("warn_msg", "구름/CAPE 분석 경고")
            else:
                route_cloud_table.append(row)
        if route_cloud_table:
            logger.info(f"경로 구름/CAPE: {len(route_cloud_table)}개 구간")
except Exception as e:
    logger.warning(f"경로 구름/CAPE 분석 실패: {e}")
```

- render_template 인자에 route_cloud_table, route_cloud_warn 추가.

### 8.3 결과 표시 (templates/results.html)

- WAFS CAT 카드 다음에 "⑤ 경로 구름 / 대류(CAPE)" 블록 추가.
- 테이블 컬럼: 구간(Waypoint) | ACTM | 고도(FL) | 구름 걸림 | 사용 층 | CAPE | CB 가능성.
- cloud_on_route True → "걸림" 뱃지, cb_risk "높음" → "대류 활발(CB 가능성)" 강조.
