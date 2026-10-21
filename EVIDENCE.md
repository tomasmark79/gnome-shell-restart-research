# Published historical evidence

The export contains **224 structured reports: 140 historically passed and 84
historically failed**. Three live/personal reports were excluded. Browse the
[report index](evidence/INDEX.md) for direct links to each exported result.

`evidence/manifest.json` lists exported structured reports, original SHA-256,
published SHA-256, historical pass/fail and per-report redaction counts.
`evidence/reports/` contains the sanitized reports themselves. Both failures
and successes are retained. The manifest records exclusions without disclosing
the names or contents of personal desktop evidence directories.

This is an export of prior runs, not a newly executed overnight suite. The
original source history is unavailable: this snapshot cannot be mapped exactly
to every historical run. Any source hashes embedded by an original test are
left in that report. The manifest hashes describe original versus redacted
report bytes; they are not a claim that the current source passed every run.

## Publication filter

The exporter includes `result.json` reports and top-level JSON controls with
an explicit boolean `passed` field. Directories marked live/personal are
excluded entirely. Free-text home paths, email addresses, private IPs, known
personal hostname and GitHub-token-shaped strings are redacted. Other native
IDs and paths, including Nix store paths, remain useful historical evidence.
This changes report bytes, so both original and published hashes are recorded.

Raw logs, screenshots, core dumps and VM disks are excluded. The original
private directory remains untouched. Export code is in tools/export-evidence.py;
it requires explicit paths and refuses to overwrite an existing output.

```sh
# Check this public export without the private originals:
python3 tools/verify-evidence.py

# For maintainers with a reviewed artifact corpus, export to a NEW directory:
python3 tools/export-evidence.py /path/to/private/artifacts \
  --output /path/to/new-export
```

The filter is deliberately narrow, not a general guarantee that arbitrary
input logs are safe to publish. Review each new corpus before public upload.
Never point the exporter at a directory of unrelated personal files.

See RESEARCH-GUIDE.md to interpret negative controls, historical limitations
and the difference between UI recovery and complete runtime replacement.
