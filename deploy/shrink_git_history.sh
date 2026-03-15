#!/usr/bin/env bash
# .git 히스토리에서 .herbie 제거 (용량 축소)
# 사용법: 프로젝트 루트에서 실행
#   cd "/Users/sunghyunkim/Documents/Documents - Sunghyun/SmartBriefier_GCR_James (1)"
#   bash deploy/shrink_git_history.sh

if [ ! -d .git ]; then
  echo "오류: 프로젝트 루트(.git 있는 폴더)에서 실행하세요."
  echo "  cd \"\$(dirname \"\$0\")/..\" && bash deploy/shrink_git_history.sh"
  exit 1
fi

echo "=== .git 히스토리에서 .herbie 제거 ==="
echo "현재 .git 크기: $(du -sh .git 2>/dev/null | cut -f1)"
echo ""

if [ -f .git/index.lock ]; then
  echo "오류: Git 작업이 진행 중입니다. push/merge가 끝난 뒤 다시 실행하세요."
  exit 1
fi

if command -v git-filter-repo >/dev/null 2>&1; then
  echo "git-filter-repo 사용하여 .herbie 제거 중..."
  git filter-repo --path .herbie --invert-paths --force
  git reflog expire --expire=now --all
  git gc --prune=now --aggressive
  echo ""
  echo "완료. .git 크기: $(du -sh .git 2>/dev/null | cut -f1)"
  echo "다음: git remote add origin git@github.com:rokafpilot/smartbrief.git"
  echo "      git push --force origin main"
  exit 0
fi

echo "git-filter-repo가 없어 filter-branch로 진행합니다 (오래 걸릴 수 있음)."
echo "빠르게 하려면: pip install git-filter-repo"
read -r -p "계속할까요? (y/N): " CONFIRM
if [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ]; then
  echo "취소."
  exit 0
fi

git filter-branch --force --index-filter 'git rm -rf --cached --ignore-unmatch .herbie 2>/dev/null || true' --prune-empty --tag-name-filter cat -- --all
rm -rf .git/refs/original/
git reflog expire --expire=now --all
git gc --prune=now --aggressive

echo ""
echo "완료. .git 크기: $(du -sh .git 2>/dev/null | cut -f1)"
echo "다음: git push --force origin main"
