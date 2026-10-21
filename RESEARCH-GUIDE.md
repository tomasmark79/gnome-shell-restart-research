# Reading the experiments

This is a map of architectural approaches, not a reconstructed timestamped
commit history. Original reports retain their experimental scope and wording.

| Approach | Reports | What to learn |
| --- | --- | --- |
| Panel/UI ownership | PANEL-REPORT.md, OWNERSHIP-REPORT.md, OWNED-REPORT.md | Actor, registration and teardown boundaries |
| UI reconstruction in one runtime | STABLE-REPORT.md, PARTIAL-REPORT.md, CONSTRUCTION-REPORT.md | Partial construction, rollback and retained backends |
| Input and session integration | INPUT-REPORT.md, SECURITY-REPORT.md, VM-RELOAD-REPORT.md | Why a visible panel alone is insufficient |
| Lock races and quarantine | LOCK-RACE-REPORT.md, QUARANTINE-REPORT.md, DURABLE-LOCK-REPORT.md | Preparation/commit boundaries and failed cleanup |
| JS interruption | INTERRUPT-REPORT.md, SHELL-INTERRUPT-REPORT.md, PROTECTED-SCOPE-REPORT.md | Interruptible work versus unsafe native/backend boundaries |
| Alternative JS realms | REALM-REPORT.md, PANEL-REALM-REPORT.md, DATE-MENU-REALM-REPORT.md | Realm ownership without assuming native object isolation |
| Native context/type lifetime | NATIVE-CONTEXT-REPORT.md, NATIVE-CLOSURE-REPORT.md, NATIVE-SHELL-BOUNDARY-AUDIT.md | Static GTypes, vfuncs, callbacks and finalized contexts |
| Executable UI fallback | RECOVERY-ACCEPTANCE.md | Complete fallback acceptance, explicitly short of whole-runtime restart |
| Complete runtime replacement | FULL-CONTEXT-RECOVERY.md | Reattachment and lifetime bridges that overcame earlier blockers |

The archived HISTORICAL-README.md, HISTORICAL-STATUS.md, REPORT.md and PLAN.md
are useful context but are not the current project landing page or roadmap.

## Source map

`flake.nix` composes exact upstream patches and `.inc` fragments. `shell/` holds
the architecture variants and native reset supervisor. `tests/isolated.py`
starts a private compositor, bus/profile and client probes. `tests/probe.c`
measures live client state and connections. Native C++ probes separate small
GJS/GObject lifetime questions from full Shell integration. `tests/vm-*.py`
run in disposable NixOS guests. `tests/acceptance.py` verifies the UI fallback,
not a complete context restart.

## Evidence interpretation

A report's `passed` field refers to that experiment's acceptance contract.
For example, a negative control can pass by demonstrating the expected refusal
or failure. Inspect classification, diagnostics and the corresponding report.
Do not count all passing files as successful Shell restarts. Directory names
such as `final` and `verified` are historical labels, not global quality gates.

No public evidence file includes personal live-desktop snapshots. Raw logs,
screenshots, core dumps, VM images and private session data are not exported.
