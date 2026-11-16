@echo off
cd /d "%~dp0"

echo ============================================
echo   下载内置 ffmpeg（用于音频转码）
echo ============================================
echo.

set "FFMPEG_ZIP=%TEMP%\ffmpeg.zip"
set "FFMPEG_EXTRACT=%TEMP%\ffmpeg_extract"
set "URL=https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"

echo 正在从 GitHub 下载 ffmpeg（约 100MB），请耐心等待...
powershell -NoProfile -Command ^
    "$ProgressPreference = 'SilentlyContinue';" ^
    "try { Invoke-WebRequest -Uri '%URL%' -OutFile '%FFMPEG_ZIP%' -UseBasicParsing }" ^
    "catch { Write-Host '下载失败:' $_.Exception.Message; exit 1 }"

if errorlevel 1 (
    echo 下载失败，请检查网络连接或手动从以下地址下载：
    echo %URL%
    echo 解压后将 ffmpeg.exe 和 ffprobe.exe 放入 bin\ 目录
    pause
    exit /b 1
)

echo 下载完成，正在解压...
if exist "%FFMPEG_EXTRACT%" rmdir /s /q "%FFMPEG_EXTRACT%"
powershell -NoProfile -Command ^
    "$ProgressPreference = 'SilentlyContinue';" ^
    "Expand-Archive -Path '%FFMPEG_ZIP%' -DestinationPath '%FFMPEG_EXTRACT%' -Force"

echo 正在复制 ffmpeg.exe 和 ffprobe.exe 到 bin\ 目录...
if not exist "bin" mkdir "bin"
copy /y "%FFMPEG_EXTRACT%\ffmpeg-master-latest-win64-gpl\bin\ffmpeg.exe" "bin\ffmpeg.exe" >nul
copy /y "%FFMPEG_EXTRACT%\ffmpeg-master-latest-win64-gpl\bin\ffprobe.exe" "bin\ffprobe.exe" >nul

if exist "bin\ffmpeg.exe" (
    echo.
    echo 安装成功！ffmpeg 已放入 bin\ 目录
) else (
    echo.
    echo 复制失败，请手动解压 %FFMPEG_ZIP% 并将 ffmpeg.exe、ffprobe.exe 放入 bin\
)

:: 清理临时文件
if exist "%FFMPEG_ZIP%" del "%FFMPEG_ZIP%"
if exist "%FFMPEG_EXTRACT%" rmdir /s /q "%FFMPEG_EXTRACT%"

echo.
pause
