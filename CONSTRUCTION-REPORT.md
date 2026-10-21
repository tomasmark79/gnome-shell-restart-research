> Historical research report. Claims apply to its original experiment, not
> today's implementation. See [STATUS.md](STATUS.md) and
> [RESEARCH-GUIDE.md](RESEARCH-GUIDE.md) before interpreting results.

# Bounded UI construction and candidate identity

Classification: **SHELL RELOAD in the isolated headless stable build**.
This extends [PREPARATION-REPORT.md](PREPARATION-REPORT.md). The compositor,
original client connections, GJS context and explicit backend models survive.
The complete whole-Shell restart objective is still unfulfilled.

## Construction lifetime

Every native construction attempt has a monotonically increasing serial. Its
JS candidate owns cancellation and cleanup callbacks. Main checks the candidate
after asynchronous steps and before installing post-initialization services.
Layout captures its own candidate and rechecks cancellation after the inspected
monitor/background waits, before touching actors or completing startup.

Native code gives construction five seconds. Expiry requests cancellation;
JS disconnects pending background loading, settles owned monitor/background
waiters, removes its standalone startup actor and cover pane, and releases the
native window-group clip. Failure cleanup then uses the existing single
corrective-attempt protocol. The compositor and original clients stay alive.

`UiStarted` and `UiFailed` now require the candidate serial in addition to the
Shell connection's own sender. An old candidate cannot commit a newer attempt.
JS increments the committed UI generation only after native acceptance, closing
the timeout/acknowledgement race. This changes a private laboratory interface,
not a public GNOME API.

If cancellation produces no outcome within another two seconds, native code
records a terminal cancellation timeout and quarantines subsequent requests.
That fallback is implemented but its unresponsive-cleanup path has not yet been
exercised by a dedicated integration scenario. The passing cases below require
responsive cancellation and ordinary cleanup. Neither timer can interrupt a
blocked compositor/GJS main thread.

## Controlled async producers

`startup-wait` pauses Main after UI initialization but before post-initialization
services. `layout-wait` pauses background startup while its standalone stage
background remains alive. Both delay a controlled non-mutating completion for
seven seconds, exceeding the native deadline.

The late test completion deliberately survives ordinary UI source removal and
sends the obsolete candidate's success serial through the actual Shell
connection. It records native status before and after. Rejection must leave
serial, transaction state, commits, failures, activity, timeouts and request count
unchanged. With two timeouts, the first stale message must arrive while the
corrective candidate is still constructing, not merely after an idle refusal.

This is an explicit cancellation contract for selected waits. A Promise race
alone cannot undo arbitrary side effects or make every third-party callback safe.

## Resource defect exposed by the new gate

`construction-normal-1` and the first startup-timeout prototype passed existing
selected-object checks. Adding direct stage-child inventory then failed the
subsequent `construction-*-final` and `*-verified` runs on the first ordinary
generation: two `UIAreaIndicator` actors remained instead of one.

The hidden screencast area indicator belongs to ScreenshotUI but is parented
directly to the stage. Collecting ScreenshotUI did not destroy that separate
native actor. Teardown now destroys and clears it explicitly, and retirement
accounting observes its destroy signal and finalization independently. Stage
inventory must match the original baseline; the extra actor is not filtered out.

Preparation also refuses ScreenshotUI's active-screencast property before
reservation and at commit. This guard is supported by source inspection; a
real recording/screen-sharing migration test remains outstanding. Destroying
a privacy indicator does not preserve a recording and its user controls.

## Final evidence

All four final runs exited 0, reported `passed: true`, had zero post-baseline
diagnostic problems and removed their private profiles after descendant cleanup:

| Evidence directory | Scenario | Failures / corrective attempts / UI commits | Selected retired objects collected | Soak |
| --- | --- | --- | ---: | ---: |
| `artifacts/construction-startup-clean` | Two startup deadlines, then explicit recovery | 2 / 1 / 2 | 48 | 65.007 s |
| `artifacts/construction-layout-clean` | Background wait cancellation and automatic recovery | 1 / 1 / 3 | 48 | 65.008 s |
| `artifacts/construction-caller-clean` | Killed CLI, concurrency and post-construction fault | 1 / 1 / 3 | 48 | None |
| `artifacts/construction-preparation-clean` | Preparation deadline regression | 0 / 0 / 2 | 24 | None |

The first run recorded old serial 2 being rejected while native serial 3 was
active in `same-context-ui-starting`. Before/after native transaction fields
were identical. Old serial 3 was later rejected while serial 4 was ready. The
second run also rejected serial 2 after serial 3 became ready. Two construction
deadlines exhausted the automatic retry allowance; native state then stayed
terminal while original clients kept round-tripping, until an explicit third
request restored UI. None of these passing scenarios entered quarantine.

Every generation matched the original direct stage-child inventory: one hidden
`UIAreaIndicator` and one `uiGroup:UiActor`. The independent retired screencast
indicators were destroyed and collected, alongside the other selected targets.
Finalization and retention controls passed. Native types warmed once from 988
to 989, then stayed stable. The original time-accounting model, active transition
records and native clock source survived with no reload-time shutdown calls.

Original Wayland/X11 PIDs, socket FDs/inodes and native window IDs survived.
Text stayed unchanged until the deliberate final edits, whose predicted hashes
matched through the same native virtual keyboard. Compositor/XWayland identity,
window placement/workspaces/focus, tracked registrations and stage actions
remained stable. Menus, new client mapping and native Super/Escape worked.

For the two-deadline run, the original Wayland client was PID 2433612, socket
inode 7280606, surface 10; the original X11 client was PID 2433657, inode 7280610,
XID 2097156. Full records are in each run's JSON and client heartbeat files.
The desktop after layout cancellation (not exported: `artifacts/construction-layout-clean/desktop-after.png`)
and overview after two deadlines (not exported: `artifacts/construction-startup-clean/overview-after.png`)
were visually inspected.

All four used
`/nix/store/zamdfs21i1p7mlv43ndaji5q9i3xrkpv-gnome-shell-50.5/bin/.gnome-shell-wrapped`.
The final flake check passed, compilation used `-j16`, and local patches had no
fuzz, offset, failed-hunk or unexpected-end warnings. No private-runtime test
processes remained. Host Shell PID 1350942 still ran its original
`/nix/store/8m77m1b9n4z4lv00l7d5455lkfbqy5jg-gnome-shell-50.5/bin/.gnome-shell-wrapped`.
No live host Shell replacement, physical-output trial or NixOS activation occurred.

## Reproduce

```sh
nix build --cores 0 .#stable-shell --no-link
nix flake check --cores 0
nix develop --cores 0 .#stable -c python3 tests/isolated.py --reload-ui-in-place --owned-request --track-time --ui-failure twice --ui-failure-stage startup-wait --soak-seconds 65 --output artifacts/construction-local
```

Use `--ui-failure once --ui-failure-stage layout-wait` for cancellation with the
startup background alive. Choose a fresh evidence directory. Compilation uses
all available threads. The harness creates and removes only its private buses,
processes, virtual monitor and temporary profile. [README.md](README.md) records
enable/disable and optional result-link cleanup. No host activation is involved.

## Remaining scope

`construction-caller-safe` subsequently failed the selected-object gate after
an ordinary post-construction fault. The tagged heap traced a persistent emitter
through an `_initializeUI` closure into `candidate.cancelHandlers`, the old
layout and its tracked actors. `global.context` was missing from tracked root
emitters, and ordinary failures had not cancelled the candidate's handlers.
The registry now owns those context subscriptions, and all failed candidates
are cancelled, including non-timeout failures. Cancellation-hook errors are
recorded and prevent a corrective attempt with unproven cleanup.

The guards cover the inspected Main/Layout startup waits. General constructor,
service and callback ownership remains incomplete. Lock/authentication state,
notification/composition preservation, arbitrary extensions, recording/sharing
transitions, multiple monitors and physical devices still need full fixtures.
A blocked GJS runtime or crashing compositor needs a stronger restartable
boundary; the retained-context design cannot claim that recovery.

Implementation changes are in `flake.nix`, `shell/tgnome-runtime.h`,
`shell/runtimeInit.js`, `shell/stableMain.js`, `shell/stableRegistry.js`,
`shell/stableLayout.js`, `shell/construction-lifetime.patch`,
`extension/extension.js` and `tests/isolated.py`; README, PLAN and reports record
the scope. The subsequent [quarantine phase](QUARANTINE-REPORT.md) verifies
unresponsive cleanup and late explicit recovery. A complete VM fixture for
security-sensitive lock/authentication ownership remains to be built.
