# GitHub Actions + 비공개 저장소 배포 가이드

소스 코드를 공개하지 않고 사용자가 배포할 수 있는 방법을 단계별로 설명합니다.

---

## 🎯 개요

**이 방법의 핵심:**
- 소스 코드는 GitHub 비공개 저장소에만 있음
- 사용자는 저장소 접근 권한만 받음
- GitHub Actions가 자동으로 배포
- 사용자는 소스 코드를 직접 볼 필요 없음 ✅

---

## 📋 전체 과정 요약

```
1. 개발자: GitHub 비공개 저장소 생성
2. 개발자: 코드 업로드
3. 개발자: 사용자에게 Collaborator 권한 부여
4. 사용자: GitHub Secrets 설정
5. 사용자: GitHub Actions로 배포 실행
6. 완료! (소스 코드는 보지 않음)
```

---

## 🔧 개발자 작업 (1회만)

### 1단계: GitHub 비공개 저장소 생성

1. [GitHub](https://github.com) 접속 및 로그인
2. 우측 상단 "+" → "New repository" 클릭
3. 저장소 정보 입력:
   - **Repository name**: `smartnotam-private` (원하는 이름)
   - **Description**: "Smart NOTAM - Private Deployment"
   - **Visibility**: **Private** 선택 (중요!)
   - "Initialize this repository with a README" 체크 해제
4. "Create repository" 클릭

### 2단계: 코드 업로드

**방법 A: Git 명령어 사용**

```bash
# 프로젝트 디렉토리로 이동
cd "/Users/sunghyunkim/Documents/Documents - Sunghyun/SmartNOTAM3_GCR_James (9)"

# Git 초기화 (이미 있으면 스킵)
git init

# 원격 저장소 추가
git remote add origin https://github.com/YOUR_USERNAME/smartnotam-private.git

# 파일 추가
git add .

# 커밋
git commit -m "Initial commit"

# 푸시
git branch -M main
git push -u origin main
```

**방법 B: GitHub Desktop 사용**

1. GitHub Desktop 실행
2. "Add" → "Add Existing Repository"
3. 프로젝트 폴더 선택
4. "Publish repository" 클릭
5. "Private" 선택
6. "Publish repository" 클릭

### 3단계: GitHub Actions 워크플로우 확인

`.github/workflows/deploy-cloud-run.yml` 파일이 이미 있는지 확인:

```bash
ls -la .github/workflows/
```

**파일이 있으면:** 그대로 사용 ✅

**파일이 없으면:** 위의 파일 내용을 `.github/workflows/deploy-cloud-run.yml`에 생성

### 4단계: 사용자에게 권한 부여

1. GitHub 저장소 페이지 접속
2. "Settings" 탭 클릭
3. 왼쪽 메뉴에서 "Collaborators" 선택
4. "Add people" 버튼 클릭
5. 사용자 GitHub 사용자명 또는 이메일 입력
6. 권한: "Write" 선택 (읽기/쓰기 권한)
7. "Add [username] to this repository" 클릭
8. 사용자에게 초대 이메일 전송됨

**또는 직접 링크 공유:**
```
https://github.com/YOUR_USERNAME/smartnotam-private/invitations
```

---

## 👤 사용자 작업 (배포)

### 1단계: GitHub 초대 수락

1. 이메일에서 초대 링크 클릭
2. 또는 저장소 초대 페이지 접속
3. "Accept invitation" 클릭
4. 저장소 접근 권한 획득 ✅

### 2단계: Google Cloud 서비스 계정 생성

**사용자가 자신의 Google Cloud에서 생성:**

```bash
# 1. Google Cloud 프로젝트 생성 (또는 기존 프로젝트 사용)
gcloud projects create smartnotam-user-project
# 또는 기존 프로젝트 ID 사용

# 2. 서비스 계정 생성
gcloud iam service-accounts create github-actions \
  --display-name="GitHub Actions Deployer" \
  --project=smartnotam-user-project

# 3. 권한 부여
gcloud projects add-iam-policy-binding smartnotam-user-project \
  --member="serviceAccount:github-actions@smartnotam-user-project.iam.gserviceaccount.com" \
  --role="roles/run.admin"

gcloud projects add-iam-policy-binding smartnotam-user-project \
  --member="serviceAccount:github-actions@smartnotam-user-project.iam.gserviceaccount.com" \
  --role="roles/artifactregistry.writer"

gcloud projects add-iam-policy-binding smartnotam-user-project \
  --member="serviceAccount:github-actions@smartnotam-user-project.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountUser"

# 4. 키 생성
gcloud iam service-accounts keys create key.json \
  --iam-account=github-actions@smartnotam-user-project.iam.gserviceaccount.com

# 5. 키 파일 내용 확인 (전체 내용 복사 필요)
cat key.json
```

**또는 Google Cloud Console에서:**

1. [Google Cloud Console](https://console.cloud.google.com) 접속
2. 프로젝트 선택
3. "IAM & Admin" → "Service Accounts" 메뉴
4. "Create Service Account" 클릭
5. 이름: `github-actions`
6. "Create and Continue"
7. 역할 부여:
   - Cloud Run Admin
   - Artifact Registry Writer
   - Service Account User
8. "Done"
9. 생성된 서비스 계정 클릭
10. "Keys" 탭 → "Add Key" → "Create new key"
11. JSON 선택 → "Create"
12. 다운로드된 JSON 파일 열기 → 전체 내용 복사

### 3단계: GitHub Secrets 설정

1. GitHub 저장소 페이지 접속
2. "Settings" 탭 클릭
3. 왼쪽 메뉴에서 "Secrets and variables" → "Actions" 선택
4. "New repository secret" 버튼 클릭

**다음 3개의 Secret을 각각 생성:**

#### Secret 1: GCP_PROJECT_ID
- **Name**: `GCP_PROJECT_ID`
- **Secret**: 사용자의 Google Cloud 프로젝트 ID (예: `smartnotam-user-project`)
- "Add secret" 클릭

#### Secret 2: GCP_SA_KEY
- **Name**: `GCP_SA_KEY`
- **Secret**: 서비스 계정 키 JSON 파일의 **전체 내용** (위에서 복사한 것)
- "Add secret" 클릭

**중요:** JSON 파일의 전체 내용을 복사해야 합니다:
```json
{
  "type": "service_account",
  "project_id": "smartnotam-user-project",
  "private_key_id": "...",
  "private_key": "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n",
  ...
}
```

#### Secret 3: GEMINI_API_KEY
- **Name**: `GEMINI_API_KEY`
- **Secret**: Gemini API 키 (예: `AIzaSy...`)
- "Add secret" 클릭

### 4단계: 배포 실행

1. GitHub 저장소 페이지 접속
2. "Actions" 탭 클릭
3. 왼쪽 메뉴에서 "Deploy to Google Cloud Run" 워크플로우 선택
4. "Run workflow" 버튼 클릭 (우측 상단)
5. "Run workflow" 확인
6. 배포 진행 상황 확인

**배포 완료까지:**
- 약 5-10분 소요
- 실시간으로 진행 상황 확인 가능
- 초록색 체크 표시 = 성공 ✅

### 5단계: 배포 URL 확인

1. "Actions" 탭에서 실행된 워크플로우 클릭
2. "Get deployment URL" 단계 클릭
3. 로그에서 URL 확인:
   ```
   ✅ 배포 완료: https://smartnotam-xxxxx-xx.a.run.app
   ```

**또는 Google Cloud Console에서:**
1. [Cloud Run 콘솔](https://console.cloud.google.com/run) 접속
2. `smartnotam` 서비스 선택
3. URL 확인

---

## 🔄 재배포 (코드 업데이트 후)

### 개발자가 코드 업데이트 시

```bash
# 코드 수정 후
git add .
git commit -m "Update feature"
git push origin main
```

**자동으로 배포됨!** ✅
- GitHub Actions가 자동으로 감지
- 자동으로 빌드 및 배포

### 사용자가 수동 재배포 시

1. "Actions" 탭
2. "Deploy to Google Cloud Run" 선택
3. "Run workflow" 클릭

---

## 🔐 보안 고려사항

### 1. 비공개 저장소 필수

- ✅ **Private** 저장소 사용
- ❌ Public 저장소는 누구나 볼 수 있음

### 2. Secrets 보안

- ✅ Secrets는 암호화되어 저장
- ✅ 로그에 출력되지 않음
- ✅ Collaborator만 볼 수 있음

### 3. 접근 권한 관리

- ✅ 필요한 사람만 Collaborator 권한
- ✅ 더 이상 필요 없으면 권한 제거
- ✅ Settings → Collaborators에서 관리

### 4. 서비스 계정 키 보안

- ⚠️ 서비스 계정 키는 민감 정보
- ⚠️ GitHub Secrets에만 저장
- ⚠️ 로컬에 남기지 않기

---

## 📊 장단점

### 장점

- ✅ **소스 코드 보호** - 사용자가 직접 볼 수 없음
- ✅ **자동 배포** - 코드 push 시 자동 배포
- ✅ **사용자 편의성** - Secrets만 설정하면 됨
- ✅ **업데이트 용이** - 개발자가 push하면 자동 반영
- ✅ **버전 관리** - Git으로 코드 관리

### 단점

- ⚠️ **GitHub 계정 필요** - 사용자도 GitHub 계정 필요
- ⚠️ **초기 설정 복잡** - 서비스 계정 생성 필요
- ⚠️ **GitHub Actions 이해 필요** - 기본 개념 이해 필요

---

## 🛠️ 문제 해결

### 문제 1: "Workflow not found"

**원인:** `.github/workflows/deploy-cloud-run.yml` 파일이 없음

**해결:**
1. 저장소에 `.github/workflows/` 폴더 생성
2. `deploy-cloud-run.yml` 파일 생성
3. 워크플로우 내용 추가

### 문제 2: "Secrets not found"

**원인:** Secrets가 설정되지 않음

**해결:**
1. Settings → Secrets → Actions 확인
2. 필요한 3개 Secret 모두 설정 확인:
   - GCP_PROJECT_ID
   - GCP_SA_KEY
   - GEMINI_API_KEY

### 문제 3: "Permission denied"

**원인:** 서비스 계정 권한 부족

**해결:**
```bash
# 권한 다시 부여
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:github-actions@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/run.admin"
```

### 문제 4: "Build failed"

**원인:** Dockerfile 오류 또는 네트워크 문제

**해결:**
1. Actions 로그 확인
2. Dockerfile 확인
3. requirements.txt 확인

---

## 📝 체크리스트

### 개발자 체크리스트

- [ ] GitHub 비공개 저장소 생성
- [ ] 코드 업로드
- [ ] GitHub Actions 워크플로우 확인
- [ ] 사용자에게 Collaborator 권한 부여
- [ ] 사용자 가이드 제공

### 사용자 체크리스트

- [ ] GitHub 초대 수락
- [ ] Google Cloud 프로젝트 생성
- [ ] 서비스 계정 생성 및 권한 부여
- [ ] 서비스 계정 키 생성
- [ ] GitHub Secrets 설정 (3개)
- [ ] GitHub Actions로 배포 실행
- [ ] 배포 URL 확인

---

## 💡 팁

### 1. 여러 사용자에게 배포

각 사용자마다:
- Collaborator 권한 부여
- 각자의 Google Cloud 프로젝트 사용
- 각자의 Secrets 설정

### 2. 자동 배포 비활성화

코드 push 시 자동 배포를 원하지 않으면:

`.github/workflows/deploy-cloud-run.yml`에서:
```yaml
on:
  # push:  # 주석 처리
  #   branches:
  #     - main
  workflow_dispatch:  # 수동 실행만
```

### 3. 배포 알림

GitHub Actions에서 배포 완료 시 알림 받기:
- Settings → Notifications → Actions 체크

---

## 🎯 요약

### 개발자 작업 (1회)

1. 비공개 저장소 생성
2. 코드 업로드
3. 사용자 권한 부여

### 사용자 작업

1. 초대 수락
2. Google Cloud 설정
3. GitHub Secrets 설정
4. 배포 실행

### 결과

- ✅ 소스 코드 보호
- ✅ 자동 배포
- ✅ 사용자는 코드를 보지 않음

---

**이제 소스 코드를 공개하지 않고도 사용자가 배포할 수 있습니다!** 🎉
