> Historical research report. Claims apply to its original experiment, not
> today's implementation. See [STATUS.md](STATUS.md) and
> [RESEARCH-GUIDE.md](RESEARCH-GUIDE.md) before interpreting results.

# Retired desktop UI ownership audit

The earlier three-generation reload and 65-second soak passed the tracked
resource tests in [STABLE-REPORT.md](STABLE-REPORT.md). A stronger collection
gate now also requires retired UI wrappers and JavaScript managers to become
unreachable. A stable count of root registrations does not establish that.
The complete safe Shell restart remains unproven.

## Validating the observer

`ui-collection-1` failed preparation because the first diagnostic referenced an
unimported `Clutter` name; it was corrected to use the already imported
`St.Widget` for the two actor targets. No UI reset occurred in that run.

`ui-collection-2` through `ui-collection-4` are invalid collection measurements:
their unreferenced control did not finalize. They must not be interpreted as
evidence of UI retention. WeakRef-based observations were replaced with
FinalizationRegistry notifications, which do not dereference the observed
targets during polling.

In GJS 1.88.1, queuing finalizer cleanup does not itself schedule a promise job.
The normal job dispatcher runs cleanup after jobs. The isolated probe therefore
performs `System.gc()` and enqueues an empty resolved-promise callback, then
reads status in a later D-Bus call. This was checked against the pinned
[GJS context implementation](https://github.com/GNOME/gjs/blob/1.88.1/gjs/context.cpp#L1200)
and an independent experiment, now reproduced by `tests/gc-control.js`.

The flake's `gc-observer` check requires an unreferenced object to finalize while
a deliberately retained object remains alive. Each UI generation repeats those
two controls. The retained control is the actual persistent window manager.
Actor destruction and wrapper collection are separate recorded properties.
These probes establish facts about selected wrappers/managers, not the
finalization of every native resource or the total absence of memory leaks.

## Findings

`ui-collection-5` used the corrected observer: both controls behaved correctly.
The old panel, Quick Settings and extension manager were collected; the old
layout manager, overview, input method and keyboard manager were retained.
The extension manager required replacing raw subscriptions to the permanent
session mode and St settings with UI-owned subscriptions.

The retained window manager also cached its window-menu source actor in the
destroyed UI group. Its UI helper is now recreated after the new layout exists.
The test opens and closes an actual client window menu before the baseline and
after each reconstruction. It waits for the opening animation before closing
and destroying the menu; a same-frame close during opening produced disposed
actor diagnostics and was an invalid interaction test.

`ui-collection-6` and `ui-collection-7` stopped at the native-type gate. Opening
the window menu lazily registered `CoglPixelBuffer` before the reload baseline.
The native diagnostic's type list is cumulative from its first query, so the
test now compares added types relative to its actual baseline. It still permits
only the previously identified first-use `GVfsMetadataProxy` type after that
baseline; later generations must keep the exact type count.

`ui-collection-8/ui-generation-1.heap` captures the remaining four retained UI
objects after GC. `tools/heap_paths.py` finds traced paths from roots to tagged
retired objects without treating the dump's weak-map entries as roots:

| Retired object | Observed root path |
| --- | --- |
| Layout manager | Persistent native wrapper with background source/cache fields → `_layoutManager` |
| Overview | The same background root → old layout → bound signal callback → old overview |
| Input method | Persistent native wrapper → bound signal callback → old input method |
| Keyboard manager | Persistent native wrapper → bound signal callback → old keyboard manager |

The background group is a child of the preserved native window group. Destroying
the UI group alone therefore preserves its old background actors and source.
The reset now destroys the layout's background managers and background group
before adopting the native window groups into the surviving stage. Native
window actors themselves remain preserved.

The input method subscribed directly to the retained input-source model and
IBus bus. The keyboard manager subscribed directly to the persistent seat and
backend. Those subscriptions now use `connectObject` with their UI owner so the
UI lifetime cleanup disconnects them. Integration verification of this expanded
cleanup is recorded in subsequent runs; source inspection alone is not a pass.

`ui-collection-9` confirmed collection of the old input method and keyboard
manager after those subscription fixes. Its remaining heap paths ran through
our own `_tgnomeDurableOwners` set to the old layout and onward to overview.
The backend construction scope had incorrectly promoted a UI owner. Layout and
overview now carry an explicit UI-owned marker, which both durable-owner
registration paths must respect. This preserves backend objects while ensuring
that incidental UI work during backend construction cannot become permanent.

`ui-collection-10` showed that this removed the durable-set path; the old layout
still had raw subscriptions to workspace-count changes and session-mode changes.
Those were converted to UI-owned subscriptions. `ui-collection-11` collected
the layout and isolated overview retention to the transform callback of a
`SwipeTracker` orientation binding. That binding is now explicitly unbound when
the overview's tracker is destroyed before its actors disappear.

`ui-collection-12` then isolated a further path through the backend's native
drag-and-drop object into the old XdndHandler and its overview callbacks. Its
three native subscriptions now use UI ownership as well. XdndHandler was added
to the finalization targets to catch this ownership regression directly.

`ui-collection-13` passed all three UI generations with the expanded gate:
all eight retired targets per generation were finalized (24 targets total),
both actor targets per generation had emitted destruction, each unreferenced
control finalized, and every persistent window-manager control remained alive.
It also passed window-menu interaction, the previous registry/connection/text
checks, three post-reload extension lifecycle cycles and new client mapping.
The post-reload diagnostic problem count was zero. This run had no extended
soak; the combined delayed-callback run is recorded separately.

## Final combined result

`ui-collection-final` passed the inner UI/collection checks and 65-second soak,
but the outer command exited 1: a D-Bus-activated helper was still writing into
the temporary profile while Python removed it. Its inner `passed: true` alone
must not be treated as a passing overall command.

The dedicated outer test launcher is now a Linux child subreaper. After its
worker exits, it reaps or terminates only its own adopted descendants, identified
by direct parentage and `waitpid`, before deleting the profile. It never selects
processes by name, host bus or display. Cleanup is bounded and recorded in
`supervisor.json` and the final `result.json`. A separate flake check exercises a
real orphaned helper to verify that containment and reaping work.

`artifacts/ui-collection-final-2` passed with outer exit code 0 and
`supervisor.privateProfileRemoved: true`. It demonstrated:

- Three UI reconstructions, with all eight selected retired UI targets per
  generation finalized: 24 old UI targets in total.
- Three unreferenced finalization controls collected and all three persistent
  window-manager controls retained. The two actor targets per generation emitted
  destruction before collection.
- Working panel menus, overview and client window menus after each generation.
- Stable tracked registration inventories; native object types warmed from 986
  to 987 once for GVfs metadata, then stayed stable.
- Three further extension disable/enable cycles, a 65-second soak, original
  Wayland/X11 socket and window identities, unchanged probe text hashes, and
  mapping/removal of additional clients afterwards.
- Zero post-reload diagnostic problems and safe rejection of a fourth request.

The tested patched executable was
`/nix/store/wbxn62b282yzyljvq2n0vjly7n9bn9da-gnome-shell-50.5/bin/.gnome-shell-wrapped`.
A read-only process-environment scan after cleanup found no remaining processes
with a private `/tgnome-…` runtime directory. The live host Shell remained PID
1350942 with its original executable. Compilation used all available threads
through `--cores 0`; no system configuration or physical display was activated.
The final `nix flake check --cores 0` passed, including CLI safety, independent
GC controls and the real orphaned-helper supervisor check.

This is **SHELL RELOAD in the tested headless scope**. Bounded recovery from a
failed full UI rebuild, lock/unlock security and native input behavior remain
next requirements. These collection results do not complete the original goal.

## Reproduce

```sh
nix build --cores 0 .#stable-shell --no-link
nix flake check --cores 0
nix develop --cores 0 .#stable -c python3 tests/isolated.py --reload-ui-in-place --soak-seconds 65 --output artifacts/ownership-local
python3 tools/heap_paths.py artifacts/ownership-local/ui-generation-1.heap
```

A heap is saved only if the collection gate fails. It is copied only from the
private test data directory, which the harness validates before reading. Heap
dumps contain private runtime details and remain ignored under `artifacts/`.
All tests use the private headless Shell; the live desktop is not a target.
Native physical input, lock/unlock authentication, failed-rebuild rollback and
complete JavaScript/native resource collection remain separate requirements.
