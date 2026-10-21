# GNOME Shell restart research

Experiments, failed approaches and isolated test evidence behind
[gnome-shell-restart-nix](https://github.com/tomasmark79/gnome-shell-restart-nix).
This repository is the research companion; use the linked implementation for
the current NixOS module and cooperative complete-context restart.

The work targets GNOME Shell/Mutter 50.5, GJS 1.88.1 and SpiderMonkey 140 on
x86_64 Linux, pinned by flake.lock. It investigates how to replace Shell UI and
eventually its complete JavaScript runtime without replacing Mutter or
disconnecting existing Wayland/XWayland clients.

## What is here

- Original isolated compositor harness, client probes and native GObject/GJS
  controls, including interrupt, realm, static-type and callback experiments.
- Nix builds for alternative architectures and VM tests of lock/authentication,
  failed construction, quarantine and recovery.
- Sanitized historical structured reports, with both passing and failing runs.
- Original research reports, retained in their original Czech/English language.
  They describe the state at their own experimental stage, not current support.

Start with [RESEARCH-GUIDE.md](RESEARCH-GUIDE.md), then
[REPRODUCING.md](REPRODUCING.md) and [EVIDENCE.md](EVIDENCE.md).

## Read the historical claims carefully

A successful UI reconstruction is **not** a complete Shell runtime restart.
Early reports found static GTypes and native callbacks prevented context
replacement. Later GType reattachment and native lifetime bridges addressed
those specific blockers. The implementation repository subsequently added
external-shortcut preservation and login PATH fixes, which this older source
snapshot does not include.

The original checkout had no usable Git history when this export was made.
This repository therefore does not invent historical commits or claim that its
single source snapshot reproduces every earlier run byte for byte. Report
hashes and any embedded source fingerprints are retained where available.
See [STATUS.md](STATUS.md) for the exact boundary.

## Quick checks

```sh
git clone https://github.com/tomasmark79/gnome-shell-restart-research.git
cd gnome-shell-restart-research
python3 tools/verify-evidence.py
python3 -m unittest discover -s tests -p 'test_*.py'
nix flake check --no-build
```

Nix with flakes is required for the builds. Native VM tests additionally need
x86_64 Linux with usable KVM. See the reproduction guide before expensive runs.
All desktop experiments must run in their private compositor or VM; do not
point the harness at an active personal session.

## Continue the work

Contributions that explain a failure, independently reproduce a result or
improve lifetime boundaries are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).
New implementation fixes belong primarily in the implementation repository;
architecture experiments and reproducible negative controls fit here.

This is independent experimental work, not an official GNOME feature.
Project contributions are GPL-2.0-or-later; see LICENSE and NOTICE.md for
upstream attribution and licensing.
