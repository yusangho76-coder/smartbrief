# Smart NOTAM 배포 가이드 (초보자용)

이 가이드는 Google Cloud Run에 Smart NOTAM을 배포하는 방법을 단계별로 안내합니다.

## 📋 목차

1. [사전 준비](#사전-준비)
2. [빠른 시작 (5분 배포)](#빠른-시작-5분-배포)
3. [상세 배포 가이드](#상세-배포-가이드)
4. [문제 해결](#문제-해결)
5. [비용 정보](#비용-정보)

---

## 사전 준비

### 필요한 것들

1. **Google 계정** (Gmail 계정으로 충분)
2. **Gemini API 키** (Google AI Studio에서 발급)
3. **터미널 접근** (macOS, Linux, Windows)

### 1. Google Cloud SDK 설치

#### macOS
```bash
# Homebrew 사용
brew install google-cloud-sdk

# 또는 직접 설치
curl https://sdk.cloud.google.com | bash
exec -l $SHELL
```

#### Linux
```bash
# Ubuntu/Debian
echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | sudo tee -a /etc/apt/sources.list.d/google-cloud-sdk.list
curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo apt-key --keyring /usr/share/keyrings/cloud.google.gpg add -
sudo apt-get update && sudo apt-get install google-cloud-sdk
```

#### Windows
1. [Google Cloud SDK 설치 프로그램](https://cloud.google.com/sdk/docs/install) 다운로드
2. 설치 프로그램 실행
3. PowerShell 또는 Command Prompt에서 사용

### 2. Gemini API 키 발급

1. [Google AI Studio](https://makersuite.google.com/app/apikey) 접속
2. "Create API Key" 클릭
3. API 키 복사 (나중에 사용)

---

## 빠른 시작 (5분 배포)

### 방법 1: 대화형 모드 (가장 쉬움)

```bash
# 프로젝트 디렉토리로 이동
cd /path/to/SmartNOTAM3_GCR_James

# 대화형 배포 스크립트 실행
./deploy/deploy_simple.sh --interactive
```

스크립트가 다음을 자동으로 처리합니다:
- ✅ Google Cloud 로그인
- ✅ 프로젝트 생성 (없는 경우)
- ✅ 필요한 API 활성화
- ✅ Docker 이미지 빌드 및 배포
- ✅ 환경변수 설정

**필요한 입력:**
- Gemini API 키
- (선택) 프로젝트 ID (없으면 자동 생성)

### 방법 2: 설정 파일 사용

```bash
# 1. 설정 파일 복사
cp deploy/config.example.sh deploy/config.sh

# 2. 설정 파일 편집
nano deploy/config.sh  # 또는 원하는 에디터 사용

# 3. 필수 값 입력:
#    - GEMINI_API_KEY: Gemini API 키
#    - (선택) PROJECT_ID: 프로젝트 ID

# 4. 배포 실행
./deploy/deploy_simple.sh
```

---

## 상세 배포 가이드

### 1단계: 설정 파일 생성

```bash
cd /path/to/SmartNOTAM3_GCR_James
cp deploy/config.example.sh deploy/config.sh
```

### 2단계: 설정 파일 편집

`deploy/config.sh` 파일을 열고 다음 값들을 입력하세요:

```bash
# Google Cloud 프로젝트 ID (없으면 자동 생성)
PROJECT_ID="smartnotam-123456"  # 원하는 ID 또는 비워두기

# 리전 (서울 권장)
REGION="asia-northeast3"

# Artifact Registry 저장소명
REPO="smartnotam-repo"

# Cloud Run 서비스명
SERVICE="smartnotam"

# Gemini API 키 (필수!)
GEMINI_API_KEY="AIzaSy..."  # 여기에 실제 API 키 입력

# 접근 권한을 부여할 이메일 (선택사항)
GRANTEE_EMAIL="your-email@gmail.com"
```

**중요:**
- `GEMINI_API_KEY`는 반드시 입력해야 합니다
- `PROJECT_ID`는 비워두면 자동으로 생성됩니다
- `GRANTEE_EMAIL`은 비워두면 현재 로그인한 계정이 사용됩니다

### 3단계: Google Cloud 로그인

```bash
gcloud auth login
```

브라우저가 열리면 Google 계정으로 로그인하세요.

### 4단계: 배포 실행

```bash
./deploy/deploy_simple.sh
```

스크립트가 자동으로 다음을 수행합니다:

1. ✅ 필수 도구 확인 (gcloud CLI)
2. ✅ Google Cloud 로그인 확인
3. ✅ 프로젝트 생성 (없는 경우)
4. ✅ 필수 API 활성화
5. ✅ Artifact Registry 저장소 생성
6. ✅ Docker 이미지 빌드 및 푸시
7. ✅ Cloud Run 배포
8. ✅ 환경변수 설정
9. ✅ 접근 권한 설정

### 5단계: 배포 확인

배포가 완료되면 다음과 같은 URL이 표시됩니다:

```
✅ 배포 완료!
배포 URL: https://smartnotam-xxxxx-xx.a.run.app
```

이 URL을 브라우저에서 열어 애플리케이션이 정상 작동하는지 확인하세요.

---

## 문제 해결

### 문제 1: "gcloud: command not found"

**원인:** Google Cloud SDK가 설치되지 않음

**해결:**
```bash
# macOS
brew install google-cloud-sdk

# Linux
# 위의 "사전 준비" 섹션 참고

# Windows
# 설치 프로그램 다운로드 및 실행
```

### 문제 2: "Permission denied"

**원인:** 스크립트에 실행 권한이 없음

**해결:**
```bash
chmod +x deploy/deploy_simple.sh
```

### 문제 3: "프로젝트 생성 실패"

**원인:** 프로젝트 ID가 이미 사용 중이거나 권한 부족

**해결:**
- 다른 프로젝트 ID 사용
- 또는 `PROJECT_ID`를 비워두어 자동 생성 사용

### 문제 4: "API 활성화 실패"

**원인:** 빌링 계정이 연결되지 않음 (일부 API는 빌링 필요)

**해결:**
- 무료 티어 사용 시: 빌링 계정 연결 불필요 (Cloud Run은 무료 티어 제공)
- 프로젝트 생성 시 빌링 계정 연결 옵션이 나타나면 "건너뛰기" 선택 가능

### 문제 5: "이미지 빌드 실패"

**원인:** Dockerfile 오류 또는 네트워크 문제

**해결:**
- Dockerfile이 프로젝트 루트에 있는지 확인
- `requirements.txt`가 있는지 확인
- 네트워크 연결 확인

### 문제 6: "배포 후 404 오류"

**원인:** 환경변수 미설정 또는 앱 오류

**해결:**
```bash
# 환경변수 확인
gcloud run services describe smartnotam \
  --region asia-northeast3 \
  --format="value(spec.template.spec.containers[0].env)"

# 로그 확인
gcloud run services logs read smartnotam \
  --region asia-northeast3
```

---

## 비용 정보

### Cloud Run 무료 티어

- **월 200만 요청 무료**
- **월 360,000 vCPU-초 무료** (1 vCPU × 100시간)
- **월 400,000 GiB-초 무료** (1 GiB × 111시간)

### 실제 사용 예시

| 사용 패턴 | 월간 비용 |
|----------|----------|
| **가끔 사용** (월 10회, 30분) | **$0** (완전 무료) ✅ |
| **자주 사용** (월 100회, 5시간) | **$0** (무료 티어 내) ✅ |
| **매우 자주 사용** (월 1,000회, 50시간) | **$0** (무료 티어 내) ✅ |
| **24시간 운영** (항상 켜져 있음) | 약 $40-50/월 |

**결론:** 일반적인 사용 패턴에서는 **완전 무료**입니다!

### 추가 비용

- **Gemini API**: 별도 과금 (플랫폼과 무관)
- **네트워크 전송**: 첫 10GB 무료, 이후 $0.12/GB

---

## 재배포 (업데이트)

코드를 수정한 후 다시 배포하려면:

```bash
./deploy/deploy_simple.sh
```

스크립트가 자동으로:
- 새로운 이미지 빌드
- Cloud Run에 배포
- 기존 설정 유지

---

## 고급 설정

### 환경변수 추가

```bash
gcloud run services update smartnotam \
  --region asia-northeast3 \
  --update-env-vars "NEW_VAR=value" \
  --project YOUR_PROJECT_ID
```

### 리소스 조정

```bash
gcloud run services update smartnotam \
  --region asia-northeast3 \
  --cpu 2 \
  --memory 4Gi \
  --project YOUR_PROJECT_ID
```

### 로그 확인

```bash
# 실시간 로그
gcloud run services logs tail smartnotam \
  --region asia-northeast3 \
  --project YOUR_PROJECT_ID

# 최근 로그
gcloud run services logs read smartnotam \
  --region asia-northeast3 \
  --limit 50 \
  --project YOUR_PROJECT_ID
```

---

## 다음 단계

1. ✅ 배포 완료 후 URL 확인
2. ✅ 애플리케이션 테스트
3. ✅ (선택) 커스텀 도메인 연결
4. ✅ (선택) GitHub Actions로 자동 배포 설정

---

## 도움말

문제가 발생하면:
1. 이 가이드의 [문제 해결](#문제-해결) 섹션 확인
2. Google Cloud 콘솔에서 로그 확인
3. 이슈 등록

**행운을 빕니다! 🚀**
