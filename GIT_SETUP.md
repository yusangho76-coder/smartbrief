# Git 저장소 설정 가이드

Git 저장소에 너무 많은 파일이 추적되어 성능 문제가 발생할 수 있습니다. 이 가이드를 따라 설정하세요.

---

## 🔍 문제 상황

**에러 메시지:**
```
The git repository has too many active changes, 
only a subset of Git features will be enabled.
```

**원인:**
- `.gitignore` 파일이 없어서 불필요한 파일들이 추적됨
- `__pycache__`, `.venv`, `.env` 등이 Git에 포함됨
- 너무 많은 파일로 인한 성능 저하

---

## ✅ 해결 방법

### 1단계: .gitignore 파일 확인

`.gitignore` 파일이 루트에 있는지 확인:

```bash
ls -la .gitignore
```

**파일이 있으면:** 다음 단계로

**파일이 없으면:** 이미 생성되어 있습니다 ✅

### 2단계: Git 캐시 정리 (이미 추적 중인 파일 제거)

이미 Git에 추가된 불필요한 파일들을 제거:

```bash
# Git 캐시에서 제거 (파일은 삭제하지 않음)
git rm -r --cached __pycache__/
git rm -r --cached .venv/
git rm -r --cached .env
git rm -r --cached ATSplanvalidation/.venv/
git rm -r --cached ATSplanvalidation/__pycache__/
git rm -r --cached src/__pycache__/
git rm -r --cached temp/
git rm -r --cached uploads/
git rm -r --cached saved_results/

# .gitignore 적용
git add .gitignore
git commit -m "Add .gitignore and remove unnecessary files"
```

### 3단계: Git 상태 확인

```bash
git status
```

이제 훨씬 적은 수의 파일만 표시되어야 합니다.

---

## 📋 .gitignore에 포함된 항목

다음 항목들이 자동으로 제외됩니다:

- ✅ `__pycache__/` - Python 캐시 파일
- ✅ `*.pyc` - 컴파일된 Python 파일
- ✅ `.venv/`, `venv/` - 가상환경
- ✅ `.env` - 환경 변수 파일
- ✅ `temp/`, `uploads/` - 임시 파일
- ✅ `saved_results/` - 저장된 결과 파일
- ✅ `*.log` - 로그 파일
- ✅ `.DS_Store` - macOS 시스템 파일
- ✅ `*.backup` - 백업 파일

---

## 🚀 Git 저장소 초기화 (처음부터 시작)

**이미 Git 저장소가 있지만 처음부터 깨끗하게 시작하고 싶다면:**

```bash
# 기존 Git 제거
rm -rf .git

# 새로 초기화
git init

# .gitignore 추가
git add .gitignore

# 필요한 파일만 추가
git add app.py
git add src/
git add templates/
git add static/
git add deploy/
git add Dockerfile
git add requirements.txt
git add .github/
# ... 필요한 파일들만 추가

# 첫 커밋
git commit -m "Initial commit"
```

---

## 💡 추천 작업 순서

### 옵션 A: 기존 저장소 정리 (권장)

```bash
# 1. .gitignore 확인 (이미 생성됨)
cat .gitignore

# 2. 불필요한 파일 제거
git rm -r --cached __pycache__/ .venv/ .env temp/ uploads/ saved_results/ 2>/dev/null || true

# 3. .gitignore 추가
git add .gitignore

# 4. 커밋
git commit -m "Add .gitignore and clean up repository"
```

### 옵션 B: 새로 시작

```bash
# 1. 기존 Git 제거
rm -rf .git

# 2. 새로 초기화
git init

# 3. .gitignore 추가
git add .gitignore
git commit -m "Initial commit with .gitignore"

# 4. 필요한 파일만 추가
git add app.py src/ templates/ static/ deploy/ Dockerfile requirements.txt .github/
git commit -m "Add application files"
```

---

## ⚠️ 주의사항

### 제외하면 안 되는 파일

다음 파일들은 **반드시 포함**해야 합니다:

- ✅ `app.py` - 메인 애플리케이션
- ✅ `src/` - 소스 코드
- ✅ `templates/` - HTML 템플릿
- ✅ `static/` - 정적 파일
- ✅ `Dockerfile` - Docker 이미지 정의
- ✅ `requirements.txt` - Python 의존성
- ✅ `deploy/` - 배포 스크립트
- ✅ `.github/` - GitHub Actions 워크플로우

### 제외해도 되는 파일

다음 파일들은 **제외**해도 됩니다:

- ❌ `__pycache__/` - 자동 생성
- ❌ `.venv/` - 가상환경 (각자 설치)
- ❌ `.env` - 환경 변수 (민감 정보)
- ❌ `temp/`, `uploads/` - 임시 파일
- ❌ `saved_results/` - 사용자 결과 파일
- ❌ `*.pyc` - 컴파일된 파일

---

## 🔧 빠른 해결 스크립트

다음 명령어를 한 번에 실행:

```bash
# 불필요한 파일 제거
git rm -r --cached __pycache__/ .venv/ .env temp/ uploads/ saved_results/ 2>/dev/null || true

# .gitignore 추가
git add .gitignore

# 커밋
git commit -m "Add .gitignore and remove unnecessary files"

# 상태 확인
git status
```

---

## 📊 결과 확인

정상적으로 설정되면:

```bash
git status
```

**이전:** 수백 개의 파일 표시  
**이후:** 필요한 파일만 표시 ✅

---

## 🎯 다음 단계

`.gitignore`가 제대로 작동하면:

1. ✅ Git 성능 향상
2. ✅ 불필요한 파일 제외
3. ✅ 저장소 크기 감소
4. ✅ GitHub에 업로드 시 빠름

---

**이제 Git 저장소가 정상적으로 작동할 것입니다!** ✅
