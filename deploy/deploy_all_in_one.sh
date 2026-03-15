#!/bin/bash

# ===== SmartBrief - All-in-One 배포 스크립트 (macOS/Linux) =====
# 사용자가 아래 설정값만 채우면, 이 값대로만 배포가 진행됩니다.
# 요구: gcloud SDK 설치, gcloud auth login 후 실행
# 실행: deploy 폴더에서 실행하며, 프로젝트 루트를 자동으로 찾습니다.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# --- 설정값 --- (사용자가 미리 채운 값만 사용합니다)
PROJECT_ID="project-13c9df8c-21c3-40ef-8d3"
REGION="asia-northeast3"               # 서울 권장
REPO="smartnotam"                       # Artifact Registry 저장소명
SERVICE="smartnotam3"                    # Cloud Run 서비스명
API_KEY="AIzaSyBZDC5DNk_ywkN2SMdRgWnc_eNjOfGogfk"
GOOGLE_MAPS_API_KEY=""                 # 비워 두면 이 프로젝트에서 자동 생성
GRANTEE="user:stellakim6741@gmail.com"

# 색상
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# 설정값 필수 확인 (PROJECT_ID, GRANTEE는 반드시 입력)
if [ -z "$PROJECT_ID" ]; then
    echo -e "${RED}❌ PROJECT_ID가 비어 있습니다. 위 설정값을 채운 뒤 다시 실행하세요.${NC}"
    exit 1
fi
if [ -z "$GRANTEE" ]; then
    echo -e "${RED}❌ GRANTEE가 비어 있습니다. 위 설정값을 채운 뒤 다시 실행하세요.${NC}"
    exit 1
fi

echo -e "${CYAN}=== SmartBrief All-in-One 배포 ===${NC}"
echo -e "프로젝트: ${GREEN}$PROJECT_ID${NC} | 리전: ${GREEN}$REGION${NC} | 서비스: ${GREEN}$SERVICE${NC}"
echo -e "API_KEY: ${YELLOW}$([ -n "$API_KEY" ] && echo '설정됨' || echo '비어 있음 -> 이 프로젝트에서 자동 생성')${NC}"
echo -e "GOOGLE_MAPS_API_KEY: ${YELLOW}$([ -n "$GOOGLE_MAPS_API_KEY" ] && echo '설정됨' || echo '비어 있음 -> 자동 생성')${NC}"
echo ""

EXPECTED_EMAIL="${GRANTEE#user:}"

force_set_project() {
    local target_project=$1
    gcloud config set project "$target_project" 2>&1
    gcloud config configurations activate default 2>/dev/null || true
    export CLOUDSDK_CORE_PROJECT=$target_project
}

verify_project() {
    CURRENT=$(gcloud config get-value project 2>/dev/null)
    if [ "$CURRENT" != "$PROJECT_ID" ]; then
        force_set_project "$PROJECT_ID"
    fi
    export CLOUDSDK_CORE_PROJECT=$PROJECT_ID
}

# [1/9] 로그인/프로젝트
echo -e "\n${CYAN}[1/9] gcloud 로그인/프로젝트${NC}"
CURRENT_ACCOUNT=$(gcloud config get-value account 2>/dev/null || true)
if [ -z "$CURRENT_ACCOUNT" ]; then
    echo -e "${YELLOW}로그인이 필요합니다...${NC}"
    gcloud auth login
fi
if ! gcloud projects list --limit=1 >/dev/null 2>&1; then
    echo -e "${RED}❌ 자격 증명이 유효하지 않습니다. gcloud auth login 후 다시 실행하세요.${NC}"
    exit 1
fi
force_set_project "$PROJECT_ID"
echo -e "${GREEN}✅ 프로젝트: $PROJECT_ID (설정값 사용)${NC}"

# [2/9] 권한 확인
echo -e "\n${CYAN}[2/9] 권한 확인 (Owner/Editor)${NC}"
CURRENT_ACCOUNT_FINAL=$(gcloud config get-value account 2>/dev/null || echo "")
IAM_ROLES=$(gcloud projects get-iam-policy "$PROJECT_ID" \
  --flatten="bindings[].members" \
  --format="table(bindings.role,bindings.members)" 2>/dev/null | grep "user:${CURRENT_ACCOUNT_FINAL}" || true)
if ! echo "$IAM_ROLES" | grep -E "roles/owner|roles/editor" >/dev/null 2>&1; then
    echo -e "${RED}❌ 이 프로젝트에서 Owner/Editor 권한이 필요합니다.${NC}"
    exit 1
fi
echo -e "${GREEN}✅ 권한 확인 완료${NC}"

# [3/9] API 활성화 + 키 자동 생성
echo -e "\n${CYAN}[3/9] API 활성화 및 API 키 처리${NC}"
verify_project
force_set_project "$PROJECT_ID"
export CLOUDSDK_CORE_PROJECT=$PROJECT_ID

FINAL_CHECK=$(gcloud config get-value project 2>/dev/null)
if [ "$FINAL_CHECK" != "$PROJECT_ID" ]; then
    echo -e "${RED}❌ 프로젝트 설정 실패: $FINAL_CHECK -> $PROJECT_ID${NC}"
    exit 1
fi

if ! gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com \
  maps-backend.googleapis.com geocoding-backend.googleapis.com apikeys.googleapis.com \
  generativelanguage.googleapis.com \
  --project="$PROJECT_ID"; then
  echo -e "${RED}❌ API 활성화 실패. 아래를 확인하세요.${NC}"
  echo -e "${YELLOW}  1) 이 프로젝트에서 로그인한 계정이 Owner(또는 Editor)인지: IAM 및 관리자 -> 해당 계정에 Owner/Editor 역할${NC}"
  echo -e "${YELLOW}  2) 프로젝트에 결제(빌링)가 연결되어 있는지: 결제 -> 이 프로젝트에 결제 계정 연결${NC}"
  echo -e "${YELLOW}  3) 프로젝트 ID가 맞는지: $PROJECT_ID${NC}"
  exit 1
fi
echo -e "${GREEN}✅ API 활성화 완료${NC}"

# Gemini 키: 비어 있으면 자동 생성
if [ -z "$API_KEY" ]; then
  echo -e "${CYAN}Gemini API 키 자동 생성 중...${NC}"
  GEMINI_KEY_NAME=""
  if GEMINI_KEY_NAME=$(gcloud beta services api-keys create \
    --display-name="SmartBrief-Gemini-$(date +%Y%m%d)" \
    --project="$PROJECT_ID" \
    --format="value(name)" 2>/dev/null); then
    sleep 2
    API_KEY=$(gcloud beta services api-keys get-key-string "$GEMINI_KEY_NAME" --project="$PROJECT_ID" 2>/dev/null || true)
    if [ -n "$API_KEY" ]; then
      echo -e "${GREEN}✅ Gemini API 키 자동 생성 완료${NC}"
    else
      echo -e "${YELLOW}⚠️  Gemini 키 조회 실패. 스크립트 상단 API_KEY에 키를 넣고 다시 실행하세요.${NC}"
    fi
  else
    echo -e "${YELLOW}⚠️  Gemini 키 자동 생성 실패. API_KEY를 수동 설정하세요.${NC}"
  fi
fi

# Maps 키: 비어 있으면 자동 생성
if [ -z "$GOOGLE_MAPS_API_KEY" ]; then
  echo -e "${CYAN}Google Maps API 키 자동 생성 중...${NC}"
  MAPS_KEY_NAME=""
  if MAPS_KEY_NAME=$(gcloud beta services api-keys create \
    --display-name="SmartBrief-Maps-$(date +%Y%m%d)" \
    --project="$PROJECT_ID" \
    --format="value(name)" 2>/dev/null); then
    sleep 2
    GOOGLE_MAPS_API_KEY=$(gcloud beta services api-keys get-key-string "$MAPS_KEY_NAME" --project="$PROJECT_ID" 2>/dev/null || true)
    if [ -n "$GOOGLE_MAPS_API_KEY" ]; then
      echo -e "${GREEN}✅ Maps API 키 자동 생성 완료${NC}"
    else
      echo -e "${YELLOW}⚠️  Maps 키 조회 실패. GOOGLE_MAPS_API_KEY를 수동 설정하면 지도 사용 가능.${NC}"
    fi
  else
    echo -e "${YELLOW}⚠️  Maps 키 자동 생성 실패. GOOGLE_MAPS_API_KEY를 수동 설정하면 지도 사용 가능.${NC}"
  fi
fi

if [ -z "$API_KEY" ]; then
  echo -e "${RED}❌ Gemini API 키가 비어 있습니다. 스크립트 상단 API_KEY에 키를 넣은 뒤 다시 실행하세요.${NC}"
  exit 1
fi

# [4/9] Artifact Registry
echo -e "\n${CYAN}[4/9] Artifact Registry${NC}"
verify_project
if gcloud artifacts repositories create $REPO \
  --repository-format=docker --location=$REGION --description="SmartBrief images" \
  --project="$PROJECT_ID" 2>/dev/null; then
  echo -e "${GREEN}✅ 저장소 생성 완료${NC}"
else
  echo -e "${YELLOW}이미 존재하거나 스킵${NC}"
fi
gcloud artifacts repositories describe $REPO --location=$REGION --project="$PROJECT_ID" >/dev/null

# Cloud Build 서비스 계정에 역할 부여 (처음 배포 시 PERMISSION_DENIED 방지)
echo -e "\n${CYAN}[4.5/9] Cloud Build 서비스 계정 역할 부여${NC}"
verify_project
PROJECT_NUM=$(gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)" --project="$PROJECT_ID" 2>/dev/null || true)
if [ -n "$PROJECT_NUM" ]; then
  CB_SA="${PROJECT_NUM}@cloudbuild.gserviceaccount.com"
  COMPUTE_SA="${PROJECT_NUM}-compute@developer.gserviceaccount.com"
  for ROLE in roles/run.admin roles/iam.serviceAccountUser roles/storage.admin; do
    gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:${CB_SA}" --role="$ROLE" --project="$PROJECT_ID" --quiet 2>/dev/null || true
  done
  # Compute Engine 기본 서비스 계정: 버킷 읽기, Artifact Registry 푸시, 로그 기록
  for ROLE in roles/storage.admin roles/artifactregistry.writer roles/logging.logWriter; do
    gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:${COMPUTE_SA}" --role="$ROLE" --project="$PROJECT_ID" --quiet 2>/dev/null || true
  done
  echo -e "${GREEN}✅ Cloud Build 서비스 계정 역할 부여 완료${NC}"
else
  echo -e "${YELLOW}⚠️  프로젝트 번호 조회 실패. 빌드 단계에서 권한 오류가 나면 IAM에서 해당 Cloud Build 서비스 계정에 Cloud Run 관리자/서비스 계정 사용자/Storage 관리자 역할을 수동 부여하세요.${NC}"
fi

# 실행 사용자(GRANTEE)에게 Cloud Build·Storage 권한 부여 (gcloud builds submit 시 PERMISSION_DENIED 방지)
echo -e "\n${CYAN}[4.5/9] 실행 사용자(GRANTEE) Cloud Build·Storage 권한 부여${NC}"
verify_project
for ROLE in roles/cloudbuild.builds.editor roles/storage.objectAdmin; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="$GRANTEE" --role="$ROLE" --project="$PROJECT_ID" --quiet 2>/dev/null || true
done
echo -e "${GREEN}✅ GRANTEE 권한 부여 시도 완료 (이미 있으면 무시)${NC}"

# [5/9] 이미지 빌드 & 푸시
echo -e "\n${CYAN}[5/9] 이미지 빌드 & 푸시 (Cloud Build)${NC}"
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
  gcloud builds submit --tag $IMAGE --project="$PROJECT_ID" --no-source-config
else
  gcloud builds submit --tag $IMAGE --project="$PROJECT_ID"
fi
if [ -n "$CLOUDBUILD_BACKUP" ] && [ -f "$CLOUDBUILD_BACKUP" ]; then
  mv "$CLOUDBUILD_BACKUP" cloudbuild.yaml
fi

# latest 태그
echo -e "\n${CYAN}[6/9] latest 태그 & Cloud Run 배포${NC}"
verify_project
gcloud container images add-tag $IMAGE "$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/$SERVICE:latest" --quiet --project="$PROJECT_ID"

gcloud run deploy $SERVICE \
  --image "$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/$SERVICE:latest" \
  --region $REGION --platform managed --allow-unauthenticated \
  --cpu 1 --memory 2Gi --max-instances 3 --timeout 900 \
  --project="$PROJECT_ID"

LATEST_REVISION=$(gcloud run revisions list --service=$SERVICE --region=$REGION --format="value(name)" --limit=1 --sort-by=~metadata.creationTimestamp --project="$PROJECT_ID")
if [ -n "$LATEST_REVISION" ]; then
  gcloud run services update-traffic $SERVICE --region $REGION --to-latest --project="$PROJECT_ID"
  echo -e "${GREEN}✅ 최신 리비전 트래픽 100%${NC}"
fi

# [7/9] 환경 변수
echo -e "\n${CYAN}[7/9] 환경 변수 설정${NC}"
verify_project
STREAMLIT_URL=""
STREAMLIT_SERVICE="ats-fpl-validator"
if gcloud run services describe $STREAMLIT_SERVICE --region=$REGION --format="value(status.url)" --project="$PROJECT_ID" >/dev/null 2>&1; then
  STREAMLIT_URL=$(gcloud run services describe $STREAMLIT_SERVICE --region=$REGION --format="value(status.url)" --project="$PROJECT_ID")
fi
ENV_VARS="GEMINI_API_KEY=$API_KEY,GOOGLE_API_KEY=$API_KEY"
[ -n "$GOOGLE_MAPS_API_KEY" ] && ENV_VARS="$ENV_VARS,GOOGLE_MAPS_API_KEY=$GOOGLE_MAPS_API_KEY"
[ -n "$STREAMLIT_URL" ] && ENV_VARS="$ENV_VARS,STREAMLIT_URL=$STREAMLIT_URL"
gcloud run services update $SERVICE --region $REGION --update-env-vars "$ENV_VARS" --project="$PROJECT_ID"
echo -e "${GREEN}✅ 환경 변수 반영 완료${NC}"

# [8/9] 권한
echo -e "\n${CYAN}[8/9] 실행 권한 부여${NC}"
verify_project
gcloud run services add-iam-policy-binding $SERVICE \
  --region $REGION --member="$GRANTEE" --role="roles/run.invoker" --project="$PROJECT_ID"
gcloud run services add-iam-policy-binding $SERVICE \
  --region $REGION --member="allUsers" --role="roles/run.invoker" --project="$PROJECT_ID" 2>/dev/null || true

# [9/9] 완료
URL=$(gcloud run services describe $SERVICE --region=$REGION --format="value(status.url)" --project="$PROJECT_ID")
echo -e "\n${GREEN}✅ 배포 완료: $URL${NC}\n"
