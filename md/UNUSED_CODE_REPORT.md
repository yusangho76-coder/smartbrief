# 사용되지 않는 코드/함수 검토 결과

## 1. app.py에서 사용하지 않는 인스턴스

### 제거 가능한 인스턴스:
```python
# app.py 라인 140-142
notam_translator = NOTAMTranslator()  # ❌ 사용 안 함
hybrid_translator = HybridNOTAMTranslator()  # ❌ 사용 안 함
parallel_translator = ParallelHybridNOTAMTranslator()  # ❌ 사용 안 함
```

**현재 사용 중인 번역기**: `integrated_translator`만 실제로 사용됨

**제거 방법**:
- `app.py` 라인 36-38에서 import 제거
- `app.py` 라인 140-142에서 인스턴스 생성 제거

---

## 2. src/notam_filter.py에서 사용하지 않는 함수들

### 제거 가능한 함수:

#### 1. `translate_notam()` (라인 301)
```python
def translate_notam(text):
    """NOTAM 텍스트를 영어와 한국어로 번역합니다."""
    # 이 함수는 어디서도 호출되지 않음
```

#### 2. `perform_translation()` (라인 446)
```python
def perform_translation(text, target_lang, notam_type):
    # translate_notam() 내부에서만 사용
    # translate_notam()이 사용되지 않으므로 이 함수도 사용 안 함
```

#### 3. `preprocess_notam_text()` (라인 379)
```python
def preprocess_notam_text(notam_text):
    # perform_translation() 내부에서만 사용
    # 사용 안 함
```

#### 4. `postprocess_translation()` (라인 394)
```python
def postprocess_translation(translated_text):
    # perform_translation() 내부에서만 사용
    # 사용 안 함
```

#### 5. `_batch_translate_notams()` (라인 926)
```python
def _batch_translate_notams(self, notams, batch_size=10):
    # 주석 처리된 코드에서만 참조됨 (라인 2619)
    # 실제로는 호출되지 않음
```

**참고**: 이 함수들은 `integrated_translator`가 별도로 구현한 번역 로직으로 대체됨

---

## 3. 테스트/디버그 함수

### 제거 가능한 테스트 함수:

#### 1. `test_kzak_coordinate_detection()` (src/ai_route_analyzer.py 라인 1890)
```python
def test_kzak_coordinate_detection():
    """KZAK FIR 좌표 감지 기능 테스트"""
    # if __name__ == "__main__"에서만 실행
    # 프로덕션 코드에서는 사용 안 함
```

**제거 방법**: 테스트 파일로 분리하거나 제거

---

## 4. 사용되는 함수들 (제거하지 말 것)

### 다음 함수들은 실제로 사용되고 있음:

1. **`get_utc_offset()`** (src/icao.py) - `notam_filter.py`, `notam_translator.py`에서 사용
2. **`get_timezone_by_fir_pattern()`** (src/icao.py) - `get_utc_offset()` 내부에서 사용
3. **`_load_airport_timezones()`** (src/icao.py) - `get_utc_offset()` 내부에서 사용
4. **`get_utc_offset_api()`** (src/timezone_api.py) - `icao.py`에서 사용
5. **`get_timezone_info_api()`** (src/timezone_api.py) - 향후 사용 가능성 있음
6. **`analyze_notam_category()`** (src/notam_filter.py) - 실제로 사용됨
7. **`apply_color_styles()`** (src/notam_filter.py) - 실제로 사용됨
8. **`extract_e_section()`** (src/notam_filter.py) - 실제로 사용됨

---

## 5. 추천 제거 순서

### 우선순위 1 (즉시 제거 가능):
1. `app.py`의 미사용 번역기 인스턴스 (3개)
2. `src/notam_filter.py`의 미사용 번역 함수들 (5개)

### 우선순위 2 (검토 후 제거):
1. `test_kzak_coordinate_detection()` - 테스트 파일로 이동 고려

---

## 6. 예상 효과

- **코드 라인 수 감소**: 약 200-300 라인 감소
- **메모리 사용량 감소**: 사용하지 않는 인스턴스 3개 제거
- **유지보수성 향상**: 실제 사용되는 코드만 남김으로 코드 이해도 향상
- **로딩 시간 단축**: 불필요한 모듈 import 및 인스턴스 생성 제거

