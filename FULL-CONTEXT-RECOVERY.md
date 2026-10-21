> Historical research report. Claims apply to its original experiment, not
> today's implementation. See [STATUS.md](STATUS.md) and
> [RESEARCH-GUIDE.md](RESEARCH-GUIDE.md) before interpreting results.

# Complete Shell context replacement

This separate build replaces the entire GJS context and bootstraps GNOME Shell
50.5 again inside the original Mutter process. It does not reuse the old Main
module, window manager, module graph, JavaScript global or JavaScript runtime.
The `stable` UI recovery alternative is unchanged.

## Current validation status

**The complete-context implementation passed the isolated end-to-end test.**
`artifacts/full-context-rebind-outer/result.json` records three actual old
GjsContext finalizations, four different runtime epochs, the same Mutter PID,
unchanged original Wayland/XWayland socket identities, native keyboard input
after recovery, working overview and menus, newly mapped clients and 65 seconds
of observation. There are no transition diagnostics or retired callbacks.
All three cycles retain 989 native object types and 229 native vfunc bridges.

Earlier independent clean runs are retained in
`artifacts/full-context-rebind-native-listener` and
`artifacts/full-context-rebind-repeat`. They also pass three replacements each;
the outer-loop safeguard was subsequently added after native VM testing.

The real native-backend VM test also passed three context replacements,
keyboard-driven overview after every replacement, real logind locking, an
incorrect password rejection, successful GDM/PAM unlock and another 65 seconds
of observation with original clients. Its immutable evidence is
`/nix/store/7v5kmz5vmcmxj68dg16jgn00gj9cs6m3-vm-test-run-tgnome-full-context/evidence/tgnome-evidence/result.json`.
This evidence applies to the explicitly scoped cooperative idle restart;
it does not establish recovery of an arbitrary hung runtime.

## Reproduction

Run from this checkout:

```sh
nix develop --cores 0 .#type-rebind -c python3 \
  tests/type-rebind-supervisor.py tgnome-type-rebind-probe \
  artifacts/type-rebind-lifetimes.json

nix develop --cores 0 .#rebind -c python3 tests/isolated.py \
  --reset-runtime --soak-seconds 65 \
  --output artifacts/full-context-recovery

nix build --no-link .#full-context-vm
```

The second command uses a private headless compositor, session bus, mock system
bus, temporary profile and software rendering. It never targets the running
desktop and never activates a NixOS configuration. There is no public host
restart command in this research checkout. `tgnome restart-shell-context`
implements the complete operation within the explicitly selected private
session. The private native reset endpoint is bounded to three
attempts, requires an idle prepared unlocked desktop, and pins the bus owner.

For private crash diagnosis, add `--debug-shell`. The optional
`--debug-glib-assertions` and `--debug-retired-callbacks` stop that debugger at
the respective failure. Only the private child enables debugger attachment;
no system debugging policy is changed, and core dumps are disabled.

## Implementation

`shell/buildTypeRebind.py` patches the pinned GJS 1.88.1 source. All type
reattachment is explicitly gated by `TGNOME_REBIND_TYPES=1` in the separate
build. A native weak ownership record permits reusing a JS-registered static
GType only after its previous GjsContext has finalized and only with compatible
parent, flags, interfaces and property metadata. Signals must also match.
Live-owner duplicate registration and incompatible schemas are rejected.

Native process-lifetime libffi dispatchers keep vtable addresses valid. Each
runtime supplies its own delegate; invalidation removes that delegate before
its old trampoline can be freed. In the gap, native parent behavior or a neutral
return applies. Native class-signal bridges similarly detach old JS handlers.
No unique generation-specific GType names are used.

Two process-global GJS assumptions also require changes: object-prototype qdata
is cleared when its owner is destroyed, and each new runtime registers its own
moving-GC weak-wrapper hook. The native toggle queue is reopened only when it
is empty. Without the latter changes, the complete Shell reproducibly crashed
in a native wrapper toggle after an otherwise successful new bootstrap.

`shell/fullContextInit.js` tracks JavaScript registrations with `Meta.Laters`
and `Meta.IdleMonitor`. Shutdown removes those registrations along with the
existing GLib source registry. Mutter's native work and client connections are
outside these registries. `shell/gjsCallbackLifetimes.inc` records native
callback counts per runtime without holding JavaScript roots or contexts.

## Evidence and limits

The native control passed both direct execution and Valgrind in
`artifacts/type-rebind-native-reaper.json`. Three contexts reuse the same native
instance, GType, signal and native dispatchers. Retired globals, wrappers and
callbacks collect; native calls between runtimes do not enter old JavaScript.
The forced shrinking-GC control passes, but it did not reproduce the previous
full-Shell crash before the fix, so it is not evidence for that crash's cause.
The debugger stack from the actual Shell is the relevant evidence.

The native child-reaping control also verifies actual child exit and reaping
after its owning JS context has finalized, both directly and under Valgrind.
The Shell uses one native accessibility listener for its entire process:
libatspi 2.60's constructor destroy-notify is disabled upstream and otherwise
leaves a retired callback per restart. Per-context signal handlers are detached
before reuse. The final ownership ledger has empty entries for all retired
epochs, rather than merely ignoring these callbacks.

The VM reproduced another real failure after exercising overview: a native
Status request evaluated JavaScript, whose nested loop dispatched the reset
before the old evaluation returned. GJS then refused creating a second current
context. Complete-context Status now uses native data exclusively, and reset
dispatch defers while `g_main_depth() > 1`. The corrected VM passed.

The complete-context suite checks three distinct replacement epochs, three
finalized old contexts, stable process and client connection identities,
unchanged client state, native keyboard-driven overview, panel and window
menus, newly mapped clients, post-restart input and delayed diagnostics.
Results are written to `result.json`, with logs and rendered PNG frames.

The native VM establishes GDM/PAM/logind lock and unlock after complete
replacement. Lock arrival during replacement, accessibility event delivery,
audio behavior, network configuration, screen recording, third-party
extensions and multi-monitor behavior need separate coverage. The older
stable-UI lock-race evidence applies only to that alternative.
Complete-context replacement is cooperative and requires a
responsive idle unlocked Shell; it does not recover a dead Mutter process or
prove safe interruption of arbitrary JavaScript.

The requested separate publication workspace is `../gnome-shell-restart-nix`.
It contains the extracted patch, pinned builds, NixOS module and independent
tests. Host configuration has not been changed or activated. The working
stable UI recovery implementation and its acceptance evidence are preserved.
