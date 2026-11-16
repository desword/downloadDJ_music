@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

set "PYTHON_OK=未通过"
set "DEPS_OK=未通过"
set "FFMPEG_OK=未通过"
set "PY_VER="

echo ============================================
echo   SoundCloud 歌单下载器 - 环境安装
echo ============================================
echo.

echo [1/3] 检查 Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo   未检测到 Python
) else (
    for /f "delims=" %%v in ('python --version 2^>^&1') do set "PY_VER=%%v"
    echo   !PY_VER!
    set "PYTHON_OK=成功"
)

if "!PYTHON_OK!"=="未通过" (
    echo.
    echo 请先安装 Python 3.9+：https://www.python.org/downloads/
    goto summary
)

echo.
echo [2/3] 安装 Python 依赖...
python -m pip install --upgrade pip >nul 2>&1
python -m pip install -r backend\requirements.txt
if errorlevel 1 (
    echo   依赖安装失败，请检查网络或 pip 配置
) else (
    echo   依赖安装完成
    set "DEPS_OK=成功"
)

echo.
echo [3/3] 检查内置 ffmpeg...
if exist "bin\ffmpeg.exe" (
    echo   ffmpeg 已存在，跳过
    set "FFMPEG_OK=成功"
) else (
    echo   未发现内置 ffmpeg，正在调用下载脚本...
    call download_ffmpeg.bat
    if exist "bin\ffmpeg.exe" (
        echo   ffmpeg 下载完成
        set "FFMPEG_OK=成功"
    ) else (
        echo   ffmpeg 下载失败
    )
)

:summary
echo.
echo ============================================
echo   安装状态汇总
echo ============================================
echo   Python 环境  : !PYTHON_OK!  !PY_VER!
echo   Python 依赖  : !DEPS_OK!
echo   内置 ffmpeg  : !FFMPEG_OK!
echo ============================================
echo.
if "!PYTHON_OK!"=="成功" if "!DEPS_OK!"=="成功" if "!FFMPEG_OK!"=="成功" (
    echo 安装成功！双击 run.bat 启动程序。
) else (
    echo 部分项目未就绪，请根据上方提示处理。
)
echo.
echo 按任意键退出...
pause >nul
endlocal
