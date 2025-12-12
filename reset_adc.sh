#!/bin/bash

# ===== ADC (Application Default Credentials) 완전 초기화 스크립트 =====
# 이 스크립트는 ADC를 완전히 초기화하고 새로 설정합니다.

set -e

# 색상 정의
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${CYAN}=== ADC 완전 초기화 시작 ===${NC}\n"

# 프로젝트 ID 가져오기 (deploy_mac.sh에서)
DEPLOY_SCRIPT="$(dirname "$0")/deploy_mac.sh"
if [ -f "$DEPLOY_SCRIPT" ]; then
    PROJECT_ID=$(grep -E '^PROJECT_ID=' "$DEPLOY_SCRIPT" | grep -v '^#' | head -1 | cut -d'"' -f2)
    if [ -z "$PROJECT_ID" ]; then
        echo -e "${RED}❌ 프로젝트 ID를 찾을 수 없습니다.${NC}"
        read -p "프로젝트 ID를 입력하세요: " PROJECT_ID
    fi
else
    read -p "프로젝트 ID를 입력하세요: " PROJECT_ID
fi

echo -e "대상 프로젝트: ${GREEN}$PROJECT_ID${NC}\n"

# ADC 파일 경로
ADC_FILE="$HOME/.config/gcloud/application_default_credentials.json"

# 현재 ADC 상태 확인
echo -e "${CYAN}[1/4] 현재 ADC 상태 확인${NC}"
if [ -f "$ADC_FILE" ]; then
    echo -e "  ADC 파일 존재: ${YELLOW}$ADC_FILE${NC}"
    CURRENT_QUOTA=$(grep -o '"quota_project_id":"[^"]*"' "$ADC_FILE" 2>/dev/null | cut -d'"' -f4 || echo "")
    if [ -n "$CURRENT_QUOTA" ]; then
        echo -e "  현재 quota project: ${YELLOW}$CURRENT_QUOTA${NC}"
    else
        echo -e "  quota project: ${YELLOW}설정되지 않음${NC}"
    fi
else
    echo -e "  ADC 파일: ${GREEN}존재하지 않음${NC}"
fi

# GOOGLE_APPLICATION_CREDENTIALS 환경변수 확인
if [ -n "$GOOGLE_APPLICATION_CREDENTIALS" ]; then
    echo -e "  ${YELLOW}⚠️  GOOGLE_APPLICATION_CREDENTIALS 환경변수 발견:${NC}"
    echo -e "    ${YELLOW}$GOOGLE_APPLICATION_CREDENTIALS${NC}"
    echo -e "  ${YELLOW}이 환경변수가 설정되어 있으면 ADC 파일보다 우선순위가 높습니다.${NC}"
fi

echo ""

# ADC 완전 초기화
echo -e "${CYAN}[2/4] ADC 완전 초기화${NC}"

# ADC 파일이 존재하면 백업 후 삭제 (대화형 프롬프트 방지)
if [ -f "$ADC_FILE" ]; then
    BACKUP_FILE="${ADC_FILE}.backup.$(date +%Y%m%d_%H%M%S)"
    echo -e "  ${YELLOW}ADC 파일 백업 중: $BACKUP_FILE${NC}"
    mv "$ADC_FILE" "$BACKUP_FILE" 2>/dev/null || true
    
    # 백업 후에도 파일이 남아있으면 강제 삭제
    if [ -f "$ADC_FILE" ]; then
        echo -e "  ${YELLOW}ADC 파일 강제 삭제 중...${NC}"
        rm -f "$ADC_FILE" 2>/dev/null || true
    fi
    
    if [ ! -f "$ADC_FILE" ]; then
        echo -e "  ${GREEN}✅ ADC 파일 삭제 완료${NC}"
    else
        echo -e "  ${RED}❌ ADC 파일 삭제 실패 (권한 문제일 수 있음)${NC}"
    fi
    
    # gcloud 명령어로도 취소 시도 (--quiet로 대화형 프롬프트 방지)
    gcloud auth application-default revoke --quiet 2>/dev/null || true
else
    echo -e "  ${GREEN}✅ ADC 파일이 이미 없습니다${NC}"
    # 파일이 없어도 gcloud 명령어로 취소 시도
    gcloud auth application-default revoke --quiet 2>/dev/null || true
fi

echo ""

# 새로운 ADC 설정
echo -e "${CYAN}[3/4] 새로운 ADC 설정${NC}"
echo -e "  ${YELLOW}프로젝트: $PROJECT_ID${NC}"
echo -e "  ${YELLOW}브라우저에서 로그인하세요...${NC}"

gcloud auth application-default login --project="$PROJECT_ID" || {
    echo -e "${RED}❌ ADC 로그인 실패${NC}"
    exit 1
}

# ADC quota project 설정
echo -e "  ${YELLOW}ADC quota project 설정 중...${NC}"
gcloud auth application-default set-quota-project "$PROJECT_ID" 2>&1 || {
    echo -e "  ${YELLOW}⚠️  quota project 설정 실패 (계속 진행)${NC}"
}

echo ""

# 최종 확인
echo -e "${CYAN}[4/4] 최종 확인${NC}"
if [ -f "$ADC_FILE" ]; then
    NEW_QUOTA=$(grep -o '"quota_project_id":"[^"]*"' "$ADC_FILE" 2>/dev/null | cut -d'"' -f4 || echo "")
    if [ "$NEW_QUOTA" = "$PROJECT_ID" ]; then
        echo -e "  ${GREEN}✅ ADC 설정 완료${NC}"
        echo -e "  ${GREEN}  파일 위치: $ADC_FILE${NC}"
        echo -e "  ${GREEN}  quota project: $NEW_QUOTA${NC}"
    else
        echo -e "  ${YELLOW}⚠️  ADC 파일은 생성되었지만 quota project가 다릅니다${NC}"
        echo -e "  ${YELLOW}  quota project: ${NEW_QUOTA:-설정되지 않음}${NC}"
    fi
else
    echo -e "  ${RED}❌ ADC 파일이 생성되지 않았습니다${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}✅ ADC 초기화 및 설정 완료!${NC}\n"

