# AviationWeather.gov API 적용 검토 보고서

## 현재 구현 상태

### ✅ 이미 구현된 기능
1. **METAR** (`/api/data/metar`)
   - 현재 사용 중: `https://aviationweather.gov/api/data/metar?ids={ICAO}&format=json`
   - 구글 지도에 공항별 METAR 정보 표시
   - InfoWindow에 rawOb (원시 METAR 텍스트) 표시

2. **TAF** (`/api/data/taf`)
   - 현재 사용 중: `https://aviationweather.gov/api/data/taf?ids={ICAO}&format=json`
   - 구글 지도에 공항별 TAF 정보 표시
   - InfoWindow에 rawTAF (원시 TAF 텍스트) 표시

3. **ATIS** (atis.guru)
   - atis.guru에서 Arrival/Departure ATIS 정보 스크래핑
   - InfoWindow에 ATIS 정보 표시

## 추가 적용 가능한 API

### 1. PIREP (Pilot Reports) - ⭐ 높은 우선순위
**엔드포인트**: `/api/data/pirep`

**특징**:
- 실시간 항공기 관측 정보 (난류, 착빙, 날씨 등)
- 경로 상의 특정 지점에서의 실제 기상 조건
- 항로 계획에 매우 유용한 정보

**적용 방안**:
- 항로 상의 waypoint 근처에서 PIREP 데이터 조회
- 난류/착빙 정보가 있는 경우 경고 마커 표시
- InfoWindow에 PIREP 상세 정보 표시

**API 파라미터**:
```javascript
{
  id: "ICAO",           // 공항 ID (중심점)
  distance: 50,          // 반경 거리 (statute miles)
  format: "json",       // JSON 형식
  age: 3,               // 3시간 이내 데이터
  level: 35000,         // 고도 ±3000ft
  inten: "mod"          // 최소 강도 (lgt, mod, sev)
}
```

**데이터 구조**:
- `tbInt1`, `tbType1`, `tbBas1`, `tbTop1`: 난류 정보
- `icgInt1`, `icgType1`, `icgBas1`, `icgTop1`: 착빙 정보
- `wxString`: 관측 날씨
- `temp`, `wdir`, `wspd`: 온도, 풍향, 풍속

### 2. SIGMET/AIRMET - ⭐ 높은 우선순위
**엔드포인트**: 
- `/api/data/airsigmet` (Domestic SIGMETs - 미국)
- `/api/data/isigmet` (International SIGMETs)
- `/api/data/gairmet` (US Graphical AIRMETs)

**특징**:
- 기상 경보 정보 (난류, 착빙, 대류성 날씨 등)
- 항로에 영향을 미치는 기상 현상 경고
- GeoJSON 형식으로 폴리곤 제공

**적용 방안**:
- 항로와 교차하는 SIGMET/AIRMET 영역 표시
- 폴리곤 오버레이로 경고 영역 시각화
- 색상 코딩 (난류=빨강, 착빙=파랑, 대류=노랑)

**API 파라미터**:
```javascript
{
  format: "geojson",    // GeoJSON 형식
  hazard: "turb",       // turb, ice, conv, ifr
  level: 35000,         // 고도 ±3000ft
  date: "20231220_0000" // 날짜/시간
}
```

### 3. Wind/Temp Point Data - ⭐ 중간 우선순위 (⚠️ 시간 정보 필요)
**엔드포인트**: `/api/data/windtemp`

**특징**:
- 고도별 바람 및 온도 정보
- 항로 계획 시 바람 예측에 유용
- FD (Forecast Winds) 데이터
- **⚠️ 시간대별 예보이므로 각 waypoint의 예상 도착 시간(ETA)이 필수**

**적용 방안**:
- 항로 상의 waypoint에서 고도별 바람 정보 표시
- InfoWindow에 고도별 바람/온도 테이블 표시
- **각 waypoint의 ETA를 계산하여 해당 시간대의 바람 정보 조회**

**필요한 정보**:
1. **출발 시간 (Departure Time)**: 항로 시작 시간
2. **항공기 속도 (Airspeed)**: TAS (True Airspeed) 또는 평균 속도
3. **각 waypoint 간 거리**: Haversine 공식으로 계산 가능
4. **각 waypoint의 ETA**: 출발 시간 + 누적 비행 시간

**ETA 계산 로직**:
```javascript
function calculateETAs(routePoints, departureTime, averageSpeed) {
    const etas = [];
    let cumulativeTime = 0; // 분 단위
    
    for (let i = 0; i < routePoints.length; i++) {
        if (i === 0) {
            // 첫 번째 waypoint는 출발 시간
            etas.push(departureTime);
        } else {
            // 이전 waypoint와의 거리 계산
            const prevPoint = routePoints[i - 1];
            const currentPoint = routePoints[i];
            const distance = calculateDistance(
                prevPoint.lat, prevPoint.lng,
                currentPoint.lat, currentPoint.lng
            ); // nautical miles
            
            // 비행 시간 계산 (분)
            const flightTime = (distance / averageSpeed) * 60;
            cumulativeTime += flightTime;
            
            // ETA 계산
            const eta = new Date(departureTime);
            eta.setMinutes(eta.getMinutes() + cumulativeTime);
            etas.push(eta);
        }
    }
    
    return etas;
}
```

**API 파라미터**:
```javascript
{
  region: "us",         // us, bos, mia, chi, dfw, slc, sfo, alaska, hawaii
  level: "high",        // low, high
  fcst: "24"            // 06, 12, 24 (forecast cycle)
}
```

**제한사항**: 
- 텍스트 형식만 제공 (파싱 필요)
- **시간 정보가 없으면 사용 불가**
- 지역별로 다른 region 파라미터 필요

**구현 전제 조건**:
1. ✅ 출발 시간 입력 UI 추가
2. ✅ 항공기 속도 입력 UI 추가 (또는 기본값 사용)
3. ✅ routePoints에 ETA 정보 추가
4. ✅ Wind/Temp API 호출 시 해당 waypoint의 ETA 사용

### 4. TCF (TFM Convective Forecast) - ⭐ 중간 우선순위
**엔드포인트**: `/api/data/tcf`

**특징**:
- 대류성 날씨 예보 (뇌우 등)
- 항공 교통 관리용 예보
- GeoJSON 형식으로 폴리곤 제공

**적용 방안**:
- 항로와 교차하는 대류성 날씨 영역 표시
- 폴리곤 오버레이로 예보 영역 시각화

**API 파라미터**:
```javascript
{
  format: "geojson"     // geojson 형식
}
```

### 5. Center Weather Advisories (CWA) - ⭐ 낮은 우선순위
**엔드포인트**: `/api/data/cwa`

**특징**:
- NWS Center Weather Service Units에서 발행
- 특정 공역의 기상 경고
- GeoJSON 형식 제공

**적용 방안**:
- 항로와 관련된 CWA 영역 표시

## 구현 우선순위 및 권장사항

### Phase 1: 즉시 적용 가능 (높은 가치)
1. **PIREP 통합**
   - 항로 상의 waypoint 근처 PIREP 조회
   - 난류/착빙 정보가 있는 경우 경고 마커 표시
   - InfoWindow에 PIREP 상세 정보 추가
   - ⚠️ 시간 정보 불필요 (최근 3시간 이내 데이터 조회)

2. **SIGMET/AIRMET 통합**
   - 항로와 교차하는 SIGMET/AIRMET 영역 폴리곤 표시
   - 색상 코딩으로 위험도 표시
   - 클릭 시 상세 정보 표시
   - ⚠️ 시간 정보 불필요 (현재 유효한 경보만 조회)

### Phase 2: 추가 기능 (중간 가치, 시간 정보 필요)
3. **Wind/Temp Point Data** ⚠️ **시간 정보 필수**
   - **전제 조건**: 출발 시간 + 항공기 속도 입력 필요
   - 각 waypoint의 ETA 계산
   - 고도별 바람 정보 표시
   - 항로 계획 최적화에 활용
   - **구현 복잡도**: 높음 (시간 계산 로직 필요)

4. **TCF 통합**
   - 대류성 날씨 예보 영역 표시

### Phase 3: 선택적 기능 (낮은 가치)
5. **CWA 통합**
   - 특정 공역 경고 정보

## 기술적 고려사항

### 1. API 호출 최적화
- 현재는 공항별로만 호출
- PIREP/SIGMET는 항로 전체에 대해 한 번에 조회 가능 (bbox 파라미터 사용)
- 캐싱 전략 필요 (PIREP는 3시간 이내, SIGMET는 더 자주 업데이트)

### 2. 지도 성능
- 폴리곤 오버레이가 많아지면 성능 저하 가능
- 클러스터링 또는 간소화 필요
- 사용자가 토글할 수 있는 레이어로 구현

### 3. 데이터 파싱
- Wind/Temp는 텍스트 형식만 제공 → 파싱 로직 필요
- PIREP의 난류/착빙 정보는 구조화되어 있어 파싱 용이

### 4. UI/UX 개선
- 날씨 정보가 많아질 수 있으므로 탭 또는 접기/펼치기 기능 고려
- 색상 코딩으로 위험도 시각화
- 필터링 기능 (난류만, 착빙만 등)

## 구현 예시 코드 구조

### 백엔드 (api_routes.py)
```python
@app.route('/api/aviation-weather/pirep', methods=['POST'])
def api_pirep():
    # bbox 또는 id+distance로 PIREP 조회
    # 항로 상의 waypoint 근처 PIREP 반환

@app.route('/api/aviation-weather/sigmet', methods=['POST'])
def api_sigmet():
    # bbox로 SIGMET/AIRMET 조회
    # 항로와 교차하는 영역 반환
```

### 프론트엔드 (google_maps.html)
```javascript
// PIREP 마커 추가
async function loadPIREPData(routePoints) {
    // 항로 상의 waypoint 근처 PIREP 조회
    // 난류/착빙 정보가 있는 경우 경고 마커 표시
}

// SIGMET 폴리곤 오버레이
async function loadSIGMETData(routeBounds) {
    // 항로 경계 내 SIGMET 조회
    // 폴리곤 오버레이로 표시
}
```

## 결론

AviationWeather.gov API는 현재 METAR/TAF만 사용 중이며, **PIREP**과 **SIGMET/AIRMET**을 추가하면 항로 계획에 매우 유용한 정보를 제공할 수 있습니다. 특히 실시간 난류/착빙 정보와 기상 경보는 안전한 항로 계획에 필수적입니다.

**⚠️ 중요 발견**: **Wind/Temp Point Data**는 시간대별 예보이므로, 각 waypoint의 **예상 도착 시간(ETA)**이 필수입니다. 이를 위해서는:
- 출발 시간 입력
- 항공기 속도 입력 (또는 기본값)
- 각 waypoint 간 거리 계산
- 누적 비행 시간으로 ETA 계산

**권장 구현 순서**:
1. **PIREP 통합** (실시간 관측 정보) - ⭐ 즉시 가능, 시간 정보 불필요
2. **SIGMET/AIRMET 통합** (기상 경보) - ⭐ 즉시 가능, 시간 정보 불필요
3. **Wind/Temp Data** (고도별 바람 정보) - ⚠️ 시간 정보 필수, 구현 복잡도 높음
4. **TCF** (대류성 날씨 예보) - 시간 정보 불필요

**Wind/Temp Data 구현을 위해서는 먼저 항로 시간 계산 기능이 필요합니다.**

