> Historical research report. Claims apply to its original experiment, not
> today's implementation. See [STATUS.md](STATUS.md) and
> [RESEARCH-GUIDE.md](RESEARCH-GUIDE.md) before interpreting results.

# Recovery from an incomplete UI construction

Classification: **SHELL RELOAD in the isolated headless stable build**.
The compositor, original native client connections, GJS context and selected
backend models remain alive. This extends [OWNED-REPORT.md](OWNED-REPORT.md)
with failures before desktop construction is complete. It does not establish a
complete safe Shell restart or arbitrary exception-safe construction.

## Construction and retirement boundary

The previous controlled fault happened after a complete candidate UI was built.
The new checkpoints interrupt three earlier boundaries:

- `after-layout`: the new layout and native-window-group adoption exist, while
  overview, panel, keyboard and extension manager have not been constructed.
- `overview-constructor`: the plain JavaScript overview constructor has created
  its state and subscriptions but throws before assigning `Main.overview`.
  Layout, XDND handler and that unassigned overview are retirement targets.
- `after-panel`: panel and its indicators exist, while the keyboard, extension
  manager and time-limits manager have not yet been constructed.

Before building a replacement, UI globals are reset to null. Only explicitly
durable models remain. Cleanup uses optional access for managers absent from
an incomplete candidate. Retirement records include only objects that exist;
the harness checks the precise expected target set for each checkpoint. It
must not accidentally measure old objects through stale module globals.

A small candidate journal registers overview before its constructor can throw.
Failure capture observes this unassigned object through a FinalizationRegistry,
then clears the journal. Actor destruction, managed/root signal cleanup and
source/registration release still run before the corrective construction.
Independent collectible/retained controls remain mandatory. This journal is
specific to the instrumented overview constructor; it is not a claim that all
GNOME constructors have automatic exception-safe ownership.

## Bugs found by the new boundaries

`partial-panel-1` recovered UI, but failed the target-inventory assertion: the
keyboard had already been constructed. GNU patch had discarded a one-line
context with `fuzz` and moved the injected boundary past the next constructor.
All local lifecycle patches were regenerated with full context and now apply
with `--fuzz=0`. Build assertions verify the exact Main construction boundaries.
The source patch pipeline runs local patches after Nixpkgs' packaging patches;
Nixpkgs' own patch policy remains unchanged. An initial attempt to disable fuzz
for all upstream packaging patches failed at the Nixpkgs greeter-logo patch,
so that broader change was removed. The strict local build log has no local
fuzz, offset, failed-hunk or unexpected-end warnings.

`partial-layout-final` and `partial-constructor-final` then passed extended
65-second runs. `partial-panel-twice-final` failed the diagnostic gate despite
reconstructing a usable desktop: IBus replies reached an incomplete candidate
while `Main.keyboard` was null. This is an actual lifecycle defect exposed by
the earlier failure boundary, not a reason to relax diagnostics.

The input method now has an explicit UI disposal operation: cancel pending
context creation, disconnect backend subscriptions, release its keyboard binding
and destroy the IBus input context. A late asynchronous result checks disposal
and cancellation before adoption and destroys an obsolete returned context.
Keyboard binding can be deferred until the replacement exists, and successful
UI startup explicitly rebinds it. The candidate popup stays hidden while the
keyboard is absent. Failed-candidate cleanup disposes the input method before
other asynchronous work. Unhandled promise rejections now also fail the
integration diagnostic gate.
Failed-candidate handling also clears the native backend's input-method pointer
before disposing the candidate, so a terminal failed UI does not leave that
backend pointing at a deliberately disposed input method.
The first follow-up `partial-panel-safe-final` still failed: lookup-table and
focus-out handlers also called keyboard suggestion methods before that manager
existed. Those handlers now tolerate the explicitly absent keyboard, and failed
candidate cleanup disconnects and hides the candidate popup before destroying
the input context. This keeps native focus/context teardown from calling back
into an incomplete keyboard UI.

## Verified results on the final build

All four runs below exited 0, reported `passed: true`, had zero diagnostic
problems and removed their private profiles after descendant cleanup:

| Evidence directory | Injected boundary | Failures / automatic retries / commits | Selected retired UI objects collected | Soak |
| --- | --- | --- | ---: | ---: |
| `artifacts/partial-layout-verified` | After layout | 1 / 1 / 3 | 31 | No extended soak |
| `artifacts/partial-constructor-verified` | Inside overview constructor | 1 / 1 / 3 | 33 | 65 s |
| `artifacts/partial-panel-verified` | After panel, before keyboard | 2 / 1 / 2 | 36 | 65 s |
| `artifacts/partial-post-verified` | Post-construction regression | 1 / 1 / 3 | 40 | 65 s |

The two-failure case remained terminal at native `ui-failed` with stable counters
while original clients continued round-tripping. A third explicit native request
restored the UI; no uncontrolled retry loop occurred. The ordinary extension
endpoint is disabled in that terminal state, so recovery here still uses the
private native laboratory endpoint. The post-construction regression also
terminated the real CLI during owned preparation, rejected external start/cancel
and takeover calls, and accepted only one concurrent CLI request.

Each run preserved both original client PIDs, socket FDs/inodes, native window
IDs, text hashes until the deliberate final edits, window geometry/workspaces,
compositor/XWayland identity and tracked registration counts. Final text edits
through the original virtual keyboard matched their predicted hashes. Native
Super/Escape worked before and after; menus and late client mapping worked.
Collection and retention controls passed, including the unassigned failed
overview object. Native object types warmed from 988 to 989 once and stayed
stable; the GJS context was retained throughout.

For the constructor-failure run, original Wayland PID 2291554 retained socket
inode 6983569 and surface 10; original X11 PID 2291639 retained socket inode
6991230 and XID 2097156. The other identity records and original-client heartbeats
are in each run's `result.json`, `wayland.jsonl` and `x11.jsonl`.

All four used
`/nix/store/3lgljnbmwrk02yvw28gav36qk54jvn3c-gnome-shell-50.5/bin/.gnome-shell-wrapped`.
Its build log records `build flags: -j16`, and local patches have no fuzz,
offset, failed-hunk or unexpected-end warnings. The final flake check passed.
The desktop after constructor failure (not exported: `artifacts/partial-constructor-verified/desktop-after.png`)
and overview after two incomplete candidates (not exported: `artifacts/partial-panel-verified/overview-after.png`)
were visually inspected. No process with a private fixture runtime directory
remained after cleanup. Host Shell PID 1350942 still ran its original
`/nix/store/8m77m1b9n4z4lv00l7d5455lkfbqy5jg-gnome-shell-50.5/bin/.gnome-shell-wrapped`.

## Reproduction

Build without changing the live system:

```sh
nix build --cores 0 .#stable-shell --no-link
nix flake check --cores 0
```

Run the constructor-failure scenario in a fresh private fixture:

```sh
nix develop --cores 0 .#stable -c python3 tests/isolated.py --reload-ui-in-place --owned-request --ui-failure once --ui-failure-stage overview-constructor --soak-seconds 65 --output artifacts/partial-local
```

Select `after-layout` or `after-panel` for the other boundaries. Use
`--ui-failure twice` to exhaust the single automatic corrective attempt and
then require an explicit native request to restore the UI. Do not target a live
session bus. The existing harness creates and cleans its own temporary profile,
private buses, virtual monitor, compositor, clients and descendant processes.

## Remaining requirements

The tests inject exceptions at selected source boundaries. Failures during
other constructors, arbitrary partially initialized GObjects, teardown failure,
failed preparation after mutation, stuck asynchronous work and blocked GJS need
additional ownership/recovery design. A corrective reconstruction is not a
rollback to the original UI instance. Lock/authentication safety, physical
devices/outputs, notification-state preservation and third-party extensions
remain outside the verified scope. The native compositor has not been restarted.
No NixOS activation, host Shell replacement, logout or GDM restart is involved.

The implementation changes `flake.nix`, the three existing normalized lifecycle
patches, `shell/partial-startup.patch`, `shell/stableMain.js`,
`shell/stableIBus.js`, `shell/stableInputMethod.js`, the private extension and
`tests/isolated.py`. README, PLAN and the reports record the supported scope,
build workflow, evidence and remaining requirements.
