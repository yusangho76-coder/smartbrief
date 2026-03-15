@echo off
REM git add + commit + push 한 번에 실행 (smartbrief 업데이트용)
REM 사용: git_push.bat [커밋 메시지]
REM 예:   git_push.bat "REFILE 파싱 수정"
REM       git_push.bat   (메시지 생략 시 Update 사용)

cd /d "%~dp0\.."
if "%1"=="" (set "MSG=Update") else (set "MSG=%*")
git add .
git status
echo.
set /p CONFIRM="위 변경으로 커밋 후 push 할까요? (y/N): "
if /i not "%CONFIRM%"=="y" (echo 취소했습니다. & exit /b 0)
git commit -m "%MSG%"
git push
echo.
echo push 완료.
pause
