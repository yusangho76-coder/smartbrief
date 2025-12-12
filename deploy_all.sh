#!/bin/bash

# ===== Smart NOTAM 전체 배포 스크립트 =====
# Streamlit 앱과 Flask 앱을 순차적으로 배포합니다.

set -e  # 오류 발생 시 스크립트 중단

# 스크립트가 있는 디렉토리 (프로젝트 루트)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 색상 정의
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${CYAN}=== Smart NOTAM 전체 배포 시작 ===${NC}\n"

# 1단계: Streamlit 앱 배포
echo -e "${CYAN}[1/2] Streamlit 앱 (ATS FPL Validator) 배포${NC}"
if [ -f "ATSplanvalidation/deploy_streamlit.sh" ]; then
    cd ATSplanvalidation
    chmod +x deploy_streamlit.sh
    ./deploy_streamlit.sh
    cd ..
    echo -e "${GREEN}✅ Streamlit 앱 배포 완료${NC}\n"
else
    echo -e "${RED}❌ Streamlit 배포 스크립트를 찾을 수 없습니다: ATSplanvalidation/deploy_streamlit.sh${NC}"
    exit 1
fi

# 2단계: Flask 앱 배포
echo -e "${CYAN}[2/2] Flask 앱 (Smart NOTAM) 배포${NC}"
if [ -f "deploy/deploy_mac yhj.sh" ]; then
    cd deploy
    chmod +x "deploy_mac yhj.sh"
    ./deploy_mac\ yhj.sh
    cd ..
    echo -e "${GREEN}✅ Flask 앱 배포 완료${NC}\n"
else
    echo -e "${RED}❌ Flask 배포 스크립트를 찾을 수 없습니다: deploy/deploy_mac yhj.sh${NC}"
    exit 1
fi

echo -e "${GREEN}✅ 전체 배포 완료!${NC}"
echo -e "\n${CYAN}=== 배포 완료 정보 ===${NC}"

# 배포된 서비스 URL 확인
PROJECT_ID="smartnotam-476803"
REGION="asia-northeast3"

echo -e "\n${CYAN}Streamlit 앱 URL:${NC}"
STREAMLIT_URL=$(gcloud run services describe ats-fpl-validator \
  --region=$REGION \
  --format="value(status.url)" \
  --project=$PROJECT_ID 2>/dev/null || echo "확인 실패")
echo -e "${GREEN}$STREAMLIT_URL${NC}"

echo -e "\n${CYAN}Flask 앱 URL:${NC}"
FLASK_URL=$(gcloud run services describe smartnotam \
  --region=$REGION \
  --format="value(status.url)" \
  --project=$PROJECT_ID 2>/dev/null || echo "확인 실패")
echo -e "${GREEN}$FLASK_URL${NC}"

echo -e "\n${GREEN}✅ 모든 배포가 완료되었습니다!${NC}"

