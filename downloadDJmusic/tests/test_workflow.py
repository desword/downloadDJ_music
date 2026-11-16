import time
import unittest
from unittest.mock import patch
from backend import workflow


class WorkflowTests(unittest.TestCase):
    def wait_for(self, status):
        for _ in range(100):
            if workflow.get_state()['status'] == status:
                return
            time.sleep(.02)
        self.fail(f'workflow did not reach {status}')

    def test_scan_automatically_starts_download(self):
        scan = {'status': 'finished', 'message': '', 'playlists': []}
        result = {'status': 'finished', 'error': ''}
        with patch.object(workflow.scanner, 'start'), patch.object(workflow.scanner, 'get_state', return_value=scan), \
             patch.object(workflow.downloader, 'is_running', return_value=False), \
             patch.object(workflow.downloader, 'start_download') as start, \
             patch.object(workflow.downloader, 'get_state', return_value=result):
            workflow.start('playlist', '/tmp/music', 'mp3')
            self.wait_for('finished')
            start.assert_called_once_with('playlist', '/tmp/music', 'mp3')

    def test_cancel_during_scan_prevents_download(self):
        scan = {'status': 'scanning', 'message': '', 'playlists': []}
        with patch.object(workflow.scanner, 'start'), patch.object(workflow.scanner, 'get_state', side_effect=lambda: scan.copy()), \
             patch.object(workflow.scanner, 'cancel', side_effect=lambda: scan.update(status='cancelled')), \
             patch.object(workflow.downloader, 'is_running', return_value=False), \
             patch.object(workflow.downloader, 'cancel_download'), \
             patch.object(workflow.downloader, 'start_download') as start, \
             patch.object(workflow.downloader, 'get_state', return_value={'status': 'idle'}):
            workflow.start('playlist', '/tmp/music', 'wav')
            self.assertTrue(workflow.cancel())
            self.wait_for('cancelled')
            start.assert_not_called()


if __name__ == '__main__': unittest.main()
