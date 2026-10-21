> Historical research report. Claims apply to its original experiment, not
> today's implementation. See [STATUS.md](STATUS.md) and
> [RESEARCH-GUIDE.md](RESEARCH-GUIDE.md) before interpreting results.

# Shell-owned desktop UI reload request

Classification: **SHELL RELOAD in the isolated headless stable build**.
The new `reload-desktop-ui` CLI operation starts one Shell-owned asynchronous
transaction. The compositor, GJS context and selected backend models survive.
This is not a complete safe Shell restart, process restart or crash recovery.

## Request lifetime

The earlier laboratory protocol required a caller to prepare the old UI and
then issue a second native request. Losing that caller between the two steps
could leave a prepared UI without a scheduled reconstruction.

`ReloadDesktopUi` now reserves a native transaction before asynchronous
preparation. The Shell connection then performs preparation and sends its own
`StartUiReload`; the external requester has no second responsibility. Native
`BeginUiReload`, `StartUiReload` and `CancelUiReload` accept only the Shell
connection's unique bus sender. Existing `UiStarted`/`UiFailed` outcome reports
have the same sender restriction. Active-transaction and request-budget checks
also prevent the older debug entry point from starting another rebuild.

The operation requires the actual headless backend plus the explicit persistent
context/runtime-reset/test flags. The CLI returns JSON with `accepted: true`
when reconstruction has been scheduled. That acknowledgement is not readiness.
The integration test separately waits for the expected UI generation, completed
layout startup and native `ui-ready` before exercising the replacement UI.
The CLI retains its explicit-session-bus requirement, optional unique-name pin
and bounded 15-second call timeout.

The protocol permits three external requests in each laboratory Shell. A failed
construction gets at most one automatic corrective attempt. A preparation
reservation consumes a request even when cancelled. Legacy two-call probe
methods remain available for research; they do not gain caller independence.

## Evidence

Both extended runs exited 0, reported `passed: true`, completed their 65-second
delayed-callback soak and removed the private profile after descendant cleanup:

| Run | External requests | Failed constructions | Automatic retries | Committed UI generations |
| --- | ---: | ---: | ---: | ---: |
| `artifacts/owned-once-final` | 3 | 1 | 1 | 3 |
| `artifacts/owned-twice-final` | 3 | 2 | 1 | 2 |

The first run launched the real Python CLI, observed native `ui-preparing`
while that requester was alive, and terminated only its private process group.
Requester PID 2193986 exited with signal 15; the Shell completed the first UI
generation without a second request. The second generation accepted exactly
one of two concurrent real CLI requests, rejected the other, and recovered from
one injected post-construction failure.

The second run used the new CLI for its initial requests. Two injected failures
exhausted the automatic retry allowance. Native counters then remained stable
at `ui-failed` while both original clients continued round-tripping. An explicit
legacy native recovery request restored the UI; this terminal recovery path
does not demonstrate the public extension endpoint working while disabled.

Both runs retained the original Wayland and X11 processes, socket FD/inode and
native window identifiers, original text until the deliberate final edits,
window placement, native compositor/XWayland identities and tracked backend
ownership. Both original windows accepted input through the same virtual
keyboard before/after reconstruction; their resulting text hashes matched the
predicted values. Native Super/Escape opened and closed the real overview.
Menus, late window mapping, selected retired-object finalization and independent
collection/retention controls passed. Each run collected 40 selected retired UI
objects including failed candidates. Native object types warmed from 988 to
989 once and remained stable. The diagnostic-problem count was zero.

| Run | Original Wayland PID / socket inode | Original X11 PID / socket inode |
| --- | --- | --- |
| One failure | 2192587 / 6793529 | 2192649 / 6787869 |
| Two failures | 2193015 / 6792653 | 2193024 / 6776231 |

The executable for these runs was
`/nix/store/a1rdd1b7gr1kr38jqwccx79232c1rpk1-gnome-shell-50.5/bin/.gnome-shell-wrapped`.
The desktop after caller loss and recovery (not exported: `artifacts/owned-once-final/desktop-after.png`)
and overview after terminal failure and explicit recovery (not exported: `artifacts/owned-twice-final/overview-after.png`)
were visually inspected. Captures come from the private compositor.

The follow-up short run `artifacts/owned-admission-final` also exited 0. While
the real CLI was alive and native state was `ui-preparing`, external
`StartUiReload`, `CancelUiReload` and legacy `ReloadUiProbe` calls were rejected.
Native status remained exactly unchanged. The CLI was then terminated and the
Shell completed reconstruction, concurrency refusal and one-fault recovery.
The no-fault `artifacts/owned-legacy-regression` run passed the retained two-call
protocol, including its parallel-preparation guard. These short regressions
have no extended soak; the two runs above supply that evidence.
The final `nix flake check --cores 0` passed. No process with the fixture's
private runtime directory remained afterwards. The live host Shell was still
PID 1350942, running its original
`/nix/store/8m77m1b9n4z4lv00l7d5455lkfbqy5jg-gnome-shell-50.5/bin/.gnome-shell-wrapped`.

Reproduce the caller-loss, concurrency and one-failure scenario with:

```sh
nix develop --cores 0 .#stable -c python3 tests/isolated.py --reload-ui-in-place --owned-request --interrupt-requester --parallel-prepare --ui-failure once --soak-seconds 65 --output artifacts/owned-local
```

For the terminal failure case use `--owned-request --ui-failure twice` without
the interrupt/concurrency flags. Always choose a fresh output directory.
Compilation uses all available threads through `--cores 0`.

## Remaining boundaries

Requester loss is now covered; arbitrary failures inside the Shell coordinator
are not. Cancellation records native preparation failure but does not promise
rollback of every mutation already made during preparation. Failure after UI
disable but before native scheduling, partial constructor failure, blocked JS
and stuck asynchronous preparation need separate recovery design and tests.
The controlled construction fault still occurs after a complete candidate is
built. Lock/authentication security, physical input/output, notification-state
migration, arbitrary third-party extensions and complete resource collection
remain unproven. No live NixOS activation, host Shell replacement or GDM restart
was performed.
