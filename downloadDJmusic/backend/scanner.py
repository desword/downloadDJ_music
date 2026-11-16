"""逐曲检查可提取性；只根据明确的服务响应标记 DRM。"""
import copy
import threading
from typing import Any, Dict

import yt_dlp

from .downloader import _split_urls

_lock = threading.Lock()
_state: Dict[str, Any] = {"status": "idle", "playlists": [], "checked": 0, "total": 0, "message": ""}
_cancel = threading.Event()


def get_state() -> Dict[str, Any]:
    with _lock:
        return copy.deepcopy(_state)


def _set(**values: Any) -> None:
    with _lock:
        _state.update(values)


def _reason(exc: Exception) -> tuple:
    message = str(exc).strip() or "服务未提供原因"
    lower = message.lower()
    if any(s in lower for s in ("drm protected", "drm-protected", "drm protection", "protected by drm", "drm protected content", "this video is drm protected")):
        return "restricted", "服务明确提示受 DRM 保护"
    return "unknown", message[:400]


def _entry_url(entry: Dict[str, Any]) -> str:
    url = entry.get("webpage_url") or entry.get("url") or entry.get("id") or ""
    url = str(url)
    if url.isdigit():
        return "https://api-v2.soundcloud.com/tracks/" + url
    return url


def start(raw_urls: str) -> None:
    urls = _split_urls(raw_urls)
    if not urls:
        raise ValueError("请输入歌单链接")
    with _lock:
        if _state["status"] == "scanning":
            raise RuntimeError("已有扫描正在进行")
        _cancel.clear()
        _state.update(status="scanning", playlists=[], checked=0, total=0, message="正在读取歌单…")

    def worker() -> None:
        opts = {"quiet": True, "no_warnings": True, "skip_download": True,
                "socket_timeout": 15, "retries": 0, "extractor_retries": 0}
        try:
            for url in urls:
                if _cancel.is_set():
                    break
                try:
                    with yt_dlp.YoutubeDL({**opts, "extract_flat": "in_playlist"}) as ydl:
                        info = ydl.extract_info(url, download=False)
                    if not info:
                        raise ValueError("未返回歌单信息")
                    entries = info.get("entries")
                    if entries is None:
                        entries = [{"url": url, "title": info.get("title")}]
                    else:
                        entries = list(entries)
                    playlist = {"title": info.get("title") or "未命名歌单", "url": url, "tracks": []}
                    with _lock:
                        _state["playlists"].append(playlist)
                        _state["total"] += len(entries)
                    for index, entry in enumerate(entries, 1):
                        if _cancel.is_set():
                            break
                        entry = entry or {}
                        track_url = _entry_url(entry)
                        title = entry.get("title") or entry.get("id") or f"第 {index} 首"
                        _set(message=f"正在检查 {playlist['title']} · 第 {index}/{len(entries)} 首")
                        track = {"index": index, "title": title, "url": track_url,
                                 "status": "unknown", "reason": "无法获取曲目链接"}
                        if track_url:
                            try:
                                with yt_dlp.YoutubeDL({**opts, "noplaylist": True}) as ydl:
                                    detail = ydl.extract_info(track_url, download=False)
                                if not detail:
                                    raise ValueError("服务未返回曲目信息")
                                track["title"] = detail.get("title") or title
                                if detail.get("has_drm") is True:
                                    track.update(status="restricted", reason="服务明确提示受 DRM 保护")
                                elif detail.get("formats") or detail.get("url"):
                                    track.update(status="available", reason="已获取音频信息，实际下载结果仍可能变化")
                                else:
                                    track.update(status="unknown", reason="未获取到可用音频信息")
                            except Exception as exc:
                                track["status"], track["reason"] = _reason(exc)
                        with _lock:
                            playlist["tracks"].append(track)
                            _state["checked"] += 1
                except Exception as exc:
                    with _lock:
                        _state["playlists"].append({"title": "歌单读取失败", "url": url, "tracks": [], "error": str(exc)[:400]})
            _set(status="cancelled" if _cancel.is_set() else "finished", message="扫描已取消" if _cancel.is_set() else "扫描完成，请检查结果")
        except Exception as exc:
            _set(status="error", message=str(exc))

    threading.Thread(target=worker, daemon=True).start()


def cancel() -> None:
    _cancel.set()
