# 배포 문제 해결 가이드

이 문서는 배포 중 발생할 수 있는 일반적인 문제와 해결 방법을 안내합니다.

## 🔍 문제 진단

### 1. 스크립트 실행 전 확인사항

```bash
# gcloud 설치 확인
gcloud --version

# 로그인 상태 확인
gcloud auth list

# 현재 프로젝트 확인
gcloud config get-value project
```

---

## ❌ 일반적인 오류 및 해결 방법

### 오류 1: "gcloud: command not found"

**증상:**
```bash
./deploy/deploy_simple.sh: line X: gcloud: command not found
```

**원인:** Google Cloud SDK가 설치되지 않았거나 PATH에 없음

**해결 방법:**

#### macOS
```bash
# Homebrew로 설치
brew install google-cloud-sdk

# PATH 추가 (필요한 경우)
echo 'export PATH="/usr/local/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

#### Linux
```bash
# 설치 스크립트 실행
curl https://sdk.cloud.google.com | bash
exec -l $SHELL

# 또는 패키지 매니저 사용
# Ubuntu/Debian
sudo apt-get install google-cloud-sdk
```

#### Windows
1. [공식 설치 프로그램](https://cloud.google.com/sdk/docs/install) 다운로드
2. 설치 후 PowerShell 재시작

**확인:**
```bash
gcloud --version
```

---

### 오류 2: "Permission denied"

**증상:**
```bash
bash: ./deploy/deploy_simple.sh: Permission denied
```

**원인:** 스크립트에 실행 권한이 없음

**해결 방법:**
```bash
chmod +x deploy/deploy_simple.sh
```

**확인:**
```bash
ls -l deploy/deploy_simple.sh
# -rwxr-xr-x ... 이어야 함 (x가 있어야 함)
```

---

### 오류 3: "ERROR: (gcloud.auth.login) You do not have permission"

**증상:**
```bash
ERROR: (gcloud.auth.login) You do not have permission
```

**원인:** Google 계정 권한 문제

**해결 방법:**
```bash
# 기존 인증 정보 제거
gcloud auth revoke --all

# 다시 로그인
gcloud auth login
```

**팁:** 브라우저가 열리면 올바른 Google 계정으로 로그인하세요.

---

### 오류 4: "ERROR: (gcloud.projects.create) Project creation failed"

**증상:**
```bash
ERROR: (gcloud.projects.create) Project creation failed
```

**원인:**
- 프로젝트 ID가 이미 사용 중
- 프로젝트 생성 권한 없음
- 빌링 계정 미연결

**해결 방법:**

#### 방법 1: 다른 프로젝트 ID 사용
```bash
# config.sh에서 다른 ID 사용
PROJECT_ID="smartnotam-$(date +%s)"
```

#### 방법 2: 기존 프로젝트 사용
```bash
# config.sh에서 기존 프로젝트 ID 입력
PROJECT_ID="your-existing-project-id"
```

#### 방법 3: 프로젝트 ID 자동 생성 (권장)
```bash
# config.sh에서 PROJECT_ID를 비워두기
PROJECT_ID=""
```

---

### 오류 5: "ERROR: (gcloud.services.enable) PERMISSION_DENIED"

**증상:**
```bash
ERROR: (gcloud.services.enable) PERMISSION_DENIED
```

**원인:** 프로젝트에 대한 권한 부족

**해결 방법:**
```bash
# 프로젝트 소유자 확인
gcloud projects get-iam-policy YOUR_PROJECT_ID

# 필요한 권한 확인
# - roles/owner 또는
# - roles/editor 또는
# - roles/serviceusage.serviceUsageAdmin
```

**권한 요청:** 프로젝트 소유자에게 권한을 요청하세요.

---

### 오류 6: "ERROR: (gcloud.builds.submit) Build failed"

**증상:**
```bash
ERROR: (gcloud.builds.submit) Build failed
```

**원인:**
- Dockerfile 오류
- requirements.txt 문제
- 네트워크 문제

**해결 방법:**

#### 1. Dockerfile 확인
```bash
# Dockerfile이 프로젝트 루트에 있는지 확인
ls -l Dockerfile

# Dockerfile 내용 확인
cat Dockerfile
```

#### 2. requirements.txt 확인
```bash
# requirements.txt가 있는지 확인
ls -l requirements.txt

# 내용 확인
cat requirements.txt
```

#### 3. 로컬에서 빌드 테스트
```bash
# Docker가 설치되어 있다면
docker build -t test-build .
```

#### 4. Cloud Build 로그 확인
```bash
# 최근 빌드 로그 확인
gcloud builds list --limit=5

# 특정 빌드 로그 확인
gcloud builds log BUILD_ID
```

---

### 오류 7: "ERROR: (gcloud.run.deploy) Revision failed"

**증상:**
```bash
ERROR: (gcloud.run.deploy) Revision failed
```

**원인:**
- 환경변수 오류
- 메모리 부족
- 타임아웃

**해결 방법:**

#### 1. 로그 확인
```bash
gcloud run services logs read smartnotam \
  --region asia-northeast3 \
  --limit 50
```

#### 2. 환경변수 확인
```bash
gcloud run services describe smartnotam \
  --region asia-northeast3 \
  --format="value(spec.template.spec.containers[0].env)"
```

#### 3. 리소스 증가
```bash
gcloud run services update smartnotam \
  --region asia-northeast3 \
  --memory 4Gi \
  --cpu 2
```

---

### 오류 8: "ERROR: (gcloud.artifacts.repositories.create) Already exists"

**증상:**
```bash
ERROR: (gcloud.artifacts.repositories.create) Already exists
```

**원인:** 저장소가 이미 존재함

**해결 방법:**
- 이 오류는 무시해도 됩니다 (스크립트가 자동 처리)
- 또는 기존 저장소 사용:
```bash
# 저장소 목록 확인
gcloud artifacts repositories list --location=asia-northeast3

# config.sh에서 기존 저장소명 사용
REPO="existing-repo-name"
```

---

### 오류 9: "ERROR: (gcloud.run.services.add-iam-policy-binding) Permission denied"

**증상:**
```bash
ERROR: (gcloud.run.services.add-iam-policy-binding) Permission denied
```

**원인:** IAM 권한 부족

**해결 방법:**
```bash
# 권한 확인
gcloud projects get-iam-policy YOUR_PROJECT_ID \
  --flatten="bindings[].members" \
  --filter="bindings.members:user:YOUR_EMAIL"

# 필요한 권한:
# - roles/run.admin 또는
# - roles/iam.serviceAccountUser
```

**권한 요청:** 프로젝트 소유자에게 권한을 요청하세요.

---

### 오류 10: "배포는 성공했지만 404 오류"

**증상:**
- 배포는 성공했지만 웹사이트 접속 시 404 오류

**원인:**
- 앱 라우팅 문제
- 환경변수 미설정
- 앱 시작 오류

**해결 방법:**

#### 1. 로그 확인
```bash
gcloud run services logs read smartnotam \
  --region asia-northeast3 \
  --limit 100
```

#### 2. 환경변수 확인
```bash
gcloud run services describe smartnotam \
  --region asia-northeast3 \
  --format="yaml(spec.template.spec.containers[0].env)"
```

#### 3. GEMINI_API_KEY 확인
```bash
# 환경변수 업데이트
gcloud run services update smartnotam \
  --region asia-northeast3 \
  --update-env-vars "GEMINI_API_KEY=YOUR_API_KEY"
```

#### 4. 앱 재시작
```bash
# 새 리비전 배포
gcloud run services update-traffic smartnotam \
  --region asia-northeast3 \
  --to-latest
```

---

## 🔧 고급 문제 해결

### Cloud Build 로그 확인

```bash
# 최근 빌드 목록
gcloud builds list --limit=10

# 특정 빌드 로그
gcloud builds log BUILD_ID

# 실시간 로그 스트리밍
gcloud builds log --stream
```

### Cloud Run 로그 확인

```bash
# 최근 로그
gcloud run services logs read smartnotam \
  --region asia-northeast3 \
  --limit 100

# 실시간 로그
gcloud run services logs tail smartnotam \
  --region asia-northeast3

# 특정 시간대 로그
gcloud run services logs read smartnotam \
  --region asia-northeast3 \
  --since 1h
```

### 리소스 사용량 확인

```bash
# 서비스 상태 확인
gcloud run services describe smartnotam \
  --region asia-northeast3

# 메트릭 확인 (Cloud Console에서)
# https://console.cloud.google.com/run
```

### 프로젝트 설정 확인

```bash
# 현재 프로젝트
gcloud config get-value project

# 모든 설정
gcloud config list

# 계정 확인
gcloud auth list
```

---

## 📞 추가 도움

### Google Cloud 문서
- [Cloud Run 문서](https://cloud.google.com/run/docs)
- [Cloud Build 문서](https://cloud.google.com/build/docs)
- [Artifact Registry 문서](https://cloud.google.com/artifact-registry/docs)

### 커뮤니티 지원
- [Stack Overflow](https://stackoverflow.com/questions/tagged/google-cloud-run)
- [Google Cloud Community](https://cloud.google.com/support)

### 문제 보고
이슈가 계속되면 다음 정보와 함께 보고하세요:
1. 오류 메시지 전체
2. `gcloud --version` 출력
3. `gcloud config list` 출력
4. 관련 로그

---

## ✅ 체크리스트

배포 전 확인사항:

- [ ] Google Cloud SDK 설치됨
- [ ] `gcloud auth login` 완료
- [ ] `config.sh` 파일 생성 및 설정
- [ ] `GEMINI_API_KEY` 입력됨
- [ ] `Dockerfile` 존재
- [ ] `requirements.txt` 존재
- [ ] 네트워크 연결 정상
- [ ] 프로젝트 권한 확인

배포 후 확인사항:

- [ ] 배포 URL 접근 가능
- [ ] 애플리케이션 정상 작동
- [ ] 환경변수 설정 확인
- [ ] 로그에 오류 없음

---

**문제가 해결되지 않으면 이슈를 등록해주세요!**
