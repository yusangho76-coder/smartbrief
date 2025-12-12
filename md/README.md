# Smart NOTAM3

NOTAM (Notice to Airmen) 파일을 처리하고 번역하는 웹 애플리케이션입니다.

## 🚀 빠른 시작

### 로컬 실행 (Docker)

```bash
# 컨테이너 시작
docker-compose up -d

# 로그 확인
docker-compose logs -f

# 컨테이너 중지
docker-compose down
```

### Google Cloud Run 배포 (권장)

**초보자도 5분 안에 배포 가능!**

#### 방법 1: 대화형 모드 (가장 쉬움)

```bash
./deploy/deploy_simple.sh --interactive
```

스크립트가 자동으로 모든 설정을 처리합니다. Gemini API 키만 입력하면 됩니다!

#### 방법 2: 설정 파일 사용

```bash
# 1. 설정 파일 생성
cp deploy/config.example.sh deploy/config.sh

# 2. 설정 파일 편집 (Gemini API 키 입력)
nano deploy/config.sh

# 3. 배포 실행
./deploy/deploy_simple.sh
```

**자세한 배포 가이드:** [DEPLOYMENT_GUIDE_KR.md](./DEPLOYMENT_GUIDE_KR.md)

---

## 📋 목차

- [기능](#기능)
- [요구사항](#요구사항)
- [로컬 개발](#로컬-개발)
- [배포](#배포)
- [비용](#비용)
- [문제 해결](#문제-해결)

---

## 기능

- ✅ PDF NOTAM 파일 업로드 및 처리
- ✅ AI 기반 자동 번역 (Gemini API)
- ✅ 시간대 자동 변환
- ✅ 공항별 필터링
- ✅ 경로 분석
- ✅ 웹 기반 사용자 인터페이스

---

## 요구사항

### 로컬 실행
- Python 3.11+
- Docker (선택사항)
- Gemini API 키

### Cloud Run 배포
- Google Cloud 계정
- Google Cloud SDK (gcloud CLI)
- Gemini API 키

---

## 로컬 개발

### 1. 저장소 클론

```bash
git clone <repository-url>
cd SmartNOTAM3_GCR_James
```

### 2. 가상환경 생성 및 활성화

```bash
# macOS/Linux
python3 -m venv venv
source venv/bin/activate

# Windows
python -m venv venv
venv\Scripts\activate
```

### 3. 의존성 설치

```bash
pip install -r requirements.txt
```

### 4. 환경변수 설정

`.env` 파일 생성:

```bash
GEMINI_API_KEY=your_api_key_here
FLASK_ENV=development
```

### 5. 애플리케이션 실행

```bash
python app.py
```

브라우저에서 `http://localhost:8080` 접속

---

## 배포

### Google Cloud Run 배포 (권장)

**왜 Cloud Run인가?**
- ✅ **완전 무료** (일반적인 사용 패턴 기준)
- ✅ Serverless (사용하지 않을 때 비용 없음)
- ✅ 자동 스케일링
- ✅ 간단한 배포

#### 빠른 배포 (5분)

```bash
# 대화형 모드
./deploy/deploy_simple.sh --interactive
```

#### 상세 배포 가이드

자세한 배포 방법은 [DEPLOYMENT_GUIDE_KR.md](./DEPLOYMENT_GUIDE_KR.md)를 참고하세요.

**주요 단계:**
1. Google Cloud SDK 설치
2. Gemini API 키 발급
3. 설정 파일 생성
4. 배포 스크립트 실행

### GitHub Actions 자동 배포

코드를 push하면 자동으로 배포됩니다!

**설정 방법:** [.github/workflows/README.md](./.github/workflows/README.md)

---

## 비용

### Cloud Run 무료 티어

- **월 200만 요청 무료**
- **월 360,000 vCPU-초 무료** (1 vCPU × 100시간)
- **월 400,000 GiB-초 무료** (1 GiB × 111시간)

### 실제 사용 예시

| 사용 패턴 | 월간 비용 |
|----------|----------|
| 가끔 사용 (월 10회, 30분) | **$0** (완전 무료) ✅ |
| 자주 사용 (월 100회, 5시간) | **$0** (무료 티어 내) ✅ |
| 매우 자주 사용 (월 1,000회, 50시간) | **$0** (무료 티어 내) ✅ |
| 24시간 운영 | 약 $40-50/월 |

**결론:** 일반적인 사용 패턴에서는 **완전 무료**입니다!

**자세한 비용 비교:** [COST_COMPARISON.md](./COST_COMPARISON.md)

---

## 문제 해결

### 배포 문제

배포 중 문제가 발생하면 [TROUBLESHOOTING.md](./TROUBLESHOOTING.md)를 참고하세요.

### 일반적인 문제

#### "gcloud: command not found"
```bash
# macOS
brew install google-cloud-sdk

# Linux
curl https://sdk.cloud.google.com | bash
```

#### "Permission denied"
```bash
chmod +x deploy/deploy_simple.sh
```

#### 배포 후 404 오류
```bash
# 로그 확인
gcloud run services logs read smartnotam \
  --region asia-northeast3 \
  --limit 50
```

**더 많은 해결 방법:** [TROUBLESHOOTING.md](./TROUBLESHOOTING.md)

---

## 프로젝트 구조

```
SmartNOTAM3_GCR_James/
├── app.py                 # 메인 애플리케이션
├── Dockerfile             # Docker 이미지 정의
├── requirements.txt       # Python 의존성
├── deploy/                # 배포 스크립트
│   ├── deploy_simple.sh   # 간편 배포 스크립트 ⭐
│   ├── config.example.sh  # 설정 파일 예시
│   └── ...
├── src/                   # 소스 코드
├── templates/             # HTML 템플릿
├── static/                # 정적 파일
└── .github/workflows/     # GitHub Actions
```

---

## 문서

- [배포 가이드](./DEPLOYMENT_GUIDE_KR.md) - 상세한 배포 방법
- [문제 해결](./TROUBLESHOOTING.md) - 일반적인 문제 해결
- [비용 비교](./COST_COMPARISON.md) - 플랫폼별 비용 비교
- [Railway 가격 계산](./RAILWAY_PRICING_CALCULATION.md) - Railway 비용 분석

---

## 라이선스

[라이선스 정보]

---

## 기여

이슈나 Pull Request를 환영합니다!

---

## 문의

문제가 있거나 질문이 있으면 이슈를 등록해주세요.

---

**Happy Deploying! 🚀**
