#!/bin/bash

# ===== SmartBrief - 간편 배포 스크립트 =====
# 초보자도 쉽게 사용할 수 있는 자동화된 배포 스크립트
# 
# 사용법:
#   1. deploy/config.sh 파일 생성 (config.example.sh 참고)
#   2. ./deploy/deploy_simple.sh 실행
#
# 또는 대화형 모드로 실행:
#   ./deploy/deploy_simple.sh --interactive

set -e  # 오류 발생 시 스크립트 중단

# 색상 정의
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 스크립트 디렉토리
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# 설정 파일 경로
CONFIG_FILE="$SCRIPT_DIR/config.sh"

# 대화형 모드 확인
INTERACTIVE=false
if [[ "$1" == "--interactive" ]] || [[ "$1" == "-i" ]]; then
    INTERACTIVE=true
fi

# 설정 파일 로드 함수
load_config() {
    if [ -f "$CONFIG_FILE" ]; then
        source "$CONFIG_FILE"
        echo -e "${GREEN}✅ 설정 파일을 불러왔습니다: $CONFIG_FILE${NC}"
    else
        echo -e "${YELLOW}⚠️  설정 파일이 없습니다: $CONFIG_FILE${NC}"
        if [ "$INTERACTIVE" = true ]; then
            create_config_interactive
        else
            echo -e "${RED}❌ 설정 파일이 필요합니다.${NC}"
            echo -e "${CYAN}다음 중 하나를 선택하세요:${NC}"
            echo -e "  1. ${GREEN}cp deploy/config.example.sh deploy/config.sh${NC} 후 수정"
            echo -e "  2. ${GREEN}./deploy/deploy_simple.sh --interactive${NC} (대화형 모드)"
            exit 1
        fi
    fi
}

# 대화형 설정 생성
create_config_interactive() {
    echo -e "\n${CYAN}=== 대화형 설정 모드 ===${NC}\n"
    
    # 프로젝트 ID
    if [ -z "$PROJECT_ID" ]; then
        echo -e "${YELLOW}Google Cloud 프로젝트 ID를 입력하세요 (없으면 자동 생성):${NC}"
        read -p "프로젝트 ID (Enter로 자동 생성): " PROJECT_ID
        if [ -z "$PROJECT_ID" ]; then
            PROJECT_ID="smartnotam-$(date +%s | tail -c 7)"
            echo -e "${GREEN}자동 생성된 프로젝트 ID: $PROJECT_ID${NC}"
        fi
    fi
    
    # 리전
    if [ -z "$REGION" ]; then
        echo -e "${YELLOW}리전을 선택하세요 (기본값: asia-northeast3 - 서울):${NC}"
        read -p "리전 [asia-northeast3]: " REGION
        REGION=${REGION:-asia-northeast3}
    fi
    
    # 저장소명
    if [ -z "$REPO" ]; then
        REPO="smartnotam-repo"
        echo -e "${GREEN}저장소명: $REPO${NC}"
    fi
    
    # 서비스명
    if [ -z "$SERVICE" ]; then
        SERVICE="smartnotam"
        echo -e "${GREEN}서비스명: $SERVICE${NC}"
    fi
    
    # Gemini API 키
    if [ -z "$GEMINI_API_KEY" ]; then
        echo -e "${YELLOW}Gemini API 키를 입력하세요 (필수):${NC}"
        read -p "GEMINI_API_KEY: " GEMINI_API_KEY
        if [ -z "$GEMINI_API_KEY" ]; then
            echo -e "${RED}❌ Gemini API 키는 필수입니다.${NC}"
            exit 1
        fi
    fi
    
    # 이메일
    if [ -z "$GRANTEE_EMAIL" ]; then
        CURRENT_EMAIL=$(gcloud config get-value account 2>/dev/null || echo "")
        if [ -n "$CURRENT_EMAIL" ]; then
            echo -e "${YELLOW}접근 권한을 부여할 이메일 (기본값: $CURRENT_EMAIL):${NC}"
        else
            echo -e "${YELLOW}접근 권한을 부여할 이메일:${NC}"
        fi
        read -p "이메일 [$CURRENT_EMAIL]: " GRANTEE_EMAIL
        GRANTEE_EMAIL=${GRANTEE_EMAIL:-$CURRENT_EMAIL}
    fi
    
    # 설정 파일 저장
    save_config
}

# 설정 파일 저장
save_config() {
    cat > "$CONFIG_FILE" << EOF
#!/bin/bash
# 자동 생성된 설정 파일
# 생성 시간: $(date)

PROJECT_ID="$PROJECT_ID"
REGION="$REGION"
REPO="$REPO"
SERVICE="$SERVICE"
GEMINI_API_KEY="$GEMINI_API_KEY"
GRANTEE_EMAIL="$GRANTEE_EMAIL"
EOF
    chmod 600 "$CONFIG_FILE"  # 보안을 위해 소유자만 읽기/쓰기
    echo -e "${GREEN}✅ 설정 파일이 저장되었습니다: $CONFIG_FILE${NC}"
}

# 필수 도구 확인
check_requirements() {
    echo -e "\n${CYAN}[0/9] 필수 도구 확인${NC}"
    
    # gcloud 확인
    if ! command -v gcloud &> /dev/null; then
        echo -e "${RED}❌ gcloud CLI가 설치되어 있지 않습니다.${NC}"
        echo -e "${YELLOW}설치 방법:${NC}"
        echo -e "  macOS: ${CYAN}brew install google-cloud-sdk${NC}"
        echo -e "  또는: ${CYAN}https://cloud.google.com/sdk/docs/install${NC}"
        exit 1
    fi
    echo -e "${GREEN}✅ gcloud CLI 확인됨${NC}"
    
    # Docker 확인 (선택사항, Cloud Build 사용 시 불필요)
    if command -v docker &> /dev/null; then
        echo -e "${GREEN}✅ Docker 확인됨 (로컬 빌드 가능)${NC}"
    else
        echo -e "${YELLOW}⚠️  Docker가 없습니다 (Cloud Build 사용)${NC}"
    fi
}

# 프로젝트 생성 (없는 경우)
create_project_if_needed() {
    echo -e "\n${CYAN}[1/9] Google Cloud 프로젝트 확인${NC}"
    
    # 프로젝트 존재 확인
    if gcloud projects describe "$PROJECT_ID" &>/dev/null; then
        echo -e "${GREEN}✅ 프로젝트가 이미 존재합니다: $PROJECT_ID${NC}"
    else
        echo -e "${YELLOW}프로젝트가 없습니다. 생성 중...${NC}"
        
        # 프로젝트 생성
        if gcloud projects create "$PROJECT_ID" --name="SmartBrief" 2>/dev/null; then
            echo -e "${GREEN}✅ 프로젝트 생성 완료: $PROJECT_ID${NC}"
        else
            echo -e "${RED}❌ 프로젝트 생성 실패${NC}"
            echo -e "${YELLOW}프로젝트 ID가 이미 사용 중이거나 권한이 없을 수 있습니다.${NC}"
            exit 1
        fi
        
        # 빌링 계정 연결 (선택사항)
        echo -e "${YELLOW}빌링 계정을 연결하시겠습니까? (무료 티어 사용 시 불필요)${NC}"
        read -p "연결하시겠습니까? [y/N]: " LINK_BILLING
        if [[ "$LINK_BILLING" =~ ^[Yy]$ ]]; then
            echo -e "${YELLOW}빌링 계정 ID를 입력하세요:${NC}"
            read -p "빌링 계정 ID: " BILLING_ACCOUNT
            if [ -n "$BILLING_ACCOUNT" ]; then
                gcloud billing projects link "$PROJECT_ID" --billing-account="$BILLING_ACCOUNT"
                echo -e "${GREEN}✅ 빌링 계정 연결 완료${NC}"
            fi
        fi
    fi
    
    # 프로젝트 설정
    gcloud config set project "$PROJECT_ID" --quiet
    export CLOUDSDK_CORE_PROJECT="$PROJECT_ID"
    echo -e "${GREEN}✅ 프로젝트 설정 완료${NC}"
}

# 로그인 확인
check_login() {
    echo -e "\n${CYAN}[2/9] Google Cloud 로그인 확인${NC}"
    
    CURRENT_ACCOUNT=$(gcloud config get-value account 2>/dev/null || echo "")
    if [ -z "$CURRENT_ACCOUNT" ]; then
        echo -e "${YELLOW}로그인이 필요합니다. 브라우저가 열립니다...${NC}"
        gcloud auth login
    else
        echo -e "${GREEN}✅ 로그인됨: $CURRENT_ACCOUNT${NC}"
        
        # 올바른 계정인지 확인
        if [ -n "$GRANTEE_EMAIL" ] && [ "$CURRENT_ACCOUNT" != "$GRANTEE_EMAIL" ]; then
            echo -e "${YELLOW}⚠️  현재 로그인된 계정($CURRENT_ACCOUNT)이 설정된 계정($GRANTEE_EMAIL)과 다릅니다.${NC}"
            read -p "계정을 변경하시겠습니까? [y/N]: " CHANGE_ACCOUNT
            if [[ "$CHANGE_ACCOUNT" =~ ^[Yy]$ ]]; then
                gcloud auth login
            fi
        fi
    fi
}

# API 활성화
enable_apis() {
    echo -e "\n${CYAN}[3/9] 필수 API 활성화${NC}"
    
    gcloud services enable \
        run.googleapis.com \
        artifactregistry.googleapis.com \
        cloudbuild.googleapis.com \
        --project="$PROJECT_ID" \
        --quiet
    
    echo -e "${GREEN}✅ API 활성화 완료${NC}"
}

# Artifact Registry 생성
create_repository() {
    echo -e "\n${CYAN}[4/9] Artifact Registry 저장소 생성${NC}"
    
    if gcloud artifacts repositories describe "$REPO" \
        --location="$REGION" \
        --project="$PROJECT_ID" &>/dev/null; then
        echo -e "${GREEN}✅ 저장소가 이미 존재합니다: $REPO${NC}"
    else
        gcloud artifacts repositories create "$REPO" \
            --repository-format=docker \
            --location="$REGION" \
            --description="SmartBrief Docker images" \
            --project="$PROJECT_ID" \
            --quiet
        
        echo -e "${GREEN}✅ 저장소 생성 완료: $REPO${NC}"
    fi
}

# 이미지 빌드 및 푸시
build_and_push() {
    echo -e "\n${CYAN}[5/9] Docker 이미지 빌드 및 푸시${NC}"
    
    TIMESTAMP=$(date +"%Y%m%d-%H%M%S")
    IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/$SERVICE:$TIMESTAMP"
    LATEST_IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/$SERVICE:latest"
    
    echo -e "${YELLOW}이미지 빌드 중... (몇 분 소요될 수 있습니다)${NC}"
    
    # Cloud Build로 빌드 및 푸시
    gcloud builds submit \
        --tag "$IMAGE" \
        --tag "$LATEST_IMAGE" \
        --project="$PROJECT_ID" \
        --quiet
    
    echo -e "${GREEN}✅ 이미지 빌드 및 푸시 완료${NC}"
    echo -e "  이미지: $IMAGE"
}

# Cloud Run 배포
deploy_to_cloud_run() {
    echo -e "\n${CYAN}[6/9] Cloud Run 배포${NC}"
    
    IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/$SERVICE:latest"
    
    gcloud run deploy "$SERVICE" \
        --image "$IMAGE" \
        --region "$REGION" \
        --platform managed \
        --allow-unauthenticated \
        --cpu 1 \
        --memory 2Gi \
        --max-instances 3 \
        --timeout 900 \
        --set-env-vars "GEMINI_API_KEY=$GEMINI_API_KEY" \
        --project="$PROJECT_ID" \
        --quiet
    
    echo -e "${GREEN}✅ Cloud Run 배포 완료${NC}"
}

# 권한 설정
set_permissions() {
    echo -e "\n${CYAN}[7/9] 접근 권한 설정${NC}"
    
    if [ -n "$GRANTEE_EMAIL" ]; then
        GRANTEE="user:$GRANTEE_EMAIL"
        
        gcloud run services add-iam-policy-binding "$SERVICE" \
            --region "$REGION" \
            --member="$GRANTEE" \
            --role="roles/run.invoker" \
            --project="$PROJECT_ID" \
            --quiet
        
        echo -e "${GREEN}✅ 권한 설정 완료: $GRANTEE_EMAIL${NC}"
    else
        echo -e "${YELLOW}⚠️  이메일이 설정되지 않아 권한 설정을 건너뜁니다.${NC}"
    fi
}

# 배포 URL 확인
get_deployment_url() {
    echo -e "\n${CYAN}[8/9] 배포 URL 확인${NC}"
    
    URL=$(gcloud run services describe "$SERVICE" \
        --region "$REGION" \
        --format="value(status.url)" \
        --project="$PROJECT_ID")
    
    if [ -n "$URL" ]; then
        echo -e "\n${GREEN}═══════════════════════════════════════${NC}"
        echo -e "${GREEN}✅ 배포 완료!${NC}"
        echo -e "${GREEN}═══════════════════════════════════════${NC}"
        echo -e "${CYAN}배포 URL:${NC} ${BLUE}$URL${NC}"
        echo -e "${GREEN}═══════════════════════════════════════${NC}\n"
        
        # 브라우저에서 열기 (선택사항)
        read -p "브라우저에서 열까요? [Y/n]: " OPEN_BROWSER
        if [[ ! "$OPEN_BROWSER" =~ ^[Nn]$ ]]; then
            if command -v open &> /dev/null; then
                open "$URL"  # macOS
            elif command -v xdg-open &> /dev/null; then
                xdg-open "$URL"  # Linux
            fi
        fi
    else
        echo -e "${RED}❌ 배포 URL을 가져올 수 없습니다.${NC}"
    fi
}

# 최종 요약
show_summary() {
    echo -e "\n${CYAN}[9/9] 배포 요약${NC}"
    echo -e "  프로젝트 ID: ${GREEN}$PROJECT_ID${NC}"
    echo -e "  리전: ${GREEN}$REGION${NC}"
    echo -e "  서비스: ${GREEN}$SERVICE${NC}"
    echo -e "  저장소: ${GREEN}$REPO${NC}"
    echo -e "\n${GREEN}✅ 모든 배포 작업이 완료되었습니다!${NC}\n"
}

# 메인 실행
main() {
    echo -e "${CYAN}"
    echo "╔════════════════════════════════════════╗"
    echo "║   SmartBrief 간편 배포 스크립트      ║"
    echo "╚════════════════════════════════════════╝"
    echo -e "${NC}\n"
    
    # 설정 로드
    load_config
    
    # 필수 값 확인
    if [ -z "$GEMINI_API_KEY" ]; then
        echo -e "${RED}❌ GEMINI_API_KEY가 설정되지 않았습니다.${NC}"
        exit 1
    fi
    
    # 실행 단계
    check_requirements
    check_login
    create_project_if_needed
    enable_apis
    create_repository
    build_and_push
    deploy_to_cloud_run
    set_permissions
    get_deployment_url
    show_summary
}

# 스크립트 실행
main
