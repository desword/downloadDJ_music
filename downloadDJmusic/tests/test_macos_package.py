import importlib.util
import os
from pathlib import Path
import plistlib
import stat
import subprocess
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from backend import app

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('macos_builder', ROOT / 'scripts' / 'build_macos_app.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class MacPackageTests(unittest.TestCase):
    def test_zip_has_valid_bundle_executables_and_no_local_data(self):
        with tempfile.TemporaryDirectory() as output:
            archive = builder.build(Path(output))
            with zipfile.ZipFile(archive) as z:
                self.assertIsNone(z.testzip())
                names = z.namelist()
                prefix = 'DJ Deck.app/Contents/'
                plist = plistlib.loads(z.read(prefix + 'Info.plist'))
                self.assertEqual(plist['CFBundleExecutable'], 'DJ Deck')
                self.assertEqual(plist['CFBundlePackageType'], 'APPL')
                for name in (prefix + 'MacOS/DJ Deck', prefix + 'Resources/launch.command'):
                    self.assertTrue((z.getinfo(name).external_attr >> 16) & stat.S_IXUSR)
                self.assertIn(prefix + 'Resources/app/backend/app.py', names)
                self.assertNotIn(prefix + 'Resources/app/config.json', names)
                self.assertFalse(any('__pycache__' in name or '.venv' in name for name in names))
                self.assertEqual(z.read(prefix + 'Resources/AppIcon.icns')[:4], b'icns')

    def test_config_can_be_saved_outside_application_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / 'support' / 'config.json'
            code = 'from backend import config; config.save_config({"default_format":"mp3"}); print(config.load_config()["default_format"])'
            environment = os.environ.copy()
            environment['DJ_DECK_CONFIG'] = str(config_path)
            result = subprocess.run([sys.executable, '-c', code], cwd=ROOT, env=environment, text=True, capture_output=True, check=True)
            self.assertEqual(result.stdout.strip(), 'mp3')
            self.assertTrue(config_path.is_file())

    def test_health_identifies_the_existing_server(self):
        self.assertEqual(app.health(), {'application': 'DJ Deck', 'status': 'ready'})

    def test_missing_dependency_is_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            requirements = Path(directory) / 'requirements.txt'
            requirements.write_text('a-nonexistent-dj-deck-dependency==0.0.1\n')
            result = subprocess.run([sys.executable, ROOT / 'macos' / 'check_dependencies.py', requirements], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)


if __name__ == '__main__': unittest.main()
