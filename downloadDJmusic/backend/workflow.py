"""后台串联扫描与下载，浏览器断开时任务也会继续。"""
import threading
import time
from typing import Any, Dict

from . import downloader, scanner

_lock = threading.Lock()
_cancel = threading.Event()
_state: Dict[str, Any] = {'status': 'idle', 'error': ''}


def start(url: str, download_path: str, audio_format: str) -> None:
    with _lock:
        if _state['status'] in ('scanning', 'downloading', 'cancelling') or downloader.is_running():
            raise RuntimeError('已有任务正在运行')
        scanner.start(url)
        _cancel.clear()
        _state.update(status='scanning', error='', download_started=False)

    def worker() -> None:
        try:
            while scanner.get_state()['status'] == 'scanning':
                time.sleep(.2)
            with _lock:
                scan = scanner.get_state()
                if _cancel.is_set() or scan['status'] == 'cancelled':
                    _state['status'] = 'cancelled'
                    return
                if scan['status'] == 'error':
                    _state.update(status='error', error=scan['message'])
                    return
                playlists = scan.get('playlists') or []
                scan_total = (sum(len(p.get('tracks') or []) for p in playlists)
                              if playlists and not any(p.get('error') for p in playlists) else None)
                downloader.start_download(url, download_path, audio_format, scan_total_tracks=scan_total)
                _state.update(status='downloading', download_started=True)
            while downloader.is_running():
                time.sleep(.2)
            with _lock:
                result = downloader.get_state()
                _state.update(status=result['status'], error=result.get('error', ''))
        except Exception as exc:
            with _lock:
                _state.update(status='error', error=str(exc))

    threading.Thread(target=worker, daemon=True).start()


def cancel() -> bool:
    with _lock:
        if _state['status'] not in ('scanning', 'downloading', 'cancelling'):
            return False
        _cancel.set()
        scanner.cancel()
        downloader.cancel_download()
        _state['status'] = 'cancelling'
        return True


def get_state() -> Dict[str, Any]:
    with _lock:
        state = _state.copy()
    state['scan'] = scanner.get_state()
    state['download'] = downloader.get_state() if state.get('download_started') else {}
    return state
