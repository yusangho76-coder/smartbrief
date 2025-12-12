# 속도 향상 최적화 계획

## 현재 상태 분석

### 이미 적용된 최적화 ✅
1. **번역 워커**: 5개 (환경변수로 조정 가능)
2. **타임아웃**: 30초 설정
3. **로깅 간소화**: 10개마다 또는 15초마다 진행 로그
4. **외부 라이브러리 로그 억제**: pdfminer, urllib3 등

### 발견된 성능 병목 지점 ⚠️

#### 1. 로깅 오버헤드 (즉시 개선 가능)
- **문제**: `logging.getLogger('src.integrated_translator').setLevel(logging.DEBUG)` (83번 라인)
- **영향**: 각 NOTAM 처리마다 DEBUG 로그 출력 → I/O 오버헤드
- **예상 개선**: 5-10% 성능 향상

#### 2. 시간 변환 순차 처리
- **위치**: `app.py` 1322-1333번 라인
- **문제**: for loop로 순차 처리 (100개 NOTAM = 100번 반복)
- **영향**: NOTAM 수에 비례하여 시간 증가
- **예상 개선**: 20-40% (NOTAM 수에 따라)

#### 3. 캐시 키 비효율
- **위치**: `src/integrated_translator.py` 347번 라인
- **문제**: `e_section[:100]` 사용 → 긴 문자열 비교 오버헤드
- **해결**: 해시값 사용 (MD5/SHA256)
- **예상 개선**: 2-5% (캐시 히트 시)

#### 4. 캐시 메모리 관리 부재
- **문제**: 캐시가 무제한 증가 → 메모리 부족 가능
- **해결**: LRU 캐시 또는 크기 제한
- **예상 개선**: 메모리 안정성 + 간접 성능 향상

#### 5. 불필요한 로그 출력
- **위치**: `src/integrated_translator.py` 여러 곳
- **문제**: INFO 레벨에서도 상세 로그 출력
- **예상 개선**: 3-7% 성능 향상

---

## 즉시 적용 가능한 최적화 (우선순위 순)

### 우선순위 1: 로깅 최적화 (5분 작업)

**변경사항:**
```python
# app.py 83번 라인
# 변경 전:
logging.getLogger('src.integrated_translator').setLevel(logging.DEBUG)

# 변경 후:
logging.getLogger('src.integrated_translator').setLevel(logging.WARNING)  # 또는 INFO
```

**예상 효과**: 5-10% 성능 향상

---

### 우선순위 2: 시간 변환 병렬화 (15분 작업)

**변경사항:**
```python
# app.py 1321-1334번 라인
# 변경 전:
time_conversion_start = datetime.now()
for i, notam in enumerate(notams):
    airport_code = notam.get('airport_code', 'RKSI')
    effective_time = notam.get('effective_time', '')
    expiry_time = notam.get('expiry_time', '')
    if effective_time:
        local_time_str = notam_filter.format_notam_time_with_local(
            effective_time, expiry_time, airport_code, notam
        )
        notam['local_time_display'] = local_time_str
processing_times['time_conversion'] = (datetime.now() - time_conversion_start).total_seconds()

# 변경 후:
from concurrent.futures import ThreadPoolExecutor

def convert_time_for_notam(args):
    notam, notam_filter = args
    airport_code = notam.get('airport_code', 'RKSI')
    effective_time = notam.get('effective_time', '')
    expiry_time = notam.get('expiry_time', '')
    if effective_time:
        local_time_str = notam_filter.format_notam_time_with_local(
            effective_time, expiry_time, airport_code, notam
        )
        notam['local_time_display'] = local_time_str
    return notam

time_conversion_start = datetime.now()
if len(notams) > 10:  # 10개 이상일 때만 병렬 처리
    with ThreadPoolExecutor(max_workers=min(8, len(notams))) as executor:
        notams = list(executor.map(
            convert_time_for_notam,
            [(notam, notam_filter) for notam in notams]
        ))
else:
    for notam in notams:
        airport_code = notam.get('airport_code', 'RKSI')
        effective_time = notam.get('effective_time', '')
        expiry_time = notam.get('expiry_time', '')
        if effective_time:
            local_time_str = notam_filter.format_notam_time_with_local(
                effective_time, expiry_time, airport_code, notam
            )
            notam['local_time_display'] = local_time_str
processing_times['time_conversion'] = (datetime.now() - time_conversion_start).total_seconds()
```

**예상 효과**: 
- 50개 NOTAM: 약 30% 시간 단축 (1초 → 0.7초)
- 150개 NOTAM: 약 40% 시간 단축 (3초 → 1.8초)
- 전체 처리 시간: 약 2-5% 단축

---

### 우선순위 3: 캐시 키 최적화 (10분 작업)

**변경사항:**
```python
# src/integrated_translator.py 347번 라인
import hashlib

# 변경 전:
cache_key = f"{notam_number}_{e_section[:100]}_{index}"

# 변경 후:
# 해시 사용으로 메모리 절약 및 비교 속도 향상
text_hash = hashlib.md5(e_section.encode('utf-8')).hexdigest()[:16]
cache_key = f"{notam_number}_{text_hash}_{index}"
```

**예상 효과**: 
- 캐시 히트 시: 2-5% 성능 향상
- 메모리 사용: 약 30-50% 감소 (긴 문자열 대신 해시 사용)

---

### 우선순위 4: LRU 캐시 도입 (20분 작업)

**변경사항:**
```python
# src/integrated_translator.py 초기화 부분
from functools import lru_cache
from collections import OrderedDict

class LRUCache:
    def __init__(self, capacity=500):
        self.cache = OrderedDict()
        self.capacity = capacity
    
    def get(self, key):
        if key not in self.cache:
            return None
        # 최근 사용된 항목을 끝으로 이동
        self.cache.move_to_end(key)
        return self.cache[key]
    
    def put(self, key, value):
        if key in self.cache:
            self.cache.move_to_end(key)
        self.cache[key] = value
        if len(self.cache) > self.capacity:
            # 가장 오래된 항목 제거
            self.cache.popitem(last=False)

# __init__ 메서드에서
self.cache = LRUCache(capacity=500)  # 최대 500개 항목 캐시
```

**예상 효과**:
- 메모리 사용 안정화
- 장기 실행 시 메모리 누수 방지

---

### 우선순위 5: 불필요한 로그 줄이기 (10분 작업)

**변경사항:**
```python
# src/integrated_translator.py 여러 곳
# INFO 레벨 로그를 DEBUG로 변경 또는 제거

# 예: 358번 라인
# 변경 전:
self.logger.info(f"[NOTAM {index+1}] API 호출 시작...")

# 변경 후:
self.logger.debug(f"[NOTAM {index+1}] API 호출 시작...")  # 또는 제거
```

**예상 효과**: 3-7% 성능 향상

---

## 추가 최적화 아이디어 (장기)

### 1. PDF 변환 최적화
- 현재: pdfminer 사용
- 개선: 더 빠른 PDF 파서 검토 (PyMuPDF 등)

### 2. 번역 워커 동적 조정
- CPU 사용률에 따라 워커 수 자동 조정
- 현재: 고정 5개
- 개선: 3-8개 범위에서 동적 조정

### 3. 배치 번역 개선
- 짧은 NOTAM은 배치 처리
- 긴 NOTAM은 개별 처리
- 현재: 모두 개별 처리

### 4. 결과 캐싱 개선
- Redis 등 외부 캐시 사용 고려
- 여러 인스턴스 간 캐시 공유

---

## 예상 성능 개선 효과

### 즉시 적용 가능한 최적화 (우선순위 1-5) 모두 적용 시:

| 항목 | 개선 효과 |
|------|----------|
| 로깅 최적화 | 5-10% |
| 시간 변환 병렬화 | 2-5% (전체 시간 기준) |
| 캐시 키 최적화 | 2-5% (캐시 히트 시) |
| LRU 캐시 | 메모리 안정성 |
| 로그 줄이기 | 3-7% |
| **총 예상 개선** | **약 12-27% 성능 향상** |

### 실제 처리 시간 예상

**100개 NOTAM 처리 (현재 40초):**
- 개선 후: 약 **30-35초** (12-25% 단축)

**150개 NOTAM 처리 (현재 60초):**
- 개선 후: 약 **45-53초** (12-25% 단축)

---

## 구현 순서

1. ✅ **우선순위 1**: 로깅 최적화 (5분)
2. ✅ **우선순위 2**: 시간 변환 병렬화 (15분)
3. ✅ **우선순위 3**: 캐시 키 최적화 (10분)
4. ✅ **우선순위 5**: 로그 줄이기 (10분)
5. ⏳ **우선순위 4**: LRU 캐시 (20분, 선택적)

**총 예상 시간**: 약 40-60분

---

## 주의사항

1. **시간 변환 병렬화**: 스레드 안전성 확인 필요
2. **캐시 키 변경**: 기존 캐시 무효화됨 (재시작 시)
3. **로깅 레벨 변경**: 디버깅 시 다시 DEBUG로 변경 필요
4. **테스트**: 각 최적화마다 기능 정상 작동 확인
