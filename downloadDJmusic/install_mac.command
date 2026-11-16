#!/bin/bash
set -e
cd "$(dirname "$0")"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
echo "正在检查 macOS 开发环境..."
if [ "$(uname -s)" != Darwin ]; then
    echo "此脚本只适用于 macOS。" >&2
    exit 1
fi
if ! command -v brew >/dev/null 2>&1; then
    echo "请先按照 https://brew.sh/zh-cn/ 的说明安装 Homebrew，然后重新运行此脚本。" >&2
    exit 1
fi
python_cmd=python3
if ! command -v "$python_cmd" >/dev/null 2>&1 || ! "$python_cmd" -c 'import sys; sys.exit(sys.version_info < (3, 9))'; then
    brew install python@3.12
    python_cmd="$(brew --prefix python@3.12)/bin/python3.12"
fi
if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
    brew install ffmpeg
fi
"$python_cmd" -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
echo "安装完成。请双击 run_mac.command 启动。"
