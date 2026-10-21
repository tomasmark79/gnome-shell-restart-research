"""Publication boundary and tamper detection for historical evidence."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class EvidenceExportTest(unittest.TestCase):
    def test_redacts_nested_data_excludes_live_and_detects_tampering(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / 'source'
            raw = {'passed': False, 'contextsFinalized': 2,
                   'nested': [{'error': 'Cannot read /home/person/private.txt',
                               'email': 'example@example.invalid'}]}
            for name, report in [('isolated', raw), ('live-personal',
                                 {'passed': True, 'title': 'PRIVATE-WINDOW-TITLE'})]:
                directory = source / name
                directory.mkdir(parents=True)
                (directory / 'result.json').write_text(json.dumps(report))
            output = base / 'export'
            command = [sys.executable, str(ROOT / 'tools/export-evidence.py'),
                       str(source), '--output', str(output)]
            subprocess.run(command, check=True, capture_output=True)
            manifest = json.loads((output / 'manifest.json').read_text())
            self.assertEqual(manifest['counts'],
                             {'reports': 1, 'passed': 0, 'failed': 1, 'excluded': 1})
            entry = manifest['reports'][0]
            published = output / entry['path']
            text = published.read_text()
            self.assertNotIn('/home/person', text)
            self.assertNotIn('example@example.invalid', text)
            self.assertEqual(json.loads(text)['contextsFinalized'], 2)
            self.assertFalse(json.loads(text)['passed'])
            self.assertNotEqual(entry['originalSha256'], entry['publishedSha256'])
            original = source / 'isolated/result.json'
            self.assertEqual(hashlib.sha256(original.read_bytes()).hexdigest(),
                             entry['originalSha256'])
            self.assertIn('/home/person', original.read_text())
            self.assertFalse(any('live-personal' in str(p) for p in output.rglob('*')))
            verify = [sys.executable, str(ROOT / 'tools/verify-evidence.py'),
                      '--evidence', str(output)]
            subprocess.run(verify, check=True, capture_output=True)
            published.write_text(text + ' ')
            result = subprocess.run(verify, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('hash mismatch', result.stderr)
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('refusing to overwrite', result.stderr)
