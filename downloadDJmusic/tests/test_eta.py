import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from backend import downloader
from backend.downloader import _estimate_remaining


class EstimateTests(unittest.TestCase):
    def test_first_track_estimates_total_without_completed_tracks(self):
        current, total = _estimate_remaining({'eta': 20, 'downloaded_bytes': 50, 'total_bytes': 100}, 0, 0, 4)
        self.assertEqual(current, 20)
        self.assertEqual(total, 140)

    def test_later_tracks_use_completed_average(self):
        current, total = _estimate_remaining({'eta': 12, '_percent_str': ' 50.0%'}, 2, 80, 3)
        self.assertEqual(current, 12)
        self.assertEqual(total, 92)

    def test_speed_and_elapsed_fallbacks(self):
        self.assertEqual(_estimate_remaining({'downloaded_bytes': 40, 'total_bytes_estimate': 100, 'speed': 10}, 0, 0, 2), (6, 16))
        self.assertEqual(_estimate_remaining({'_percent_str': '25%', 'elapsed': 10}, 0, 0, 1), (30, 30))

    def test_missing_or_invalid_data_does_not_invent_estimates(self):
        self.assertEqual(_estimate_remaining({'eta': None, '_percent_str': 'Unknown'}, 0, 0, 3), (None, None))
        self.assertEqual(_estimate_remaining({'eta': 12, '_percent_str': '50%'}, 0, 0, None), (12, None))
        self.assertEqual(_estimate_remaining({'eta': float('nan')}, 0, 0, 1), (None, None))

    def test_hook_includes_future_playlists_and_excludes_known_skips(self):
        snapshots = []
        class FakeYDL:
            def __init__(self, opts): self.opts = opts
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def extract_info(self, url, download=False):
                return {'title': 'Set', 'entries': [{'id': 'a', 'url': 'a', 'title': 'A'}, {'id': 'b', 'url': 'b', 'title': 'B'}]}
            def download(self, urls):
                hook = self.opts['progress_hooks'][0]
                hook({'status': 'downloading', 'info_dict': {'id': 'a', 'playlist_index': 1, 'title': 'A'}, 'eta': 20, 'downloaded_bytes': 50, 'total_bytes': 100, '_percent_str': '50%'})
                snapshots.append(downloader.get_state())
        with tempfile.TemporaryDirectory() as directory:
            playlist = Path(directory, 'Set')
            playlist.mkdir()
            (playlist / '002 - B.mp3').write_bytes(b'old')
            with patch.object(downloader.yt_dlp, 'YoutubeDL', FakeYDL), patch.object(downloader.shutil, 'which', return_value='/usr/bin/ffmpeg'):
                downloader.start_download('playlist', directory, 'mp3', scan_total_tracks=4)
                downloader._download_thread.join(timeout=5)
        self.assertEqual(snapshots[0]['track_eta_seconds'], 20)
        self.assertEqual(snapshots[0]['total_eta_seconds'], 100)


if __name__ == '__main__': unittest.main()
