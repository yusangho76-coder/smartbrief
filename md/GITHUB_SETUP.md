# GitHub 비공개 저장소 설정 가이드

원격 저장소가 설정되지 않았을 때 해결하는 방법을 설명합니다.

---

## 🔍 문제

**에러 메시지:**
```
fatal: 'origin' does not appear to be a git repository
```

**원인:**
- GitHub 원격 저장소가 설정되지 않음
- 또는 저장소가 아직 생성되지 않음

---

## ✅ 해결 방법

### 방법 1: GitHub에서 저장소 먼저 생성 (권장)

#### 1단계: GitHub에서 비공개 저장소 생성

1. [GitHub](https://github.com) 접속 및 로그인
2. 우측 상단 "+" → "New repository" 클릭
3. 저장소 정보 입력:
   - **Repository name**: `smartnotam-private` (원하는 이름)
   - **Description**: "Smart NOTAM - Private Deployment"
   - **Visibility**: **Private** 선택 (중요!)
   - "Initialize this repository with a README" 체크 해제
   - "Add .gitignore" 체크 해제 (이미 있음)
   - "Choose a license" None 선택
4. "Create repository" 클릭

#### 2단계: 원격 저장소 추가

터미널에서:

```bash
# 프로젝트 디렉토리로 이동
cd "/Users/sunghyunkim/Documents/Documents - Sunghyun/SmartNOTAM3_GCR_James (9)"

# 원격 저장소 추가 (YOUR_USERNAME을 실제 GitHub 사용자명으로 변경)
git remote add origin https://github.com/YOUR_USERNAME/smartnotam-private.git

# 확인
git remote -v
```

**또는 SSH 사용 시:**
```bash
git remote add origin git@github.com:YOUR_USERNAME/smartnotam-private.git
```

#### 3단계: 파일 추가 및 커밋

```bash
# .gitignore 먼저 추가
git add .gitignore
git commit -m "Add .gitignore"

# 필요한 파일들 추가
git add app.py
git add src/
git add templates/
git add static/
git add deploy/
git add Dockerfile
git add requirements.txt
git add .github/
git add md/
git add geojson/
git add NavData/
git add ATSplanvalidation/
git add docker-compose.yml
git add .dockerignore
git add .gcloudignore
git add .env.example
git add GITHUB_ACTIONS_DEPLOYMENT.md
git add GIT_SETUP.md

# 커밋
git commit -m "Initial commit: Smart NOTAM application"
```

#### 4단계: GitHub에 푸시

```bash
# 브랜치 이름 확인/변경
git branch -M main

# 푸시
git push -u origin main
```

**첫 푸시 시:**
- GitHub 사용자명과 비밀번호 입력 필요
- 또는 Personal Access Token 사용 (권장)

---

### 방법 2: GitHub CLI 사용 (더 쉬움)

#### 1단계: GitHub CLI 설치

```bash
# macOS
brew install gh

# 로그인
gh auth login
```

#### 2단계: 저장소 생성 및 푸시

```bash
# 저장소 생성 및 푸시 (한 번에!)
gh repo create smartnotam-private --private --source=. --remote=origin --push
```

---

## 🔐 Personal Access Token 사용 (권장)

비밀번호 대신 Personal Access Token 사용을 권장합니다.

### 1. Token 생성

1. GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)
2. "Generate new token (classic)" 클릭
3. Note: "Git Push Access"
4. Expiration: 원하는 기간 선택
5. Scopes: `repo` 체크
6. "Generate token" 클릭
7. **토큰 복사** (한 번만 보임!)

### 2. 푸시 시 사용

```bash
git push -u origin main
```

**사용자명:** GitHub 사용자명  
**비밀번호:** Personal Access Token (비밀번호 아님!)

---

## 📋 전체 과정 요약

```bash
# 1. GitHub에서 비공개 저장소 생성 (웹에서)

# 2. 원격 저장소 추가
git remote add origin https://github.com/YOUR_USERNAME/smartnotam-private.git

# 3. 파일 추가
git add .gitignore
git add app.py src/ templates/ static/ deploy/ Dockerfile requirements.txt .github/ md/ geojson/ NavData/ ATSplanvalidation/ docker-compose.yml .dockerignore .gcloudignore .env.example GITHUB_ACTIONS_DEPLOYMENT.md GIT_SETUP.md

# 4. 커밋
git commit -m "Initial commit: Smart NOTAM application"

# 5. 푸시
git branch -M main
git push -u origin main
```

---

## ⚠️ 문제 해결

### "remote origin already exists"

**원인:** 이미 origin이 설정되어 있음

**해결:**
```bash
# 기존 origin 확인
git remote -v

# 기존 origin 제거
git remote remove origin

# 새로 추가
git remote add origin https://github.com/YOUR_USERNAME/smartnotam-private.git
```

### "Authentication failed"

**원인:** 인증 실패

**해결:**
1. Personal Access Token 사용
2. 또는 SSH 키 설정

### "Repository not found"

**원인:** 저장소가 없거나 접근 권한 없음

**해결:**
1. GitHub에서 저장소 생성 확인
2. 저장소 URL 확인
3. Private 저장소인 경우 접근 권한 확인

---

## 🎯 다음 단계

GitHub에 푸시 완료 후:

1. ✅ 저장소가 Private인지 확인
2. ✅ 사용자에게 Collaborator 권한 부여
3. ✅ GitHub Actions 워크플로우 확인
4. ✅ 사용자 가이드 제공

자세한 내용: [GITHUB_ACTIONS_DEPLOYMENT.md](./GITHUB_ACTIONS_DEPLOYMENT.md)

---

**이제 GitHub에 푸시할 준비가 되었습니다!** 🚀
