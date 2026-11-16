#!/bin/bash
set -e
cd "$(dirname "$0")"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
if [ "$(uname -s)" != Darwin ]; then
    echo "此脚本只适用于 macOS。" >&2
    exit 1
fi
if ! command -v python3 >/dev/null 2>&1 || ! python3 -c 'import sys, venv; sys.exit(sys.version_info < (3, 9))'; then
    echo "请从 https://www.python.org/downloads/macos/ 安装 Python 3.9 或更新版本。" >&2
    /usr/bin/open 'https://www.python.org/downloads/macos/'
    exit 1
fi
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
.venv/bin/python -c 'import imageio_ffmpeg, subprocess; subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)'
echo "安装完成。请双击 run_mac.command 启动。"
