"""逐曲检查可提取性；只根据明确的服务响应标记 DRM。"""
import copy
import json
import re
import threading
import urllib.parse
import urllib.request
from typing import Any, Dict

import yt_dlp

from .downloader import _get_soundcloud_client_id, _split_urls

_lock = threading.Lock()
_state: Dict[str, Any] = {"status": "idle", "playlists": [], "checked": 0, "total": 0, "message": ""}
# 提取出的媒体链接可能是临时签名地址，只保留在服务端内存中。
_download_plan = []
_cancel = threading.Event()


def get_state() -> Dict[str, Any]:
    with _lock:
        return copy.deepcopy(_state)


def get_download_plan() -> list:
    with _lock:
        return copy.deepcopy(_download_plan)


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


def _is_title(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and not value.strip().isdigit()


def _lookup_title(url: str, track_id: Any, active_client_id: Any = None) -> str:
    """音频提取失败时，独立查询公开元数据；失败时再使用链接名称。"""
    parsed = urllib.parse.urlsplit(url)
    host = (parsed.hostname or '').lower()
    if host not in ('soundcloud.com', 'www.soundcloud.com', 'm.soundcloud.com', 'api-v2.soundcloud.com'):
        return ''
    track_id = str(track_id or '')
    if not track_id.isdigit():
        match = re.fullmatch(r'/tracks/(\d+)', parsed.path)
        track_id = match.group(1) if match and host == 'api-v2.soundcloud.com' else ''
    client_id = (active_client_id or _get_soundcloud_client_id()) if track_id else None
    if client_id:
        query = {'client_id': client_id}
        secret = urllib.parse.parse_qs(parsed.query).get('secret_token')
        if secret:
            query['secret_token'] = secret[0]
        endpoint = 'https://api-v2.soundcloud.com/tracks/' + track_id + '?' + urllib.parse.urlencode(query)
        try:
            with urllib.request.urlopen(endpoint, timeout=10) as response:
                title = json.load(response).get('title')
            if _is_title(title):
                return title.strip()
        except (OSError, ValueError, TypeError, AttributeError):
            pass
    if host != 'api-v2.soundcloud.com':
        endpoint = 'https://soundcloud.com/oembed?' + urllib.parse.urlencode({'format': 'json', 'url': url})
        try:
            with urllib.request.urlopen(endpoint, timeout=10) as response:
                title = json.load(response).get('title')
            if _is_title(title):
                return title.strip()
        except (OSError, ValueError, TypeError, AttributeError):
            pass
        parts = [part for part in parsed.path.split('/') if part]
        if len(parts) >= 2 and parts[1] != 'sets':
            slug = urllib.parse.unquote(parts[1]).replace('-', ' ').replace('_', ' ').strip()
            if _is_title(slug):
                return slug + '（链接名称）'
    return ''


def start(raw_urls: str) -> None:
    urls = _split_urls(raw_urls)
    if not urls:
        raise ValueError("请输入歌单链接")
    with _lock:
        if _state["status"] == "scanning":
            raise RuntimeError("已有扫描正在进行")
        _cancel.clear()
        _state.update(status="scanning", playlists=[], checked=0, total=0, message="正在读取歌单…")
        _download_plan.clear()

    def worker() -> None:
        opts = {"quiet": True, "no_warnings": True, "skip_download": True,
                "socket_timeout": 15, "retries": 0, "extractor_retries": 0}
        try:
            for url in urls:
                if _cancel.is_set():
                    break
                playlist = None
                private_playlist = None
                try:
                    with yt_dlp.YoutubeDL({**opts, "extract_flat": "in_playlist"}) as ydl:
                        info = ydl.extract_info(url, download=False)
                    if not info:
                        raise ValueError("未返回歌单信息")
                    entries = info.get("entries")
                    if entries is None:
                        entries = [{"url": url, "title": info.get("title"), "id": info.get("id"), "_single_info": info}]
                    else:
                        entries = list(entries)
                    playlist = {"title": info.get("title") or "未命名歌单", "url": url, "tracks": []}
                    private_playlist = {"title": playlist["title"], "url": url, "tracks": []}
                    with _lock:
                        _state["playlists"].append(playlist)
                        _download_plan.append(private_playlist)
                        _state["total"] += len(entries)
                    for index, entry in enumerate(entries, 1):
                        if _cancel.is_set():
                            break
                        entry = entry or {}
                        track_url = _entry_url(entry)
                        entry_title = entry.get("title")
                        title = entry_title.strip() if _is_title(entry_title) else ''
                        _set(message=f"正在检查 {playlist['title']} · 第 {index}/{len(entries)} 首")
                        track = {"index": index, "title": title, "url": track_url,
                                 "status": "unknown", "reason": "无法获取曲目链接"}
                        active_client_id = None
                        detail = None
                        title_from_metadata = bool(title)
                        if track_url:
                            try:
                                detail = entry.get('_single_info')
                                if detail is None:
                                    with yt_dlp.YoutubeDL({**opts, "noplaylist": True}) as ydl:
                                        try:
                                            detail = ydl.extract_info(track_url, download=False)
                                        finally:
                                            # 即使音频提取因 DRM 失败，提取器也可能已取得有效的 client_id。
                                            if hasattr(ydl, 'get_info_extractor') and 'soundcloud.com' in (urllib.parse.urlsplit(track_url).hostname or '').lower():
                                                try:
                                                    extractor = ydl.get_info_extractor('Soundcloud')
                                                    active_client_id = getattr(extractor, '_CLIENT_ID', None)
                                                except Exception:
                                                    pass
                                if not detail:
                                    raise ValueError("服务未返回曲目信息")
                                detail_title = detail.get("title")
                                if _is_title(detail_title):
                                    track["title"] = detail_title.strip()
                                    title_from_metadata = True
                                track["url"] = detail.get("webpage_url") or track_url
                                if detail.get("has_drm") is True:
                                    track.update(status="restricted", reason="服务明确提示受 DRM 保护")
                                elif detail.get("formats") or detail.get("url"):
                                    track.update(status="available", reason="已获取音频信息，实际下载结果仍可能变化")
                                else:
                                    track.update(status="unknown", reason="未获取到可用音频信息")
                            except Exception as exc:
                                track["status"], track["reason"] = _reason(exc)
                        if not track['title']:
                            track['title'] = _lookup_title(track['url'], entry.get('id') or entry_title, active_client_id) or f'未获取歌曲名称（第 {index} 首）'
                        with _lock:
                            playlist["tracks"].append(track)
                            private_playlist['tracks'].append({**track, 'id': (detail or {}).get('id') or entry.get('id'),
                                                              'source_url': track_url, 'info': detail if track['status'] == 'available' else None,
                                                              'trusted_title': title_from_metadata})
                            _state["checked"] += 1
                except Exception as exc:
                    status, reason = _reason(exc)
                    is_single = '/sets/' not in urllib.parse.urlsplit(url).path
                    if playlist is None and status == 'restricted' and is_single:
                        name = _lookup_title(url, None) or '未获取歌曲名称（第 1 首）'
                        track = {'index': 1, 'title': name, 'url': url, 'status': status, 'reason': reason}
                        with _lock:
                            _state['playlists'].append({'title': name, 'url': url, 'tracks': [track]})
                            _download_plan.append({'title': name, 'url': url, 'tracks': [{**track, 'id': None,
                                                   'source_url': url, 'info': None, 'trusted_title': False}]})
                            _state['total'] += 1
                            _state['checked'] += 1
                        continue
                    with _lock:
                        if playlist is None or private_playlist is None:
                            _state["playlists"].append({"title": "歌单读取失败", "url": url, "tracks": [], "error": str(exc)[:400]})
                            _download_plan.append({"title": "歌单读取失败", "url": url, "tracks": [], "error": str(exc)[:400]})
                        else:
                            playlist['error'] = str(exc)[:400]
                            private_playlist['error'] = str(exc)[:400]
            _set(status="cancelled" if _cancel.is_set() else "finished", message="扫描已取消" if _cancel.is_set() else "扫描完成，请检查结果")
        except Exception as exc:
            _set(status="error", message=str(exc))

    threading.Thread(target=worker, daemon=True).start()


def cancel() -> None:
    _cancel.set()
