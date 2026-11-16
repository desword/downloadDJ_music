import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from backend import app as api


class OpenFolderTests(unittest.TestCase):
    def test_single_playlist_opens_actual_folder_in_finder(self):
        with tempfile.TemporaryDirectory() as root:
            folder = os.path.join(root, 'A_B')
            os.mkdir(folder)
            state = {'status': 'finished', 'download': {'download_path': root, 'playlist_total': 1, 'playlist_title': 'A/B'}}
            with patch.object(api.workflow, 'get_state', return_value=state), patch.object(api.sys, 'platform', 'darwin'), patch.object(api.subprocess, 'run') as launch:
                result = api.workflow_open_folder()
            self.assertEqual(result['path'], folder)
            self.assertEqual(launch.call_args.args[0], ['open', folder])
            self.assertTrue(launch.call_args.kwargs['check'])

    def test_multiple_playlists_open_parent_folder(self):
        with tempfile.TemporaryDirectory() as root:
            state = {'status': 'finished', 'download': {'download_path': root, 'playlist_total': 2, 'playlist_title': 'Set'}}
            with patch.object(api.workflow, 'get_state', return_value=state), patch.object(api.sys, 'platform', 'darwin'), patch.object(api.subprocess, 'run') as launch:
                self.assertEqual(api.workflow_open_folder()['path'], root)
            self.assertEqual(launch.call_args.args[0], ['open', root])

    def test_requires_finished_workflow(self):
        with patch.object(api.workflow, 'get_state', return_value={'status': 'downloading'}), patch.object(api.subprocess, 'run') as launch:
            with self.assertRaises(HTTPException) as error:
                api.workflow_open_folder()
            self.assertEqual(error.exception.status_code, 409)
            launch.assert_not_called()

    def test_missing_directory_is_reported(self):
        state = {'status': 'finished', 'download': {'download_path': '/this/path/does/not/exist'}}
        with patch.object(api.workflow, 'get_state', return_value=state):
            with self.assertRaises(HTTPException) as error:
                api.workflow_open_folder()
            self.assertEqual(error.exception.status_code, 404)


if __name__ == '__main__':
    unittest.main()
