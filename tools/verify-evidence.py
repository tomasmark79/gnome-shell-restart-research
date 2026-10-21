#!/usr/bin/env python3
"""Validate published report integrity; does not rerun historical experiments."""
import argparse
import hashlib
import json
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path,
                        default=Path(__file__).resolve().parents[1] / 'evidence')
    root = parser.parse_args().evidence.resolve()
    manifest = json.loads((root / 'manifest.json').read_text())
    entries = manifest['reports']
    paths = set()
    for entry in entries:
        name = entry['path']
        path = root / name
        if name in paths or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError(f'Duplicate or escaping report path: {name}')
        paths.add(name)
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != entry['publishedSha256']:
            raise ValueError(f'Report hash mismatch: {name}')
        report = json.loads(data)
        if not isinstance(report.get('passed'), bool) or report['passed'] != entry['passed']:
            raise ValueError(f'Historical outcome mismatch: {name}')
    actual = {str(path.relative_to(root)) for path in (root / 'reports').rglob('*.json')}
    if actual != paths:
        raise ValueError('Manifest does not cover exactly the published reports')
    expected = {'reports': len(entries),
                'passed': sum(entry['passed'] for entry in entries),
                'failed': sum(not entry['passed'] for entry in entries),
                'excluded': len(manifest['exclusions'])}
    if manifest['counts'] != expected:
        raise ValueError('Manifest counts do not match its entries')
    print(json.dumps({'integrityVerified': True, **expected}))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, OSError) as error:
        sys.exit(str(error))
