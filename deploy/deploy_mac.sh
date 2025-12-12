#!/bin/bash

# ===== Smart NOTAM - GCR/Cloud Run 원클릭 배포 스크립트 (macOS/Linux) =====
# 요구: gcloud SDK 설치, 브라우저 로그인 가능 환경
# 이 스크립트는 deploy 폴더에서 실행되며, 프로젝트 루트를 자동으로 찾습니다.

set -e  # 오류 발생 시 스크립트 중단

# 스크립트가 있는 디렉토리 (deploy 폴더)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# 프로젝트 루트 디렉토리 (deploy 폴더의 상위 디렉토리)
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# 프로젝트 루트로 이동
cd "$PROJECT_ROOT"

# # --- 설정값 ---양호중
# PROJECT_ID="smartnotam-476803"
# REGION="asia-northeast3"               # 서울 권장
# REPO="smartnotam"                       # Artifact Registry 저장소명
# SERVICE="smartnotam"                    # Cloud Run 서비스명
# API_KEY="AIzaSyA7rf9lPi2h_0ff7hg2OpheObhhbRXRkxI"
# GRANTEE="user:yangs9508@gmail.com"

# --- 설정값 ---성민경
PROJECT_ID="smartnotam-475810"
REGION="asia-northeast3"               # 서울 권장
REPO="smartnotam-repo"                 # Artifact Registry 저장소명
SERVICE="smartnotam"                    # Cloud Run 서비스명
API_KEY="AIzaSyACBBkCMKp7cO73B828wFgOhATYGaJ0fcE"
GRANTEE="user:aaronandmiriam@gmail.com"

# # --- 설정값 ---광언
# PROJECT_ID="smartnotam-476502"
# REGION="asia-northeast3"               # 서울 권장
# REPO="smartnotam"                 # Artifact Registry 저장소명
# SERVICE="smartnotam"                    # Cloud Run 서비스명
# API_KEY="AIzaSyD5PPJlQJ9_ATyLdRy41yhhDIjsl3aZKPQ"
# GRANTEE="user:madword76@gmail.com"

# --- 설정값 ---안상권
# PROJECT_ID="smartnotam3-480106"
# REGION="asia-northeast3"               # 서울 권장
# REPO="smartnotam"                 # Artifact Registry 저장소명
# SERVICE="smartnotam"                    # Cloud Run 서비스명
# API_KEY="AIzaSyChkfPm_7ay6yoHdgEfdXuCjFByzrnePFY"
# GRANTEE="user:sowgun0070@gmail.com"

# # --- 설정값 ---유상
# PROJECT_ID="sh-smartnotam3"
# REGION="asia-northeast3"               # 서울 권장
# REPO="smartnotam2"                 # Artifact Registry 저장소명
# SERVICE="smartnotam2"                    # Cloud Run 서비스명
# API_KEY="AIzaSyBhm5_WpN9AEHopuLRqWJUnNlUsVgX-ie0"
# GRANTEE="user:yusangho76@gmail.com"
# gcloud config set account yusangho76@gmail.com
# gcloud config set project sh-smartnotam3

# # --- 설정값 ---선준
# PROJECT_ID="artful-sky-474201-u4"
# REGION="asia-northeast3"               # 서울 권장
# REPO="smartnotam-repo"                 # Artifact Registry 저장소명
# SERVICE="smartnotam"                    # Cloud Run 서비스명
# API_KEY="AIzaSyCjhNvn7mFoZ_rIPyOs4eFUo7Aw_XihEdQ"
# GRANTEE="user:sunjoon.kim@gmail.com"

# 색상 정의
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 디버깅: 사용할 프로젝트 ID 확인
echo -e "${CYAN}=== 배포 설정 확인 ===${NC}"
echo -e "프로젝트 ID: ${GREEN}$PROJECT_ID${NC}"
echo -e "리전: ${GREEN}$REGION${NC}"
echo -e "저장소: ${GREEN}$REPO${NC}"
echo -e "서비스: ${GREEN}$SERVICE${NC}"
echo -e "프로젝트 루트: ${GREEN}$PROJECT_ROOT${NC}"
echo ""

# 현재 gcloud 프로젝트 확인
CURRENT_CONFIG_PROJECT=$(gcloud config get-value project 2>/dev/null || echo "설정 없음")
EXPECTED_EMAIL=$(echo "$GRANTEE" | sed 's/user://')

# 프로젝트 초기화 스크립트 실행 여부 확인
INIT_RAN=false
if [ "$CURRENT_CONFIG_PROJECT" != "$PROJECT_ID" ]; then
    echo -e "${YELLOW}⚠️  gcloud 설정이 올바르지 않습니다.${NC}"
    echo -e "${CYAN}프로젝트 초기화 스크립트를 자동으로 실행합니다...${NC}"
    
    INIT_SCRIPT="$SCRIPT_DIR/init_gcloud_project.sh"
    if [ -f "$INIT_SCRIPT" ]; then
        chmod +x "$INIT_SCRIPT"
        # 호출한 스크립트 파일 경로를 인자로 전달
        bash "$INIT_SCRIPT" "$0" || {
            echo -e "${RED}❌ 초기화 스크립트 실행 실패${NC}"
            exit 1
        }
        INIT_RAN=true
        echo ""
    else
        echo -e "${RED}❌ 초기화 스크립트를 찾을 수 없습니다: $INIT_SCRIPT${NC}"
        exit 1
    fi
fi

echo -e "\n${CYAN}[1/8] gcloud 로그인/프로젝트 설정${NC}"
# 초기화 스크립트가 실행되지 않았으면 무조건 로그인
if [ "$INIT_RAN" = false ]; then
    CURRENT_ACCOUNT=$(gcloud config get-value account 2>/dev/null || echo "")
    if [ -n "$CURRENT_ACCOUNT" ]; then
        echo -e "${YELLOW}현재 로그인된 계정: $CURRENT_ACCOUNT${NC}"
    fi
    echo -e "${YELLOW}로그인을 진행합니다...${NC}"
    gcloud auth login
fi

# 프로젝트 설정 함수
force_set_project() {
    local target_project=$1
    gcloud config set project $target_project 2>&1
    gcloud config configurations activate default 2>/dev/null || true
    export CLOUDSDK_CORE_PROJECT=$target_project
}

# 프로젝트 설정
force_set_project $PROJECT_ID

# 프로젝트 설정 확인
CURRENT_PROJECT=$(gcloud config get-value project 2>/dev/null)
if [ "$CURRENT_PROJECT" != "$PROJECT_ID" ]; then
    echo -e "${RED}❌ 오류: 프로젝트 설정 실패!${NC}"
    echo -e "${RED}  현재 프로젝트: $CURRENT_PROJECT, 목표 프로젝트: $PROJECT_ID${NC}"
    exit 1
fi

echo -e "${GREEN}✅ 프로젝트 설정 확인: $PROJECT_ID${NC}"

# 모든 명령어에 사용할 공통 플래그
GCLOUD_PROJECT_FLAG="--project=$PROJECT_ID"

# 프로젝트 설정 확인 함수
verify_project() {
    CURRENT=$(gcloud config get-value project 2>/dev/null)
    if [ "$CURRENT" != "$PROJECT_ID" ]; then
        force_set_project $PROJECT_ID
    fi
    export CLOUDSDK_CORE_PROJECT=$PROJECT_ID
}

echo -e "\n${CYAN}[2/8] 필수 API 활성화${NC}"
verify_project
gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com $GCLOUD_PROJECT_FLAG

echo -e "\n${CYAN}[3/8] Artifact Registry 리포지토리 생성(존재 시 무시)${NC}"
verify_project
if gcloud artifacts repositories create $REPO \
    --repository-format=docker \
    --location=$REGION \
    --description="Smart NOTAM images" \
    $GCLOUD_PROJECT_FLAG 2>/dev/null; then
    echo "✅ 저장소 생성 완료"
else
    echo -e "${YELLOW} - 이미 존재하거나 생성 스킵${NC}"
fi

gcloud artifacts repositories describe $REPO --location=$REGION $GCLOUD_PROJECT_FLAG > /dev/null

echo -e "\n${CYAN}[4/8] 이미지 빌드 & 푸시 (Cloud Build)${NC}"
verify_project

# 프로젝트 루트에서 실행 (Dockerfile, requirements.txt 등이 있는 곳)
cd "$PROJECT_ROOT"

# cloudbuild.yaml 파일이 있으면 임시로 이름 변경 (하드코딩된 프로젝트 방지)
CLOUDBUILD_BACKUP=""
if [ -f "cloudbuild.yaml" ]; then
    CLOUDBUILD_BACKUP="cloudbuild.yaml.backup.$$"
    mv cloudbuild.yaml "$CLOUDBUILD_BACKUP"
fi

TIMESTAMP=$(date +"%Y%m%d-%H%M%S")
IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/$SERVICE:$TIMESTAMP"

# 이미지 빌드 및 푸시
if gcloud builds submit --help 2>&1 | grep -q "no-source-config"; then
    gcloud builds submit --tag $IMAGE $GCLOUD_PROJECT_FLAG --no-source-config
else
    gcloud builds submit --tag $IMAGE $GCLOUD_PROJECT_FLAG
fi

# cloudbuild.yaml 백업 복원
if [ -n "$CLOUDBUILD_BACKUP" ] && [ -f "$CLOUDBUILD_BACKUP" ]; then
    mv "$CLOUDBUILD_BACKUP" cloudbuild.yaml
fi

echo -e "\n${CYAN}[5/8] latest 태그 부여${NC}"
verify_project
gcloud container images add-tag $IMAGE "$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/$SERVICE:latest" --quiet --project=$PROJECT_ID

echo -e "\n${CYAN}[6/8] Cloud Run 배포${NC}"
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

# 배포된 최신 리비전에 트래픽 100% 할당
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

echo -e "\n${CYAN}[7/8] 환경변수(GEMINI_API_KEY) 설정${NC}"
verify_project
gcloud run services update $SERVICE \
  --region $REGION \
  --update-env-vars "GEMINI_API_KEY=$API_KEY" \
  $GCLOUD_PROJECT_FLAG

echo -e "\n${CYAN}[8/8] 실행 권한 부여(roles/run.invoker)${NC}"
verify_project
gcloud run services add-iam-policy-binding $SERVICE \
  --region $REGION \
  --member="$GRANTEE" \
  --role="roles/run.invoker" \
  $GCLOUD_PROJECT_FLAG

URL=$(gcloud run services describe $SERVICE --region $REGION --format="value(status.url)" $GCLOUD_PROJECT_FLAG)

echo -e "\n${GREEN}배포 완료: $URL${NC}"

# 배포 완료 후 ADC 삭제 (보안상 로컬에 인증 정보를 남기지 않음)
ADC_FILE="$HOME/.config/gcloud/application_default_credentials.json"
if [ -f "$ADC_FILE" ]; then
    echo -e "\n${CYAN}ADC 정리 중...${NC}"
    # 파일을 먼저 백업 후 삭제 (대화형 프롬프트 방지)
    BACKUP_FILE="${ADC_FILE}.backup.$(date +%Y%m%d_%H%M%S)"
    mv "$ADC_FILE" "$BACKUP_FILE" 2>/dev/null || rm -f "$ADC_FILE" 2>/dev/null || true
    # gcloud 명령어로도 취소 시도 (--quiet로 대화형 프롬프트 방지)
    gcloud auth application-default revoke --quiet 2>/dev/null || true
    echo -e "${GREEN}✅ ADC 정리 완료${NC}"
fi

echo -e "\n${GREEN}✅ 모든 작업 완료!${NC}"

