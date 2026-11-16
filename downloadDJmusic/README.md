# SoundCloud 歌单批量下载器

基于 **yt-dlp + FastAPI** 的本地 Web 应用，支持批量下载 SoundCloud 歌单为 wav / mp3。双击即可启动，自带 Web 界面，适合部署在 Windows 服务器上。

## macOS 快速开始

1. 安装 [Homebrew](https://brew.sh/zh-cn/)。安装 Python 3.9 或更新版本；安装脚本会在缺少可用 Python 时使用 Homebrew 安装 Python。
2. 双击 `install_mac.command`。脚本会检查并通过 Homebrew 安装 FFmpeg（含 ffprobe），在项目的 `.venv` 中安装 Python 依赖。需要网络连接。
3. 双击 `run_mac.command`，保持终端窗口打开，浏览器将打开本机页面。按 Control-C 可停止服务。

如果 Finder 提示没有执行权限，请打开终端，输入 `chmod +x `（注意末尾空格），将两个 `.command` 文件拖入终端并回车，然后重新双击。若 macOS 阻止打开脚本，可在 Finder 中右键选择“打开”。

默认下载到 `~/Music/SoundCloud`，可以在页面中修改；旧配置中的 Windows 默认路径会在 macOS 自动替换。FFmpeg 使用 Homebrew 安装的系统版本，不需要 Windows 的 exe 文件。若端口 18899 已被占用，请先关闭占用端口的程序。

SoundCloud 可能改变接口、限制访问或限制部分音轨，遇到解析失败时可检查网络和 yt-dlp 版本；受限制的音轨不保证能够下载。页面的样式依赖 Tailwind CDN，需要联网。

## 功能特性

- 输入 SoundCloud 歌单链接，先解析预览曲目列表
- 可配置下载路径（默认 `D:\Music\SoundCloud`），文件按 `歌单名/序号 - 标题.扩展名` 保存
- 支持 wav（默认）/ mp3 格式切换，自动嵌入元数据
- 实时进度展示（第 x / y 首、百分比、当前曲目）
- 支持下载中途取消
- 内置 ffmpeg，无需额外安装（首次需运行下载脚本）
- 默认配置持久化到 `config.json`

## 目录结构

```
downloadDJmusic/
├── backend/
│   ├── __init__.py
│   ├── app.py              # FastAPI 主程序 + API 接口
│   ├── downloader.py       # yt-dlp 下载核心逻辑
│   ├── config.py           # 配置管理
│   └── requirements.txt    # Python 依赖
├── frontend/
│   └── index.html          # 单页面前端界面
├── bin/                    # 内置 ffmpeg（需运行 download_ffmpeg.bat 下载）
├── config.json             # 用户配置（默认路径、格式等）
├── start.py                # 启动入口（启动后端 + 打开浏览器）
├── run.bat                 # 双击启动脚本
├── install.bat             # 首次安装依赖 + ffmpeg
├── download_ffmpeg.bat     # 单独下载内置 ffmpeg
├── build.bat               # PyInstaller 打包为单个 exe
└── README.md
```

## 快速开始

### Windows：使用 Python 环境运行

1. 安装 Python 3.9+（勾选 Add to PATH）：https://www.python.org/downloads/
2. 双击 `install.bat`，自动安装依赖并下载内置 ffmpeg
3. 双击 `run.bat` 启动程序，浏览器会自动打开 `http://127.0.0.1:18899`

### Windows：打包成 exe 运行

1. 先在本机按方式一完成依赖与 ffmpeg 安装
2. 双击 `build.bat`，生成 `dist/SoundCloudDownloader.exe`
3. 将以下文件拷贝到目标 Windows 服务器：
   - `dist/SoundCloudDownloader.exe`
   - `bin/` 目录（含 ffmpeg.exe、ffprobe.exe）
   - `frontend/` 目录
   - `config.json`
4. 在目标机器双击 `SoundCloudDownloader.exe` 即可运行

## 使用说明

1. 在「歌单链接」输入框粘贴 SoundCloud 歌单 URL
2. 点击「解析歌单」预览曲目列表
3. 在「下载配置」中填写下载路径、选择音频格式（可点击「保存为默认配置」）
4. 点击「开始下载」，在进度区查看实时进度
5. 下载完成后文件保存在 `下载路径/歌单名/` 目录下

## 技术栈

- **后端**：Python 3.9+、FastAPI、uvicorn、yt-dlp
- **前端**：HTML + Tailwind CSS（CDN）+ 原生 JavaScript
- **转码**：内置 ffmpeg（BtbN 构建版）
- **打包**：PyInstaller

## 常见问题

**Q：启动后浏览器没自动打开？**
手动访问 `http://127.0.0.1:18899`。

**Q：下载报错提示找不到 ffmpeg？**
运行 `download_ffmpeg.bat` 下载内置 ffmpeg，或确认系统 PATH 中已安装 ffmpeg。

**Q：端口 18899 被占用？**
修改 `start.py` 中的 `PORT` 常量，并同步修改前端（无需改动，前端用相对路径）。

**Q：下载的文件名有乱码？**
yt-dlp 会自动处理，若仍有问题可在 `backend/downloader.py` 的 `ydl_opts` 中加入 `"restrictfilenames": True`。
