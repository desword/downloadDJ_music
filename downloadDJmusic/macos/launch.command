#!/bin/bash
set -Ee

show_error() {
    echo
    echo "启动未完成。请查看上方提示，解决后重新双击 DJ Deck。"
    read -r -p "按回车关闭窗口..." _ || true
}
trap show_error ERR

resource_dir="$(cd "$(dirname "$0")" && pwd)"
app_source="$resource_dir/app"
support_dir="${DJ_DECK_SUPPORT_DIR:-$HOME/Library/Application Support/DJ Deck}"
venv_dir="$support_dir/venv"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
export DJ_DECK_CONFIG="$support_dir/config.json"
mkdir -p "$support_dir"

# 已经运行时直接打开现有页面，不重复安装或启动。
health="$(/usr/bin/curl -fsS --max-time 2 http://127.0.0.1:18899/api/health 2>/dev/null || true)"
if [ "$health" = '{"application":"DJ Deck","status":"ready"}' ]; then
    /usr/bin/open 'http://127.0.0.1:18899'
    exit 0
fi

echo "DJ Deck：正在检查运行环境…"
find_python() {
    for candidate in "$venv_dir/bin/python" \
        /Library/Frameworks/Python.framework/Versions/3.14/bin/python3.14 \
        /Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13 \
        /Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 \
        /Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11 \
        /Library/Frameworks/Python.framework/Versions/3.10/bin/python3.10 \
        /Library/Frameworks/Python.framework/Versions/3.9/bin/python3.9 \
        python3.12 python3; do
        if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys, venv; sys.exit(sys.version_info < (3, 9))' >/dev/null 2>&1; then
            command -v "$candidate"
            return 0
        fi
    done
    return 1
}
python_cmd="$(find_python || true)"
if [ -z "$python_cmd" ]; then
    echo "需要 Python 3.9 或更新版本。正在打开 Python 官方下载页面。"
    echo "请下载安装 macOS 版 Python，完成后回到此窗口按回车继续。"
    /usr/bin/open 'https://www.python.org/downloads/macos/'
    read -r -p "安装完成后按回车继续..." _
    python_cmd="$(find_python || true)"
    if [ -z "$python_cmd" ]; then
        echo "仍未找到 Python。请完成安装后重新双击 DJ Deck。" >&2
        exit 1
    fi
fi

if [ ! -x "$venv_dir/bin/python" ] || ! "$venv_dir/bin/python" -c 'import sys; sys.exit(sys.version_info < (3, 9))' >/dev/null 2>&1; then
    echo "正在创建 Python 环境…"
    "$python_cmd" -m venv "$venv_dir"
fi
if ! "$venv_dir/bin/python" "$resource_dir/check_dependencies.py" "$app_source/backend/requirements.txt"; then
    echo "正在安装或修复 Python 依赖…"
    "$venv_dir/bin/python" -m pip install -r "$app_source/backend/requirements.txt"
    "$venv_dir/bin/python" "$resource_dir/check_dependencies.py" "$app_source/backend/requirements.txt"
else
    echo "Python 依赖已满足，跳过安装。"
fi

if ! "$venv_dir/bin/python" -c 'import imageio_ffmpeg, subprocess; subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)' ; then
    echo "内置 FFmpeg 无法在此 Mac 上运行，请检查系统版本与处理器架构。" >&2
    exit 1
fi

echo "环境就绪，正在打开 DJ Deck。请保持此窗口运行；按 Control-C 结束。"
cd "$app_source"
"$venv_dir/bin/python" start.py
