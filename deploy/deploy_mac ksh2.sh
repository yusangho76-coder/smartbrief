#!/bin/bash

# ===== SmartBrief - GCR/Cloud Run 원클릭 배포 스크립트 (macOS/Linux) =====
# 요구: gcloud SDK 설치, 브라우저 로그인 가능 환경
# 이 스크립트는 deploy 폴더에서 실행되며, 프로젝트 루트를 자동으로 찾습니다.

set -e  # 오류 발생 시 스크립트 중단

# 스크립트가 있는 디렉토리 (deploy 폴더)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# 프로젝트 루트 디렉토리 (deploy 폴더의 상위 디렉토리)
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# 프로젝트 루트로 이동
cd "$PROJECT_ROOT"

# --- 설정값 ---김성현2 rokafpilot32@gmail.com
PROJECT_ID="smartbrief-490309"
REGION="asia-northeast3"               # 서울 권장
REPO="smartnotam"                       # Artifact Registry 저장소명
SERVICE="smartnotam3"                    # Cloud Run 서비스명
API_KEY="AIzaSyAgCVzUmUlYBPUqvsslAxFOHMuUhLeM9a4"
GRANTEE="user:rokafpilot32@gmail.com"

# 색상 정의
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 이 스크립트는 이 파일에 적힌 설정값만 사용합니다. (다른 sh 파일/gcloud config와 무관)
echo -e "${CYAN}=== 배포 설정 확인 ===${NC}"
echo -e "실행 스크립트: ${GREEN}$(basename "$0")${NC}"
echo -e "프로젝트 ID: ${GREEN}$PROJECT_ID${NC}"
echo -e "리전: ${GREEN}$REGION${NC}"
echo -e "저장소: ${GREEN}$REPO${NC}"
echo -e "서비스: ${GREEN}$SERVICE${NC}"
echo -e "프로젝트 루트: ${GREEN}$PROJECT_ROOT${NC}"
echo ""

# 현재 gcloud 프로젝트 확인
CURRENT_CONFIG_PROJECT=$(gcloud config get-value project 2>/dev/null || echo "설정 없음")
EXPECTED_EMAIL=$(echo "$GRANTEE" | sed 's/user://')

# ===== gcloud 프로젝트 초기화 (통합) =====
echo -e "${CYAN}=== gcloud 프로젝트 초기화 시작 ===${NC}\n"

CURRENT_PROJECT=$(gcloud config get-value project 2>/dev/null || echo "설정 없음")
CURRENT_ACCOUNT=$(gcloud config get-value account 2>/dev/null || echo "설정 없음")
CURRENT_CONFIG=$(gcloud config configurations list --filter="is_active:true" --format="value(name)" 2>/dev/null || echo "default")

echo -e "${CYAN}[1/5] 현재 gcloud 설정 확인${NC}"
echo -e "  현재 프로젝트: ${YELLOW}$CURRENT_PROJECT${NC}"
echo -e "  현재 계정: ${YELLOW}$CURRENT_ACCOUNT${NC}"
echo -e "  현재 configuration: ${YELLOW}$CURRENT_CONFIG${NC}"
echo ""

# 자격 증명이 유효한지 확인
CREDENTIALS_VALID=false
if [ -n "$CURRENT_ACCOUNT" ]; then
    # 간단한 gcloud 명령어로 자격 증명 테스트
    if gcloud projects list --limit=1 >/dev/null 2>&1; then
        CREDENTIALS_VALID=true
    fi
fi

# 프로젝트나 계정이 불일치하거나 자격 증명이 유효하지 않은 경우 초기화
if [ "$CURRENT_PROJECT" != "$PROJECT_ID" ] || [ "$CURRENT_ACCOUNT" != "$EXPECTED_EMAIL" ] || [ "$CREDENTIALS_VALID" = false ]; then
    if [ "$CURRENT_PROJECT" != "$PROJECT_ID" ]; then
        echo -e "${YELLOW}⚠️  프로젝트 불일치: $CURRENT_PROJECT → $PROJECT_ID${NC}"
    fi
    if [ "$CURRENT_ACCOUNT" != "$EXPECTED_EMAIL" ]; then
        echo -e "${YELLOW}⚠️  계정 불일치: $CURRENT_ACCOUNT → $EXPECTED_EMAIL${NC}"
    fi
    if [ "$CREDENTIALS_VALID" = false ]; then
        echo -e "${YELLOW}⚠️  자격 증명이 유효하지 않습니다.${NC}"
    fi
    
    echo -e "${CYAN}[2/5] gcloud configuration 초기화${NC}"
    # 발견된 configurations 확인
    CONFIGS=$(gcloud config configurations list --format="value(name)" 2>/dev/null || echo "default")
    echo -e "  발견된 configurations: ${YELLOW}$CONFIGS${NC}"
    
    # default configuration으로 전환
    echo -e "  default configuration으로 전환 중...${NC}"
    gcloud config configurations activate default 2>/dev/null || true
    
    # 프로젝트 설정 초기화
    echo -e "  프로젝트 설정 초기화 중...${NC}"
    gcloud config unset project 2>/dev/null || true
    
    # 기존 인증 정보 초기화
    echo -e "  기존 인증 정보 초기화 중...${NC}"
    gcloud auth revoke --all 2>/dev/null || true
    
    # ADC 초기화
    echo -e "  ADC 초기화 중...${NC}"
    ADC_FILE="$HOME/.config/gcloud/application_default_credentials.json"
    if [ -f "$ADC_FILE" ]; then
        rm -f "$ADC_FILE" 2>/dev/null || true
    fi
    gcloud auth application-default revoke --quiet 2>/dev/null || true
    
    echo -e "${GREEN}✅ gcloud 설정 초기화 완료${NC}"
    
    echo -e "\n${CYAN}[3/5] 새로운 계정으로 로그인${NC}"
    echo -e "  예상 계정: ${GREEN}$EXPECTED_EMAIL${NC}"
    echo -e "  ${YELLOW}브라우저에서 로그인하세요...${NC}"
    gcloud auth login
    
    # 로그인 후 자격 증명 확인 및 재시도
    LOGGED_IN_ACCOUNT=$(gcloud config get-value account 2>/dev/null || echo "")
    echo -e "  로그인된 계정: ${GREEN}$LOGGED_IN_ACCOUNT${NC}"
    
    # 자격 증명이 유효한지 확인 (최대 3회 시도)
    echo -e "  ${CYAN}자격 증명 확인 중...${NC}"
    MAX_RETRIES=3
    RETRY_COUNT=0
    while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
        # 실제 API 호출로 자격 증명 검증
        if gcloud projects list --limit=1 >/dev/null 2>&1; then
            echo -e "  ${GREEN}✅ 자격 증명 확인 완료${NC}"
            break
        else
            RETRY_COUNT=$((RETRY_COUNT + 1))
            if [ $RETRY_COUNT -lt $MAX_RETRIES ]; then
                echo -e "  ${YELLOW}⚠️  자격 증명이 유효하지 않습니다. 다시 로그인합니다... (시도 $RETRY_COUNT/$MAX_RETRIES)${NC}"
                gcloud auth login
            else
                echo -e "  ${RED}❌ 자격 증명 확인 실패. 수동으로 로그인하세요:${NC}"
                echo -e "  ${CYAN}gcloud auth login${NC}"
                exit 1
            fi
        fi
    done
    
    # 최종 계정 확인
    FINAL_ACCOUNT=$(gcloud config get-value account 2>/dev/null || echo "")
    if [ "$FINAL_ACCOUNT" != "$EXPECTED_EMAIL" ]; then
        echo -e "${YELLOW}⚠️  경고: 로그인한 계정($FINAL_ACCOUNT)이 예상 계정($EXPECTED_EMAIL)과 다릅니다.${NC}"
        echo -e "${YELLOW}계속 진행합니다...${NC}"
    fi
    echo -e "${GREEN}✅ 로그인 완료${NC}"
    
    echo -e "\n${CYAN}[4/5] 프로젝트 설정${NC}"
    echo -e "  목표 프로젝트: ${GREEN}$PROJECT_ID${NC}"
    gcloud config set project $PROJECT_ID 2>&1
    echo -e "${GREEN}✅ 프로젝트 설정 확인: $PROJECT_ID${NC}"
    echo -e "${GREEN}✅ 프로젝트 설정 완료${NC}"
    
    echo -e "\n${CYAN}[5/5] ADC 설정${NC}"
    echo -e "  ${YELLOW}ADC 설정을 건너뜁니다 (배포 스크립트에서 사용하지 않음)${NC}"
    echo -e "${GREEN}✅ ADC 설정 스킵 완료${NC}"
    
    echo -e "\n${CYAN}=== 최종 설정 확인 ===${NC}"
    FINAL_PROJECT=$(gcloud config get-value project 2>/dev/null)
    FINAL_ACCOUNT=$(gcloud config get-value account 2>/dev/null)
    echo -e "  gcloud 프로젝트: ${GREEN}$FINAL_PROJECT${NC}"
    echo -e "  gcloud 계정: ${GREEN}$FINAL_ACCOUNT${NC}"
    echo -e "  환경변수: ${GREEN}$PROJECT_ID${NC}"
    echo ""
    echo -e "${GREEN}✅ gcloud 프로젝트 초기화 완료!${NC}"
    echo ""
else
    echo -e "${GREEN}✅ gcloud 설정이 올바릅니다.${NC}"
    echo ""
fi

# 프로젝트 설정 함수
force_set_project() {
    local target_project=$1
    gcloud config set project $target_project 2>&1
    gcloud config configurations activate default 2>/dev/null || true
    export CLOUDSDK_CORE_PROJECT=$target_project
}

# 프로젝트 설정 확인
CURRENT_PROJECT=$(gcloud config get-value project 2>/dev/null)
if [ "$CURRENT_PROJECT" != "$PROJECT_ID" ]; then
    force_set_project $PROJECT_ID
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
# 자격 증명 최종 확인
CURRENT_ACCOUNT_FINAL=$(gcloud config get-value account 2>/dev/null || echo "")
if [ -z "$CURRENT_ACCOUNT_FINAL" ]; then
    echo -e "${RED}❌ 계정이 설정되지 않았습니다. 로그인을 진행합니다...${NC}"
    gcloud auth login
fi

# 자격 증명이 유효한지 최종 확인
if ! gcloud projects list --limit=1 >/dev/null 2>&1; then
    echo -e "${RED}❌ 자격 증명이 유효하지 않습니다. 로그인을 진행합니다...${NC}"
    gcloud auth login
    # 재확인
    if ! gcloud projects list --limit=1 >/dev/null 2>&1; then
        echo -e "${RED}❌ 자격 증명 확인 실패. 수동으로 로그인하세요:${NC}"
        echo -e "${CYAN}gcloud auth login${NC}"
        exit 1
    fi
fi

# 프로젝트 설정 확인
CURRENT_PROJECT_FINAL=$(gcloud config get-value project 2>/dev/null)
if [ "$CURRENT_PROJECT_FINAL" != "$PROJECT_ID" ]; then
    force_set_project $PROJECT_ID
fi

echo -e "${GREEN}✅ 프로젝트 설정 확인: $PROJECT_ID${NC}"
echo -e "${GREEN}✅ 계정 설정 확인: $(gcloud config get-value account 2>/dev/null || echo '설정 없음')${NC}"
echo -e "${GREEN}✅ 자격 증명 확인 완료${NC}"

echo -e "\n${CYAN}[2/9] 필수 API 활성화${NC}"
# 프로젝트 설정 강제 확인 (API 활성화 전에 반드시 올바른 프로젝트로 설정)
verify_project
force_set_project $PROJECT_ID
export CLOUDSDK_CORE_PROJECT=$PROJECT_ID
# 최종 프로젝트 확인
FINAL_CHECK=$(gcloud config get-value project 2>/dev/null)
if [ "$FINAL_CHECK" != "$PROJECT_ID" ]; then
    echo -e "${RED}❌ 프로젝트 설정 실패! 현재: $FINAL_CHECK, 목표: $PROJECT_ID${NC}"
    echo -e "${YELLOW}수동으로 프로젝트를 설정하세요: gcloud config set project $PROJECT_ID${NC}"
    exit 1
fi
echo -e "${GREEN}✅ 프로젝트 최종 확인: $PROJECT_ID${NC}"
# Run/빌드 + Gemini + Maps JavaScript + Places(기존/신규) + Geocoding + API Keys
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
  # Compute Engine 기본 서비스 계정: 버킷 읽기, Artifact Registry 푸시, 로그 기록
  for ROLE in roles/storage.admin roles/artifactregistry.writer roles/logging.logWriter; do
    gcloud projects add-iam-policy-binding $PROJECT_ID --member="serviceAccount:${COMPUTE_SA}" --role="$ROLE" $GCLOUD_PROJECT_FLAG --quiet 2>/dev/null || true
  done
  echo -e "${GREEN}✅ Cloud Build 서비스 계정 역할 부여 완료${NC}"
else
  echo -e "${YELLOW}⚠️  프로젝트 번호 조회 실패. 빌드 단계에서 권한 오류가 나면 IAM에서 프로젝트의 Cloud Build 서비스 계정(프로젝트번호@cloudbuild.gserviceaccount.com)에 Cloud Run 관리자/서비스 계정 사용자/Storage 관리자 역할을 수동 부여하세요.${NC}"
fi

# 스크립트 실행 사용자(GRANTEE)에게 Cloud Build·Storage 권한 부여 (gcloud builds submit 시 PERMISSION_DENIED 방지)
echo -e "\n${CYAN}[3.6/9] 실행 사용자(GRANTEE) Cloud Build·Storage 권한 부여${NC}"
verify_project
for ROLE in roles/cloudbuild.builds.editor roles/storage.objectAdmin; do
  gcloud projects add-iam-policy-binding $PROJECT_ID --member="$GRANTEE" --role="$ROLE" $GCLOUD_PROJECT_FLAG --quiet 2>/dev/null || true
done
echo -e "${GREEN}✅ GRANTEE 권한 부여 시도 완료 (이미 있으면 무시)${NC}"

echo -e "\n${CYAN}[4/9] 이미지 빌드 & 푸시 (Cloud Build)${NC}"
verify_project

# 프로젝트 루트에서 실행 (Dockerfile, requirements.txt 등이 있는 곳)
cd "$PROJECT_ROOT"

# cloudbuild.yaml temporarily renamed to avoid hardcoded project in trigger
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

echo -e "\n${CYAN}[7/9] 환경변수 설정${NC}"
verify_project

# Streamlit 앱 URL 확인 (ats-fpl-validator 서비스)
STREAMLIT_SERVICE="ats-fpl-validator"
STREAMLIT_URL=""
if gcloud run services describe $STREAMLIT_SERVICE --region=$REGION --format="value(status.url)" $GCLOUD_PROJECT_FLAG > /dev/null 2>&1; then
    STREAMLIT_URL=$(gcloud run services describe $STREAMLIT_SERVICE --region=$REGION --format="value(status.url)" $GCLOUD_PROJECT_FLAG)
    echo -e "${GREEN}Streamlit 앱 URL 발견: $STREAMLIT_URL${NC}"
else
    echo -e "${YELLOW}⚠️  Streamlit 앱($STREAMLIT_SERVICE)이 배포되지 않았습니다.${NC}"
    echo -e "${YELLOW}   ATSplanvalidation/deploy_streamlit.sh를 먼저 실행하세요.${NC}"
fi

# 환경 변수 설정 (GEMINI_API_KEY, GOOGLE_MAPS_API_KEY, GOOGLE_API_KEY)
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
# 특정 사용자에게 권한 부여
gcloud run services add-iam-policy-binding $SERVICE \
  --region $REGION \
  --member="$GRANTEE" \
  --role="roles/run.invoker" \
  $GCLOUD_PROJECT_FLAG

# 모든 사용자(비인증 포함)에게 접근 허용 - Forbidden 오류 방지
echo -e "${YELLOW}공개 접근 권한 부여 (allUsers)...${NC}"
gcloud run services add-iam-policy-binding $SERVICE \
  --region $REGION \
  --member="allUsers" \
  --role="roles/run.invoker" \
  $GCLOUD_PROJECT_FLAG 2>/dev/null || echo -e "${YELLOW}⚠️  allUsers 권한 부여 실패 - 조직 정책 제한일 수 있습니다. 아래 수동 해결 방법을 확인하세요.${NC}"

URL=$(gcloud run services describe $SERVICE --region $REGION --format="value(status.url)" $GCLOUD_PROJECT_FLAG)

echo -e "\n${CYAN}[9/9] 배포 완료 확인${NC}"
echo -e "${GREEN}Flask 앱 배포 완료: $URL${NC}"

# Streamlit 앱 URL도 확인
STREAMLIT_SERVICE="ats-fpl-validator"
STREAMLIT_URL_FINAL=""
if gcloud run services describe $STREAMLIT_SERVICE --region=$REGION --format="value(status.url)" $GCLOUD_PROJECT_FLAG > /dev/null 2>&1; then
    STREAMLIT_URL_FINAL=$(gcloud run services describe $STREAMLIT_SERVICE --region=$REGION --format="value(status.url)" $GCLOUD_PROJECT_FLAG)
    echo -e "${GREEN}Streamlit 앱 URL: $STREAMLIT_URL_FINAL${NC}"
else
    echo -e "${YELLOW}⚠️  Streamlit 앱 URL을 확인할 수 없습니다.${NC}"
fi

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

# cloudbuild.yaml을 GitHub에 올려 트리거에서 사용 가능하게 함
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
