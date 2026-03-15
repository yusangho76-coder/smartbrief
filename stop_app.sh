#!/bin/bash
# SmartBrief 앱 종료 스크립트

PORT=5005
PID_FILE=".smartbrief.pid"

echo "🛑 SmartBrief 앱을 종료합니다..."

# 방법 1: PID 파일에서 프로세스 종료
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "📌 PID 파일에서 프로세스 찾음: $PID"
        kill -TERM "$PID" 2>/dev/null
        sleep 2
        # 여전히 실행 중이면 강제 종료
        if ps -p "$PID" > /dev/null 2>&1; then
            echo "⚠️  프로세스가 종료되지 않아 강제 종료합니다..."
            kill -9 "$PID" 2>/dev/null
        fi
        rm -f "$PID_FILE"
        echo "✅ 프로세스 종료 완료"
        exit 0
    else
        echo "⚠️  PID 파일의 프로세스가 이미 종료되었습니다."
        rm -f "$PID_FILE"
    fi
fi

# 방법 2: 포트를 사용하는 프로세스 찾아서 종료
if command -v lsof > /dev/null 2>&1; then
    PIDS=$(lsof -ti :$PORT 2>/dev/null)
    if [ -n "$PIDS" ]; then
        echo "📌 포트 $PORT를 사용하는 프로세스 찾음: $PIDS"
        for PID in $PIDS; do
            echo "   프로세스 $PID 종료 중..."
            kill -TERM "$PID" 2>/dev/null
        done
        sleep 2
        # 여전히 실행 중인 프로세스 강제 종료
        REMAINING=$(lsof -ti :$PORT 2>/dev/null)
        if [ -n "$REMAINING" ]; then
            echo "⚠️  일부 프로세스가 종료되지 않아 강제 종료합니다..."
            for PID in $REMAINING; do
                kill -9 "$PID" 2>/dev/null
            done
        fi
        echo "✅ 포트 $PORT를 사용하는 프로세스 종료 완료"
        exit 0
    fi
fi

# 방법 3: Python 프로세스 중 app.py를 실행하는 것 찾기
PYTHON_PIDS=$(ps aux | grep "[p]ython.*app.py" | awk '{print $2}')
if [ -n "$PYTHON_PIDS" ]; then
    echo "📌 app.py를 실행하는 Python 프로세스 찾음: $PYTHON_PIDS"
    for PID in $PYTHON_PIDS; do
        echo "   프로세스 $PID 종료 중..."
        kill -TERM "$PID" 2>/dev/null
    done
    sleep 2
    # 여전히 실행 중인 프로세스 강제 종료
    REMAINING=$(ps aux | grep "[p]ython.*app.py" | awk '{print $2}')
    if [ -n "$REMAINING" ]; then
        echo "⚠️  일부 프로세스가 종료되지 않아 강제 종료합니다..."
        for PID in $REMAINING; do
            kill -9 "$PID" 2>/dev/null
        done
    fi
    echo "✅ Python 프로세스 종료 완료"
    exit 0
fi

echo "❌ 실행 중인 SmartBrief 앱을 찾을 수 없습니다."
echo "💡 앱이 이미 종료되었거나 다른 포트에서 실행 중일 수 있습니다."

