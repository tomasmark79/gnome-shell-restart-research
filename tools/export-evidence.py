#!/usr/bin/env python3
"""Export historical structured reports, excluding personal desktop evidence.

This is a conservative publication filter, not a general secret scanner.
Review the exported files before publishing a new corpus.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re


def digest(data):
    return hashlib.sha256(data).hexdigest()


def clean(value, counts):
    if isinstance(value, dict):
        return {key: clean(item, counts) for key, item in value.items()}
    if isinstance(value, list):
        return [clean(item, counts) for item in value]
    if not isinstance(value, str):
        return value
    for name, pattern, replacement in (
        ('homePaths', r'/home/[^\s\x22\x27<>]+', '<redacted-home-path>'),
        ('emails', r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', '<redacted-email>'),
        ('privateIPs', r'\b(?:192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+|172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+)\b', '<redacted-private-ip>'),
        ('hostName', r'\bnixon\b', '<redacted-host>'),
        ('tokens', r'gh[pousr]_[A-Za-z0-9_]{15,}', '<redacted-token>'),
    ):
        value, number = re.subn(pattern, replacement, value)
        counts[name] += number
    if 'PRIVATE KEY-----' in value:
        counts['privateKeys'] += 1
        return '<redacted-private-key-value>'
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('artifacts', type=Path)
    parser.add_argument('--output', type=Path, default=Path('evidence'))
    args = parser.parse_args()
    root = args.artifacts.resolve()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit('Use a fresh output directory; refusing to overwrite evidence')
    candidates = sorted(set(root.rglob('result.json')) | set(root.glob('*.json')))
    entries, skipped = [], []
    for path in candidates:
        relative = path.relative_to(root)
        if any('live' in part.lower() or 'personal' in part.lower() for part in relative.parts):
            skipped.append({'reason': 'personal/live evidence excluded'})
            continue
        raw = path.read_bytes()
        report = json.loads(raw)
        if not isinstance(report, dict) or not isinstance(report.get('passed'), bool):
            skipped.append({'reason': 'no explicit boolean passed field'})
            continue
        counts = Counter()
        sanitized = clean(report, counts)
        data = (json.dumps(sanitized, indent=2, ensure_ascii=True) + '\n').encode()
        target = output / 'reports' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        entries.append({
            'path': str(target.relative_to(output)),
            'passed': report['passed'],
            'classification': clean(report.get('classification'), Counter()),
            'originalSha256': digest(raw), 'publishedSha256': digest(data),
            'redactions': {key: count for key, count in counts.items() if count},
        })
    manifest = {
        'schemaVersion': 1,
        'kind': 'Historical evidence export, not a fresh test run',
        'sourceSnapshotMatchesEveryHistoricalRun': False,
        'counts': {'reports': len(entries),
                   'passed': sum(item['passed'] for item in entries),
                   'failed': sum(not item['passed'] for item in entries),
                   'excluded': len(skipped)},
        'reports': entries, 'exclusions': skipped,
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest['counts']))


if __name__ == '__main__':
    main()
