#!/usr/bin/env python3
"""
DocPack Route Validator 실행 스크립트
이 파일을 더블클릭하거나 python run.py로 실행할 수 있습니다.
"""
import os
import sys
import subprocess
from pathlib import Path

def main():
    # 현재 스크립트의 디렉토리로 이동
    script_dir = Path(__file__).parent
    os.chdir(script_dir)
    
    # 가상환경 확인
    venv_python = script_dir / ".venv" / "bin" / "python"
    if not venv_python.exists():
        # Windows용 경로도 확인
        venv_python = script_dir / ".venv" / "Scripts" / "python.exe"
        if not venv_python.exists():
            print("❌ 가상환경을 찾을 수 없습니다.")
            print("다음 명령어로 가상환경을 생성하세요:")
            print("  python3 -m venv .venv")
            print("  source .venv/bin/activate  # macOS/Linux")
            print("  pip install -r requirements.txt")
            sys.exit(1)
    
    # Streamlit 실행
    print("🚀 DocPack Route Validator를 시작합니다...")
    print("📝 브라우저가 자동으로 열립니다.")
    print("⏹️  종료하려면 Ctrl+C를 누르세요.\n")
    
    try:
        # streamlit run app.py 실행
        subprocess.run([str(venv_python), "-m", "streamlit", "run", "app.py"])
    except KeyboardInterrupt:
        print("\n\n👋 앱을 종료합니다.")
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

