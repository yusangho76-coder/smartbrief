@echo off
chcp 65001 >nul
title SmartBrief - 대한항공 NOTAM 처리 시스템

echo ========================================
echo    SmartBrief - 대한항공 NOTAM 처리 시스템
echo ========================================
echo.

:: 현재 스크립트의 디렉토리로 이동
cd /d "%~dp0"

:: Python 설치 확인
echo [1/4] Python 설치 확인 중...
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python이 설치되지 않았습니다.
    echo    Python 3.8 이상을 설치해주세요: https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)
echo ✅ Python 설치 확인됨

:: 가상환경 확인 및 생성
echo.
echo [2/4] 가상환경 설정 중...
if not exist "venv" (
    echo 가상환경 생성 중...
    python -m venv venv
    if errorlevel 1 (
        echo ❌ 가상환경 생성 실패
        pause
        exit /b 1
    )
    echo ✅ 가상환경 생성 완료
) else (
    echo ✅ 기존 가상환경 발견
)

:: 가상환경 활성화
echo 가상환경 활성화 중...
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo ❌ 가상환경 활성화 실패
    pause
    exit /b 1
)
echo ✅ 가상환경 활성화 완료

:: 패키지 설치
echo.
echo [3/4] 필요한 패키지 설치 중...
echo 이 과정은 처음 실행 시 몇 분이 소요될 수 있습니다...
pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
    echo ❌ 패키지 설치 실패
    echo    인터넷 연결을 확인하고 다시 시도해주세요.
    pause
    exit /b 1
)
echo ✅ 패키지 설치 완료

:: 환경 변수 파일 확인
echo.
echo [4/4] 환경 설정 확인 중...
if not exist ".env" (
    echo .env 파일이 없습니다. 기본 설정으로 실행합니다.
    echo.
    echo ⚠️  AI 번역 기능을 사용하려면 .env 파일에 다음을 추가하세요:
    echo    GEMINI_API_KEY=your_api_key_here
    echo    GOOGLE_MAPS_API_KEY=your_maps_api_key_here
    echo.
) else (
    echo ✅ 환경 설정 파일 확인됨
)

:: 애플리케이션 실행
echo.
echo ========================================
echo    SmartBrief 애플리케이션 시작
echo ========================================
echo.
echo 🌐 웹 브라우저에서 http://localhost:5005 로 접속하세요
echo.
echo ⏹️  종료하려면 Ctrl+C를 누르세요
echo.

:: Flask 애플리케이션 실행
python app.py

:: 오류 발생 시 일시정지
if errorlevel 1 (
    echo.
    echo ❌ 애플리케이션 실행 중 오류가 발생했습니다.
    echo    오류 내용을 확인하고 다시 시도해주세요.
    echo.
    pause
)

:: 가상환경 비활성화
call venv\Scripts\deactivate.bat

echo.
echo 애플리케이션이 종료되었습니다.
pause
