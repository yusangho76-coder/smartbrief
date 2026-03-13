#!/bin/bash

# =======================================================================
# SmartNOTAM / SmartBriefier - GCP 원클릭 부트스트랩 & 배포 스크립트 (macOS/Linux)
# -----------------------------------------------------------------------
# 대상:
#   - Google 계정만 막 만들고
#   - 결제 계정도 하나 만들어 둔 사용자
#   가 이 스크립트 하나만 실행해서
#     1) GCP 프로젝트 생성/연결
#     2) 필수 API 활성화
#     3) Artifact Registry 생성
#     4) Cloud Run 배포
#   까지 자동으로 끝내는 것을 목표로 합니다.
#
# 전제:
#   - gcloud SDK 설치 및 'gcloud init' 한 번은 해 둔 상태 (로그인 가능)
#   - 이 스크립트는 repo 루트의 `deploy/` 폴더 안에서 실행
#     예) cd deploy && bash deploy_mac_bootstrap.sh
#
# 이후 업데이트:
#   - 같은 프로젝트에 대해 재배포할 때는
#       - 이 스크립트를 다시 실행하거나
#       - GitHub Actions(GCR 배포 워크플로)에서 자동 배포 가능
# =======================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# ───────────────────── 색상 정의 ─────────────────────
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${CYAN}=== SmartNOTAM GCP 부트스트랩 & 배포 ===${NC}"
echo -e "프로젝트 루트: ${GREEN}$PROJECT_ROOT${NC}"
echo ""

# ───────────────────── 사용자 입력 받기 ─────────────────────
read -rp "새로 만들거나 사용할 GCP 프로젝트 ID를 입력하세요 (예: smartnotam-123456): " PROJECT_ID
if [[ -z "$PROJECT_ID" ]]; then
  echo -e "${RED}❌ PROJECT_ID가 비어 있습니다.${NC}"
  exit 1
fi

read -rp "Cloud Run 리전 (기본: asia-northeast3, 그냥 Enter): " REGION
REGION=${REGION:-asia-northeast3}

read -rp "Cloud Run 서비스 이름 (기본: smartnotam3, 그냥 Enter): " SERVICE
SERVICE=${SERVICE:-smartnotam3}

read -rp "Artifact Registry Docker 리포지토리 이름 (기본: smartnotam, 그냥 Enter): " REPO
REPO=${REPO:-smartnotam}

echo ""
echo -e "${CYAN}=== 입력값 확인 ===${NC}"
echo -e "  프로젝트 ID : ${GREEN}$PROJECT_ID${NC}"
echo -e "  리전        : ${GREEN}$REGION${NC}"
echo -e "  서비스명    : ${GREEN}$SERVICE${NC}"
echo -e "  리포지토리  : ${GREEN}$REPO${NC}"
echo ""

read -rp "위 설정으로 진행할까요? (y/N): " CONFIRM
if [[ "$CONFIRM" != "y" && "$CONFIRM" != "Y" ]]; then
  echo -e "${YELLOW}배포를 취소했습니다.${NC}"
  exit 0
fi

# ───────────────────── gcloud 로그인 및 기본 설정 ─────────────────────
echo -e "${CYAN}[1/6] gcloud 로그인 및 기본 설정 확인${NC}"
ACCOUNT=$(gcloud config get-value account 2>/dev/null || echo "")
if [[ -z "$ACCOUNT" ]]; then
  echo -e "${YELLOW}gcloud 계정이 설정되어 있지 않습니다. 로그인합니다...${NC}"
  gcloud auth login
  ACCOUNT=$(gcloud config get-value account 2>/dev/null || echo "")
fi
echo -e "  사용 계정: ${GREEN}${ACCOUNT:-'(없음)'}${NC}"

echo -e "  gcloud 프로젝트를 ${GREEN}$PROJECT_ID${NC} 로 설정합니다."
gcloud config set project "$PROJECT_ID" >/dev/null 2>&1 || true

# ───────────────────── 프로젝트 존재 여부 확인 & 생성 ─────────────────────
echo -e "${CYAN}[2/6] GCP 프로젝트 준비${NC}"
if gcloud projects describe "$PROJECT_ID" >/dev/null 2>&1; then
  echo -e "  ${GREEN}기존 프로젝트를 사용합니다:${NC} $PROJECT_ID"
else
  echo -e "  ${YELLOW}프로젝트가 없습니다. 새 프로젝트를 생성합니다.${NC}"
  read -rp "  프로젝트 이름(콘솔에 표시될 이름, 기본: SmartNOTAM): " PROJECT_NAME
  PROJECT_NAME=${PROJECT_NAME:-SmartNOTAM}

  gcloud projects create "$PROJECT_ID" \
    --name="$PROJECT_NAME"
  echo -e "  ${GREEN}프로젝트 생성 완료:${NC} $PROJECT_ID"

  echo ""
  echo -e "  ${CYAN}결제 계정 연결이 필요합니다.${NC}"
  echo -e "  사용 가능한 결제 계정을 먼저 확인합니다."
  gcloud beta billing accounts list
  echo ""
  read -rp "  연결할 결제 계정 ID를 입력하세요 (예: 0X0X0X-0X0X0X-0X0X0X): " BILLING_ID
  if [[ -z "$BILLING_ID" ]]; then
    echo -e "${RED}❌ BILLING_ID가 비어 있습니다. 콘솔에서 수동으로 결제 계정 연결 후 다시 실행하세요.${NC}"
    exit 1
  fi

  gcloud beta billing projects link "$PROJECT_ID" \
    --billing-account="$BILLING_ID"
  echo -e "  ${GREEN}결제 계정 연결 완료${NC}"
fi

gcloud config set project "$PROJECT_ID" >/dev/null
export CLOUDSDK_CORE_PROJECT="$PROJECT_ID"

# ───────────────────── 필수 API 활성화 ─────────────────────
echo -e "${CYAN}[3/6] 필수 API 활성화 (Run / Artifact Registry / Cloud Build)${NC}"
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com
echo -e "  ${GREEN}필수 API 활성화 완료${NC}"

# ───────────────────── Artifact Registry 리포지토리 생성 ─────────────────────
echo -e "${CYAN}[4/6] Artifact Registry Docker 리포지토리 준비${NC}"
if gcloud artifacts repositories describe "$REPO" \
     --location="$REGION" >/dev/null 2>&1; then
  echo -e "  ${GREEN}기존 리포지토리를 사용합니다:${NC} $REPO ($REGION)"
else
  gcloud artifacts repositories create "$REPO" \
    --repository-format=docker \
    --location="$REGION" \
    --description="SmartNOTAM Docker images"
  echo -e "  ${GREEN}리포지토리 생성 완료:${NC} $REPO ($REGION)"
fi

IMAGE_URI="$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/$SERVICE"

# ───────────────────── 컨테이너 빌드 & 푸시 ─────────────────────
echo -e "${CYAN}[5/6] Cloud Build를 이용한 컨테이너 빌드 & 푸시${NC}"
echo -e "  이미지: ${GREEN}$IMAGE_URI${NC}"

gcloud builds submit "$PROJECT_ROOT" \
  --tag "$IMAGE_URI"

echo -e "  ${GREEN}이미지 빌드 & 푸시 완료${NC}"

# ───────────────────── Cloud Run 배포 ─────────────────────
echo -e "${CYAN}[6/6] Cloud Run 배포${NC}"

gcloud run deploy "$SERVICE" \
  --image="$IMAGE_URI" \
  --platform=managed \
  --region="$REGION" \
  --allow-unauthenticated \
  --port=5005

SERVICE_URL=$(gcloud run services describe "$SERVICE" \
  --region="$REGION" \
  --format="value(status.url)")

echo ""
echo -e "${GREEN}✅ 배포 완료!${NC}"
echo -e "  Cloud Run URL: ${CYAN}$SERVICE_URL${NC}"
echo ""
echo -e "이후에는:"
echo -e "  - 같은 프로젝트에서 로컬 재배포: ${YELLOW}bash deploy/deploy_mac_bootstrap.sh${NC} 다시 실행"
echo -e "  - GitHub Actions를 이용한 자동 배포도 구성할 수 있습니다."
echo ""

