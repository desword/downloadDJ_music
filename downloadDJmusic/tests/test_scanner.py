import time
import tempfile
import unittest
import io
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

    def test_numeric_title_uses_public_metadata_when_audio_restricted(self):
        class RestrictedYDL(FakeYDL):
            def extract_info(self, url, download=False):
                if url == 'playlist':
                    return {'title': 'Set', 'entries': [{'id': '2391881370', 'title': '2391881370', 'url': 'https://soundcloud.com/welkermusic/hot-girl-walk'}]}
                raise Exception('This video is DRM protected')

        with patch.object(scanner.yt_dlp, 'YoutubeDL', RestrictedYDL), \
             patch.object(scanner, '_get_soundcloud_client_id', return_value='client'), \
             patch.object(scanner.urllib.request, 'urlopen', return_value=io.BytesIO(b'{"title":"Hot Girl Walk (Original Mix)"}')):
            scanner.start('playlist')
            for _ in range(100):
                state = scanner.get_state()
                if state['status'] != 'scanning':
                    break
                time.sleep(.01)
        track = state['playlists'][0]['tracks'][0]
        self.assertEqual(track['title'], 'Hot Girl Walk (Original Mix)')
        self.assertEqual(track['status'], 'restricted')

    def test_title_fallback_labels_link_name(self):
        with patch.object(scanner, '_get_soundcloud_client_id', return_value=None), \
             patch.object(scanner.urllib.request, 'urlopen', side_effect=OSError('offline')):
            title = scanner._lookup_title('https://soundcloud.com/welkermusic/hot-girl-walk', '2391881370')
        self.assertEqual(title, 'hot girl walk（链接名称）')

    def test_numeric_id_without_metadata_does_not_appear_as_title(self):
        with patch.object(scanner, '_get_soundcloud_client_id', return_value=None):
            self.assertEqual(scanner._lookup_title('https://api-v2.soundcloud.com/tracks/2391881370', '2391881370'), '')

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

    def test_existing_track_is_skipped_after_reordering(self):
        class ReorderedYDL:
            def __init__(self, opts): self.opts = opts
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def extract_info(self, url, download=False):
                return {'title': 'My set', 'entries': [{'id': 'new', 'url': 'new', 'title': 'New'}, {'id': 'old', 'url': 'old', 'title': 'Old'}]}
            def download(self, urls):
                self_items.append(self.opts['playlist_items'])
                Path(directory, 'My set', '001 - New.mp3').write_bytes(b'new')
        self_items = []
        with tempfile.TemporaryDirectory() as directory:
            playlist = Path(directory) / 'My set'
            playlist.mkdir()
            (playlist / '001 - Old.mp3').write_bytes(b'old')
            with patch.object(downloader.yt_dlp, 'YoutubeDL', ReorderedYDL), patch.object(downloader.shutil, 'which', return_value='/usr/bin/ffmpeg'):
                downloader.start_download('playlist', directory, 'mp3')
                downloader._download_thread.join(timeout=5)
                state = downloader.get_state()
            self.assertEqual(self_items, ['1'])
            self.assertEqual(state['track_results'][1]['status'], 'skipped')
            self.assertEqual(downloader._load_download_index(str(playlist))['mp3:old'], '001 - Old.mp3')

    def test_index_matches_same_track_after_title_changes(self):
        class RenamedYDL:
            def __init__(self, opts): self.opts = opts
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def extract_info(self, url, download=False):
                return {'title': 'My set', 'entries': [{'id': '123', 'url': 'track', 'title': 'New title'}]}
            def download(self, urls): self.fail('should not download')
        with tempfile.TemporaryDirectory() as directory:
            playlist = Path(directory) / 'My set'
            playlist.mkdir()
            (playlist / '005 - Old title.mp3').write_bytes(b'old')
            downloader._save_download_index(str(playlist), {'mp3:123': '005 - Old title.mp3'})
            with patch.object(downloader.yt_dlp, 'YoutubeDL', RenamedYDL), patch.object(downloader.shutil, 'which', return_value='/usr/bin/ffmpeg'):
                downloader.start_download('playlist', directory, 'mp3')
                downloader._download_thread.join(timeout=5)
                state = downloader.get_state()
            self.assertEqual(state['status'], 'finished')
            self.assertEqual(state['track_results'][0]['status'], 'skipped')


if __name__ == '__main__':
    unittest.main()
