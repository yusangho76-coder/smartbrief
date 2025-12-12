# NOTAM 분석 및 번역 규칙 검증 보고서

## 검증 일자
2025년 11월 20일

## 검증 항목

### 1. original_text 필드 완전성 검증

#### 현재 구현 상태
- ✅ **일반 NOTAM**: D) 필드부터 시작하는 모든 내용을 추출
  - D) 필드가 있으면: D) 필드부터 시작
  - D) 필드가 없으면: E) 필드부터 시작
  - 이론적으로 D), E), F), G), COMMENT) 필드가 모두 포함됨

- ✅ **COAD NOTAM**: 시간 정보와 NOTAM 번호 헤더를 제거하고 그 이후의 모든 내용을 추출
  - 패턴 매칭으로 헤더 제거: `DDMMMYY HH:MM - (UFN|PERM|DDMMMYY HH:MM) [A-Z]{4} COAD##/YY`
  - 헤더를 찾지 못하면 첫 줄 제거 시도

#### 코드 위치
- `src/notam_filter.py`의 `_filter_airport_notams` 메서드 (라인 2360-2398)
- `src/notam_filter.py`의 `_filter_package_notams` 메서드 (라인 2570-2608)

#### 검증 결과
코드 로직상으로는 모든 필드가 포함되어야 합니다. 실제 결과에서 문제가 있는지 확인하려면 실제 NOTAM 데이터를 테스트해야 합니다.

---

### 2. 번역 규칙 검증

#### 2.1 TWY vs TXL 번역 규칙

##### 규칙 정의
- **TWY** = 택시웨이 (Taxiway: 공항 내에서 항공기의 이동을 위해 설계된 공식 통로)
- **TXL** = 택시레인 (Taxilane: 주기장(에이프런) 또는 격납고 주변에서 주차 공간 사이를 이동하기 위한 보조 이동로)
- **절대 금지 사항**:
  - TWY를 "택시레인"으로 번역하지 않음
  - TXL을 "택시웨이"로 번역하지 않음
  - TXL을 "텍사스"나 "딜레이"로 번역하지 않음

##### 프롬프트 위치
- `src/integrated_translator.py`의 `create_korean_integrated_prompt` 메서드 (라인 786-860)
- `src/integrated_translator.py`의 `create_english_integrated_prompt` 메서드 (라인 1073-1083)

##### 검증 결과
✅ 규칙이 프롬프트에 명확하게 정의되어 있습니다.

---

#### 2.2 DE/ANTI-ICING FLUID 번역 규칙

##### 규칙 정의
- **DE/ANTI-ICING FLUID** → "제/방빙 용액" (절대 "안티이싱 유체"로 번역하지 않음)
- **DE-ICING** = 제빙 (기존 얼음을 제거)
- **ANTI-ICING** = 방빙 (얼음 형성 방지)
- "/" 기호를 반드시 유지

##### 프롬프트 위치
- `src/integrated_translator.py`의 `create_korean_integrated_prompt` 메서드 (라인 834-837, 950)
- `src/integrated_translator.py`의 `create_english_integrated_prompt` 메서드 (라인 1085-1094)

##### 검증 결과
✅ 규칙이 프롬프트에 명확하게 정의되어 있습니다.

---

#### 2.3 회사명 번역 규칙

##### 규칙 정의
- **INLAND** → INLAND (Inland Technologies 회사명, 절대 "국내"로 번역하지 않음)
- **Purolator** → Purolator 또는 Purolator(택배/물류 회사) (번역하지 않고 그대로 유지)
- **KILFROST** → KILFROST (회사명, 번역하지 않음)
- **DOW** → DOW (DOW Chemical 회사명, 번역하지 않음)
- **KAS** → KAS (회사명, 번역하지 않음)

##### 프롬프트 위치
- `src/integrated_translator.py`의 `create_korean_integrated_prompt` 메서드 (라인 839-846, 964, 984)

##### 오번역 수정 로직
- `src/integrated_translator.py`의 `remove_instruction_text` 메서드 (라인 1118-1129)
  - "국내"가 제빙 용액 관련 문맥에서 나오면 "INLAND"로 자동 수정

##### 검증 결과
✅ 규칙이 프롬프트에 명확하게 정의되어 있고, 오번역 수정 로직도 구현되어 있습니다.

---

### 3. COAD NOTAM 원문 추출 로직 검증

#### 현재 구현 상태
- ✅ 시간 정보와 NOTAM 번호 헤더 패턴 매칭: `\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}\s*-\s*(?:UFN|PERM|\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2})\s+[A-Z]{4}\s+COAD\d{2}/\d{2}`
- ✅ 헤더를 찾으면 그 이후의 모든 내용 추출
- ✅ 헤더를 찾지 못하면 첫 줄 제거 시도

#### 코드 위치
- `src/notam_filter.py`의 `_filter_airport_notams` 메서드 (라인 2365-2382)
- `src/notam_filter.py`의 `_filter_package_notams` 메서드 (라인 2575-2592)

#### 검증 결과
✅ 로직이 올바르게 구현되어 있습니다.

---

## 발견된 잠재적 문제점

### 1. original_text 필드 완전성
- **이론적으로는 문제 없음**: D) 필드부터 시작하는 모든 내용을 가져오므로 F), G), COMMENT) 필드도 포함되어야 함
- **실제 검증 필요**: 실제 NOTAM 데이터에서 모든 필드가 포함되는지 확인 필요

### 2. 번역 규칙 준수
- **프롬프트에 명확히 정의됨**: 모든 번역 규칙이 프롬프트에 명시되어 있음
- **실제 검증 필요**: 실제 번역 결과에서 규칙이 준수되는지 확인 필요

---

## 권장 사항

### 1. 실제 데이터 검증
실제 NOTAM 데이터를 사용하여 다음을 검증하세요:
- `original_text`에 D), E), F), G), COMMENT) 필드가 모두 포함되는지
- TWY vs TXL 번역이 올바른지
- DE/ANTI-ICING FLUID 번역이 올바른지
- 회사명(Purolator, INLAND 등)이 번역되지 않았는지

### 2. 검증 스크립트 사용
`scripts/verify_notam_rules.py` 스크립트를 사용하여 NOTAM 결과를 자동으로 검증할 수 있습니다.

### 3. 로깅 강화
문제가 발견되면 다음 정보를 로깅하세요:
- NOTAM 번호
- 원문 텍스트
- 추출된 original_text
- 번역 결과
- 발견된 문제점

---

## 결론

코드 검토 결과, **이론적으로는 모든 규칙이 올바르게 구현되어 있습니다**. 하지만 실제 NOTAM 데이터를 사용한 검증이 필요합니다. 

특히 다음 사항을 확인하세요:
1. `original_text`에 모든 필드(D), E), F), G), COMMENT))가 포함되는지
2. 번역 결과가 규칙을 준수하는지
3. COAD NOTAM의 원문에서 헤더가 제거되었는지

실제 데이터에서 문제가 발견되면 해당 사례를 보고해주시면 수정하겠습니다.

