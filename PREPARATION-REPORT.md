> Historical research report. Claims apply to its original experiment, not
> today's implementation. See [STATUS.md](STATUS.md) and
> [RESEARCH-GUIDE.md](RESEARCH-GUIDE.md) before interpreting results.

# Preparation ownership and cancellation

Classification: **SHELL RELOAD in the isolated headless stable build**.
This extends [PARTIAL-REPORT.md](PARTIAL-REPORT.md). The original compositor,
GJS context, client connections and selected session models remain alive.
It does not implement restart of the Shell process or recovery from blocked GJS.

## Why the preparation boundary changed

GNOME 50.5's `TimeLimitsManager.shutdown()` stops its state machine before
awaiting history I/O: it removes clock/timer subscriptions and login-user state,
releases its inhibitor, sets `DISABLED` and adds an inactive transition. This
model accounts for a login session, whereas `TimeLimitsDispatcher` presents UI.
Stopping/recreating the model on each desktop UI reload changed session state
and introduced asynchronous mutation before the reconstruction was scheduled.

The stable build now retains one backend time-limits manager. Its clock sources
receive backend ownership even when created after an asynchronous continuation.
Its actual native `shutdown` handler retains upstream's final history flush.
UI reset no longer invokes that flush. The UI dispatcher is still replaced,
explicitly destroyed once and included in selected retirement targets. The
headless fixture can enable real usage history with `--track-time`; it checks
native model identity, active state, transition records, login-user readiness
and zero shutdown calls across reconstructions.

## Native reservation and synchronous commit

The Shell connection reserves a native transaction with a five-second deadline.
Only non-mutating asynchronous preparation occurs while that lease is active.
Native expiry ends the reservation and rejects the Shell coordinator's pending
wait. Cancellation does not require the original CLI to remain alive.

`StartUiReload` now validates the deadline, stops its timer, invokes a fixed
Shell-owned commit callback synchronously, and schedules reconstruction before
returning. The callback rechecks idle/unlocked mode, captures retirement targets,
releases keybindings and disables the old controller. There is no asynchronous
gap between those UI changes and native scheduling. This supersedes the earlier
owned coordinator's separate prepare-then-start boundary.

A failure before mutation returns an error, releases the reservation and leaves
the original UI active. Once release has begun, controlled failures after
keybindings or controller disable complete the idempotent release and proceed
with reconstruction. The acknowledgement records `forwardRecovered` and a
string-only preparation error. This is corrective reconstruction, not rollback
to the previous UI instance. An unexpected failure of the corrective release
itself remains an explicit terminal failure; arbitrary exception safety is not
established by these checkpoints.

The five-second deadline requires a responsive native/GJS event loop. It cannot
interrupt a blocked JavaScript function or recover the process hosting Mutter.
The controlled stall is a pending, non-mutating async wait, with a deliberately
late completion. A real operation with side effects would need its own
cancellation/ownership contract; racing its Promise against a timeout would
not by itself make that operation safe.

## Failures found while testing

`preparation-model-1` failed because the shared teardown helper ran twice and
destroyed the dispatcher twice. Its release is now guarded by the live manager
reference and is idempotent across the two teardown calls.

`preparation-model-2`, `preparation-before-1` and `preparation-bindings-1` passed
short runs. `preparation-stall-1` demonstrated deadline expiry, unchanged old UI,
late completion without a stale commit, and successful subsequent reconstruction,
but failed the diagnostic gate. A notification policy had already disposed its
native GObject while managed signal tracking still referenced that emitter.

Notification policies now emit a registered `destroy` signal before disposal,
so signal tracking disconnects while the emitter is still valid. A separate
policy-retirement exercise destroys a policy before its callback owner and
requires a clean diagnostic gate. The test does not rely on a randomly arriving
notification to reproduce this ownership defect.

## Final evidence

All seven final runs exited 0, reported `passed: true`, had zero post-baseline
diagnostic problems and removed their private profiles after descendant cleanup:

| Evidence directory | Scenario | UI commits | Selected retired UI objects collected | Recorded soak |
| --- | --- | ---: | ---: | ---: |
| `artifacts/preparation-before-final` | Refuse before mutation | 2 | 22 | None |
| `artifacts/preparation-stall-final` | Deadline and late completion | 2 | 22 | 65.007 s |
| `artifacts/preparation-bindings-final` | Error after keybinding release | 3 | 33 | 65.007 s |
| `artifacts/preparation-disable-final` | Error after controller disable | 3 | 33 | 65.008 s |
| `artifacts/preparation-partial-final` | Two failures before keyboard construction | 2 | 38 | 65.007 s |
| `artifacts/preparation-caller-final` | Killed CLI, concurrency and one UI fault | 3 | 44 | None |
| `artifacts/preparation-clock-final` | Follow-up native clock-source check | 3 | 33 | None |

The timeout returned an error after 5.051 seconds. Native state was terminal
`ui-preparation-timeout`, inactive, with one preparation failure/timeout and zero
UI commits. The original UI generation, build serial, desktop, time-limits model,
registrations, stage actions and retirement records stayed unchanged. The harness
waited for the original seven-second operation to complete late, observed its
completion counter, and required native transaction status to remain unchanged.
The old panel and window menus still worked before issuing another request.
Two subsequent reconstructions then passed all ordinary checks.

Both mutating fault cases reported forward completion and committed all three
generations. These are recorded in the JS preparation error history, whereas
native preparation-failure counters count reservations that terminate without
committing. The partial-construction regression exhausted the single automatic
retry and required a third explicit native request; there was no restart loop.

Every run preserved the original Wayland/X11 client processes, native socket
FD/inodes, window IDs and text until the deliberate final edits. Desktop state,
native compositor/XWayland identity, registration counts and virtual keyboard
identity stayed stable. Menus, new client mapping, Super/Escape and predicted
entry edits through that keyboard passed. Selected object finalization and its
independent retention/collection controls passed. Native types warmed once from
988 to 989 and then remained stable.

With usage history enabled, the original time-limits model stayed active with
the same native address, unchanged transition records and zero shutdown calls.
The clock follow-up additionally required its actual native main-context clock
source to remain present after all three generations. That run retained model
address `0x555557b00830`, active state 1 and its original inactive-to-active
transition, rather than merely reconstructing equivalent-looking state.

All final runs used
`/nix/store/4f0d39pwy9qizyrph00iam459cfj0g07-gnome-shell-50.5/bin/.gnome-shell-wrapped`.
The desktop after cancelled preparation (not exported: `artifacts/preparation-stall-final/desktop-after.png`)
and overview after partial-construction recovery (not exported: `artifacts/preparation-partial-final/overview-after.png`)
were visually inspected. The final flake check passed; the build used `-j16`.
No private-runtime test processes remained after cleanup. Host Shell PID 1350942
still ran its original
`/nix/store/8m77m1b9n4z4lv00l7d5455lkfbqy5jg-gnome-shell-50.5/bin/.gnome-shell-wrapped`.

## Reproduce

```sh
nix build --cores 0 .#stable-shell --no-link
nix flake check --cores 0
nix develop --cores 0 .#stable -c python3 tests/isolated.py --reload-ui-in-place --owned-request --track-time --preparation-fault stalled --soak-seconds 65 --output artifacts/preparation-local
```

Other preparation checkpoints are `before-mutation`, `after-bindings` and
`after-disable`. A cancelled reservation consumes one of the laboratory's three
requests, leaving two UI generations for that run. Mutating checkpoints complete
their original request, leaving three committed generations. The harness records
requested and actual soak duration. Use a fresh evidence directory for every run.

No system installation or activation is needed. The harness enables the extension
only in its temporary profile and cleans its private buses, processes and profile
afterwards. [README.md](README.md) documents removal of optional result links and
the supported operations. Compilation uses all available threads.

## Distance to a complete restart

The verified direction remains a controlled UI reload, with explicitly durable
backend models. A complete safe implementation still needs security-sensitive
lock/authentication ownership, preservation of notification/composition state,
general constructor/teardown exception safety, third-party extension compatibility,
physical devices/outputs, multiple monitors and longer resource validation.
Recovery from a hung GJS runtime or a crashing process requires a stronger
restartable boundary than this retained-context design. No defensible completion
percentage or end-to-end implementation date follows from the current tests.
The original whole-Shell restart objective remains incomplete.

Changed implementation files are `flake.nix`, `shell/tgnome-runtime.h`,
`shell/stableMain.js`, `shell/stableTimeLimits.js`,
`shell/preparation-lifetime.patch`, `extension/extension.js` and
`tests/isolated.py`; README, PLAN and the reports describe the new boundary.
Next address bounded construction waits and explicit security/UI ownership,
then complete VM-based lock/authentication and device tests before proposing
any separately approved physical-session trial.
