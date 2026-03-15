#!/bin/bash
# git add + commit + push 한 번에 실행 (smartbrief 업데이트용)
# 사용: ./git_push.sh [커밋 메시지]
# 예:   ./git_push.sh "REFILE 파싱 수정"
#      ./git_push.sh   (메시지 생략 시 "Update" 사용)

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

MSG="${1:-Update}"
git add .
git status
echo ""
read -rp "위 변경으로 커밋 후 push 할까요? (y/N): " CONFIRM
if [[ "$CONFIRM" != "y" && "$CONFIRM" != "Y" ]]; then
  echo "취소했습니다."
  exit 0
fi
git commit -m "$MSG"
git push
echo ""
echo "✅ push 완료: $(git remote get-url origin)"
if [ -f "$PROJECT_ROOT/.github/workflows/deploy-cloud-run.yml" ]; then
  echo "   → main 브랜치면 GitHub Actions에서 Cloud Run 자동 배포가 진행됩니다."
  echo "   → 확인: https://github.com/rokafpilot/smartbrief/actions"
fi
