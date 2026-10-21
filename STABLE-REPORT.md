> Historical research report. Claims apply to its original experiment, not
> today's implementation. See [STATUS.md](STATUS.md) and
> [RESEARCH-GUIDE.md](RESEARCH-GUIDE.md) before interpreting results.

# Persistent-context Shell UI reconstruction

Classification: **SHELL RELOAD**, limited to the tested headless desktop UI
boundary. Three UI generations and the delayed-callback gate passed in
`artifacts/stable-settings-final`. The complete safe Shell restart goal remains unmet.
This is separate from the panel-only reload in [PANEL-REPORT.md](PANEL-REPORT.md).

The subsequent [object ownership audit](OWNERSHIP-REPORT.md) adds a stronger
collection gate. It found retained layout, overview and input managers outside
the earlier root-registration inventory. Earlier passing runs remain evidence
for their recorded scope, not proof of complete lifecycle cleanup.
The subsequent combined run `artifacts/ui-collection-final-2` passed this added
gate and the 65-second soak, including cleanup of the private process tree.
See the ownership report for the exact retained-reference fixes and controls.

## Boundary and implementation

The `stable-shell` package keeps Mutter's native main loop, Wayland server,
XWayland, window actors, GJS context and registered GTypes alive. A private
native endpoint requests a bounded UI teardown and a new `Main.start()`.
This replaces desktop UI instances while retaining selected backend models:
window management, input sources, IBus, component services and system actions.
Definitions remain cached; this does not reload source code or recover a
blocked JavaScript runtime.

The preceding whole-context disposal experiment could finalize GJS while
clients survived, but required new GType names and left callbacks entering
disposed JS. See [RUNTIME-REPORT.md](RUNTIME-REPORT.md). Reusing the context
avoids attempting to unregister static GTypes. It introduces a different
requirement: every old UI subscription, gesture, export, timer and cached
actor must be released without dismantling a retained backend.

The experiment tracks root signal subscriptions, session-bus exports and name
ownership, bus watches, stage actions and JavaScript-created GLib sources.
Explicit backend scopes retain backend-owned registrations. The normal
process shutdown signal remains separate from the experimental UI reset.
Input gestures are detached before their old target actors are destroyed.
Recreated UI rearms its signal tracking and extension lifecycle. Menu and
overview functionality are exercised after reconstruction.

Implementation files are `shell/stable-lifetime.patch`, `stableRegistry.js`,
`stableMain.js`, `stableEnvironment.js`, `stableSignalTracker.js`, `stableIBus.js`
and `stableSystemActions.js`, plus the native-loop infrastructure described
in the runtime report. `flake.nix` applies them to GNOME Shell 50.5 with the
existing pinned Mutter 50.5; `tests/isolated.py` performs the experiment.

## Evidence and failures

Runs `artifacts/stable-1` through `stable-11` are failed research runs, not
successful reloads. Existing native Wayland and X11 probe connections continued
to round-trip in the observed first reconstruction. Their original processes,
display sockets and window IDs were retained. The strict whole-test result
remained false.

The audits found and corrected several concrete ownership mistakes: loss of
the keyring bus name and GeoClue watch, accumulated stage gestures, callbacks
from an old IBus panel service, and background-app UI subscriptions that
survived their actors. A preload timer belongs to the retained IBus manager;
deleting it with the UI left a stale source ID. Its allocation is now scoped
to the backend. These corrections require the subsequent integration gate;
passing construction alone does not establish correctness.

The missing `workareas-changed` subscription was traced to the initial welcome
dialog, which remains allocated after first startup but is not recreated once
the welcome-tour version has been recorded. The private fixture now represents
an established profile with the tour already shown. This keeps the inventory
comparison strict and compares equivalent generations; the onboarding dialog
itself is outside this test's coverage.

`stable-12` passed three reconstructions and a 65-second soak with original
client connections intact. `stable-13` and `stable-final` mapped new clients and
preserved the probe's editable text, but failed the diagnostic gate when the
X11 decoration helper tried to activate an unavailable AT-SPI service. The
private fixture now sets `NO_AT_BRIDGE=1` and `GTK_A11Y=none` for GTK helpers.
This does not filter critical messages; accessibility remains untested.

`stable-final-2` passed the expanded test: three reconstructions, functional
menus and overview, stable tracked registries, stable GJS epoch and compositor
identity, a 65-second soak, unchanged original native display sockets and
window IDs, unchanged hashes of random text held in GTK entry widgets, and
successful mapping/removal of additional Wayland and X11 windows afterwards.
The fourth reload request was refused without changing native supervisor
state. No post-reload critical messages were recorded.

The observed registry sizes were 14 session-bus exports, 8 owned names, 1 bus
watch, 4 attached stage actions and 64 tracked root signals. Registered native
object types changed from 985 to 986 once for lazy `GVfsMetadataProxy` loading,
then remained at 986. No GJS context was disposed. These are specific measured
registries, not a proof that every old JavaScript object was collected.

A subsequent source audit found raw `global.settings` subscriptions in the
extension manager outside those measured roots. Tracking now includes global
settings, with the cached favorites model scoped to backend lifetime. This
expanded audit passed in `artifacts/stable-settings`: all 74 tracked signals
remained identical across three UI reconstructions, including the ten settings
subscriptions (two backend-owned and eight UI-owned). That run did not include
the 65-second soak.

The final combined run, `artifacts/stable-settings-final`, passed all of the
above, including the 65-second soak and three additional disable/enable cycles
of the test extension after the third UI reconstruction. This exercises the
settings changes with old extension-manager subscriptions removed. Its final
tracked signal inventory remained at 74, the diagnostic problem count was zero,
and the fourth UI reload was safely rejected. The result deliberately reports
`desktopUiReloadDemonstrated: true` and `wholeShellReloadDemonstrated: false`.

| Final run identity | Original identity retained |
| --- | --- |
| Wayland client | PID `1929919`, socket inode `6312621`, surface ID `10` |
| X11 client | PID `1929934`, socket inode `6311714`, XID `2097156` |
| Patched Shell executable | `/nix/store/zj23v0qd3b5jb67wf5kcvf0ggzaqnnah-gnome-shell-50.5/bin/.gnome-shell-wrapped` |
| Registered object types | `985` before; `986` after the one GVfs warmup; stable thereafter |
| Unsaved entry text | Original SHA-256 unchanged in both clients throughout all heartbeats |

The fixture never recreates the original windows or reconnects their displays.
Additional clients are separate, explicitly created test processes. After test
cleanup, a read-only process-environment scan found no processes retaining a
private `/tgnome-…` runtime directory. The host Shell remained PID `1350942`
with its original executable. The final flake check passed using cached valid
checks; the patched package and GTK probe had already built successfully.

The package builds locally. A recorded build used `build flags: -j16` after
the user requested all available compilation threads. `nix flake check
--cores 0` passed, including the CLI safety checks. Neither result is a
successful in-session restart demonstration.

## Reproduce and revert

```sh
nix build --cores 0 .#stable-shell --no-link
nix flake check --cores 0
nix develop --cores 0 .#stable -c python3 tests/isolated.py --reload-ui-in-place --soak-seconds 65 --output artifacts/stable-local
```

Use a new output directory. `--cores 0` uses all available build cores. The
test runs only a private headless Shell and two real GTK probes, on a private
D-Bus with temporary XDG directories. Its mock logind lives on that private
bus, which also replaces the test's system-bus address. It never invokes the
host Shell reset endpoint. Three attempts are permitted per private process;
the fourth is rejected. No automatic retry loop exists.

Building or testing does not install an extension in the live desktop or
activate a NixOS generation. No host rollback, logout or service restart is
needed. The harness stops its own process groups. Logs remain under the chosen
artifact directory; Nix outputs are ordinary garbage-collectable store paths.

## Outstanding engineering requirements

The next step is to expand the persistent-emitter audit and verify collection
of obsolete UI objects. Lazy window-manager UI and third-party extension
lifecycles require additional coverage. The GTK entry fixture demonstrates
preserved in-memory text in those two clients; it establishes no general
application-state restoration mechanism.

The fixture does not implement GDM authentication or demonstrate lock/unlock
security. Native physical input, real display outputs, multi-monitor changes,
arbitrary third-party extensions and recovery from a failed full UI rebuild
are not generally established. [Subsequent tests](RECOVERY-REPORT.md) restore
working UI after an injected post-construction failure with one corrective
attempt, and stop after a second failure until an explicit request. This
reconstructs new UI; it does not restore the former actor objects or prove
recovery from partial construction or blocked JS. Those are substantive remaining
requirements. The public `reload-shell` command therefore still fails safely
as unsupported. The live workstation Shell has not been replaced or restarted.
