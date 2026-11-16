"""启动入口：启动后端服务并自动用默认浏览器打开应用页面。"""
import os
import socket
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

    # 提前提示端口冲突，避免打开已有的其他服务。
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((HOST, PORT))
        except OSError:
            print(f"端口 {PORT} 已被占用，请先关闭占用该端口的程序。", file=sys.stderr)
            sys.exit(1)

    # 启动后端服务（uvicorn）
    server = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn",
            "backend.app:app",
            "--host", HOST,
            "--port", str(PORT),
        ]
    )

    # 确认子进程仍在运行并开始监听后再打开浏览器。
    for _ in range(100):
        if server.poll() is not None:
            sys.exit(server.returncode or 1)
        try:
            with socket.create_connection((HOST, PORT), timeout=0.2):
                break
        except OSError:
            time.sleep(0.1)
    else:
        server.terminate()
        server.wait()
        print("服务启动超时，请检查终端中的错误信息。", file=sys.stderr)
        sys.exit(1)

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
