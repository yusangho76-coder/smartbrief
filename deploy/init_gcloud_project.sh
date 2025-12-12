#!/bin/bash

# ===== gcloud 프로젝트 초기화 스크립트 =====
# 이 스크립트는 gcloud 설정을 완전히 초기화하고 올바른 프로젝트로 설정합니다.

set -e  # 오류 발생 시 스크립트 중단

# 색상 정의
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${CYAN}=== gcloud 프로젝트 초기화 시작 ===${NC}\n"

# deploy_mac.sh에서 설정값 자동 추출
DEPLOY_SCRIPT="$(dirname "$0")/deploy_mac.sh"
if [ -f "$DEPLOY_SCRIPT" ]; then
    # 주석 처리되지 않은 PROJECT_ID 추출
    PROJECT_ID=$(grep -E '^PROJECT_ID=' "$DEPLOY_SCRIPT" | grep -v '^#' | head -1 | cut -d'"' -f2)
    # GRANTEE에서 이메일 추출
    GRANTEE=$(grep -E '^GRANTEE=' "$DEPLOY_SCRIPT" | grep -v '^#' | head -1 | cut -d'"' -f2)
    EXPECTED_EMAIL=$(echo "$GRANTEE" | sed 's/user://')
    
    if [ -z "$PROJECT_ID" ] || [ -z "$EXPECTED_EMAIL" ]; then
        echo -e "${RED}❌ deploy_mac.sh에서 설정값을 찾을 수 없습니다.${NC}"
        echo -e "${YELLOW}수동으로 설정하세요.${NC}"
        exit 1
    fi
    
    echo -e "${GREEN}deploy_mac.sh에서 설정값을 자동으로 읽었습니다:${NC}"
    echo -e "  프로젝트 ID: ${GREEN}$PROJECT_ID${NC}"
    echo -e "  예상 계정: ${GREEN}$EXPECTED_EMAIL${NC}"
    echo ""
else
    echo -e "${RED}❌ deploy_mac.sh를 찾을 수 없습니다: $DEPLOY_SCRIPT${NC}"
    echo -e "${YELLOW}수동으로 설정하세요.${NC}"
    exit 1
fi

echo -e "${CYAN}[1/5] 현재 gcloud 설정 확인${NC}"
CURRENT_PROJECT=$(gcloud config get-value project 2>/dev/null || echo "설정 없음")
CURRENT_ACCOUNT=$(gcloud config get-value account 2>/dev/null || echo "설정 없음")
CURRENT_CONFIG=$(gcloud config configurations list --filter="is_active:true" --format="value(name)" 2>/dev/null || echo "default")

echo -e "  현재 프로젝트: ${YELLOW}$CURRENT_PROJECT${NC}"
echo -e "  현재 계정: ${YELLOW}$CURRENT_ACCOUNT${NC}"
echo -e "  현재 configuration: ${YELLOW}$CURRENT_CONFIG${NC}"
echo ""

# 현재 설정이 목표와 일치하는지 확인
NEEDS_RESET=false
if [ "$CURRENT_PROJECT" != "$PROJECT_ID" ]; then
    echo -e "${YELLOW}⚠️  프로젝트 불일치: $CURRENT_PROJECT → $PROJECT_ID${NC}"
    NEEDS_RESET=true
fi

if [ "$CURRENT_ACCOUNT" != "$EXPECTED_EMAIL" ]; then
    echo -e "${YELLOW}⚠️  계정 불일치: $CURRENT_ACCOUNT → $EXPECTED_EMAIL${NC}"
    NEEDS_RESET=true
fi

if [ "$NEEDS_RESET" = false ]; then
    echo -e "${GREEN}✅ 현재 설정이 올바릅니다. 초기화를 건너뜁니다.${NC}\n"
    exit 0
fi

echo -e "${CYAN}[2/5] gcloud configuration 초기화${NC}"

# 모든 configuration 확인
CONFIGS=$(gcloud config configurations list --format="value(name)" 2>/dev/null || echo "default")
echo -e "  발견된 configurations: ${YELLOW}$CONFIGS${NC}"

# default configuration으로 전환
echo -e "  default configuration으로 전환 중...${NC}"
gcloud config configurations activate default 2>/dev/null || {
    echo -e "  ${YELLOW}default configuration이 없어 생성 중...${NC}"
    gcloud config configurations create default 2>/dev/null || true
}

# 프로젝트 설정 초기화
echo -e "  프로젝트 설정 초기화 중...${NC}"
gcloud config unset project 2>/dev/null || true
gcloud config unset core/project 2>/dev/null || true

# 계정 설정 초기화 (로그아웃)
echo -e "  기존 인증 정보 초기화 중...${NC}"
gcloud auth revoke --all 2>/dev/null || true

# ADC (Application Default Credentials) 초기화
echo -e "  ADC 초기화 중...${NC}"
ADC_FILE="$HOME/.config/gcloud/application_default_credentials.json"

# ADC 파일이 존재하면 백업 후 삭제 (대화형 프롬프트 방지)
if [ -f "$ADC_FILE" ]; then
    echo -e "  ${YELLOW}기존 ADC 파일 백업 후 삭제 중...${NC}"
    BACKUP_FILE="${ADC_FILE}.backup.$(date +%Y%m%d_%H%M%S)"
    mv "$ADC_FILE" "$BACKUP_FILE" 2>/dev/null || true
    # 백업 후에도 파일이 남아있으면 강제 삭제
    [ -f "$ADC_FILE" ] && rm -f "$ADC_FILE" 2>/dev/null || true
    echo -e "  ${GREEN}✅ ADC 파일 삭제 완료${NC}"
else
    # ADC 파일이 없어도 gcloud 명령어로 취소 시도 (--quiet로 대화형 프롬프트 방지)
    gcloud auth application-default revoke --quiet 2>/dev/null || true
fi

# 방법 3: ADC 관련 환경변수도 확인
if [ -n "$GOOGLE_APPLICATION_CREDENTIALS" ]; then
    echo -e "  ${YELLOW}GOOGLE_APPLICATION_CREDENTIALS 환경변수 발견: $GOOGLE_APPLICATION_CREDENTIALS${NC}"
    echo -e "  ${YELLOW}이 환경변수는 ADC보다 우선순위가 높습니다.${NC}"
fi

# 환경변수 초기화
unset CLOUDSDK_CORE_PROJECT
unset GOOGLE_APPLICATION_CREDENTIALS

echo -e "${GREEN}✅ gcloud 설정 초기화 완료${NC}\n"

echo -e "${CYAN}[3/5] 새로운 계정으로 로그인${NC}"
echo -e "  예상 계정: ${GREEN}$EXPECTED_EMAIL${NC}"
echo -e "  ${YELLOW}브라우저에서 로그인하세요...${NC}"
gcloud auth login

# 로그인 후 계정 확인
AFTER_LOGIN_ACCOUNT=$(gcloud config get-value account 2>/dev/null || echo "")
echo -e "  로그인된 계정: ${GREEN}$AFTER_LOGIN_ACCOUNT${NC}"

if [ "$AFTER_LOGIN_ACCOUNT" != "$EXPECTED_EMAIL" ]; then
    echo -e "${YELLOW}⚠️  경고: 로그인한 계정($AFTER_LOGIN_ACCOUNT)이 예상 계정($EXPECTED_EMAIL)과 다릅니다.${NC}"
    echo -e "${YELLOW}계속 진행합니다...${NC}"
fi

echo -e "${GREEN}✅ 로그인 완료${NC}\n"

echo -e "${CYAN}[4/5] 프로젝트 설정${NC}"
echo -e "  목표 프로젝트: ${GREEN}$PROJECT_ID${NC}"

# 프로젝트 설정
gcloud config set project "$PROJECT_ID" 2>&1 || {
    echo -e "${RED}❌ 프로젝트 설정 실패: $PROJECT_ID${NC}"
    echo -e "${YELLOW}프로젝트가 존재하는지 확인하세요:${NC}"
    echo -e "  ${CYAN}gcloud projects list${NC}"
    exit 1
}

# 환경변수 설정
export CLOUDSDK_CORE_PROJECT="$PROJECT_ID"

# 프로젝트 확인
VERIFIED_PROJECT=$(gcloud config get-value project 2>/dev/null)
if [ "$VERIFIED_PROJECT" = "$PROJECT_ID" ]; then
    echo -e "${GREEN}✅ 프로젝트 설정 확인: $PROJECT_ID${NC}"
else
    echo -e "${RED}❌ 프로젝트 설정 확인 실패: $VERIFIED_PROJECT${NC}"
    exit 1
fi

echo -e "${GREEN}✅ 프로젝트 설정 완료${NC}\n"

# ADC 설정은 배포 스크립트에서 사용하지 않으므로 스킵
# (배포 완료 후 ADC를 삭제하므로 초기화 시 설정할 필요 없음)
echo -e "${CYAN}[5/5] ADC 설정${NC}"
echo -e "  ${YELLOW}ADC 설정을 건너뜁니다 (배포 스크립트에서 사용하지 않음)${NC}"
echo -e "${GREEN}✅ ADC 설정 스킵 완료${NC}\n"

# 최종 확인
echo -e "${CYAN}=== 최종 설정 확인 ===${NC}"
FINAL_PROJECT=$(gcloud config get-value project 2>/dev/null)
FINAL_ACCOUNT=$(gcloud config get-value account 2>/dev/null)
FINAL_ENV=$CLOUDSDK_CORE_PROJECT

echo -e "  gcloud 프로젝트: ${GREEN}$FINAL_PROJECT${NC}"
echo -e "  gcloud 계정: ${GREEN}$FINAL_ACCOUNT${NC}"
echo -e "  환경변수: ${GREEN}$FINAL_ENV${NC}"

if [ "$FINAL_PROJECT" = "$PROJECT_ID" ]; then
    echo -e "\n${GREEN}✅ gcloud 프로젝트 초기화 완료!${NC}"
    echo -e "${GREEN}이제 deploy_mac.sh를 실행할 수 있습니다.${NC}\n"
    exit 0
else
    echo -e "\n${RED}❌ 초기화 실패: 프로젝트가 올바르게 설정되지 않았습니다.${NC}"
    exit 1
fi

