# Export status — 2026-10-21

This repository preserves a research source snapshot and historical evidence.
It is not the latest deployment candidate. The current implementation is at
https://github.com/tomasmark79/gnome-shell-restart-nix.

## Established results

The research progressed from panel replacement to UI reconstruction in a
surviving runtime, and then to complete GjsContext replacement in a surviving
Mutter process. Isolated complete-context runs measured distinct epochs,
actual old-context finalization, unchanged client sockets and subsequent input.
VM tests separately exercised GDM/PAM/logind integration.

The implementation repository contains the newer five-cycle test evidence and
the subsequent hardware result: one updated complete-context replacement kept
all seven windows and their positions, and the user confirmed working custom
shortcuts. Hardware observations do not independently prove each client socket.

## Snapshot limitations

Historical reports use the original three-cycle and other acceptance contracts.
The research checkout also received later edits to remove the reset count limit;
some old tests still expect that limit. Such a test may fail against this source
snapshot even though its saved older report passed. Do not silently rewrite the
archive to turn a historical experiment into a current success claim.

The published implementation contains the corrected repeatability checks and
shortcut/environment fixes. Use it for a current complete recovery baseline.
No old report should be interpreted as an unqualified statement of today's
support or as recovery of a hung compositor.

Quick checks and evidence integrity are rerun during export. Heavy historical
experiments are not all rerun merely to publish this archive. Publication does
not activate a NixOS configuration or restart the running desktop.
