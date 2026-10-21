> Historical research report. Claims apply to its original experiment, not
> today's implementation. See [STATUS.md](STATUS.md) and
> [RESEARCH-GUIDE.md](RESEARCH-GUIDE.md) before interpreting results.

# Bounded recovery of a failed UI reconstruction

This extends the controlled desktop UI reload in [OWNERSHIP-REPORT.md](OWNERSHIP-REPORT.md).
It preserves the native compositor and original client connections. It does
not restart the compositor process, replace GJS, or restore applications after
losing their connections. The full safe Shell restart goal remains open.

Classification: **SHELL RELOAD**, with bounded recovery for the tested
post-construction failure. Existing graphical clients retain their original
connections throughout both automatic and explicit corrective requests.

## Transaction and ownership

The headless native supervisor now records an active construction transaction.
The UI reports either `UiStarted` or `UiFailed` through the native D-Bus endpoint.
Only the Shell connection's own unique bus name may report an outcome; an
external caller cannot forge completion. A new external reload is rejected
while construction is active. Native status distinguishes requests, failed
constructions, scheduled retry attempts, committed UI generations and activity.
Unprepared native requests are rejected before consuming a request slot.
Preparation checks the native budget before changing UI, owns a JavaScript
preparation lock across asynchronous work, and refuses a second concurrent
preparation. Rejection at the laboratory limit leaves the working UI exported
with its original registrations and desktop state.

After a construction failure, the JavaScript coordinator records a string-only
failure history, captures retirement targets, shuts down the candidate's time
limits manager, disables its extensions and releases its UI keybindings. Only
after that preparation succeeds does it mark the candidate ready for cleanup.
The native supervisor schedules destruction on its next low-priority idle,
after the reporting JavaScript stack has returned. It then performs the same
source, registration, gesture and actor cleanup as an ordinary reload before
building another UI.

There is at most one automatic retry per external request. A second failure,
or an inability to prepare cleanup, ends the transaction in `ui-failed` without
scheduling another attempt. A separate explicit request can begin another
transaction within the process's existing three-request laboratory limit.
This is bounded reconstruction of another UI, not rollback to old actor objects.

## Injected failures and additional fixes

`ArmUiFailure` is a private test method restricted to the explicitly enabled
stable headless fixture. It injects one or two errors after the candidate UI is
constructed and its layout startup completes, before its generation commits.
Failure history identifies those deliberate errors. Unexpected exceptions and
critical log messages remain failing diagnostics.

`recovery-once-1` restored UI with exactly one corrective attempt, but its test
failed on callbacks entering destroyed widgets. The stacks identified two
additional lifetime bugs:

- The screenshot UI's asynchronous screencast proxy initialization completed
  after its capture button was destroyed. Initialization now has a cancellable,
  destruction guard and signal disconnection. Its permanent session-mode
  subscription is UI-owned, and screenshot UI was added to finalization targets.
- The old layout had a pending Mutter `BEFORE_REDRAW` callback, separate from
  GLib sources. Reset now cancels that callback and prevents region updates from
  being queued again while actors are being destroyed.

`recovery-once-2` then passed three committed generations, one injected failure,
one automatic corrective attempt, collection of failed-candidate targets,
functional menus/overview, stable registries/types and surviving clients.
Its post-reload diagnostic problem count was zero.

`recovery-twice-1` passed a further scenario: two consecutive failed constructions
exhausted the automatic retry budget, the supervisor remained at `ui-failed`
with stable counters while original clients continued round-tripping, and a new
explicit native request restored a functional UI. This used three external
requests and committed two UI generations. The first scheduled retry itself
failed; a scheduled retry must not be counted as a successful recovery.

Those preliminary runs had no extended soak. Subsequent combined runs exercise
the same scenarios with 65 seconds of delayed-callback observation and the
final counter names `uiFailures`, `uiRetryAttempts` and `uiCommits`.

The preparation concurrency test races two real D-Bus calls and requires exactly
one accepted preparation. The rejected call must report the pending preparation
or find the already unexported endpoint; it must not become another successful
preparation. The suite also verifies that an unprepared native call consumes no
slot and that a refused fourth preparation does not disable the working UI.

## Final evidence

All three final commands exited 0, recorded zero post-reload diagnostic problems,
and removed their private profiles through the outer process supervisor:

| Artifact directory | External requests | Failed constructions | Scheduled retries | Committed UI generations | Soak |
| --- | ---: | ---: | ---: | ---: | ---: |
| `artifacts/recovery-safe-normal` | 3 | 0 | 0 | 3 | 0 s |
| `artifacts/recovery-safe-final` | 3 | 1 | 1 | 3 | 65 s |
| `artifacts/recovery-safe-twice` | 3 | 2 | 1 | 2 | 65 s |

The once-failure run also passed parallel preparation rejection. Every run
rejected forged completion, rejected an unprepared native request without
changing native status, and rejected exhausted preparation without changing its
working desktop or exported registrations.

The normal run finalized 27 selected old UI objects (nine per generation).
Each failure scenario finalized 36, including the failed candidate generations.
Independent unreferenced controls finalized and persistent window-manager
controls remained alive. All scenarios preserved original Wayland/X11 socket
and window identities and probe text, then mapped additional clients. Native
object types warmed once from 986 to 987 and stayed stable; the GJS epoch did
not change and no GJS context finalized.

All three used
`/nix/store/89v099wa5p2nsi3ac3slxi0yb8q15pp9-gnome-shell-50.5/bin/.gnome-shell-wrapped`.
The final flake check passed. The changed implementation files are
`shell/tgnome-runtime.h`, `shell/runtimeInit.js`, `shell/stableMain.js`,
`shell/stable-lifetime.patch`, `extension/extension.js` and `tests/isolated.py`;
the README, plan and reports describe their scope and use.

## Reproduce

```sh
nix build --cores 0 .#stable-shell --no-link
nix flake check --cores 0
nix develop --cores 0 .#stable -c python3 tests/isolated.py --reload-ui-in-place --ui-failure once --parallel-prepare --soak-seconds 65 --output artifacts/recovery-once-local
nix develop --cores 0 .#stable -c python3 tests/isolated.py --reload-ui-in-place --ui-failure twice --soak-seconds 65 --output artifacts/recovery-twice-local
```

Use new output directories. All compilation uses available cores; the tests
run only the private headless Shell, private buses and temporary profile. The
outer supervisor contains and reaps its helper descendants before removing the
profile. No host installation, configuration activation, logout or physical
display test is involved. There is no host configuration to roll back.

## Remaining requirements

The injected fault is specifically after full candidate construction and before
commit. An exception halfway through component construction, a hung promise,
blocked GJS, native crashes and cleanup failures are not established recovery
cases. A terminal failure leaves the native compositor inspectable and original
clients connected; it does not guarantee a complete working UI until another
explicit reconstruction succeeds. Native input, lock/unlock authentication,
arbitrary third-party extensions and physical display behavior remain unproven.
The two-call laboratory preparation protocol also does not establish recovery
from a controller disappearing between preparation and the native request.
The public `reload-shell` and `recover-session` commands remain unsupported.
