#!/bin/bash
cd "$(dirname "$0")" || exit 1
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
if [ ! -x .venv/bin/python ]; then
    echo "请先双击 install_mac.command 安装依赖。" >&2
    exit 1
fi
exec .venv/bin/python start.py
