#!/bin/bash
# 임시 파일 정리 스크립트

echo "🧹 임시 파일 정리 시작..."

# Python 캐시 파일 삭제
echo "📦 Python 캐시 파일 (__pycache__) 삭제 중..."
find . -type d -name "__pycache__" -not -path "./.venv/*" -not -path "./ATSplanvalidation/.venv/*" -exec rm -rf {} + 2>/dev/null
find . -type f -name "*.pyc" -not -path "./.venv/*" -not -path "./ATSplanvalidation/.venv/*" -delete 2>/dev/null
find . -type f -name "*.pyo" -not -path "./.venv/*" -not -path "./ATSplanvalidation/.venv/*" -delete 2>/dev/null
echo "✅ Python 캐시 파일 삭제 완료"

# macOS 시스템 파일 삭제
echo "🍎 macOS 시스템 파일 (.DS_Store) 삭제 중..."
find . -name ".DS_Store" -type f -delete 2>/dev/null
echo "✅ .DS_Store 파일 삭제 완료"

# 백업 파일 삭제
echo "📋 백업 파일 삭제 중..."
find . -name "*.backup.*" -type f -delete 2>/dev/null
find . -name "cloudbuild.yaml.backup.*" -type f -delete 2>/dev/null
echo "✅ 백업 파일 삭제 완료"

# 로그 파일 삭제 (선택사항)
echo "📝 로그 파일 확인 중..."
if [ -f "./ATSplanvalidation/logs/streamlit.log" ]; then
    echo "  - streamlit.log 발견 (삭제하려면 주석 해제)"
    # rm -f ./ATSplanvalidation/logs/streamlit.log
fi

echo ""
echo "✅ 임시 파일 정리 완료!"
echo ""
echo "📊 남은 용량 확인:"
du -sh temp uploads saved_results 2>/dev/null
