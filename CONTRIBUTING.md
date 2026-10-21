# Contributing to the research companion

Keep new documentation and issues in English. Preserve historical reports and
their original language; make corrections in a clearly dated note rather than
rewriting an old failure into a successful result.

Use private compositor sessions and disposable VMs. Never weaken admission,
lock or callback-lifetime guards to make a test pass. Report builds, cached
results, fresh execution and live activation separately.

For each new experiment, state the hypothesis, exact source revision, nixpkgs
revision, command, expected control, observed result and architectural limit.
Keep failed runs that explain a result. Do not infer a whole Shell restart from
a panel redraw or from a new UI generation alone.

Run the quick checks in REPRODUCING.md. Code changes need the relevant isolated
test in addition to unit tests. Review exported evidence for personal data
before committing it; keep new raw artifacts under ignored artifacts/.

Current deployment fixes belong in gnome-shell-restart-nix. This repository
welcomes independently reproduced experiments, new negative controls, lifetime
analysis and ports with precise version boundaries. Preserve upstream license
notices and use contributions compatible with GPL-2.0-or-later.
