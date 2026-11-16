#!/bin/bash
# Finder 启动入口：在 Terminal 中显示首次安装进度和错误。
app_dir="$(cd "$(dirname "$0")/.." && pwd)"
exec /usr/bin/open -a Terminal "$app_dir/Resources/launch.command"
