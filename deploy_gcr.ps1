# ===== SmartBrief - GCR/Cloud Run 원클릭 배포 스크립트 (PowerShell) =====
# 요구: gcloud SDK 설치, 브라우저 로그인 가능 환경
$ErrorActionPreference = "Stop"

# --- 설정값 ---
$PROJECT_ID = "smartnotam-476803"
$REGION     = "asia-northeast3"               # 서울 권장
$REPO       = "smartnotam"                    # Artifact Registry 저장소명
$SERVICE    = "smartnotam"                    # Cloud Run 서비스명
$API_KEY    = "AIzaSyA7rf9lPi2h_0ff7hg2OpheObhhbRXRkxI"
$GRANTEE    = "user:yangs9508@gmail.com"

Write-Host "`n[1/8] gcloud 로그인/프로젝트 설정" -ForegroundColor Cyan
gcloud auth login
gcloud config set project $PROJECT_ID
gcloud auth application-default login

Write-Host "`n[2/8] 필수 API 활성화" -ForegroundColor Cyan
gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com

Write-Host "`n[3/8] Artifact Registry 리포지토리 생성(존재 시 무시)" -ForegroundColor Cyan
try {
  gcloud artifacts repositories create $REPO `
    --repository-format=docker `
    --location=$REGION `
    --description="SmartBrief images" | Out-Null
} catch {
  Write-Host " - 이미 존재하거나 생성 스킵" -ForegroundColor Yellow
}
gcloud artifacts repositories describe $REPO --location=$REGION | Out-Null

Write-Host "`n[4/8] 이미지 빌드 & 푸시 (Cloud Build)" -ForegroundColor Cyan
$TIMESTAMP = (Get-Date -Format "yyyyMMdd-HHmmss")
$IMAGE     = "$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/$($SERVICE):$TIMESTAMP"
gcloud builds submit --tag $IMAGE

Write-Host "`n[5/8] latest 태그 부여" -ForegroundColor Cyan
gcloud container images add-tag $IMAGE "$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/$($SERVICE):latest" --quiet

Write-Host "`n[6/8] Cloud Run 배포" -ForegroundColor Cyan
gcloud run deploy $SERVICE `
  --image "$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/$($SERVICE):latest" `
  --region $REGION `
  --platform managed `
  --allow-unauthenticated `
  --cpu 1 --memory 1Gi `
  --max-instances 3 `
  --timeout 900

Write-Host "`n[7/8] 환경변수(GEMINI_API_KEY) 설정" -ForegroundColor Cyan
gcloud run services update $SERVICE `
  --region $REGION `
  --update-env-vars "GEMINI_API_KEY=$API_KEY"

Write-Host "`n[8/8] 실행 권한 부여(roles/run.invoker)" -ForegroundColor Cyan
gcloud run services add-iam-policy-binding $SERVICE `
  --region $REGION `
  --member="$GRANTEE" `
  --role="roles/run.invoker"

$URL = gcloud run services describe $SERVICE --region $REGION --format="value(status.url)"
Write-Host "`n배포 완료: $URL" -ForegroundColor Green

