> Historical research report. Claims apply to its original experiment, not
> today's implementation. See [STATUS.md](STATUS.md) and
> [RESEARCH-GUIDE.md](RESEARCH-GUIDE.md) before interpreting results.

# Restartable GNOME Shell investigation

Primary goal: restart GNOME Shell with original graphical client connections
preserved. A partial experiment does not complete this goal.

1. Identify installed packages and exact upstream lifecycle code.
2. Establish a restartable UI ownership island inside the existing Shell process.
   Its supervisor, GJS context, Mutter, window actors and Wayland server survive.
3. Build a version-pinned extension, CLI and persistent GTK Wayland/X11 probes.
4. Run only a private D-Bus, headless Shell, temporary runtime/config/data dirs,
   software rendering and explicit virtual monitor. Never target host D-Bus.
5. Recreate the island repeatedly, including an injected construction failure,
   and verify PID, original native display connection and round trips.
6. Document what this demonstrates and the missing whole-Shell teardown contract.

No system activation, host extension installation, logout or host compositor kill.
At the end of phase one, no process restart, GJS context replacement or session
recovery was implemented. Later experiments are recorded below.

## Second phase: actual GNOME panel boundary

Implemented a local GNOME Shell 50.5 override that stages a replacement panel
actor and transfers durable indicator objects, signal ownership and menus.
The headless integration test now checks ten real panel replacements, menu
operation, rejection during overview, rollback after partial adoption, stable
focus/menu counts and original Wayland/XWayland connections. Both the patched
and stock test suites pass; details are in PANEL-REPORT.md.

Next: audit and implement complete teardown of a real core indicator before
expanding the restartable boundary to backend services. A full Shell/GJS or
process restart is still an unmet requirement.

## Third phase: native loop and whole-GJS lifetime

The runtime development package now owns Mutter's loop in C, independently of
GJS, with a headless-only native diagnostic endpoint and one reset attempt.
The old GJS context can finalize and a new context can build UI while original
Wayland/XWayland connections survive. Tests intentionally reject retained type
registrations and callbacks into disposed JS. See RUNTIME-REPORT.md for evidence.
This is progress toward the original boundary, not completion of the goal.

## Fourth phase: persistent-context UI lifetime

Rebuild UI instances in the same GJS context, retaining native compositor state
and selected backend models. Track and compare exports, bus names, watches,
root signals, source ownership, stage actions and registered types. Require
original client round trips and functional menus/overview after each generation.
Three desktop UI generations now pass tracked-registration checks, functional
menus/overview, original connections, editable probe text, new window mapping
and a 65-second soak. Global settings were added to the audit after finding
raw subscriptions retained by old extension managers. Continue the persistent
emitter and obsolete-object collection audit; this is not a complete safe Shell
restart. See STABLE-REPORT.md for failures, commands and remaining
security, input and rollback requirements. Use all available compilation threads
(`--cores 0`); do not change the host NixOS configuration.

## Fifth phase: prove obsolete UI collection and failure recovery

Use finalization controls independent of the UI before interpreting GC results.
Retire and observe selected managers/actors across all three UI generations;
capture a private tagged heap on failure and follow traced root paths. Correct
background-group ownership, raw input subscriptions and accidental promotion of
UI objects to backend lifetime. Exercise real window menus after reconstruction.
See OWNERSHIP-REPORT.md. Full-rebuild rollback and lock/input security remain
required after these lifecycle gates, rather than being inferred from them.

The combined ownership/65-second-soak run now passes. All 24 selected retired
UI targets across three generations finalized, with positive/negative controls;
private helper descendants were reaped before profile removal. Next implement
and inject a bounded full-UI reconstruction failure, verify surviving original
clients through recovery, and add native input and lock security fixtures.

The native supervisor now receives authenticated self-reports of construction
outcomes and permits one corrective attempt per request. Post-construction
fault tests cover automatic recovery and the retry cap followed by an explicit
request. Pending redraw work and screenshot proxy initialization are now
cancelled with the old UI. See RECOVERY-REPORT.md. Partial-construction failures,
hung/blocked JS, native input and lock security are still outstanding.

Final recovery runs passed both fault scenarios with 65-second soaks and the
normal no-fault regression. Native admission rejects unprepared requests without
consuming the budget; preparation rejects concurrency and exhausted budgets
before disabling UI. Follow up with partial-construction cleanup, a single
atomic user-facing request protocol, and native input/lock security fixtures.

## Seventh phase: native virtual input and pixels

A virtual keyboard created before the UI baseline now survives reconstruction.
Native Super/Escape events open/close real overview before and after; End/a
events edit the original Wayland/X11 probe entries, with predicted hashes and
unchanged native connection identities. Frame captures show the actual rendered
desktop and overview with two deliberately positioned windows. These events
exposed an old message tray's native idle watch; its watch and proxy lifetimes
are now cleaned and the tray is included in finalization targets. Both fault
scenarios passed 65-second combined runs; see INPUT-REPORT.md. Physical devices,
lock authentication, notification-state migration, partial-construction cleanup
and an atomic public request protocol remain outstanding.

## Eighth phase: Shell-owned request

Add a single `reload-desktop-ui` CLI request. Reserve the native transaction
before asynchronous preparation; the Shell connection owns the start and outcome
messages. Reject external start/cancel/forged completion and concurrent requests.
Terminate the real requesting CLI while preparation is demonstrably active and
require the Shell to finish without another command. Combine this with both
bounded failure scenarios, original client input/connection checks, collection
controls and a 65-second soak. See OWNED-REPORT.md. Server-side preparation
failure, partial construction, blocked JS, lock security and physical-device
validation remain separate requirements; caller independence is not universal
transaction rollback.

Both extended owned-request failure scenarios passed, along with short active
coordination-refusal and legacy-protocol regressions. Caller loss and concurrency
are covered through the actual CLI. The next lifecycle boundary is recovery
when preparation or a UI constructor itself fails, rather than after a complete
candidate has been built. Keep the native supervisor bounded and require old
client continuity, explicit terminal state, cleanup and functioning input after
any corrective attempt. Do not infer lock security from the unlocked fixture.

## Ninth phase: incomplete UI construction

Start each candidate with empty UI globals, retain only declared backend models
and account for managers that have not been constructed. Register an overview
candidate before its constructor returns so an exception before Main assignment
does not hide it from retirement accounting. Test failure after layout, inside
the overview constructor and after panel but before keyboard construction.
Apply local source patches with complete context and no fuzz; verify exact
construction boundaries in the build. Cancel/disconnect obsolete input-method
and IBus candidate-popup work exposed by these checkpoints. Retain the bounded
native recovery protocol and all original client, registration, collection,
input and frame checks. See PARTIAL-REPORT.md for results and failed attempts.

The final constructor-failure, two-incomplete-candidate and caller-loss regression
runs passed their 65-second soaks; the final early-layout run also passed without
an extended soak. All retain original connections and working native virtual
input, with selected candidate objects collected and no diagnostic errors.
Next address preparation failure before/after mutation, bounded cancellation of
stuck asynchronous preparation and explicit ownership of security-sensitive UI.
The tested constructor journal does not cover arbitrary failing constructors.

## Tenth phase: preparation and persistent session accounting

Retain the time-limits backend model and its clock sources while replacing its
UI dispatcher; require active history and transitions to survive unchanged.
Stop flushing that session model during UI preparation. Add a native five-second
lease for non-mutating async preparation, then invoke synchronous release and
schedule reconstruction in the same native start method. Test failure before
mutation, after keybinding release, after controller disable, deadline expiry
and a late completion. Preserve caller-loss/concurrency and partial-construction
regressions. Notification policy disposal exposed by the longer precommit wait
must disconnect managed signals before native disposal. See PREPARATION-REPORT.md.

The final preparation checkpoints, deadline/late-completion case and active-model
checks passed, along with caller-loss and partial-construction regressions. Four
combined runs recorded 65-second soaks; three shorter checks have separate scope.
Next bound construction waits while preserving exact lifetime ownership, audit
security-sensitive UI and build a complete VM fixture for lock/authentication
before considering a separately approved physical-session test.

## Eleventh phase: construction deadlines and candidate identities

Assign each construction a native serial; require it in authenticated outcome
reports and preserve it across asynchronous continuations. Bound responsive
construction with a five-second native deadline, cancel inspected Main/Layout
waits and allow one corrective attempt. Test late authorized success messages
while the next candidate is constructing and require unchanged native state.
Add stage-child inventory and retirement of the standalone screencast indicator
exposed by that stronger resource gate. The two-second cancellation/quarantine
fallback stays explicitly unverified until a dedicated unresponsive-cleanup
scenario proves it. See CONSTRUCTION-REPORT.md.

Both final deadline runs passed their 65-second soaks. An old authenticated
success outcome was rejected while the corrective candidate was actively
constructing, without changing its native state. Caller-loss/post-fault and
preparation-deadline regressions also passed. After fixing the independent
screencast actor and persistent context subscriptions, direct stage inventory
and selected finalization both stayed stable. Next test terminal quarantine
with deliberately unresponsive cleanup, then address full VM lock/authentication
and security/UI ownership before any approved physical-session trial.

## Twelfth phase: terminal quarantine and late cleanup

The dedicated unresponsive-cleanup fixture passed: new requests and invalid
outcome acknowledgements leave native quarantine unchanged while original
clients keep communicating for 65 seconds. A delayed valid cleanup acknowledgement
ends quarantine without an automatic retry; a new explicit request restores UI.
Ordinary construction and preparation regressions also passed. Permanent
quarantine is containment only and is classified as a research prototype.
See QUARANTINE-REPORT.md for exact evidence and the remaining architectural work.
Next build the full VM lock/authentication fixture and audit persistent security
ownership. Blocked GJS and compositor crashes remain unresolved boundaries.

## Thirteenth phase: actual GDM/PAM security fixture

The isolated NixOS VM baseline now passes real logind locking, rejection of an
incorrect password, and GDM/PAM unlocking with the correct disposable password.
Original Wayland and XWayland clients preserve their sockets, windows and
unsaved probe text. This run uses upstream Shell, not the patched lifecycle;
it proves the fixture only. See SECURITY-REPORT.md for measurements and fixes
to the driver. Next attach the patched lifecycle in a VM-restricted variant,
exercise lock/refusal and lock-arrival races, then fix persistent security
ownership from the resulting evidence. No host session trial is authorized.

## Fourteenth phase: patched UI lifecycle in a real security VM

A separate compile-time VM variant permits the native backend only with a
root-owned regular marker and exact virtual DMI identity. The VM reload test
now preserves original Wayland/XWayland clients through UI reconstruction and
subsequent actual logind lock and PAM unlock. The first run exposed stale
ScreenShield and SessionMode subscriptions; selected persistent JS/DBus roots
now release UI subscribers, and ScreenShield cancels its pending work.
The old ScreenShield joins the collection gate. See VM-RELOAD-REPORT.md.
Next test lock arrival during preparation, construction and failed recovery,
including input and visible-state guarantees. Security state still lacks a
fully independent durable lifetime. Full GJS/compositor recovery remains open.

## Fifteenth phase: accepted lock during preparation and construction

Actual VM logind locking now interrupts non-mutating preparation cleanly.
The construction fixture exercises a five-second startup timeout and one retry
while 400 keyboard events span recovery. It exposed a lost locked state,
stale idle watch, modal-grab teardown order and leaked unlock backgrounds.
The dedicated VM now keeps lock intent and a topmost stage input curtain
outside UI candidates; it reapplies the accepted lock before commit.
Both VM scenarios and a 65-second headless regression pass, including PAM,
client identities and selected collection. See LOCK-RACE-REPORT.md.
Next test lock delivery when ScreenShield is absent, terminal quarantine with
pending lock, and additional authentication/monitor transitions. Blocking GJS
and native compositor failure still need a stronger architecture.

## Sixteenth phase: lock delivery without ScreenShield

A backend-owned logind session Lock subscription now survives the absence of
all ScreenShield instances. The explicit pre-constructor gap fixture proves
absence, a protected stage and actual LockedHint before the timeout/retry.
One durable request, unchanged original app hashes during 400 keyboard events,
PAM and selected collection all pass. This exposed calendar proxy initialization
being disposed too early; cancellation now waits for init completion before
disposal. The ordinary construction VM and 65-second headless regression pass.
See DURABLE-LOCK-REPORT.md.
Next cover terminal quarantine with pending lock and remaining lock entry
points. A stronger boundary for blocked GJS remains a primary architectural
milestone. The pinned GJS 1.88.1 public header/source exposes the native context
accessor; thread interruption still needs its own source audit and prototype,
and no recovery claim follows from that accessor alone.

## Seventeenth phase: native interruption of blocked JS

The standalone GJS embedding prototype now interrupts real infinite loops.
Upstream GJS survives direct eval interruption but aborts on uncatchable GI
callback termination. A separate opt-in GJS patch consumes a per-context marker
at either GI callback bridge and preserves native dispatch/context identity.
The 77 upstream tests and standalone baseline/marked/one-shot controls pass.
Catch/finally are skipped. The nested JS-to-C-to-JS characterization also proves
that the older JS frame can resume unsafely; it is not recovery proof.
See INTERRUPT-REPORT.md. No Shell package uses this GJS variant.
Next implement conservative native-entry boundary guards and reject unsupported
nesting before linking any watchdog to an isolated Shell. Then test actual
callback interruption, UI reconstruction and original client connections.

## Eighteenth phase: conservative native-entry guards

The GJS prototype now combines tracked entry depth, engine caller inspection
and an owner-thread check. Direct eval and outer native Closure entries are
eligible; jobs, modules, nested entries and unscoped raw eval are refused.
Six unsupported infinite-loop fixtures prove refusal, not recovery: their own
supervisor terminates them after two seconds. A benign nested signal/Promise
control completes before all five permitted interruptions, verifying restoration
of the boundary state. Baseline, one-shot fatal policy, foreign-thread refusal
and all 77 upstream GJS tests pass. See BOUNDARY-REPORT.md.

Next integrate this GJS into a separate headless Shell variant. Attach the
watchdog after the initial module eval returns to native main.c; test a blocked
outer callback, native-loop resumption, owned UI reconstruction and original
Wayland/XWayland connections. Audit registries and lifetime counters skipped
by JS unwinding. No Shell package currently uses the interruption variant.

## Nineteenth phase: controlled blocked callback in actual Shell

A separate interruption-shell now links the guarded GJS and a one-shot native
watchdog. A deliberately blocked outer GLib callback is interrupted after one
second; a native idle invokes the existing Shell-owned reconstruction protocol.
The full client/input/retirement test passes with a 65-second soak, unchanged
original Wayland/XWayland sockets and no unexpected diagnostics. The same Shell
PID, GJS epoch and Mutter survive. This is controlled blocked-JS UI recovery,
not process/runtime restart. See SHELL-INTERRUPT-REPORT.md.

Next test interruption inside a real partially completed owned operation and
repair state skipped by JS finally; then add bounded detection of known safe
entry failures. Promise/nested refusal, native deadlock/crash recovery and a
stronger lifetime/process boundary remain unresolved. Do not generalize the
fixture's clean loop into arbitrary callback safety or lock security.

## Twentieth phase: interrupted real panel transfer

Panel replacement now publishes its pending ownership journal before detaching
indicators. Native interruption recovery settles that journal before requesting
the existing whole-UI reconstruction. Tests interrupt after detachment and after
one indicator has been adopted: all nine indicators return to their exact
original locations, and the staged actor is destroyed and collected. Original
Wayland/XWayland clients, input, state and three UI generations survive; the
adoption run includes a 65-second soak. Ordinary panel success/fault regressions
and flake checks pass. See PANEL-INTERRUPT-REPORT.md.

Next force a competing UI request between interruption and native settlement,
and serialize admission across that handoff. Keep backend scope consistency,
automatic detection and unsupported JS/native failures separate; the selected
panel checkpoints do not prove their recovery or process restart.

## Twenty-first phase: competing requests before native settlement

A held-handoff fixture exposed ReloadDesktopUi accepting work while the panel
journal was still pending. A shared admission check now refuses all five
extension reload/preparation operations before mutation or native reservation.
Both partial-panel states pass actual external D-Bus competition, with original
client communication while held. Explicit release and the eight-second native
deadline each settle exactly once; the former has a 65-second soak. Baseline
panel/UI tests and flake checks pass. See HANDOFF-REPORT.md, including the
failed pre-fix characterization. This covers those reload commands, not every
possible callback or extension-manager mutation.

Next protect backend lifetime scopes against interruption that skips finally.
Require a real refusal/recovery experiment with later correct ownership and
unchanged original clients. Keep the full runtime/process restart objective;
the pending-scope guard is another prerequisite, not completion of that goal.

## Twenty-second phase: protected synchronous backend lifetimes

The private GJS counter now rejects interruption inside protected owner-thread
scopes. A bridge added only to interruption-shell brackets the actual synchronous
backend lifetime helper. Standalone tests prove nested depth, underflow and
foreign-thread refusal, plus five later permitted interruptions; an infinite
protected loop is refused and externally terminated, not recovered. All 77
upstream tests pass. The actual Shell finite-scope test proves depth 2 to 0,
correct later UI signal ownership/cleanup and original clients through three
reloads and a 65-second soak. Actual interrupted-panel/handoff regression and
flake checks pass. See PROTECTED-SCOPE-REPORT.md.

Next audit execution of callbacks registered as durable: registration-time
lifetime does not automatically protect later callback execution. Require a
real delayed-callback experiment before enabling automatic interruption. Keep
the stronger runtime/process boundary in scope for unrecoverable protected,
Promise/nested and native failures; refusing them does not achieve full restart.

## Twenty-third phase: delayed backend callback execution

A real delayed timeout exposed interruption after its registration scope had
closed. The private Shell now separates protected execution from allocation
lifetime, captures protection for selected source/signal registrations, and
does not retain callback return objects. Actual timeout, Source and native-C
GObject signal tests pass with original clients and later UI cleanup; the
timeout has a 65-second soak. Arming moved to the actual callback entry after
a faulty signal fixture had armed an unrelated interruption. Source validation
and a panel/handoff regression pass. Extension toggles now wait for real manager
states; one earlier intermittent endpoint loss is recorded without claiming a
proved production fix. See DURABLE-CALLBACK-REPORT.md.

Next inspect Gjs::Closure construction/invocation for native callback provenance
and test uncovered GI async entry families. Keep execution protection separate
from allocation lifetime; surface wrappers do not establish general coverage
or a full runtime/process restart. Preserve the stronger boundary objective.

## Twenty-fourth phase: native closure provenance

Gjs::Closure now captures native protection at creation and restores it through
C++ RAII on invocation, without extra persistent callable/context roots.
Standalone tests prove delayed timer/signal protection, closure after an ordinary
exception and a later permitted interruption. All 77 configured upstream tests
pass (GTK4 tests remain disabled by the package configuration). Actual GIO async,
specialized cancellable, chained async and timeout tests pass; duplicate timer
and GObject JS protection wrappers were removed. Original clients survive three
reloads and the GIO case has a 65-second soak. Panel/handoff recovery and flake
checks pass. See NATIVE-CLOSURE-REPORT.md, including the negative old-GJS run.

Next move toward actual UI runtime/global/module recreation, rather than more
refusal predicates. Audit native GType/vfunc/callback owners and the previous
re-registration blocker; test whether a fresh UI realm can coexist with the
durable compositor boundary. This is a hypothesis requiring evidence, not a
claim that backend scopes, Promise flow or the process are restartable already.

## Twenty-fifth phase: fresh UI realms and a permanent native type boundary

Implemented a separate realm-gjs variant and standalone embedding probe.
The experiment routes module compilation to the new global while canonical
native GI bindings remain in the original backend. Three generations load
the same module URIs independently, complete the real GJS ESM bootstrap,
Promise/timer and native cancellable callbacks, then pass weak GC checks.
Registering a GType inside the first realm retains it and prevents repeated
registration. A permanent backend FileEnumerator GType/vfunc/object instead
dispatches to three disposable UI delegates, with BUSY during each gap.
All detached realms collect; a deliberately retained delegate is detected.
See REALM-REPORT.md and artifacts/realm-verified/result.json.

Next implement this boundary in an actual St/Clutter Shell component and verify
old-realm collection with original Wayland/XWayland clients. Establish stable
type/vfunc owners and a candidate failure/teardown contract. The same JSContext,
process and compositor still survive; this is not a whole-Shell restart.

## Twenty-sixth phase: actual Panel behavior in disposable realms

The private realm-shell now preserves the canonical Panel GType and forwards
its real methods/vfuncs to a generated resource module in a new UI global.
Explicit backend bindings retain Main/services/indicator constructors.
Destroy disconnects the implementation. Ten replacements and adoption-failure
rollback pass with eleven retired globals collected and no type-count growth.
Three subsequent desktop reconstructions and a 65-second soak preserve original
Wayland/XWayland connections, text and native input; fourteen retired panel
globals collect. Fixed real IC retention through foreign call/apply intrinsics
and Map prototypes in the internal loader. See PANEL-REALM-REPORT.md.

Next extend the actual UI boundary to components with JS parent classes and
owned widget/model graphs. Prove constructor/super dispatch, native type metadata,
callback teardown and whole-realm collection. Main, indicator implementations,
the JSContext, compositor and process still remain original. Native failures and
full runtime/process restart remain unmet requirements.

## Twenty-seventh phase: date menu graph, JS parent construction and typed GI

Moved the original method bodies of all eight dateMenu.js classes to one owned
UI realm, with backend canonical types and pre-native WeakMap scope association.
Real JS parent construction, typed selected-date signals, native clicked/layout
vfuncs and rendered screenshots pass. Fixed persistent AppSystem callback
retention through scoped disconnect journals, missing GI argument conversion
through the canonical native registry, and GIO Settings prototype IC retention
by copying options into the backend realm. A boxed-GI negative control fails
before the native-registry fix and all four standalone cases pass afterward.
Three UI reconstructions collect 24 wrapper objects and three date-menu realms;
after-panel candidate failure/retry collects 32 wrappers and four realms. Soak,
original clients, native input, type counts and flake checks pass.
See DATE-MENU-REALM-REPORT.md.

The permanent GTypes still contain JS callbacks from the original context.
Next test a native GType/vfunc bridge independent of that context, retaining
the same native object through serial GjsContext disposal/recreation. Do not
confuse more component realms with a proved whole-context/process restart.
