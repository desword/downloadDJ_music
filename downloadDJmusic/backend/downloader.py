"""下载核心逻辑模块：封装 yt-dlp 调用，支持歌单解析与批量下载。"""
import json
import os
import re
import shutil
import time
import threading
import tempfile
import urllib.request
from typing import Any, Dict, List, Optional

import yt_dlp

from . import config as cfg

# ffmpeg 目录（项目根目录下的 bin/）
BIN_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "bin",
)


def _load_download_index(directory: str) -> Dict[str, str]:
    try:
        with open(os.path.join(directory, '.dj-deck-downloads.json'), encoding='utf-8') as f:
            data = json.load(f)
        return {str(k): v for k, v in data.items() if isinstance(v, str) and os.path.basename(v) == v}
    except (OSError, ValueError, AttributeError):
        return {}


def _save_download_index(directory: str, index: Dict[str, str]) -> None:
    temp_path = None
    try:
        os.makedirs(directory, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=directory, delete=False) as f:
            temp_path = f.name
            json.dump(index, f, ensure_ascii=False)
        os.replace(temp_path, os.path.join(directory, '.dj-deck-downloads.json'))
    except OSError:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)

# 用于构建 playlist_items 字符串（支持范围格式 "1-5,7,9-11"）
def _build_playlist_items(indices: List[int]) -> str:
    if not indices:
        return ""
    ranges: List[str] = []
    start = indices[0]
    end = indices[0]
    for i in indices[1:]:
        if i == end + 1:
            end = i
        else:
            ranges.append(str(start) if start == end else f"{start}-{end}")
            start = i
            end = i
    ranges.append(str(start) if start == end else f"{start}-{end}")
    return ",".join(ranges)

# 格式化剩余时间（秒）→ "X分Y秒"
def _format_eta(seconds: float) -> str:
    if seconds <= 0:
        return ""
    if seconds < 60:
        return f"{int(seconds)}秒"
    elif seconds < 3600:
        return f"{int(seconds / 60)}分{int(seconds % 60)}秒"
    else:
        return f"{int(seconds / 3600)}小时{int((seconds % 3600) / 60)}分"

# 获取 SoundCloud API client_id（从 yt-dlp 缓存目录读取）
def _get_soundcloud_client_id() -> Optional[str]:
    """从 yt-dlp 缓存目录读取 soundcloud client_id。"""
    cache_paths = [
        os.path.join(os.path.expanduser("~"), ".cache", "yt-dlp", "soundcloud", "client_id.json"),
        os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "yt-dlp", "soundcloud", "client_id.json"),
    ]
    for path in cache_paths:
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                client_id = data.get("data") or data.get("client_id")
                if client_id:
                    return client_id
            except Exception:
                continue
    return None


# 通过 SoundCloud API 获取曲目真实标题（即使 DRM 曲目也能获取元数据）
def _fetch_soundcloud_track_title(track_id: str, client_id: Optional[str] = None) -> str:
    """调用 SoundCloud API 获取 track_id 对应的 title。失败返回空字符串。"""
    if not client_id:
        client_id = _get_soundcloud_client_id()
    if not client_id or not track_id:
        return ""
    url = f"https://api-v2.soundcloud.com/tracks/{track_id}?client_id={client_id}"
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data.get("title") or ""
    except Exception:
        return ""


# 从 SoundCloud URL 的 slug 提取曲目标题（用于 DRM 曲目无法获取标题时的回退）
def _title_from_url(url: str) -> str:
    """从 URL 提取可读标题：
       - 普通 URL: soundcloud.com/user/track-name → Track Name
       - API URL:   api-v2.soundcloud.com/tracks/12345 → Track#12345
    """
    if not url:
        return ""
    from urllib.parse import urlparse
    url = str(url)  # 确保是字符串
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    parts = [p for p in path.split("/") if p]
    # API URL 格式: tracks/1935098720 → 提取 ID
    if len(parts) >= 2 and parts[0].lower() == "tracks":
        track_id = parts[-1]
        if track_id.isdigit():
            # 先尝试通过 SoundCloud API 获取真实标题
            real_title = _fetch_soundcloud_track_title(track_id)
            if real_title:
                return real_title
            return f"Track#{track_id}"
    # 普通 URL 格式: user/track-slug → 提取 slug
    if len(parts) >= 2:
        slug = parts[-1]
        if slug and not slug.isdigit():
            return slug.replace("-", " ").title()
    return ""


class DownloadCancelled(Exception):
    """用户取消下载时抛出。"""


def _sanitize_filename(name: str) -> str:
    """清理 Windows 文件名中的非法字符。"""
    return re.sub(r'[<>:"/\\|?*]', "_", name).strip().rstrip(".") or "Unknown"


# 全局任务状态
_task_state: Dict[str, Any] = {
    "status": "idle",          # idle | parsing | downloading | finished | error | cancelled
    "current_track": 0,        # 1-based，当前歌单内正在下载的曲目序号
    "total_tracks": 0,         # 当前歌单的曲目总数
    "percent": "0%",           # 当前曲目下载百分比
    "current_title": "",
    "playlist_title": "",      # 当前歌单名
    "playlist_index": 0,       # 1-based，当前是第几个歌单
    "playlist_total": 0,       # 歌单总数
    "download_path": "",
    "message": "",             # 阶段提示文案
    "error": "",
    "eta": "",                 # 当前曲目剩余时间预估
    "track_results": [],       # [{index, title, status: "ok"|"failed"|"skipped", reason}]
}
_task_lock = threading.Lock()
_cancel_flag = threading.Event()
_download_thread: Optional[threading.Thread] = None


def _update_state(**kwargs: Any) -> None:
    with _task_lock:
        _task_state.update(kwargs)


def get_state() -> Dict[str, Any]:
    """获取当前任务状态的副本。"""
    with _task_lock:
        return _task_state.copy()


def reset_state() -> None:
    _cancel_flag.clear()
    _update_state(
        status="idle",
        current_track=0,
        total_tracks=0,
        percent="0%",
        current_title="",
        message="",
        playlist_title="",
        playlist_index=0,
        playlist_total=0,
        download_path="",
        error="",
        eta="",
        track_results=[],
    )


def is_running() -> bool:
    return _download_thread is not None and _download_thread.is_alive()


def _check_cancel() -> None:
    """统一取消检查点，被取消时抛出 DownloadCancelled。"""
    if _cancel_flag.is_set():
        raise DownloadCancelled()


def fetch_playlist_info(url: str) -> Dict[str, Any]:
    """用 flat 模式快速解析歌单（秒级），返回标题、曲目数与曲目 URL 列表。

    flat 模式下 entry 只有 id/url，不含 title/uploader/duration，
    但速度极快（1-2 秒），适合在下载前快速确定曲目数。

    返回: { "title": str, "track_count": int, "track_urls": [str] }
    """
    ydl_opts = {
        "extract_flat": "in_playlist",
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    if info is None:
        return {"title": "", "track_count": 0, "track_urls": []}

    # 兼容单曲输入（非 playlist 时 entries 为 None）
    raw_entries = info.get("entries")
    if raw_entries is None:
        return {
            "title": info.get("title") or "单曲",
            "track_count": 1,
            "track_urls": [url],
        }

    playlist_title = info.get("title") or info.get("id") or "未知歌单"
    track_urls: List[str] = []
    for entry in raw_entries:
        if entry is None:
            track_urls.append("")
            continue
        u = entry.get("url") or entry.get("id")
        track_urls.append(u or "")

    return {
        "title": playlist_title,
        "track_count": len(track_urls),
        "track_urls": track_urls,
    }


def _split_urls(raw: str) -> List[str]:
    """将用户输入的多个链接拆分为列表。

    支持英文分号 `;` 或换行（\\n / \\r\\n）分隔，自动去空白、去重、保序。
    """
    if not raw:
        return []
    # 统一换行符后按分号或换行拆分
    normalized = raw.replace("\r\n", "\n").replace("\r", "\n")
    parts = re.split(r"[;\n]", normalized)
    urls: List[str] = []
    seen = set()
    for p in parts:
        u = p.strip()
        if not u:
            continue
        if u in seen:
            continue
        seen.add(u)
        urls.append(u)
    return urls


def start_download(
    url: str,
    download_path: str,
    audio_format: str,
    playlist_title: str = "",
    track_count: int = 0,
) -> None:
    """在后台线程中启动下载任务。立即返回，进度通过 get_state() 查询。

    支持多个歌单链接（分号 `;` 或换行分隔），依次下载到各自歌单名子目录。
    流程：
      1. flat 快速解析歌单信息（秒级，用于 UI 显示标题和曲目数）
      2. 完整提取歌单元数据，检查已存在文件，构建待下载曲目列表
      3. 歌单级别下载（ydl.download([playlist_url])），yt-dlp 内部统一处理
    使用 playlist_items 跳过已存在文件，ignoreerrors 确保单首失败不影响后续。
    """
    global _download_thread

    if is_running():
        raise RuntimeError("已有下载任务正在运行")

    # 拆分多歌单链接
    urls = _split_urls(url)
    if not urls:
        raise RuntimeError("未提供有效的歌单链接")

    _cancel_flag.clear()
    reset_state()
    _update_state(download_path=download_path, playlist_total=len(urls))

    sleep_interval = int(cfg.load_config().get("sleep_interval", 2))

    def _worker() -> None:
        try:
            fmt = (audio_format or "wav").lower()
            if fmt not in ("wav", "mp3"):
                fmt = "wav"

            postprocessors: List[Dict[str, Any]] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": fmt,
                    "preferredquality": "0" if fmt == "wav" else "192",
                },
                {"key": "FFmpegMetadata"},
            ]

            base_opts: Dict[str, Any] = {
                "format": "bestaudio/best",
                "postprocessors": postprocessors,
                "sleep_interval": sleep_interval,
                "quiet": True,
                "no_warnings": True,
                "noprogress": True,
                "ignoreerrors": True,
            }
            binary = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
            if os.path.isfile(os.path.join(BIN_DIR, binary)):
                base_opts["ffmpeg_location"] = BIN_DIR
            elif not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
                raise RuntimeError("未找到 ffmpeg 或 ffprobe，请先运行安装脚本，或安装 FFmpeg 并确保它在 PATH 中")

            # 保留所有歌单的结果，下载结束后可以一起核对。
            all_results: List[Dict[str, Any]] = []
            # 外层循环：逐个歌单
            for pl_idx, pl_url in enumerate(urls, start=1):
                _check_cancel()

                # 阶段一：flat 快速解析歌单（秒级，用于 UI 显示标题和曲目数）
                _update_state(
                    status="parsing",
                    playlist_index=pl_idx,
                    message=f"正在获取第 {pl_idx}/{len(urls)} 个歌单信息...",
                    playlist_title="",
                    current_track=0,
                    total_tracks=0,
                    percent="0%",
                )
                playlist_info = fetch_playlist_info(pl_url)
                total = playlist_info["track_count"]
                playlist_title_resolved = playlist_info["title"]
                track_urls = playlist_info["track_urls"]

                _check_cancel()
                if total == 0:
                    _update_state(
                        status="downloading",
                        playlist_title=playlist_title_resolved,
                        playlist_index=pl_idx,
                        message=f"歌单「{playlist_title_resolved}」无可下载曲目，跳过",
                    )
                    continue

                playlist_dir = _sanitize_filename(playlist_title_resolved)

                # 阶段二：full 提取获取曲目名（可获取的用 full 提取，DRM 曲目用 URL slug 回退）
                _update_state(
                    status="parsing",
                    playlist_index=pl_idx,
                    playlist_title=playlist_title_resolved,
                    total_tracks=total,
                    message=f"正在解析歌单「{playlist_title_resolved}」曲目名称...",
                )
                _check_cancel()

                # 扫描已存在文件
                existing_files: set = set()
                pl_dir_path = os.path.join(download_path, playlist_dir)
                if os.path.isdir(pl_dir_path):
                    for fname in os.listdir(pl_dir_path):
                        existing_files.add(fname)
                download_index = _load_download_index(pl_dir_path)

                # full 提取获取曲目标题（ignoreerrors 让 DRM 曲目返回 None）
                full_extract_opts: Dict[str, Any] = {
                    "quiet": True,
                    "no_warnings": True,
                    "skip_download": True,
                    "ignoreerrors": True,
                    "extract_flat": False,
                }
                full_titles: Dict[int, str] = {}  # {index: title}
                full_ids: Dict[int, str] = {}
                try:
                    with yt_dlp.YoutubeDL(full_extract_opts) as ydl_full:
                        full_info = ydl_full.extract_info(pl_url, download=False)
                    entries = list(full_info.get("entries") or []) if full_info else []
                    if full_info and full_info.get("entries") is None:
                        entries = [full_info]
                    for i, entry in enumerate(entries, start=1):
                        if entry is not None:
                            full_titles[i] = entry.get("title") or ""
                            if entry.get('id'):
                                full_ids[i] = str(entry['id'])
                except Exception:
                    pass

                # 构建 track_results：full 提取标题 + URL slug 回退
                track_results: List[Dict[str, Any]] = []
                items_to_download: List[int] = []
                skipped_count = 0
                title_counts: Dict[str, int] = {}
                for known in full_titles.values():
                    if known:
                        title_counts[known] = title_counts.get(known, 0) + 1

                for i in range(1, total + 1):
                    # 获取标题：优先 full 提取，其次 URL slug
                    title = full_titles.get(i, "")
                    if not title and i <= len(track_urls):
                        title = _title_from_url(track_urls[i - 1])
                    if not title:
                        title = f"第 {i} 首"

                    # 相同序号不代表同一首歌：歌单可能已被用户替换。
                    known_title = full_titles.get(i, "")
                    track_id = full_ids.get(i, '')
                    index_key = f'{fmt}:{track_id}' if track_id else ''
                    indexed_name = download_index.get(index_key, '')
                    existing_name = indexed_name if indexed_name in existing_files else ''
                    # 旧版没有索引时，用完整标题匹配，允许序号变化。
                    if not existing_name and known_title and title_counts[known_title] == 1:
                        suffix = ' - ' + yt_dlp.utils.sanitize_filename(known_title) + f'.{fmt}'
                        candidates = [f for f in existing_files if re.match(r'^\d{3,} - ', f) and f.endswith(suffix)
                                      and not any(v == f and k != index_key for k, v in download_index.items())]
                        if len(candidates) == 1:
                            existing_name = candidates[0]
                    if existing_name:
                        if index_key:
                            download_index[index_key] = existing_name
                            _save_download_index(pl_dir_path, download_index)
                        skipped_count += 1
                        track_results.append({
                            "index": i, "title": title,
                            "status": "skipped", "reason": "已存在",
                        })
                    else:
                        items_to_download.append(i)
                        track_results.append({
                            "index": i, "title": title,
                            "status": "pending", "reason": "",
                        })

                for track in track_results:
                    track["playlist_title"] = playlist_title_resolved
                all_results.extend(track_results)
                _update_state(track_results=all_results)
                _check_cancel()

                if not items_to_download:
                    _update_state(
                        status="downloading",
                        playlist_title=playlist_title_resolved,
                        playlist_index=pl_idx,
                        total_tracks=total,
                        current_track=total,
                        percent="100%",
                        message=f"歌单「{playlist_title_resolved}」全部曲目已存在，跳过",
                    )
                    continue

                # 阶段三：歌单级别下载，带 ETA 计算
                _update_state(
                    status="downloading",
                    total_tracks=total,
                    playlist_title=playlist_title_resolved,
                    playlist_index=pl_idx,
                    current_track=items_to_download[0],
                    percent="0%",
                    message=f"已跳过 {skipped_count} 首已存在，开始下载剩余 {len(items_to_download)} 首...",
                    error="",
                )

                output_template = os.path.join(
                    download_path,
                    playlist_dir,
                    ("001 - %(title)s.%(ext)s" if total == 1
                     else "%(playlist_index)03d - %(title)s.%(ext)s"),
                )

                # ETA 统计：记录每首完成时间，估算总剩余时间
                first_download_time: float = 0.0
                completed_tracks: int = 0
                observed_titles: Dict[int, str] = {}
                def progress_hook(d: Dict[str, Any]) -> None:
                    nonlocal first_download_time, completed_tracks
                    if _cancel_flag.is_set():
                        raise DownloadCancelled()
                    info = d.get("info_dict") or {}
                    if info.get("title"):
                        observed_titles[info.get("playlist_index") or 1] = info["title"]
                    if d["status"] == "downloading":
                        if first_download_time == 0:
                            first_download_time = time.time()
                        pct = d.get("_percent_str", "0%")
                        pct = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", pct).strip()
                        pl_track_idx = info.get("playlist_index") or 0
                        pl_track_count = info.get("playlist_count") or total
                        title = info.get("title", "")

                        # 计算 ETA：已完成曲目的平均耗时 × 剩余曲目数
                        eta_str = ""
                        if completed_tracks > 0 and first_download_time > 0:
                            elapsed = time.time() - first_download_time
                            avg_per_track = elapsed / completed_tracks
                            # 当前曲目剩余 + 剩余曲目
                            try:
                                current_pct = float(pct.replace("%", "")) / 100.0
                            except ValueError:
                                current_pct = 0.5
                            remaining_current = avg_per_track * (1.0 - current_pct)
                            remaining_others = avg_per_track * (pl_track_count - pl_track_idx)
                            total_eta = remaining_current + remaining_others
                            eta_str = _format_eta(total_eta)

                        _update_state(
                            percent=pct,
                            current_title=title or f"第 {pl_track_idx}/{pl_track_count} 首",
                            current_track=pl_track_idx,
                            total_tracks=pl_track_count,
                            playlist_index=pl_idx,
                            playlist_title=playlist_title_resolved,
                            status="downloading",
                            eta=eta_str,
                        )
                    elif d["status"] == "finished":
                        completed_tracks += 1
                        pl_track_idx = info.get("playlist_index") or 0
                        title = info.get("title", "")
                        _update_state(
                            current_track=pl_track_idx,
                            percent="100%",
                            current_title=title or f"第 {pl_track_idx} 首",
                            eta="",
                        )

                playlist_items = _build_playlist_items(items_to_download)

                opts = dict(base_opts)
                opts["outtmpl"] = output_template
                opts["progress_hooks"] = [progress_hook]
                opts["playlist_items"] = playlist_items

                def postprocessor_hook(data: Dict[str, Any]) -> None:
                    if data.get('status') != 'finished' or data.get('postprocessor') != 'FFmpegMetadata':
                        return
                    info = data.get('info_dict') or {}
                    track_id = info.get('id')
                    filepath = info.get('filepath') or ''
                    if track_id and os.path.isfile(filepath) and os.path.dirname(os.path.abspath(filepath)) == os.path.abspath(pl_dir_path) and filepath.lower().endswith('.' + fmt):
                        download_index[f'{fmt}:{track_id}'] = os.path.basename(filepath)
                        _save_download_index(pl_dir_path, download_index)

                opts['postprocessor_hooks'] = [postprocessor_hook]

                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([pl_url])

                # 下载完成后匹配结果
                existing_files = set()
                if os.path.isdir(pl_dir_path):
                    for fname in os.listdir(pl_dir_path):
                        existing_files.add(fname)

                for tr in track_results:
                    if tr["status"] in ("pending", "unknown"):
                        idx = tr["index"]
                        prefix = f"{idx:03d} - "
                        expected_title = observed_titles.get(idx) or full_titles.get(idx, "")
                        if total == 1 and not expected_title:
                            expected_title = playlist_title_resolved
                        expected_name = (prefix + yt_dlp.utils.sanitize_filename(expected_title) + "." + fmt
                                         if expected_title else "")
                        found = bool(expected_name and expected_name in existing_files)
                        if found:
                            tr["status"] = "ok"
                            tr["reason"] = ""
                            if full_ids.get(idx):
                                download_index[f'{fmt}:{full_ids[idx]}'] = expected_name
                                _save_download_index(pl_dir_path, download_index)
                        else:
                            tr["status"] = "failed"
                            tr["reason"] = "下载失败，请检查网络、权限或服务限制"
                _update_state(track_results=all_results)

                _check_cancel()

            if _cancel_flag.is_set():
                _update_state(status="cancelled")
            else:
                _update_state(
                    status="finished",
                    percent="100%",
                    current_track=_task_state.get("total_tracks", 0),
                )
        except DownloadCancelled:
            _update_state(status="cancelled")
        except Exception as e:  # noqa: BLE001
            _update_state(status="error", error=str(e))

    _download_thread = threading.Thread(target=_worker, daemon=True)
    _download_thread.start()


def cancel_download() -> bool:
    """请求取消当前下载任务。返回是否成功发起取消。

    设置取消标志后，下载循环会在下一首开始前或当前首的进度回调中
    检测到并抛出 DownloadCancelled，秒级内停止。
    """
    if not is_running():
        return False
    _cancel_flag.set()
    return True
