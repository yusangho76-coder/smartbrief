# 임시 파일 분석 및 정리 방안

## 발견된 임시 파일들

### 1. Python 캐시 파일 (__pycache__)
**위치**: 
- `./__pycache__/` (252KB)
- `./src/__pycache__/` (많은 .pyc 파일들)
- `./ATSplanvalidation/__pycache__/`
- `./ATSplanvalidation/.venv/` 내부의 수많은 __pycache__

**용량**: 약 252KB (프로젝트 루트 기준, .venv 제외)

**정리 가능**: ✅ 자동 재생성되므로 삭제 가능

---

### 2. saved_results 폴더 (HTML 결과 파일)
**위치**: `./saved_results/`
**용량**: **8.7MB**
**파일 목록**:
- NOTAM_Results_20251120_203002.html
- NOTAM_Results_20251128_182745.html
- NOTAM_Results_20251203_141247.html

**현재 설정**: `cleanup_old_saved_results(keep_count=5)` - 최근 5개 유지

**정리 가능**: ✅ 2개로 줄이기 권장 (약 5.8MB 절감)

---

### 3. 백업 파일
**위치**: 
- `./cloudbuild.yaml.backup.57361`

**정리 가능**: ✅ 삭제 가능 (백업 파일)

---

### 4. macOS 시스템 파일 (.DS_Store)
**개수**: 6개
**정리 가능**: ✅ 삭제 가능 (자동 재생성됨)

---

### 5. 로그 파일
**위치**: 
- `./ATSplanvalidation/logs/streamlit.log`

**정리 가능**: ✅ 삭제 가능 (로그는 자동 재생성됨)

---

## 정리 권장 사항

### 즉시 정리 가능 (안전)
1. ✅ `__pycache__` 폴더들 - 자동 재생성됨
2. ✅ `.DS_Store` 파일들 - 시스템 파일, 자동 재생성됨
3. ✅ `cloudbuild.yaml.backup.*` - 백업 파일
4. ✅ 로그 파일들

### 설정 변경 권장
1. ✅ `saved_results` 정리 개수: 5개 → 2개로 변경

---

## 예상 용량 절감

- `saved_results`: 8.7MB → 약 2.9MB (5.8MB 절감)
- `__pycache__`: 252KB → 0KB (자동 재생성)
- `.DS_Store`: 미미함
- **총 절감**: 약 **6MB 이상**
