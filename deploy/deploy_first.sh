#!/bin/bash

# ===== SmartBrief - 처음 배포용 원클릭 배포 스크립트 (macOS/Linux) =====
# gcloud auth login + gcloud config set project <프로젝트ID> 만 하면 누구나 자기 프로젝트에 배포 가능.
# PROJECT_ID: 환경변수 GCP_PROJECT_ID > gcloud 현재 프로젝트 > 기본값 smartbrief-490309
# GRANTEE: 환경변수 GRANTEE_EMAIL > gcloud 현재 로그인 계정
# 요구: gcloud SDK 설치, 브라우저 로그인 가능 환경

set -e  # 오류 발생 시 스크립트 중단

# 스크립트가 있는 디렉토리 (deploy 폴더)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# 프로젝트 루트 디렉토리 (deploy 폴더의 상위 디렉토리)
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# 프로젝트 루트로 이동
cd "$PROJECT_ROOT"

# --- 프로젝트/계정: 환경변수 > gcloud 현재값 > 기본값 ---
if [ -n "$GCP_PROJECT_ID" ]; then
  PROJECT_ID="$GCP_PROJECT_ID"
else
  _cfg_project=$(gcloud config get-value project 2>/dev/null | tr -d '\r\n' || true)
  if [ -n "$_cfg_project" ]; then
    PROJECT_ID="$_cfg_project"
  else
    PROJECT_ID="smartbrief-490309"
  fi
fi

if [ -n "$GRANTEE_EMAIL" ]; then
  GRANTEE="user:$GRANTEE_EMAIL"
else
  _cfg_account=$(gcloud config get-value account 2>/dev/null | tr -d '\r\n' || true)
  if [ -n "$_cfg_account" ]; then
    GRANTEE="user:$_cfg_account"
  else
    GRANTEE=""
  fi
fi

# 고정 설정값
REGION="asia-northeast3"               # 서울 권장
REPO="smartnotam"                       # Artifact Registry 저장소명
SERVICE="smartnotam3"                  # Cloud Run 서비스명
API_KEY="AIzaSyAgCVzUmUlYBPUqvsslAxFOHMuUhLeM9a4"

# 색상 정의
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${CYAN}=== 배포 설정 확인 (deploy_first.sh) ===${NC}"
echo -e "프로젝트 ID: ${GREEN}$PROJECT_ID${NC}"
echo -e "실행 사용자(GRANTEE): ${GREEN}$GRANTEE${NC}"
echo -e "리전: ${GREEN}$REGION${NC}"
echo -e "저장소: ${GREEN}$REPO${NC}"
echo -e "서비스: ${GREEN}$SERVICE${NC}"
echo -e "프로젝트 루트: ${GREEN}$PROJECT_ROOT${NC}"
echo ""

# GRANTEE가 비어 있으면 로그인 필요
if [ -z "$GRANTEE" ]; then
  echo -e "${YELLOW}⚠️  로그인된 계정이 없습니다. 로그인합니다.${NC}"
  gcloud auth login
  _cfg_account=$(gcloud config get-value account 2>/dev/null | tr -d '\r\n' || true)
  [ -n "$_cfg_account" ] || { echo -e "${RED}❌ 로그인 후 계정을 확인할 수 없습니다.${NC}"; exit 1; }
  GRANTEE="user:$_cfg_account"
  echo -e "  사용자(GRANTEE): ${GREEN}$GRANTEE${NC}"
fi

# ===== gcloud 로그인/프로젝트 확인 (간단 버전: revoke 없음, 현재 계정 유지) =====
echo -e "${CYAN}=== gcloud 설정 확인 ===${NC}\n"

CURRENT_PROJECT=$(gcloud config get-value project 2>/dev/null | tr -d '\r\n' || echo "")
CURRENT_ACCOUNT=$(gcloud config get-value account 2>/dev/null | tr -d '\r\n' || echo "")

echo -e "${CYAN}[1/3] 현재 gcloud 설정${NC}"
echo -e "  프로젝트: ${YELLOW}$CURRENT_PROJECT${NC}"
echo -e "  계정: ${YELLOW}$CURRENT_ACCOUNT${NC}"
echo ""

# 자격 증명 유효한지 확인
if ! gcloud projects list --limit=1 >/dev/null 2>&1; then
  echo -e "${YELLOW}⚠️  자격 증명이 유효하지 않습니다. 로그인합니다.${NC}"
  gcloud auth login
  if ! gcloud projects list --limit=1 >/dev/null 2>&1; then
    echo -e "${RED}❌ 자격 증명 확인 실패. gcloud auth login 후 다시 실행하세요.${NC}"
    exit 1
  fi
  echo -e "${GREEN}✅ 로그인 완료${NC}"
  CURRENT_ACCOUNT=$(gcloud config get-value account 2>/dev/null | tr -d '\r\n' || echo "")
  GRANTEE="user:$CURRENT_ACCOUNT"
fi

# 프로젝트가 다르면 설정
if [ "$CURRENT_PROJECT" != "$PROJECT_ID" ]; then
  echo -e "${CYAN}[2/3] 프로젝트 설정: $CURRENT_PROJECT → $PROJECT_ID${NC}"
  gcloud config set project "$PROJECT_ID"
  echo -e "${GREEN}✅ 프로젝트 설정 완료${NC}"
else
  echo -e "${CYAN}[2/3] 프로젝트 일치${NC}"
fi

echo -e "${CYAN}[3/3] 최종 확인${NC}"
echo -e "  gcloud 프로젝트: ${GREEN}$(gcloud config get-value project 2>/dev/null)${NC}"
echo -e "  gcloud 계정: ${GREEN}$(gcloud config get-value account 2>/dev/null)${NC}"
echo -e "${GREEN}✅ gcloud 설정 완료${NC}\n"

# 프로젝트 설정 함수
force_set_project() {
    local target_project=$1
    gcloud config set project $target_project 2>&1
    gcloud config configurations activate default 2>/dev/null || true
    export CLOUDSDK_CORE_PROJECT=$target_project
}

# 모든 명령어에 사용할 공통 플래그
GCLOUD_PROJECT_FLAG="--project=$PROJECT_ID"

# 프로젝트 설정 확인 함수
verify_project() {
    CURRENT=$(gcloud config get-value project 2>/dev/null | tr -d '\r\n')
    if [ "$CURRENT" != "$PROJECT_ID" ]; then
        force_set_project $PROJECT_ID
    fi
    export CLOUDSDK_CORE_PROJECT=$PROJECT_ID
}

echo -e "${GREEN}✅ 프로젝트 설정 확인: $PROJECT_ID${NC}"

echo -e "\n${CYAN}[0/9] Streamlit 앱 (ATS FPL Validator) 배포 확인${NC}"
# Streamlit 앱 배포 스크립트 확인 및 실행
STREAMLIT_DEPLOY_SCRIPT="$PROJECT_ROOT/ATSplanvalidation/deploy_streamlit.sh"
if [ -f "$STREAMLIT_DEPLOY_SCRIPT" ]; then
    echo -e "${CYAN}Streamlit 앱 배포 시작...${NC}"
    cd "$PROJECT_ROOT/ATSplanvalidation"
    chmod +x deploy_streamlit.sh
    ./deploy_streamlit.sh
    cd "$PROJECT_ROOT"
    echo -e "${GREEN}✅ Streamlit 앱 배포 완료${NC}\n"
else
    echo -e "${YELLOW}⚠️  Streamlit 배포 스크립트를 찾을 수 없습니다: $STREAMLIT_DEPLOY_SCRIPT${NC}"
    echo -e "${YELLOW}   Streamlit 앱이 이미 배포되어 있거나 수동으로 배포해야 합니다.${NC}\n"
fi

echo -e "\n${CYAN}[1/9] gcloud 로그인/프로젝트 설정${NC}"
CURRENT_ACCOUNT_FINAL=$(gcloud config get-value account 2>/dev/null || echo "")
if [ -z "$CURRENT_ACCOUNT_FINAL" ]; then
    echo -e "${RED}❌ 계정이 설정되지 않았습니다. 로그인을 진행합니다...${NC}"
    gcloud auth login
fi

if ! gcloud projects list --limit=1 >/dev/null 2>&1; then
    echo -e "${RED}❌ 자격 증명이 유효하지 않습니다. 로그인을 진행합니다...${NC}"
    gcloud auth login
    if ! gcloud projects list --limit=1 >/dev/null 2>&1; then
        echo -e "${RED}❌ 자격 증명 확인 실패. gcloud auth login 후 다시 실행하세요.${NC}"
        exit 1
    fi
fi

# 프로젝트 설정 확인
CURRENT_PROJECT_FINAL=$(gcloud config get-value project 2>/dev/null | tr -d '\r\n')
if [ "$CURRENT_PROJECT_FINAL" != "$PROJECT_ID" ]; then
    force_set_project $PROJECT_ID
fi

echo -e "${GREEN}✅ 프로젝트 설정 확인: $PROJECT_ID${NC}"
echo -e "${GREEN}✅ 계정 설정 확인: $(gcloud config get-value account 2>/dev/null || echo '설정 없음')${NC}"
echo -e "${GREEN}✅ 자격 증명 확인 완료${NC}"

echo -e "\n${CYAN}[2/9] 필수 API 활성화${NC}"
verify_project
force_set_project $PROJECT_ID
export CLOUDSDK_CORE_PROJECT=$PROJECT_ID
FINAL_CHECK=$(gcloud config get-value project 2>/dev/null | tr -d '\r\n')
if [ "$FINAL_CHECK" != "$PROJECT_ID" ]; then
    echo -e "${RED}❌ 프로젝트 설정 실패! 현재: $FINAL_CHECK, 목표: $PROJECT_ID${NC}"
    echo -e "${YELLOW}수동으로 설정하세요: gcloud config set project $PROJECT_ID${NC}"
    exit 1
fi
echo -e "${GREEN}✅ 프로젝트 최종 확인: $PROJECT_ID${NC}"
gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com \
  generativelanguage.googleapis.com \
  maps-backend.googleapis.com geocoding-backend.googleapis.com apikeys.googleapis.com \
  places.googleapis.com places-backend.googleapis.com \
  $GCLOUD_PROJECT_FLAG
echo -e "${GREEN}✅ API 활성화 완료 (Run, Artifact Registry, Cloud Build, Gemini, Maps, Geocoding, API Keys, Places)${NC}"

echo -e "\n${CYAN}[3/9] Artifact Registry 리포지토리 생성(존재 시 무시)${NC}"
verify_project
if gcloud artifacts repositories create $REPO \
    --repository-format=docker \
    --location=$REGION \
    --description="SmartBrief images" \
    $GCLOUD_PROJECT_FLAG 2>/dev/null; then
    echo "✅ 저장소 생성 완료"
else
    echo -e "${YELLOW} - 이미 존재하거나 생성 스킵${NC}"
fi

gcloud artifacts repositories describe $REPO --location=$REGION $GCLOUD_PROJECT_FLAG > /dev/null

# Cloud Build 서비스 계정에 역할 부여 (처음 배포 시 PERMISSION_DENIED 방지)
echo -e "\n${CYAN}[3.5/9] Cloud Build 서비스 계정 역할 부여${NC}"
verify_project
PROJECT_NUM=$(gcloud projects describe $PROJECT_ID --format="value(projectNumber)" $GCLOUD_PROJECT_FLAG 2>/dev/null || true)
if [ -n "$PROJECT_NUM" ]; then
  CB_SA="${PROJECT_NUM}@cloudbuild.gserviceaccount.com"
  COMPUTE_SA="${PROJECT_NUM}-compute@developer.gserviceaccount.com"
  for ROLE in roles/run.admin roles/iam.serviceAccountUser roles/storage.admin; do
    gcloud projects add-iam-policy-binding $PROJECT_ID --member="serviceAccount:${CB_SA}" --role="$ROLE" $GCLOUD_PROJECT_FLAG --quiet 2>/dev/null || true
  done
  for ROLE in roles/storage.admin roles/artifactregistry.writer roles/logging.logWriter; do
    gcloud projects add-iam-policy-binding $PROJECT_ID --member="serviceAccount:${COMPUTE_SA}" --role="$ROLE" $GCLOUD_PROJECT_FLAG --quiet 2>/dev/null || true
  done
  echo -e "${GREEN}✅ Cloud Build 서비스 계정 역할 부여 완료${NC}"
else
  echo -e "${YELLOW}⚠️  프로젝트 번호 조회 실패. 빌드 단계에서 권한 오류가 나면 IAM에서 Cloud Build 서비스 계정에 역할을 수동 부여하세요.${NC}"
fi

# 스크립트 실행 사용자(GRANTEE)에게 Cloud Build·Storage 권한 부여
echo -e "\n${CYAN}[3.6/9] 실행 사용자(GRANTEE) Cloud Build·Storage 권한 부여${NC}"
verify_project
for ROLE in roles/cloudbuild.builds.editor roles/storage.objectAdmin; do
  gcloud projects add-iam-policy-binding $PROJECT_ID --member="$GRANTEE" --role="$ROLE" $GCLOUD_PROJECT_FLAG --quiet 2>/dev/null || true
done
echo -e "${GREEN}✅ GRANTEE 권한 부여 시도 완료 (이미 있으면 무시)${NC}"

echo -e "\n${CYAN}[4/9] 이미지 빌드 & 푸시 (Cloud Build)${NC}"
verify_project
cd "$PROJECT_ROOT"

CLOUDBUILD_BACKUP=""
if [ -f "cloudbuild.yaml" ]; then
    CLOUDBUILD_BACKUP="cloudbuild.yaml.backup.$$"
    mv cloudbuild.yaml "$CLOUDBUILD_BACKUP"
fi

TIMESTAMP=$(date +"%Y%m%d-%H%M%S")
IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/$SERVICE:$TIMESTAMP"

if gcloud builds submit --help 2>&1 | grep -q "no-source-config"; then
    gcloud builds submit --tag $IMAGE $GCLOUD_PROJECT_FLAG --no-source-config
else
    gcloud builds submit --tag $IMAGE $GCLOUD_PROJECT_FLAG
fi

if [ -n "$CLOUDBUILD_BACKUP" ] && [ -f "$CLOUDBUILD_BACKUP" ]; then
    mv "$CLOUDBUILD_BACKUP" cloudbuild.yaml
fi

echo -e "\n${CYAN}[5/9] latest 태그 부여${NC}"
verify_project
gcloud container images add-tag $IMAGE "$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/$SERVICE:latest" --quiet --project=$PROJECT_ID

echo -e "\n${CYAN}[6/9] Cloud Run 배포${NC}"
verify_project
gcloud run deploy $SERVICE \
  --image "$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/$SERVICE:latest" \
  --region $REGION \
  --platform managed \
  --allow-unauthenticated \
  --cpu 1 --memory 2Gi \
  --max-instances 3 \
  --timeout 900 \
  $GCLOUD_PROJECT_FLAG

echo -e "${CYAN}최신 리비전에 트래픽 100% 할당 중...${NC}"
LATEST_REVISION=$(gcloud run revisions list --service=$SERVICE --region=$REGION --format="value(name)" --limit=1 --sort-by=~metadata.creationTimestamp $GCLOUD_PROJECT_FLAG)
if [ -n "$LATEST_REVISION" ]; then
    echo -e "${YELLOW}최신 리비전: $LATEST_REVISION${NC}"
    gcloud run services update-traffic $SERVICE \
      --region $REGION \
      --to-latest \
      $GCLOUD_PROJECT_FLAG
    echo -e "${GREEN}✅ 최신 리비전에 트래픽 100% 할당 완료${NC}"
else
    echo -e "${YELLOW}⚠️  리비전을 찾을 수 없습니다. (이미 100% 할당되었을 수 있음)${NC}"
fi

echo -e "\n${CYAN}[7/9] 환경변수 설정${NC}"
verify_project

STREAMLIT_SERVICE="ats-fpl-validator"
STREAMLIT_URL=""
if gcloud run services describe $STREAMLIT_SERVICE --region=$REGION --format="value(status.url)" $GCLOUD_PROJECT_FLAG > /dev/null 2>&1; then
    STREAMLIT_URL=$(gcloud run services describe $STREAMLIT_SERVICE --region=$REGION --format="value(status.url)" $GCLOUD_PROJECT_FLAG)
    echo -e "${GREEN}Streamlit 앱 URL 발견: $STREAMLIT_URL${NC}"
else
    echo -e "${YELLOW}⚠️  Streamlit 앱($STREAMLIT_SERVICE)이 배포되지 않았습니다.${NC}"
    echo -e "${YELLOW}   ATSplanvalidation/deploy_streamlit.sh를 먼저 실행하세요.${NC}"
fi

ENV_VARS="GEMINI_API_KEY=$API_KEY,GOOGLE_MAPS_API_KEY=$API_KEY,GOOGLE_API_KEY=$API_KEY"
if [ -n "$STREAMLIT_URL" ]; then
    ENV_VARS="$ENV_VARS,STREAMLIT_URL=$STREAMLIT_URL"
fi

gcloud run services update $SERVICE \
  --region $REGION \
  --update-env-vars "$ENV_VARS" \
  $GCLOUD_PROJECT_FLAG

echo -e "\n${CYAN}[8/9] 실행 권한 부여(roles/run.invoker)${NC}"
verify_project
gcloud run services add-iam-policy-binding $SERVICE \
  --region $REGION \
  --member="$GRANTEE" \
  --role="roles/run.invoker" \
  $GCLOUD_PROJECT_FLAG

echo -e "${YELLOW}공개 접근 권한 부여 (allUsers)...${NC}"
gcloud run services add-iam-policy-binding $SERVICE \
  --region $REGION \
  --member="allUsers" \
  --role="roles/run.invoker" \
  $GCLOUD_PROJECT_FLAG 2>/dev/null || echo -e "${YELLOW}⚠️  allUsers 권한 부여 실패 - 조직 정책 제한일 수 있습니다.${NC}"

URL=$(gcloud run services describe $SERVICE --region=$REGION --format="value(status.url)" $GCLOUD_PROJECT_FLAG)

echo -e "\n${CYAN}[9/9] 배포 완료 확인${NC}"
echo -e "${GREEN}Flask 앱 배포 완료: $URL${NC}"

STREAMLIT_SERVICE="ats-fpl-validator"
STREAMLIT_URL_FINAL=""
if gcloud run services describe $STREAMLIT_SERVICE --region=$REGION --format="value(status.url)" $GCLOUD_PROJECT_FLAG > /dev/null 2>&1; then
    STREAMLIT_URL_FINAL=$(gcloud run services describe $STREAMLIT_SERVICE --region=$REGION --format="value(status.url)" $GCLOUD_PROJECT_FLAG)
    echo -e "${GREEN}Streamlit 앱 URL: $STREAMLIT_URL_FINAL${NC}"
else
    echo -e "${YELLOW}⚠️  Streamlit 앱 URL을 확인할 수 없습니다.${NC}"
fi

# ADC 정리
ADC_FILE="$HOME/.config/gcloud/application_default_credentials.json"
if [ -f "$ADC_FILE" ]; then
    echo -e "\n${CYAN}ADC 정리 중...${NC}"
    BACKUP_FILE="${ADC_FILE}.backup.$(date +%Y%m%d_%H%M%S)"
    mv "$ADC_FILE" "$BACKUP_FILE" 2>/dev/null || rm -f "$ADC_FILE" 2>/dev/null || true
    gcloud auth application-default revoke --quiet 2>/dev/null || true
    echo -e "${GREEN}✅ ADC 정리 완료${NC}"
fi

if [ -f "$PROJECT_ROOT/cloudbuild.yaml" ] && [ -d "$PROJECT_ROOT/.git" ]; then
  cd "$PROJECT_ROOT"
  if git status --short cloudbuild.yaml | grep -q .; then
    echo -e "\n${CYAN}cloudbuild.yaml을 GitHub에 올리는 중...${NC}"
    git add cloudbuild.yaml
    git commit -m "Update cloudbuild.yaml for Cloud Build trigger" 2>/dev/null && git push origin main 2>/dev/null && echo -e "${GREEN}✅ cloudbuild.yaml 푸시 완료${NC}" || echo -e "${YELLOW}⚠️  cloudbuild.yaml 푸시 실패 또는 변경 없음. 수동으로 git push 하세요.${NC}"
  fi
  cd - >/dev/null
fi

echo -e "\n${GREEN}✅ 모든 작업 완료!${NC}"
