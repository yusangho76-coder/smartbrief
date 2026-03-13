#!/bin/bash
# Flask 앱을 터미널에서 실행하는 스크립트

# 현재 디렉토리로 이동
cd "$(dirname "$0")"

# Python 가상환경 활성화 (있는 경우)
if [ -d "venv" ]; then
    source venv/bin/activate
elif [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Flask 앱 실행
echo "🚀 Flask 앱을 시작합니다..."
echo "📍 종료하려면 Ctrl+C를 누르세요"
echo ""

python3 app.py

