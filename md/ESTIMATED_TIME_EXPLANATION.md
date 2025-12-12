# 예상 남은 시간 계산 로직 설명

## 계산 로직 개요

예상 남은 시간은 **프론트엔드 JavaScript**에서 계산됩니다.

### 핵심 공식

```javascript
총 예상 시간 = 총 NOTAM 개수 × 0.6초
남은 시간 = 총 예상 시간 - 경과 시간
```

---

## 상세 계산 흐름

### 1단계: NOTAM 개수 추출

**파일 선택 시 (`templates/index.html` 507-571번 라인):**

1. 파일이 선택되면 `extractAirportsFromFile()` 함수 실행
2. `/api/extract_airports` API 호출 (5초 타임아웃)
3. API 응답에서 `notam_count` 추출
4. `totalNotamCount` 변수에 저장

```javascript
// 파일 선택 이벤트
document.getElementById('file').addEventListener('change', function(e) {
    const file = e.target.files[0];
    if (file && file.type === 'application/pdf') {
        extractAirportsFromFile(file);  // NOTAM 개수 추출
    }
});

// API 호출하여 NOTAM 개수 가져오기
async function extractAirportsFromFile(file) {
    const response = await fetch('/api/extract_airports', {
        method: 'POST',
        body: formData
    });
    const data = await response.json();
    
    if (data.notam_count) {
        totalNotamCount = data.notam_count;  // 전역 변수에 저장
    }
}
```

**백엔드 API (`app.py` 1860-1950번 라인):**
- PDF에서 공항 코드와 NOTAM 개수를 추출
- `notam_count` 필드로 반환

### 2단계: 폼 제출 시 초기화

**업로드 버튼 클릭 시 (`templates/index.html` 598-627번 라인):**

```javascript
document.getElementById('uploadForm').addEventListener('submit', function(e) {
    startTime = Date.now();  // 시작 시간 기록
    
    // NOTAM 개수가 추출되지 않았으면 기본값 100 사용
    if (totalNotamCount === 0) {
        totalNotamCount = 100;  // 기본값
    }
    
    // 1초마다 업데이트
    progressInterval = setInterval(updateElapsedTime, 1000);
});
```

### 3단계: 예상 남은 시간 계산 (1초마다 업데이트)

**`updateElapsedTime()` 함수 (`templates/index.html` 472-504번 라인):**

```javascript
function updateElapsedTime() {
    if (!startTime) return;
    
    // 1. 경과 시간 계산
    const elapsed = Math.floor((Date.now() - startTime) / 1000);
    
    // 2. 예상 남은 시간 계산
    if (totalNotamCount > 0) {
        // 총 예상 시간 = NOTAM 개수 × 0.6초
        const totalEstimatedTime = totalNotamCount * 0.6;
        
        // 남은 시간 = 총 예상 시간 - 경과 시간
        let estimatedRemaining = Math.max(0, totalEstimatedTime - elapsed);
        
        // 3. 표시 형식 변환 (MM:SS)
        if (estimatedRemaining > 0) {
            const estMinutes = Math.floor(estimatedRemaining / 60);
            const estSeconds = Math.floor(estimatedRemaining % 60);
            document.getElementById('estimatedTime').textContent = 
                `${estMinutes.toString().padStart(2, '0')}:${estSeconds.toString().padStart(2, '0')}`;
        } else {
            document.getElementById('estimatedTime').textContent = '거의 완료';
        }
    } else {
        document.getElementById('estimatedTime').textContent = '계산 중...';
    }
}
```

---

## 계산 예시

### 예시 1: 파일 `uploads/20251212_090017_af0a122b_Notam-20251212.pdf`

**시나리오:**
- 총 NOTAM 개수: 100개 (가정)
- 경과 시간: 0초

**계산:**
```
총 예상 시간 = 100 × 0.6 = 60초
남은 시간 = 60 - 0 = 60초
표시: "01:00"
```

**시나리오 2:**
- 총 NOTAM 개수: 100개
- 경과 시간: 20초

**계산:**
```
총 예상 시간 = 100 × 0.6 = 60초
남은 시간 = 60 - 20 = 40초
표시: "00:40"
```

### 예시 2: 150개 NOTAM 파일

**시나리오:**
- 총 NOTAM 개수: 150개
- 경과 시간: 30초

**계산:**
```
총 예상 시간 = 150 × 0.6 = 90초
남은 시간 = 90 - 30 = 60초
표시: "01:00"
```

### 예시 3: NOTAM 개수 미확인

**시나리오:**
- `totalNotamCount = 0` (API 호출 실패 또는 진행 중)

**동작:**
- 기본값 100개 사용 (폼 제출 시)
- 또는 "계산 중..." 표시

---

## 중요한 특징

### 1. 고정된 처리 속도 가정
- **0.6초/NOTAM**: 모든 NOTAM이 동일한 속도로 처리된다고 가정
- 실제로는 NOTAM 길이, 네트워크 상태, 서버 부하에 따라 변동

### 2. 실시간 업데이트
- **1초마다** `updateElapsedTime()` 함수 실행
- 경과 시간이 증가하면 남은 시간 자동 감소

### 3. 최소값 보장
```javascript
Math.max(0, totalEstimatedTime - elapsed)
```
- 남은 시간이 음수가 되지 않도록 보장
- 0 이하일 때는 "거의 완료" 표시

### 4. NOTAM 개수 추출 실패 시
- 기본값 **100개** 사용
- 실제와 다를 수 있음 (부정확한 예상 시간)

---

## 실제 처리 시간 vs 예상 시간

### 실제 처리 시간 구성
```
전체 처리 시간 = PDF 변환 + 필터링 + 시간 변환 + 번역
```

각 단계별 예상 시간:
1. **PDF 변환**: 1-3초 (NOTAM 개수와 무관)
2. **필터링**: 1-2초 (NOTAM 개수와 무관)
3. **시간 변환**: 0.5-1초 (NOTAM 개수에 비례, 병렬 처리)
4. **번역**: **10-60초** (NOTAM 개수에 비례, 가장 큰 병목)

### 0.6초/NOTAM 가정의 한계

**문제점:**
- 실제로는 번역 단계가 대부분의 시간을 차지
- NOTAM 길이에 따라 처리 시간이 크게 달라짐
- 고정 속도(0.6초)는 실제와 차이날 수 있음

**예상 시간 계산 예시:**
- 100개 NOTAM × 0.6초 = 60초
- 실제 처리 시간: 40-70초 (변동성 큼)

---

## 개선 방안 (향후)

### 1. 실제 진행률 기반 계산
```javascript
// 백엔드에서 실제 처리 진행률 제공
// 예: 번역 완료된 NOTAM 개수 / 총 NOTAM 개수
const progress = completedNotams / totalNotams;
const remaining = (elapsed / progress) - elapsed;
```

### 2. 가중 평균 사용
```javascript
// 실제 처리 속도 반영
const avgTimePerNotam = elapsed / completedNotams;
const remaining = avgTimePerNotam * remainingNotams;
```

### 3. 단계별 예상 시간
```javascript
// 각 단계별로 다른 예상 시간
const baseTime = 5;  // PDF 변환 등 고정 시간
const translationTime = totalNotams * 0.5;  // 번역 시간
const totalEstimated = baseTime + translationTime;
```

---

## 결론

**현재 로직:**
- 단순하고 빠름
- 고정된 처리 속도(0.6초/NOTAM) 가정
- NOTAM 개수만으로 계산

**표시 형식:**
- `MM:SS` 형식 (예: "01:00")
- 1초마다 업데이트
- "거의 완료" 또는 "계산 중..." 표시

**정확도:**
- 대략적인 예상 시간 제공
- 실제 처리 시간과 ±20-30% 차이 가능
- 번역 속도가 가장 큰 변수
