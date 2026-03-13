# GitHub Actions 자동 배포 설정 가이드

이 폴더에는 GitHub Actions를 사용한 자동 배포 워크플로우가 포함되어 있습니다.

## 설정 방법

### 1. Google Cloud 서비스 계정 생성

```bash
# 서비스 계정 생성
gcloud iam service-accounts create github-actions \
  --display-name="GitHub Actions Deployer" \
  --project=YOUR_PROJECT_ID

# 권한 부여
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:github-actions@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/run.admin"

gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:github-actions@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/artifactregistry.writer"

gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:github-actions@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountUser"

# 키 생성
gcloud iam service-accounts keys create key.json \
  --iam-account=github-actions@YOUR_PROJECT_ID.iam.gserviceaccount.com
```

### 2. GitHub Secrets 설정

GitHub 저장소의 Settings → Secrets and variables → Actions에서 다음 secrets를 추가하세요:

1. **GCP_PROJECT_ID**: Google Cloud 프로젝트 ID
2. **GCP_SA_KEY**: 서비스 계정 키 JSON 파일 내용 (위에서 생성한 key.json)
3. **GEMINI_API_KEY**: Gemini API 키

### 3. 자동 배포 활성화

이제 `main` 또는 `master` 브랜치에 push하면 자동으로 배포됩니다!

## 수동 배포

GitHub Actions 탭에서 "Deploy to Google Cloud Run" 워크플로우를 선택하고 "Run workflow"를 클릭하면 수동으로도 배포할 수 있습니다.
