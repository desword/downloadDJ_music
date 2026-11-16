"""FastAPI 主程序：提供 RESTful API 与前端静态文件托管。"""
import os
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config as cfg
from . import downloader
from . import scanner
from . import workflow

# 项目根目录
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(ROOT_DIR, "frontend")

app = FastAPI(title="SoundCloud 歌单下载器", version="1.0.0")

# 允许本地前端跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------- 请求模型 ----------------

class PlaylistInfoRequest(BaseModel):
    url: str


class DownloadStartRequest(BaseModel):
    url: str
    download_path: str
    format: str = "wav"
    # 可选：若前端已解析过歌单，传入以避免下载时重复解析
    playlist_title: Optional[str] = None
    track_count: Optional[int] = None


class ConfigUpdateRequest(BaseModel):
    default_download_path: Optional[str] = None
    default_format: Optional[str] = None
    sleep_interval: Optional[int] = None


class PathValidateRequest(BaseModel):
    path: str


# ---------------- 配置接口 ----------------

@app.get("/api/config")
def get_config() -> Dict[str, Any]:
    return cfg.load_config()


@app.put("/api/config")
def update_config(req: ConfigUpdateRequest) -> Dict[str, Any]:
    current = cfg.load_config()
    if req.default_download_path is not None:
        current["default_download_path"] = req.default_download_path
    if req.default_format is not None:
        if req.default_format not in ("wav", "mp3"):
            raise HTTPException(status_code=400, detail="format 仅支持 wav 或 mp3")
        current["default_format"] = req.default_format
    if req.sleep_interval is not None:
        if req.sleep_interval < 0:
            raise HTTPException(status_code=400, detail="sleep_interval 不能为负数")
        current["sleep_interval"] = req.sleep_interval
    cfg.save_config(current)
    return current


# ---------------- 歌单解析接口 ----------------

@app.post("/api/playlist/info")
def playlist_info(req: PlaylistInfoRequest) -> Dict[str, Any]:
    url = (req.url or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="url 不能为空")
    try:
        return downloader.fetch_playlist_info(url)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"解析歌单失败: {e}")


@app.post("/api/scan/start")
def scan_start(req: PlaylistInfoRequest) -> Dict[str, str]:
    try:
        scanner.start(req.url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"status": "started"}


@app.get("/api/scan/progress")
def scan_progress() -> Dict[str, Any]:
    return scanner.get_state()


@app.post("/api/scan/cancel")
def scan_cancel() -> Dict[str, str]:
    scanner.cancel()
    return {"status": "cancelling"}


@app.post("/api/workflow/start")
def workflow_start(req: DownloadStartRequest) -> Dict[str, str]:
    url = (req.url or "").strip()
    path = os.path.expanduser(req.download_path.strip())
    if not url:
        raise HTTPException(status_code=400, detail="请输入歌单链接")
    if not path or not os.path.isabs(path):
        raise HTTPException(status_code=400, detail="请填写绝对下载路径")
    if req.format not in ("wav", "mp3"):
        raise HTTPException(status_code=400, detail="format 仅支持 wav 或 mp3")
    try:
        os.makedirs(path, exist_ok=True)
        workflow.start(url, path, req.format)
    except OSError as e:
        raise HTTPException(status_code=400, detail=f"无法创建下载目录: {e}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"status": "started"}


@app.get("/api/workflow/progress")
def workflow_progress() -> Dict[str, Any]:
    return workflow.get_state()


@app.post("/api/workflow/cancel")
def workflow_cancel() -> Dict[str, bool]:
    return {"cancelled": workflow.cancel()}


# ---------------- 下载接口 ----------------

@app.post("/api/download/start")
def download_start(req: DownloadStartRequest) -> Dict[str, Any]:
    url = (req.url or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="url 不能为空")
    if not req.download_path.strip():
        raise HTTPException(status_code=400, detail="download_path 不能为空")
    if req.format not in ("wav", "mp3"):
        raise HTTPException(status_code=400, detail="format 仅支持 wav 或 mp3")

    if downloader.is_running():
        raise HTTPException(status_code=409, detail="已有下载任务正在运行")

    download_path = os.path.expanduser(req.download_path.strip())
    if not os.path.isabs(download_path):
        raise HTTPException(status_code=400, detail="请使用绝对路径")
    # 确保下载根目录存在
    try:
        os.makedirs(download_path, exist_ok=True)
    except OSError as e:
        raise HTTPException(status_code=400, detail=f"无法创建下载目录: {e}")

    try:
        downloader.start_download(
            url,
            download_path,
            req.format,
            playlist_title=req.playlist_title or "",
            track_count=req.track_count or 0,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return {"status": "started"}


@app.get("/api/download/progress")
def download_progress() -> Dict[str, Any]:
    return downloader.get_state()


@app.post("/api/download/cancel")
def download_cancel() -> Dict[str, Any]:
    ok = downloader.cancel_download()
    return {"cancelled": ok}


# ---------------- 路径校验接口 ----------------

@app.post("/api/path/validate")
def path_validate(req: PathValidateRequest) -> Dict[str, Any]:
    p = os.path.expanduser((req.path or "").strip())
    if not p:
        return {"valid": False, "reason": "路径不能为空"}
    if not os.path.isabs(p):
        return {"valid": False, "reason": "请使用绝对路径"}
    if os.path.exists(p):
        if not os.path.isdir(p):
            return {"valid": False, "reason": "路径不是目录"}
        if not os.access(p, os.W_OK):
            return {"valid": False, "reason": "目录不可写"}
        return {"valid": True}
    # 不存在则尝试创建
    try:
        os.makedirs(p, exist_ok=True)
        return {"valid": True}
    except OSError as e:
        return {"valid": False, "reason": f"无法创建目录: {e}"}


# ---------------- 前端静态托管 ----------------

if os.path.isdir(FRONTEND_DIR):
    # 挂载静态资源目录（如 css/js 子目录），但 index.html 用根路由返回
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/")
def index():
    index_file = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return JSONResponse(
        status_code=404,
        content={"detail": "前端文件未找到，请确认 frontend/index.html 存在"},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=18899)
