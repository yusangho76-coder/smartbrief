# GitHub 푸시 오류 해결: workflow scope 필요

워크플로우 파일을 푸시하려면 Personal Access Token에 `workflow` 권한이 필요합니다.

---

## 🔍 문제

**에러 메시지:**
```
refusing to allow an OAuth App to create or update workflow 
`.github/workflows/deploy-cloud-run.yml` without `workflow` scope
```

**원인:**
- Personal Access Token에 `workflow` 권한이 없음
- GitHub Actions 워크플로우 파일은 특별한 권한 필요

---

## ✅ 해결 방법

### 방법 1: Personal Access Token에 workflow 권한 추가 (권장)

#### 1단계: 새 Token 생성

1. [GitHub Settings](https://github.com/settings/tokens) 접속
2. "Personal access tokens" → "Tokens (classic)" 클릭
3. "Generate new token (classic)" 클릭
4. Token 정보 입력:
   - **Note**: "Git Push with Workflow"
   - **Expiration**: 원하는 기간 선택
   - **Scopes**: 다음을 체크:
     - ✅ `repo` (전체 저장소 접근)
     - ✅ `workflow` (워크플로우 업데이트) ← **중요!**
5. "Generate token" 클릭
6. **토큰 복사** (한 번만 보임!)

#### 2단계: Git에 새 Token 사용

**방법 A: URL에 토큰 포함**

```bash
# 원격 저장소 URL 변경
git remote set-url origin https://YOUR_TOKEN@github.com/rokafpilot/smartnotam3-private.git

# 푸시
git push -u origin main
```

**방법 B: Git Credential Helper 사용**

```bash
# macOS Keychain 사용
git config --global credential.helper osxkeychain

# 푸시 시도
git push -u origin main
# 사용자명: rokafpilot
# 비밀번호: Personal Access Token (workflow 권한 포함)
```

---

### 방법 2: 워크플로우 파일 나중에 추가

워크플로우 파일 없이 먼저 푸시:

```bash
# 워크플로우 파일 제외
git rm --cached .github/workflows/deploy-cloud-run.yml

# 커밋
git commit -m "Temporarily remove workflow file"

# 푸시
git push -u origin main

# 나중에 워크플로우 파일 추가 (토큰 권한 추가 후)
git add .github/workflows/deploy-cloud-run.yml
git commit -m "Add GitHub Actions workflow"
git push origin main
```

---

### 방법 3: GitHub CLI 사용 (가장 쉬움)

```bash
# GitHub CLI 설치 (없다면)
brew install gh

# 로그인
gh auth login

# 저장소에 푸시
gh repo sync

# 또는 직접 푸시
git push -u origin main
```

GitHub CLI는 자동으로 올바른 권한을 사용합니다.

---

## 🎯 추천 순서

### 빠른 해결 (5분)

1. **Personal Access Token 재생성** (workflow 권한 포함)
2. **Git에 새 토큰 사용**
3. **푸시**

### 단계별 가이드

#### 1. Token 생성

```
GitHub → Settings → Developer settings → 
Personal access tokens → Tokens (classic) → 
Generate new token (classic)

Scopes:
✅ repo
✅ workflow  ← 이것이 중요!
```

#### 2. Git 원격 URL 업데이트

```bash
# 토큰을 URL에 포함 (보안상 권장하지 않지만 빠름)
git remote set-url origin https://YOUR_TOKEN@github.com/rokafpilot/smartnotam3-private.git

# 또는 credential helper 사용 (더 안전)
git config --global credential.helper osxkeychain
```

#### 3. 푸시

```bash
git push -u origin main
```

---

## 🔐 보안 팁

### Token을 URL에 포함하는 경우

**주의:**
- ⚠️ Git 히스토리에 토큰이 남을 수 있음
- ⚠️ 다른 사람이 볼 수 있음

**더 안전한 방법:**
```bash
# credential helper 사용
git config --global credential.helper osxkeychain

# 푸시 시 토큰 입력 (한 번만)
git push -u origin main
```

---

## 📋 전체 명령어 (복사해서 사용)

```bash
# 1. 원격 저장소 확인
git remote -v

# 2. Personal Access Token 생성 (GitHub 웹에서)
#    - repo 권한
#    - workflow 권한

# 3. credential helper 설정
git config --global credential.helper osxkeychain

# 4. 푸시
git push -u origin main
# 사용자명: rokafpilot
# 비밀번호: Personal Access Token
```

---

## ✅ 성공 확인

푸시가 성공하면:

```
Enumerating objects: X, done.
Counting objects: 100% (X/X), done.
Writing objects: 100% (X/X), done.
To https://github.com/rokafpilot/smartnotam3-private.git
 * [new branch]      main -> main
Branch 'main' set up to track remote branch 'main' from 'origin'.
```

GitHub 저장소에서 파일들이 보이면 성공! ✅

---

**Personal Access Token에 `workflow` 권한을 추가하면 해결됩니다!** 🔑
