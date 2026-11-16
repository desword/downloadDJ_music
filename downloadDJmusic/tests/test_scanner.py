import time
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import downloader, scanner


class FakeYDL:
    def __init__(self, opts):
        self.opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def extract_info(self, url, download=False):
        if url == 'playlist':
            return {'title': 'My set', 'entries': [
                {'url': 'ok', 'title': 'One'},
                {'url': 'drm', 'title': 'Two'},
                {'url': 'network', 'title': 'Three'},
                None,
            ]}
        if url == 'ok':
            return {'title': 'One', 'formats': [{'url': 'audio'}]}
        if url == 'drm':
            raise Exception('This video is DRM protected')
        raise Exception('HTTP Error 403: Forbidden')


class ScanTests(unittest.TestCase):
    def test_track_statuses_and_missing_entries(self):
        with patch.object(scanner.yt_dlp, 'YoutubeDL', FakeYDL):
            scanner.start('playlist')
            for _ in range(100):
                state = scanner.get_state()
                if state['status'] != 'scanning':
                    break
                time.sleep(.01)
        self.assertEqual(state['status'], 'finished')
        self.assertEqual((state['checked'], state['total']), (4, 4))
        tracks = state['playlists'][0]['tracks']
        self.assertEqual([t['status'] for t in tracks], ['available', 'restricted', 'unknown', 'unknown'])
        self.assertEqual([t['index'] for t in tracks], [1, 2, 3, 4])
        self.assertIn('403', tracks[2]['reason'])

    def test_missing_playlist_entries_preserve_indices_for_download(self):
        with patch.object(downloader.yt_dlp, 'YoutubeDL', FakeYDL):
            result = downloader.fetch_playlist_info('playlist')
        self.assertEqual(result['track_count'], 4)
        self.assertEqual(result['track_urls'], ['ok', 'drm', 'network', ''])

    def test_unavailable_playlist_is_reported(self):
        with patch.object(scanner.yt_dlp, 'YoutubeDL', FakeYDL):
            scanner.start('network')
            for _ in range(100):
                state = scanner.get_state()
                if state['status'] != 'scanning':
                    break
                time.sleep(.01)
        self.assertIn('403', state['playlists'][0]['error'])

    def test_replaced_track_with_same_index_is_downloaded(self):
        class ReplacementYDL:
            def __init__(self, opts):
                self.opts = opts
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def extract_info(self, url, download=False):
                return {'title': 'My set', 'entries': [{'url': 'new', 'title': 'New'}]}
            def download(self, urls):
                Path(self.opts['outtmpl'].replace('%(title)s', 'New').replace('%(ext)s', 'mp3')).write_bytes(b'new')

        with tempfile.TemporaryDirectory() as directory:
            playlist = Path(directory) / 'My set'
            playlist.mkdir()
            (playlist / '001 - Old.mp3').write_bytes(b'old')
            with patch.object(downloader.yt_dlp, 'YoutubeDL', ReplacementYDL), patch.object(downloader.shutil, 'which', return_value='/usr/bin/ffmpeg'):
                downloader.start_download('playlist', directory, 'mp3')
                downloader._download_thread.join(timeout=5)
                state = downloader.get_state()
            self.assertEqual(state['status'], 'finished')
            self.assertEqual(state['track_results'][0]['status'], 'ok')
            self.assertTrue((playlist / '001 - New.mp3').is_file())


if __name__ == '__main__':
    unittest.main()
