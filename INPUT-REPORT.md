> Historical research report. Claims apply to its original experiment, not
> today's implementation. See [STATUS.md](STATUS.md) and
> [RESEARCH-GUIDE.md](RESEARCH-GUIDE.md) before interpreting results.

# Native virtual input and rendered UI across reload

Classification: **SHELL RELOAD in an isolated headless fixture**. This adds
native input-path and pixel evidence to [RECOVERY-REPORT.md](RECOVERY-REPORT.md).
It does not establish physical keyboard, display or lock/unlock behavior, and
does not complete the full safe Shell restart goal.

## What the fixture exercises

Before the UI baseline, the test creates one virtual keyboard on the private
compositor's Clutter seat. It records its native GObject address and keeps that
same device through the UI reconstructions. Its identity must match afterwards.
The extension checks `global.backend.is_headless()` as well as the explicit
laboratory flags before creating a device or injecting input.

The events use `ClutterVirtualInputDevice.notify_keyval()` with monotonic
microsecond timestamps and explicit press/release pairs. Mutter 50.5's
`src/backends/native/meta-virtual-input-device-native.c` routes those events to
the seat implementation associated with that virtual device. This is an
in-process input path in the private compositor, not an input service targeting
the host desktop. The API and signatures were checked in the pinned Mutter
archive, including its existing virtual-keyboard tests.

The two existing probe windows are arranged at distinct 500×160 frame rectangles
before the reload baseline. The ordinary desktop-state comparison requires
their positions, sizes, workspace, focus and monitor data to survive reload.
No window is recreated or moved as a recovery operation.

The same native keyboard exercises two routes before/after reconstruction:

- Super opens GNOME overview, and Escape closes it. The helper waits for actual
  overview state and normal action mode; these transitions are not direct calls
  to `Main.overview.show()` or `hide()` in the successful path.
- After all preservation checks, it focuses each original PID/title-matched
  probe window, sends End followed by `a`, and restores the prior focused window.
  The GTK process must report the precomputed SHA-256 of its original random
  entry text with exactly one appended `a`.

The probe initializes its entry once and never changes its text in the heartbeat
loop. It only reads the actual GTK entry and hashes it. The extension does not
set client widget text or call a client-side text setter. Process IDs, socket
FDs/inodes and native window IDs must remain unchanged while input is received.
The original text hash must remain constant until the deliberate edit at the
end; the test does not confuse that intentional edit with state loss.

## Failures and fixes

`input-1` failed an API lookup before input testing: the seat accessor belongs
to the stage's Clutter backend, not the `global.backend` Meta backend. The
helper was corrected to use `global.stage.context.get_backend()`.

`input-2` delivered the intended text edit to both original clients, but failed
the critical-log gate. Native user activity fired an old message tray's idle
watch, which tried to update an already destroyed actor. The fix tracks and
removes that tray's native active-watch IDs during destruction. Presence proxy
initialization now has a cancellable and destruction guard; its signal is
disconnected. Session-mode and source-policy subscriptions use UI ownership.
Message tray was added to finalization targets so the old actor must collect.

`input-3` passed after those fixes. `input-4` additionally captured actual desktop
pixels. `input-5` passed native Super/Escape transitions and text editing after
the three reloads, with before/after desktop and overview images. These were
short runs; the longer failure/retry scenarios are recorded separately.

## Final combined evidence

Both `artifacts/input-native-once-final` and
`artifacts/input-native-twice-final` exited 0 after 65-second soaks, with zero
post-reload diagnostic problems and `supervisor.privateProfileRemoved: true`.
They repeat the bounded recovery scenarios and all existing connection,
registration, collection and admission checks, then exercise native overview
and both original clients through the preserved virtual keyboard.

| Run | Keyboard native address before and after | Original Wayland client | Original X11 client |
| --- | --- | --- | --- |
| One injected failure | `0x555557c6bdb0` | PID 2160214, inode 6713615, surface 10 | PID 2160259, inode 6716771, XID 2097156 |
| Two failures, then explicit recovery | `0x55555b8a7ad0` | PID 2160236, inode 6715771, surface 10 | PID 2160261, inode 6720556, XID 2097156 |

Each run finalized 40 selected old UI objects, including the failed candidates
and message trays; its finalization and retention controls also passed. Native
object types warmed once from 988 to 989 and then stayed stable across the
reconstructions. All preserved client identities continued round-tripping;
their deliberately edited text matched the predicted digest in both backends.
Super/Escape worked before and after using the same native virtual keyboard.

The tested executable was
`/nix/store/yrkm0g1c9i33xf4djr33b5vjlf18yhfg-gnome-shell-50.5/bin/.gnome-shell-wrapped`.
The final combined desktop and overview frames were visually inspected as well
as checked for PNG format/dimensions. Local evidence includes the
restored desktop after automatic recovery (not exported: `artifacts/input-native-once-final/desktop-after.png`)
and overview after explicit recovery (not exported: `artifacts/input-native-twice-final/overview-after.png`).

The follow-up `artifacts/input-guard-final` short run also passed a refusal
check: requesting the native overview exercise while overview was already open
returned an error and left it open. Cleanup owns only transitions initiated by
that exercise. The final flake check passed, the built Shell log records
`build flags: -j16`, and no processes with a private `/tgnome-…` runtime remained
after cleanup. The live host Shell stayed PID 1350942 with its original store
executable; it was not replaced, restarted or used as an input/capture target.

## Rendered evidence

The native `Shell.Screenshot` implementation saves 1280×720 PNGs in the private
profile, copied into the chosen artifact directory with their permissions.
The harness verifies the PNG signature and dimensions. These are compositor
captures, not reconstructed illustrations or external screenshots of the host.

The four artifacts are `desktop-before.png`, `overview-before.png`,
`overview-after.png` and `desktop-after.png`. Desktop-after is captured after
the deliberate client edits; overview-after is captured before those edits.
The short-run frames were visually inspected: the restored panel/background,
both probe windows, overview thumbnails, search field and dock were visible.

## Reproduce

```sh
nix build --cores 0 .#stable-shell --no-link
nix flake check --cores 0
nix develop --cores 0 .#stable -c python3 tests/isolated.py --reload-ui-in-place --ui-failure once --parallel-prepare --soak-seconds 65 --output artifacts/input-once-local
nix develop --cores 0 .#stable -c python3 tests/isolated.py --reload-ui-in-place --ui-failure twice --soak-seconds 65 --output artifacts/input-twice-local
```

The source changes are in `tests/probe.c`, `tests/isolated.py`,
`extension/extension.js`, `shell/stable-lifetime.patch` and
`shell/stableMain.js`. The test needs no host installation or activation; its
supervisor removes only its own private process tree and temporary profile.
Compilation uses `--cores 0` for all available threads.

Physical input/output, IME composition, pointer/touch devices, accessibility,
notification-history preservation, lock/unlock authentication, partial startup
failure and atomic recovery if a controller disappears remain unproven. A
working virtual keyboard and image capture must not be used as proof of those
requirements or as permission to replace the live Shell.
