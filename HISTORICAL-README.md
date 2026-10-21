> Historical research report. Claims apply to its original experiment, not
> today's implementation. See [STATUS.md](STATUS.md) and
> [RESEARCH-GUIDE.md](RESEARCH-GUIDE.md) before interpreting results.

# Tgnome: restartable GNOME UI lifetime experiment

The new [complete-context replacement build](FULL-CONTEXT-RECOVERY.md) now
passes isolated end-to-end tests: three complete GJS context replacements,
unchanged Mutter and client connections, working input/UI and a 65-second soak.
A real native-backend VM also passes context replacement, GDM/PAM authentication
and logind lock/unlock. The earlier static-GType blocker has a separate native
reattachment solution.
Historical reports below describe their original builds, not this new build.

The current executable recovery alternative and its complete isolated acceptance
suite are documented in [RECOVERY-ACCEPTANCE.md](RECOVERY-ACCEPTANCE.md).
`recover-desktop-ui` uses the surviving native supervisor when failed UI has no
extension endpoint. This preserved fallback retains Main, GJS and Mutter;
the complete-context build is a separate implementation.

**Complete Shell runtime reinitialization is now verified in isolation.
It is cooperative, limited to an idle unlocked responsive Shell, and has not
been activated on the host desktop.**

The separate [fresh UI realm experiment](REALM-REPORT.md) now demonstrates
three independently instantiated and collected GJS globals/module graphs,
including ESM bootstrap and Promise/timer callbacks. A permanent native
GType/vfunc/object can dispatch to replaceable UI implementations. Registering
a GType in the disposable realm instead retains that realm and rejects the
next registration. The newer [actual panel realm experiment](PANEL-REALM-REPORT.md)
moves Panel behavior into disposable globals while its native type remains
canonical. Ten panel replacements, a failed candidate and three desktop UI
reconstructions preserve original clients; fourteen retired panel globals
collect. Other Shell UI modules remain in the original global.

The [date menu realm experiment](DATE-MENU-REALM-REPORT.md) additionally moves
eight real widget/layout implementations into a shared disposable realm,
including construction through a JS parent class. Typed GI signals, native
clicked/layout vfuncs and rendered menu checks pass. Three retired date-menu
realms and 24 wrappers collect; an injected failed candidate increases this to
four realms and 32 wrappers. Permanent native bindings are shared, UI module
registries remain separate, and the original GJS context still survives.

The patched build replaces GNOME's real panel actor, including its three layout
boxes, drag gesture, focus group and popup menu manager. Existing status
indicators, their backend connections and menus transfer to the new container.
The JavaScript context and compositor stay alive. The original baseline also
rebuilds an extension-owned panel indicator while the supervisor,
JavaScript context, Mutter compositor, Wayland connections, windows and XWayland
remain alive. It also exposes GNOME's existing theme reload operation. This is
useful experimental scaffolding for a future Shell lifecycle refactor; it does
not repair a crashed or blocked Shell and does not reload extension source code.

The initial workspace was empty and had no Git repository or existing build
conventions. No host NixOS configuration was changed. See [REPORT.md](REPORT.md)
for source evidence, environment, exact results and unresolved requirements.

The separate [runtime experiment](RUNTIME-REPORT.md) tests disposal and recreation
of the entire GJS context while a native compositor loop survives. It has
deliberately failing gates for retained type registrations and callbacks into
disposed JS. It is a research prototype, not a supported Shell restart.

The [persistent-context experiment](STABLE-REPORT.md) rebuilds desktop UI
instances while retaining GJS and selected backend models. Three reconstructions
and a 65-second delayed-callback test passed, including original client sockets,
editable probe text and new window mapping. Broader lifecycle audits continue.
The newer [object collection audit](OWNERSHIP-REPORT.md) exposed and corrected
retained managers outside those earlier registration counts. Its final combined
run also passed: 24 selected old UI objects collected across three generations,
window menus working, a 65-second soak and complete private-process cleanup.
The test uses independent finalization/retention controls.
[Bounded reconstruction recovery](RECOVERY-REPORT.md) now covers injected
post-construction failure, one automatic retry, and an explicit new request
after that retry budget is exhausted. Partial-construction failures, complete
resource collection and lock/input security remain unproven.
[Native virtual input and rendered frames](INPUT-REPORT.md) now verify that the
same private keyboard can open/close overview and edit both original client
windows after reconstruction and failure recovery. This uncovered a stale
notification idle watch; teardown now removes those watches and cancels the
message tray's presence proxy initialization. Physical devices and lock
authentication are still outside the verified scope.
[Shell-owned reload requests](OWNED-REPORT.md) add a single CLI operation whose
asynchronous preparation and reconstruction continue after the requester exits.
Concurrent requests cannot take over the active native transaction. This does
not establish recovery from a failure inside preparation or a blocked JS loop.
[Incomplete UI construction](PARTIAL-REPORT.md) adds early failure checkpoints
and retirement accounting for an overview constructor that throws before its
assignment. This exposed IBus callbacks reaching an absent keyboard. The
experimental lifecycle now cancels obsolete input contexts and disconnects
candidate popup subscriptions during failed-candidate cleanup. General
exception-safe construction and preparation rollback remain open work.
[Preparation ownership](PREPARATION-REPORT.md) now retains the session's
time-limits backend model, bounds non-mutating preparation with a native lease
and commits UI release plus native scheduling in one synchronous step. Tests
exercise refusal before mutation, forward completion after mutation, expiry
and a late async completion that must not commit. This still requires a
responsive event loop and does not recover blocked GJS.
[Bounded construction](CONSTRUCTION-REPORT.md) adds cancellation identities for
the inspected Main/Layout startup waits and rejects obsolete native outcomes.
Stage-child inventory exposed a hidden screencast indicator left behind by old
ScreenshotUI instances; teardown and retirement checks now cover it separately.
This is still a retained-context UI reload in a private headless fixture.
[Terminal quarantine](QUARANTINE-REPORT.md) now rejects new work when failed
construction does not acknowledge cleanup. Original clients kept communicating
through a 65-second quarantine. A late, validated cleanup acknowledgement allows
an explicit new recovery request, without restarting automatic retries.
Permanent quarantine preserves clients but does not restore the desktop UI.
[The security VM baseline](SECURITY-REPORT.md) now verifies actual GDM/PAM
lock/unlock with both original client connections and unsaved probe text intact.
It deliberately uses upstream Shell; security across patched UI reconstruction
remains unproven. Run this separate VM target with
`nix build --cores 0 --print-build-logs .#security-vm --out-link result-security-vm`.
[The patched security VM](VM-RELOAD-REPORT.md) additionally verifies controlled
UI reconstruction followed by real locking, wrong-password rejection and PAM
unlocking, with original clients preserved and the old ScreenShield collected.
It exposed stale subscriptions to persistent JS/DBus emitters; teardown now
tracks them. Its dedicated native-backend build requires both a VM marker and
the exact virtual DMI identity. [Lock-race tests](LOCK-RACE-REPORT.md) now cover
an accepted lock during preparation and a responsive construction timeout/retry.
The VM keeps independent lock intent and a topmost input curtain across UI
candidates. Original app entries remained unchanged during 400 keyboard events
across recovery. [Durable logind locking](DURABLE-LOCK-REPORT.md) now also
accepts a real session Lock while ScreenShield is absent, preserving the lock
across the timeout/retry and subsequent PAM authentication. Other lock entry
points and terminal quarantine with a pending lock still need VM coverage.
The regular stable package keeps its headless restriction.
[A standalone native interrupt prototype](INTERRUPT-REPORT.md) now tests the
blocked-JS boundary using pinned GJS/SpiderMonkey. Unmodified GJS aborts on
an uncatchable GI callback interruption. A separate GJS build permits an
explicitly marked return to an owned native boundary, preserving the context
and native objects. The subsequent [boundary guards](BOUNDARY-REPORT.md)
refuse tested unsupported nesting; JS `finally` is still skipped. The standalone
baseline and patched characterization are included in `nix flake check`.
[Controlled blocked-JS recovery](SHELL-INTERRUPT-REPORT.md) now links that GJS
only into the separate `interruption-shell`. One real infinite GLib callback
was interrupted, UI reconstructed and original Wayland/XWayland clients
preserved through a 65-second soak. This is an explicitly armed fixture;
arbitrary partially completed operations, Promise jobs and native crashes
remain outside its demonstrated recovery scope.
[Interrupted panel transfer](PANEL-INTERRUPT-REPORT.md) now covers two actual
partially completed operations: after all indicators are detached and after
the replacement adopts one. A persistent ownership journal lets native recovery
restore the old panel, destroy and collect the incomplete actor, then rebuild
UI with original clients retained. This proves those checkpoints; competing
requests during native handoff and general backend mutations remain open.
[Handoff admission](HANDOFF-REPORT.md) now fixes an observed race: a full UI
reload could start before the interrupted panel transaction was settled.
Five reload/preparation operations now refuse that pending transaction without
consuming a native attempt. Explicit release and an eight-second native deadline
both pass actual competing-request tests with the original clients retained.
Other callbacks and extension-manager mutations remain outside that test.
[Protected backend scopes](PROTECTED-SCOPE-REPORT.md) now add an authoritative
native counter around synchronous backend lifetime helpers. Their interruption
is refused so JS finally can close ownership state. A finite real-Shell test
proves nested depth returns to zero and a later UI signal is cleaned on reload;
the panel-interruption regression still passes. An infinite protected scope
remains blocked. Registration as durable does not yet automatically protect
every later callback, and this still does not restart the GJS runtime/process.
[Delayed backend callbacks](DURABLE-CALLBACK-REPORT.md) now capture protection
for selected GLib sources and GObject signal registrations in the private build.
Actual delayed timeout, Source and native-C signal tests refuse interruption
without promoting callback returns or later UI resources to permanent owners.
The timer has a 65-second soak; panel/handoff recovery still passes. This is
selected-entry coverage, not a generic solution for all GI async callbacks.
[Native closure provenance](NATIVE-CLOSURE-REPORT.md) now moves capture into
GJS itself. Real GIO async completion, specialized cancellation and a chained
callback inherit native protection while allocation lifetime stays unchanged.
Duplicate GLib/GObject protection wrappers were removed. Standalone scope/error
controls, real-client runs and panel recovery pass; actual fresh UI runtime
recreation remains the next architectural milestone.
Selected JS-object collection does not prove cleanup of independently parented
native actors. Keep direct stage-child inventory and separate retirement targets
for those actors; the screencast-indicator failure demonstrates why both gates
are required. Root signal tracking includes the persistent `global.context`.
Run it only with
`nix develop --cores 0 .#stable -c python3 tests/isolated.py --reload-ui-in-place --soak-seconds 65 --output artifacts/stable-local`.
Use `--cores 0` on build and development commands to compile with all available
threads. A local build was verified to use `-j16`.

The established-profile fixture marks the welcome tour as already shown, so
one-shot onboarding actors do not distort generation comparisons. Its private
bus has no AT-SPI service: GTK helper accessibility is explicitly disabled using
`NO_AT_BRIDGE=1` and `GTK_A11Y=none`. Accessibility and authentication need separate
complete fixtures and are not established by these passing tests.

```sh
nix develop --cores 0 .#runtime -c python3 tests/isolated.py --reset-runtime --unique-gtypes --soak-seconds 65 --output artifacts/runtime-local
```

This explicit command performs one reset only in the private headless test.
It may exit nonzero and must not be adapted to target the live desktop.

## Build and test

The flake pins the same nixpkgs revision as the inspected workstation:
`8ce73368d1efd4d657e9064d29b144a52046b4e8`. Only x86_64-linux is defined.

```sh
nix build --cores 0 .#default .#extension .#probe --no-link
nix flake check --cores 0
nix develop --cores 0 -c python3 tests/isolated.py --output artifacts/local
```

The integration test starts a headless GNOME Shell with a 1280×720 virtual
monitor, private D-Bus session, temporary XDG directories, keyfile settings,
and an explicit private Wayland socket. It requests software rendering and
does not modeset a physical output. Mutter can still open a GPU render node.
It enables the extension only in that temporary environment, starts two real
GTK windows, performs 21 UI rebuilds, tests one injected construction failure,
reloads the theme and cycles the extension lifecycle three times. It checks
original native display socket identities and post-operation round trips,
window identifiers, window state, compositor PID and XWayland process identity.

Both backends are required: missing XWayland produces a failing test, not a
partial pass. Use a new output directory to retain evidence from previous runs.
Read `result.json`, `shell.log`, `wayland.jsonl`, `x11.jsonl` and client logs in
that directory. The harness stops only process groups it created; startup,
test and cleanup waits are bounded. It performs no host bus discovery.

The test is intentionally not part of automatic flake checks: starting a
compositor requires an explicit integration test command outside a Nix build
sandbox. The checks exercise CLI safety and package construction.

To inspect the exact upstream release archives used by the pinned packages:

```sh
nix build --cores 0 .#upstream-sources --out-link result-sources
nix build --cores 0 .#shell .#mutter --no-link
```

`shell` and `mutter` are unmodified upstream Nixpkgs builds. The optional
`panel-shell` is a locally rebuilt GNOME Shell 50.5 using the same Mutter.
The extension and probe compile/package locally.

## Test the real GNOME panel reload

```sh
nix build --cores 0 .#panel-shell --no-link
nix develop --cores 0 .#panel -c python3 tests/isolated.py --output artifacts/panel-local
```

This build applies `shell/panel-lifecycle.patch`, appends `panelLifecycle.js`
to upstream `panel.js` and `mainLifecycle.js` to upstream `main.js`. It does
not modify the store or activate a NixOS generation. The override compiles a
separate Shell package and the harness launches only that package headlessly.

Local lifecycle patches use full source context and `patch --fuzz=0`. The stable
build additionally asserts the exact placement of its UI construction hooks.
Do not restore fuzzy one-line insertions: a passing compilation can otherwise
place a lifecycle boundary after the wrong constructor. Nixpkgs' own packaging
patches retain their upstream application policy.

The replacement is staged before transfer. A snapshot retains each indicator,
box, position and visibility. The old panel releases its menu registrations,
owned signal connections and indicator containers; the replacement adopts them.
The old panel is destroyed after successful adoption. A failed partial adoption
destroys the staged actor and reattaches the indicators to the surviving old
panel once. The test injects precisely this failure.

Only an isolated Shell started with `TGNOME_ALLOW_PANEL_RELOAD=1` permits the
operation. Open menus, overview and non-user modes are rejected. Unknown
children or extra menu-manager entries are rejected before transfer. Arbitrary
third-party extensions caching the old panel are not supported or tested.
Core indicator instances, ES modules, Quick Settings backend objects, calendar
services, overview and window management are deliberately retained.

In this environment the integration test additionally replaces the real panel
ten times, checks menu operation after each replacement, verifies rollback,
and requires stable panel/focus-group/menu counts and original indicator
identity. The baseline test still works against unmodified GNOME Shell.

## Operations

These commands require the experiment's extension on the explicitly selected
session bus. Nothing is installed into the live desktop by building the flake.

| Command | Actual effect |
| --- | --- |
| `nix run . -- status` | Read endpoint identity, owned actor counts and desktop state |
| `nix run . -- reload-ui` | Destroy and reconstruct only the experiment's indicator |
| `nix run . -- reload-theme` | Run `Main.reloadThemeResource()` and `Main.loadTheme()` |
| `nix run . -- reload-panel` | Replace the real panel container in the explicitly enabled patched development Shell |
| `nix run . -- reload-desktop-ui` | Schedule desktop UI reconstruction in the isolated stable headless Shell; retain compositor and GJS context |
| `nix run . -- recover-desktop-ui` | Recover a cleaned failed UI through the native supervisor and wait for published readiness; requires a private bus and pinned unique owner |
| `nix run . -- self-test` | Read-only endpoint health check; no client survival experiment |
| `nix run . -- reload-shell` | Exit 2: unsupported, no bus call |
| `nix run . -- reload-extensions` | Exit 2: unsupported, no bus call |
| `nix run . -- recover-session` | Exit 2: unsupported, no bus call |

GNOME 50.5 also provides the existing run-dialog command `rt` for theme reload
when development commands are enabled. That upstream feature is not a Shell
restart. Neither disabling/enabling an extension nor rebuilding this indicator
invalidates the ES module cache.

`reload-desktop-ui` returns an acknowledgement that reconstruction was scheduled,
not a readiness result. The integration test waits for both the new UI generation
and native `ui-ready` before testing functionality. It requires the actual
headless backend and the explicit laboratory flags; it is not enabled for the
live desktop. Exercise the CLI and caller-disconnect handling with:

```sh
nix develop --cores 0 .#stable -c python3 tests/isolated.py --reload-ui-in-place --owned-request --interrupt-requester --parallel-prepare --ui-failure once --soak-seconds 65 --output artifacts/owned-local
```

## Ownership, failure handling and security

The extension owns exactly one `PanelMenu.Button`, its label and one exported
D-Bus object at `/org/gnome/Shell/Extensions/Tgnome` on `org.gnome.Shell`.
It creates no additional daemon, D-Bus name, background retry timer or service.
The session bus's normal same-user permissions apply; there is no system bus
endpoint, root privilege, arbitrary evaluation or caller-supplied code/path.
`status` includes window titles and geometry and should be treated as private
desktop data. This is a development endpoint, not an authorization boundary
between applications belonging to the same user.

Indicator operations are synchronous and serialized. On construction failure the
supervisor attempts to restore the last generation exactly once, then reports
the error. If restoration also fails, `active` is false and no retry loop starts.
Disable unexports the object and destroys the indicator. Fault injection is
accepted only when the isolated Shell starts with `TGNOME_TEST_FAILURES=1`.
The optional panel override separately owns the panel replacement transaction;
the extension only calls its fixed API. The CLI refuses implicit D-Bus discovery
and imposes a 15-second call timeout.
A blocked GJS main loop can therefore make the command time out; this tool
cannot recover that failure.
The separate [native-entry interruption experiment](BOUNDARY-REPORT.md)
refuses six tested unsupported entry types while preserving interruption at
owned outer native boundaries. Only the separate `interruption-shell` links
it; [its controlled recovery test](SHELL-INTERRUPT-REPORT.md) demonstrates one
blocked callback followed by reconstruction. The regular packages keep the
blocked-main-loop limitation described above.
The desktop reconstruction operation is asynchronous: native code reserves its
transaction before preparation, and the Shell connection itself schedules the
rebuild. Only that connection may start, cancel or report outcomes for the owned
transaction. This prevents another session-bus client from forging those steps;
it does not isolate applications running as the same Unix user.
The reservation expires after five seconds while only non-mutating preparation
is permitted. A validated native start synchronously invokes the fixed commit
callback and schedules reconstruction. Usage accounting stays in its original
backend model; it is flushed on actual native Shell shutdown. Failures after
UI mutation attempt bounded forward completion, rather than claiming rollback
to a partly released old UI. The private test protocol still has a three-request
laboratory limit and is not a production installation workflow.

## Enable, disable and revert

Use the integration test to enable the prototype temporarily. It already
installs and enables it in private XDG directories and cleans up afterwards.
No NixOS rebuild, activation, GDM restart or desktop relogin is needed.
Host extension installation is intentionally not part of this workflow.

There is no host configuration to roll back. To remove an optional source
result link:

```sh
rm -f result-sources
```

Keep test evidence as desired; removing an individual `artifacts/<run>` directory
only removes that run's logs. Nix build outputs remain ordinary garbage
collectable store entries. Do not use host Shell replacement or service
restart commands to test this project.
