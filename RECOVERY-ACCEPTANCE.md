> Historical research report. Claims apply to its original experiment, not
> today's implementation. See [STATUS.md](STATUS.md) and
> [RESEARCH-GUIDE.md](RESEARCH-GUIDE.md) before interpreting results.

# Isolated desktop recovery implementation and acceptance

The deliverable is an executable **desktop UI recovery alternative** for GNOME
Shell 50.5 on the pinned NixOS packages. It retains Mutter, client connections,
Main, backend services and GjsContext. It does **not** implement a whole-Shell
restart or complete Shell/module/runtime reinitialization.

## Implementation

The existing native main loop and reconstruction coordinator in
`shell/tgnome-runtime.h` supervise replacement UI candidates. The existing
`shell/stableMain.js` tears down and reconstructs layout, panel, overview,
keyboard/input method, extension manager, ScreenShield and other UI managers.
Candidates have bounded construction and cancellation deadlines, one automatic
retry, and quarantine until cleanup is acknowledged. The native loop, window
manager, client window actors and selected session models survive.

This change adds a usable recovery operation when reconstruction has exhausted
its retries or completed late cleanup after quarantine:

1. `tgnome recover-desktop-ui` reads the **native** supervisor, without calling
   the extension that may have disappeared with the failed UI.
2. `RecoverUi(uint32 failedCandidateSerial)` atomically checks that the serial
   still identifies the current failed candidate, no operation is active, and
   cleanup has been confirmed. Stale, healthy, busy and quarantined requests are
   rejected without mutation. Existing preparation, environment and attempt
   limits still apply. No admission or cleanup checks are bypassed.
3. Reconstruction is scheduled by the surviving native loop. It continues
   independently of the recovery CLI's lifetime.
4. Native Status exposes `pid` and `publishedUiGeneration`. The latter observes
   Main's final publication **after** the asynchronous `UiStarted` acknowledgement
   and security-curtain handoff. The CLI waits for both a new native commit and
   the published generation from the same pinned compositor process.

The native readiness check matters on the lock screen: GNOME disables the
extension there. Waiting for its endpoint would falsely report failed recovery
and could never validate a deliberately locked replacement.

This remains gated to the existing private headless fixture or the separately
compiled, identity-checked security VM. Native recovery additionally requires
`TGNOME_BUS_OWNER` to pin a unique D-Bus name. The three-request laboratory cap
remains; this is not an indefinitely running production recovery service.

## Reproduce the complete acceptance suite

From this repository, with Nix and working KVM available:

```sh
python3 tests/acceptance.py --output artifacts/my-recovery-acceptance
```

The output directory must not exist. Default repetition is two independent
processes for each failure scenario; `--repeat 2..5` adjusts this. Nix builds
use `--cores 0`. The suite runs sequentially and writes console logs, commands,
exit codes, source SHA-256 hashes, timings and per-scenario evidence.

The suite verifies:

- Two independent runs exhausting constructor retries after panel creation,
  followed by the new native recovery CLI and a 65-second observation period.
- Two independent delayed-cleanup quarantines, refusal of unsafe admission,
  explicit CLI recovery after cleanup, and a 65-second observation period.
- Actual interruption during a partially adopted panel transaction, competing
  request refusal during native settlement, recovery, and a 65-second observation.
- A **negative whole-context reset control**: the original GjsContext really
  finalizes, Mutter and original clients continue, but Shell bootstrap fails on
  the expected existing static GType. An arbitrary crash/startup failure does
  not count as reproducing this blocker.
- Fresh standalone native-GType positive and JS-owned-GType negative controls,
  including Valgrind and a debugger-confirmed failing old vfunc.
- A NixOS VM with GDM, real logind, PAM, a lock request during quarantined
  cleanup, input isolation, explicit recovery into a locked desktop, rejection
  of a wrong password and successful authentication with the correct password.

Every headless test checks original Wayland **and** XWayland client PIDs, native
socket FDs/inodes, window identities and subsequent protocol roundtrips. It also
checks native virtual-keyboard editing of those original clients, overview,
panel menus, window menus, rendered frames, new window mapping, UI object
collection, resource inventories and extension disable/enable. Probe text hashes
are checked throughout phases where text is expected to remain unchanged.

Headless graphical checks are never run in an implicit host session. Each
harness uses a private bus, XDG profile, headless compositor, explicit virtual
monitor and software rendering. Cleanup targets only its own process groups
and adopted descendants. The VM boots its own test system; no host system
configuration is activated.

Nix may reuse a successful VM test derivation. The aggregate report records its
exact store path and labels this reuse; headless scenarios and native context
controls execute afresh. Repeating the VM execution independently is possible
with Nix's `--rebuild` on the test output path.

An aggregate exit zero means **the alternative passed**. The machine-readable
report keeps `originalObjectiveAchieved=false` and
`wholeShellRestartDemonstrated=false`. Failed cases, unexpected negative-control
failures, or source changes during the suite make aggregate acceptance fail.

## Individual commands

```sh
nix develop --cores 0 .#stable -c python3 tests/isolated.py \
  --reload-ui-in-place --owned-request --ui-failure twice \
  --ui-failure-stage after-panel --soak-seconds 65 \
  --output artifacts/my-constructor-recovery

nix develop --cores 0 .#stable -c python3 tests/isolated.py \
  --reload-ui-in-place --owned-request --ui-failure once \
  --ui-failure-stage startup-wait --cleanup-mode delayed --soak-seconds 65 \
  --output artifacts/my-quarantine-recovery

nix build --cores 0 .#security-quarantine-vm --out-link result-security-quarantine-vm

nix develop --cores 0 .#runtime -c python3 tests/isolated.py \
  --reset-runtime --output artifacts/my-context-blocker
# Expected exit 1; inspect reset.log and result.json for the exact blocker.

nix develop --cores 0 .#native-type -c python3 tests/native-type-supervisor.py \
  tgnome-native-type-probe artifacts/my-native-context-control.json

nix flake check --cores 0
```

Within an already running private fixture, recovery itself is:

```sh
DBUS_SESSION_BUS_ADDRESS=unix:path=/PRIVATE/bus \
TGNOME_BUS_OWNER=:PRIVATE.UNIQUE.OWNER nix run . -- recover-desktop-ui
```

Those are placeholders for a fixture's explicit bus and unique owner, not host
discovery instructions. The integration tests supply actual values themselves.
Exit zero confirms published UI recovery. A timeout or disconnected caller does
not cancel an admitted operation; inspect native Status before retrying.

## Architectural blocker and limits

The full-context control currently fails at `Gjs_TransientSignalHolder` in
`signalTracker.js`: GLib static GTypes remain registered after GjsContext
disposal, so importing the same Shell graph cannot register them again. Its
`reset.log` also records a blocked callback during shutdown. Giving each
generation unique GType names is not a bounded lifecycle solution: earlier
experiments grew registrations and invoked callbacks from disposed contexts.

The standalone negative control establishes the second constraint independently:
retaining an instance of a JS-registered native GType does not make its original
vfunc safe after disposing the owning JS context. Its debugger evidence reaches
GJS's callback trampoline from the old native vfunc. The native-owned GType
control does survive three genuinely destroyed/replaced GjsContexts. This proves
a viable boundary for a small native-owned object, not a port of Shell to that
boundary. See `NATIVE-CONTEXT-REPORT.md` and `NATIVE-SHELL-BOUNDARY-AUDIT.md` for
the prior implementation and ownership analysis.

These are blockers to replacing the current integrated Shell context safely;
they do not establish that an extensively redesigned Shell is impossible.
Whole-Shell recovery requires moving all surviving native type/vfunc/callback
ownership out of disposable JS, or separating the compositor and restartable
Shell through a new protocol. The current implementation does neither for the
whole Shell. Native hangs/crashes, arbitrary JS interruption, third-party
extensions and physical devices remain outside the acceptance claim.

The optional realm branch is deliberately excluded from accepted recovery.
`artifacts/recovery-native-command` failed its generation-one panel-realm GC
gate, with a heap dump retained; `artifacts/recovery-acceptance-baseline` passed
the same broad branch earlier in this session. This intermittent retention is
unresolved, not waived by longer waits or hidden by the stable alternative.

## Evidence from this development session

On 21 October 2026 the standalone constructor-recovery run
`artifacts/recovery-native-stable/result.json` passed: two UI construction
failures, one automatic retry, explicit native CLI recovery, two committed UI
generations, the same compositor process and a 65-second observation period.

The new security-quarantine VM passed at
`result-security-quarantine-vm/evidence/tgnome-evidence/result.json`, backed by
`/nix/store/gng6yj0374hqmhhqyzfmv52pavrggrbd-vm-test-run-tgnome-security-quarantine`.
Its real guest Shell PID remained 987 throughout. Quarantine lasted until late
cleanup confirmation; recovery produced UI generation 2 with two commits,
one construction timeout, one quarantine and zero automatic retries after
quarantine. Native security bits were 31 during shielding and 3 after locked
recovery. The wrong password left the guest locked; correct PAM authentication
returned to user mode. Both original client identities, roundtrips and text
hashes survived. The final desktop screenshot was also visually inspected.

The first VM attempt incorrectly depended on absent UI Eval during quarantine.
The second exposed the real CLI readiness defect on locked recovery, corrected
by native publication tracking. A third reached recovery but had an incorrect
test expectation for refusal after exhausting the laboratory cap. The fourth
passed. These failures were not classified as successful recovery.

The full-context blocker also reproduced independently in
`artifacts/recovery-context-blocker`: baseline passed, old context finalized once,
Mutter survived, original clients continued, and bootstrap failed on
`Gjs_TransientSignalHolder`. This run correctly exited 1.

The complete repeated suite **passed all eight cases** in
[`artifacts/recovery-verified/result.json`](evidence/reports/recovery-verified/result.json).
The runner exited 0 and confirmed that its recorded source hashes remained
unchanged throughout execution. Its original-objective and whole-Shell-restart
flags remain false.

| Case | Verified result |
| --- | --- |
| failed-construction-1, failed-construction-2 | Each: two failed candidates, one retry, native CLI recovery, two committed generations, 65-second soak |
| quarantine-1, quarantine-2 | Each: delayed cleanup, admission refusal while quarantined, native CLI recovery after confirmation, two committed generations, 65-second soak |
| interrupted-panel | Real interrupted partial adoption, refusal of competing requests, native settlement, three committed generations, 65-second soak |
| context-blocker | Expected exit 1; old context finalized, original clients and compositor survived, duplicate static GType prevented Shell bootstrap |
| native-context-control | Native-owned object survived three actual context replacements; Valgrind memory-error check passed (leak checking disabled); JS-owned old vfunc failed with debugger-confirmed SIGSEGV |
| security-quarantine-vm | Successful VM derivation above reused; actual lock in quarantine, input containment, native recovery while locked, wrong-password rejection and successful PAM unlock |

The expected negative-control failures are counted only after their specific
failure signatures pass validation; they do not indicate successful restart.
Detailed results, process and connection identities, commands, rendered frames,
collection records and logs are under each case directory. The native control
executes afresh, including both direct and debugger runs of the unsafe variant;
only the successful VM derivation is reused in this aggregate execution.

CLI safety tests (9), `nix flake check --cores 0` and `git diff --check` passed.
