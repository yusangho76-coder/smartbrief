#!/bin/bash

# DocPack Route Validator 실행 스크립트

# 현재 스크립트의 디렉토리로 이동
cd "$(dirname "$0")"

# 가상환경 활성화
if [ -d ".venv" ]; then
    source .venv/bin/activate
else
    echo "가상환경을 찾을 수 없습니다. 먼저 가상환경을 생성하세요."
    exit 1
fi

# Streamlit 앱 실행
streamlit run app.py

