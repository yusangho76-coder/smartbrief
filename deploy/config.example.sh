#!/bin/bash
# ===== 배포 설정 파일 예시 =====
# 이 파일을 복사하여 deploy/config.sh로 만들고 값을 입력하세요
# cp deploy/config.example.sh deploy/config.sh
# 그리고 아래 값들을 수정하세요

# Google Cloud 프로젝트 ID (없으면 자동 생성)
PROJECT_ID=""

# Google Cloud 리전 (서울 권장)
REGION="asia-northeast3"

# Artifact Registry 저장소명 (없으면 자동 생성)
REPO="smartnotam-repo"

# Cloud Run 서비스명
SERVICE="smartnotam"

# Gemini API 키 (필수)
GEMINI_API_KEY=""

# 접근 권한을 부여할 이메일 (선택사항, 비워두면 현재 로그인한 계정 사용)
GRANTEE_EMAIL=""
