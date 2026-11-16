"""启动入口：启动后端服务并自动用默认浏览器打开应用页面。"""
import os
import subprocess
import sys
import time
import webbrowser

HOST = "127.0.0.1"
PORT = 18899
URL = f"http://{HOST}:{PORT}"


def main() -> None:
    # 切换到脚本所在目录（项目根目录），保证相对路径生效
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    # 启动后端服务（uvicorn）
    server = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn",
            "backend.app:app",
            "--host", HOST,
            "--port", str(PORT),
        ]
    )

    # 等待服务启动
    time.sleep(2)

    # 打开浏览器
    try:
        webbrowser.open(URL)
    except Exception:
        pass

    # 保持运行，直到服务退出或被中断
    try:
        server.wait()
    except KeyboardInterrupt:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()


if __name__ == "__main__":
    main()
