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
python_cmd=""
for candidate in "$venv_dir/bin/python" python3.12 python3; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys, venv; sys.exit(sys.version_info < (3, 9))' >/dev/null 2>&1; then
        python_cmd="$(command -v "$candidate")"
        break
    fi
done
ffmpeg_ready=false
if command -v ffmpeg >/dev/null 2>&1 && command -v ffprobe >/dev/null 2>&1 && ffmpeg -version >/dev/null 2>&1 && ffprobe -version >/dev/null 2>&1; then
    ffmpeg_ready=true
fi

if [ -z "$python_cmd" ] || [ "$ffmpeg_ready" = false ]; then
    if ! command -v brew >/dev/null 2>&1; then
        echo "需要 Homebrew 来安装缺少的依赖，将从 Homebrew 官方地址安装。"
        echo "安装过程中可能要求确认、网络连接以及 Mac 管理员密码。"
        installer_path="$(mktemp "$support_dir/homebrew-install.XXXXXX")"
        if ! /usr/bin/curl -fLsS --retry 2 https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh -o "$installer_path"; then
            rm -f "$installer_path"
            echo "无法下载 Homebrew 安装程序。" >&2
            exit 1
        fi
        if ! /bin/bash "$installer_path"; then
            rm -f "$installer_path"
            echo "Homebrew 安装未完成。" >&2
            exit 1
        fi
        rm -f "$installer_path"
        export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
    fi
    if ! command -v brew >/dev/null 2>&1; then
        echo "未找到 Homebrew，请检查安装输出后重新运行。" >&2
        exit 1
    fi
    if [ -z "$python_cmd" ]; then
        echo "正在安装 Python 3.12…"
        brew install python@3.12
        python_cmd="$(brew --prefix python@3.12)/bin/python3.12"
    fi
    if [ "$ffmpeg_ready" = false ]; then
        echo "正在安装 FFmpeg…"
        brew install ffmpeg
        export PATH="$(brew --prefix ffmpeg)/bin:$PATH"
    fi
fi

if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1 || ! ffmpeg -version >/dev/null 2>&1 || ! ffprobe -version >/dev/null 2>&1; then
    echo "FFmpeg 或 ffprobe 不可用，请检查 Homebrew 的安装输出。" >&2
    exit 1
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

echo "环境就绪，正在打开 DJ Deck。请保持此窗口运行；按 Control-C 结束。"
cd "$app_source"
"$venv_dir/bin/python" start.py
