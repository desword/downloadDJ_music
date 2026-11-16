import tempfile
import functools
import http.server
import threading
import time
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

import imageio_ffmpeg
import yt_dlp
from yt_dlp.postprocessor.ffmpeg import FFmpegExtractAudioPP
from backend import downloader, scanner


class FFmpegFallbackTests(unittest.TestCase):
    def test_uses_python_package_when_system_ffmpeg_missing(self):
        with patch.object(downloader.shutil, 'which', return_value=None):
            path = downloader._find_ffmpeg()
        self.assertEqual(path, imageio_ffmpeg.get_ffmpeg_exe())
        self.assertTrue(Path(path).is_file())

    def test_converts_audio_with_packaged_ffmpeg_and_no_ffprobe(self):
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'sample.wav'
            with wave.open(str(source), 'wb') as wav:
                wav.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
                wav.writeframes(b'\0\0' * 8000)
            with yt_dlp.YoutubeDL({'quiet': True, 'ffmpeg_location': ffmpeg}) as ydl:
                postprocessor = FFmpegExtractAudioPP(ydl, preferredcodec='mp3', preferredquality='192')
                self.assertTrue(postprocessor.available)
                self.assertFalse(postprocessor.probe_available)
                _, result = postprocessor.run({'filepath': str(source), 'ext': 'wav'})
            self.assertEqual(result['ext'], 'mp3')
            self.assertGreater(Path(result['filepath']).stat().st_size, 0)

    def test_scanned_download_uses_packaged_ffmpeg(self):
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'sample.wav'
            with wave.open(str(source), 'wb') as wav:
                wav.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
                wav.writeframes(b'\0\0' * 8000)
            handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=directory)
            server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                url = f'http://127.0.0.1:{server.server_port}/sample.wav'
                scanner.start(url)
                for _ in range(100):
                    if scanner.get_state()['status'] != 'scanning':
                        break
                    time.sleep(.05)
                self.assertEqual(scanner.get_state()['status'], 'finished')
                with patch.object(downloader, '_find_ffmpeg', return_value=ffmpeg), patch.object(downloader.cfg, 'load_config', return_value={'sleep_interval': 0}):
                    downloader.start_download(url, str(Path(directory) / 'out'), 'mp3', scan_plan=scanner.get_download_plan())
                    downloader._download_thread.join(timeout=15)
                self.assertEqual(downloader.get_state()['track_results'][0]['status'], 'ok')
                self.assertTrue(list((Path(directory) / 'out').rglob('*.mp3')))
            finally:
                server.shutdown()
                server.server_close()


if __name__ == '__main__': unittest.main()
