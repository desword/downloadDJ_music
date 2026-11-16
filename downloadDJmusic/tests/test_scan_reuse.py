import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import downloader, scanner
import yt_dlp


class ReuseTests(unittest.TestCase):
    def test_reuses_audio_info_and_skips_protected_track(self):
        calls = []
        class FakeYDL:
            def __init__(self, opts): self.opts = opts
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def process_ie_result(self, info, download=True):
                calls.append(('cached', info['id']))
                path = Path(self.opts['outtmpl'].replace('%(title)s', info['title']).replace('%(ext)s', 'mp3'))
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'audio')
            def extract_info(self, url, download=True):
                calls.append(('extract', url))
                path = Path(self.opts['outtmpl'].replace('%(title)s', 'Retried').replace('%(ext)s', 'mp3'))
                self.opts['progress_hooks'][0]({'status': 'downloading', 'info_dict': {'title': 'Retried'}, 'eta': 10, '_percent_str': '50%'})
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'audio')
        plan = [{'url': 'playlist', 'title': 'Set', 'tracks': [
            {'index': 1, 'title': 'Playable', 'status': 'available', 'source_url': 'playable', 'id': 'a', 'trusted_title': True, 'info': {'id': 'a', 'title': 'Playable', 'url': 'signed'}},
            {'index': 2, 'title': 'Protected', 'status': 'restricted', 'source_url': 'protected', 'reason': 'DRM'},
            {'index': 3, 'title': 'Unknown', 'status': 'unknown', 'source_url': 'unknown', 'info': None},
        ]}]
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(downloader.yt_dlp, 'YoutubeDL', FakeYDL), patch.object(downloader.shutil, 'which', return_value='/usr/bin/ffmpeg'):
                downloader.start_download('playlist', directory, 'mp3', scan_plan=plan)
                downloader._download_thread.join(timeout=5)
                state = downloader.get_state()
            self.assertEqual(state['status'], 'finished')
            self.assertEqual([x['status'] for x in state['track_results']], ['ok', 'restricted', 'ok'])
            self.assertEqual(calls, [('cached', 'a'), ('extract', 'unknown')])
            self.assertTrue((Path(directory) / 'Set' / '001 - Playable.mp3').exists())
            self.assertTrue((Path(directory) / 'Set' / '003 - Retried.mp3').exists())

    def test_expired_cached_link_is_refreshed_once(self):
        calls = []
        class FakeYDL:
            def __init__(self, opts): self.opts = opts
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def process_ie_result(self, info, download=True):
                calls.append('cached')
                raise yt_dlp.utils.DownloadError('HTTP Error 403: Forbidden')
            def extract_info(self, url, download=True):
                calls.append('refresh')
                path = Path(self.opts['outtmpl'].replace('%(title)s', 'Song').replace('%(ext)s', 'mp3'))
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'audio')
        plan = [{'url': 'playlist', 'title': 'Set', 'tracks': [{'index': 1, 'title': 'Song', 'status': 'available', 'source_url': 'song', 'id': '1', 'info': {'id': '1', 'title': 'Song'}}]}]
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(downloader.yt_dlp, 'YoutubeDL', FakeYDL), patch.object(downloader.shutil, 'which', return_value='/usr/bin/ffmpeg'):
                downloader.start_download('playlist', directory, 'mp3', scan_plan=plan)
                downloader._download_thread.join(timeout=5)
                state = downloader.get_state()
            self.assertEqual(calls, ['cached', 'refresh'])
            self.assertEqual(state['track_results'][0]['status'], 'ok')

    def test_scan_media_urls_stay_out_of_public_state(self):
        class FakeYDL:
            def __init__(self, opts): pass
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def extract_info(self, url, download=False):
                if url == 'playlist':
                    return {'title': 'Set', 'entries': [{'id': '1', 'title': 'Song', 'url': 'song'}]}
                return {'id': '1', 'title': 'Song', 'formats': [{'url': 'https://example.com/audio?signature=private'}]}
        import time
        with patch.object(scanner.yt_dlp, 'YoutubeDL', FakeYDL):
            scanner.start('playlist')
            for _ in range(100):
                state = scanner.get_state()
                if state['status'] != 'scanning': break
                time.sleep(.01)
            plan = scanner.get_download_plan()
        self.assertNotIn('signature=private', str(state))
        self.assertIn('signature=private', str(plan))

    def test_protected_single_track_is_marked_for_skip(self):
        class FakeYDL:
            def __init__(self, opts): pass
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def extract_info(self, url, download=False):
                raise Exception('This video is DRM protected')
        import time
        with patch.object(scanner.yt_dlp, 'YoutubeDL', FakeYDL), patch.object(scanner, '_lookup_title', return_value='Song'):
            scanner.start('https://soundcloud.com/user/song')
            for _ in range(100):
                state = scanner.get_state()
                if state['status'] != 'scanning': break
                time.sleep(.01)
            plan = scanner.get_download_plan()
        self.assertEqual(state['playlists'][0]['tracks'][0]['status'], 'restricted')
        self.assertEqual(plan[0]['tracks'][0]['status'], 'restricted')


if __name__ == '__main__': unittest.main()
