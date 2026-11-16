# SoundCloud 歌单批量下载器

基于 **yt-dlp + FastAPI** 的本地 Web 应用，支持批量下载 SoundCloud 歌单为 wav / mp3。支持 macOS 应用启动与 Windows 脚本启动。

## macOS 应用

1. 下载 `dist/DJ-Deck-macOS.zip` 并解压，可将 `DJ Deck.app` 拖入“应用程序”文件夹。
2. 双击 `DJ Deck.app`。首次启动会在终端自动检查 Python、FFmpeg、ffprobe 和 Python 依赖，缺少时自动安装；请保持终端打开，安装完成后网页会自动打开。
3. 后续双击应用即可启动；已满足的依赖不会重复安装。保持终端窗口打开，按 Control-C 可以停止服务。

首次安装需要联网。如果 Mac 缺少 Python 或 FFmpeg，应用会通过 Homebrew 安装；缺少 Homebrew 时会从官方地址安装，期间可能要求确认及输入 Mac 管理员密码。安装过程由 Homebrew 和系统提示完成。

应用目前未签名和公证，macOS 可能阻止首次打开。可在 Finder 中右键点击应用并选择“打开”；如仍被阻止，请在“系统设置 → 隐私与安全性”查看打开选项。

应用的运行环境和配置保存在 `~/Library/Application Support/DJ Deck/`，不会写入应用包；默认下载到 `~/Music/SoundCloud`，可在网页上修改。首次使用应用版时，可重新设置以前使用的下载目录。

### 重新构建应用包

在项目目录运行 `python3 scripts/build_macos_app.py`，生成 `dist/DJ-Deck-macOS.zip`。构建不依赖 Mac，但使用和首次安装仍需在 macOS 上完成。

### 从源码运行

也可在 Mac 上先运行 `install_mac.command`，然后运行 `run_mac.command`。这两个脚本使用项目目录下的 `.venv`。

## 功能特性

- 输入 SoundCloud 歌单链接，一键扫描并自动下载；扫描结果可以折叠
- 可配置下载路径（macOS 默认 `~/Music/SoundCloud`，Windows 默认 `D:\Music\SoundCloud`），文件按 `歌单名/序号 - 标题.扩展名` 保存
- 支持 wav（默认）/ mp3 格式切换，自动嵌入元数据
- 实时展示当前歌曲和全部歌曲的预计剩余时间，下载任务结束后播放提示音
- 支持扫描或下载中途取消；再次运行时跳过已下载的歌曲
- macOS 应用会自动检查并安装缺少的 FFmpeg；Windows 可运行下载脚本
- 默认配置持久化保存

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
2. 填写下载路径、选择音频格式（可点击「保存默认设置」）
3. 点击「开始下载」；程序复用扫描结果自动下载并跳过受保护曲目，可展开扫描结果
4. 如需替换曲目，点击「终止任务」，在 SoundCloud 修改歌单后再次开始；已有歌曲会自动跳过
5. 下载任务结束后，可点击「打开下载目录」查看文件；保持页面打开以接收提示音

程序在各歌单目录中保存 `.dj-deck-downloads.json` 索引以识别已完成曲目。旧版下载的文件按完整标题匹配；不同音频格式分别检查。

扫描只检查是否能获取音频信息；只有服务明确提示 DRM 时才标记为受保护。网络、地区、登录或其他错误会显示为待确认；能提取也不保证实际下载一定成功。扫描不会修改 SoundCloud 歌单。

## 技术栈

- **后端**：Python 3.9+、FastAPI、uvicorn、yt-dlp
- **前端**：HTML + CSS + 原生 JavaScript
- **转码**：FFmpeg
- **打包**：macOS 应用包；Windows 使用 PyInstaller

## 常见问题

**Q：启动后浏览器没自动打开？**
手动访问 `http://127.0.0.1:18899`。

**Q：下载报错提示找不到 ffmpeg？**
macOS 应用会尝试安装 FFmpeg；Windows 可运行 `download_ffmpeg.bat`，或确认系统 PATH 中已安装 ffmpeg。

**Q：端口 18899 被占用？**
修改 `start.py` 中的 `PORT` 常量，并同步修改前端（无需改动，前端用相对路径）。

**Q：下载的文件名有乱码？**
yt-dlp 会自动处理，若仍有问题可在 `backend/downloader.py` 的 `ydl_opts` 中加入 `"restrictfilenames": True`。
