@echo off
cd /d "%~dp0"

echo ============================================
echo   打包为单个 exe（PyInstaller）
echo ============================================
echo.

echo 安装 PyInstaller...
python -m pip install pyinstaller

echo.
echo 开始打包...
pyinstaller --onefile ^
    --name "SoundCloudDownloader" ^
    --add-data "frontend;frontend" ^
    --add-data "bin;bin" ^
    --add-data "config.json;." ^
    --hidden-import "uvicorn.logging" ^
    --hidden-import "uvicorn.protocols" ^
    --hidden-import "uvicorn.protocols.http" ^
    --hidden-import "uvicorn.protocols.http.auto" ^
    --hidden-import "uvicorn.protocols.websockets" ^
    --hidden-import "uvicorn.protocols.websockets.auto" ^
    --hidden-import "uvicorn.lifespan" ^
    --hidden-import "uvicorn.lifespan.on" ^
    start.py

if errorlevel 1 (
    echo.
    echo 打包失败，请查看上方错误信息。
    pause
    exit /b 1
)

echo.
echo 打包完成！exe 位于 dist\ 目录下。
echo 将 dist\SoundCloudDownloader.exe 与 bin\、frontend\、config.json 一起拷贝到目标机器即可运行。
pause
