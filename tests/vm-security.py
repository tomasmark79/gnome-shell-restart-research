"""NixOS VM driver script: all machine commands execute inside the guest.

Baseline mode uses upstream Shell; the separate patched VM target also checks
UI reconstruction and real lock/authentication, including lock arrival during
construction or quarantined cleanup. Passwords are public fixture values.
"""
import ast
import json
import shlex
import time


def alice(command):
    return (
        "runuser -u alice -- env XDG_RUNTIME_DIR=/run/user/1000 "
        "DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus " + command
    )


def evaluate(js):
    reply = machine.succeed(alice(
        "gdbus call --session --dest org.gnome.Shell "
        "--object-path /org/gnome/Shell --method org.gnome.Shell.Eval "
        + shlex.quote(js)
    ))
    # gdbus prints GVariant booleans, not Python's True/False. Parse the
    # outer boolean separately so JSON string contents are never rewritten.
    raw = reply.strip()
    assert raw.startswith("(") and raw.endswith(")"), raw
    ok, quoted = raw[1:-1].split(",", 1)
    value = ast.literal_eval(quoted.strip())
    assert ok == "true", value
    return json.loads(value)


def wait_value(js, predicate, timeout=90):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        try:
            last = evaluate(js)
            if predicate(last):
                return last
        except (AssertionError, ValueError) as error:
            last = str(error)
        time.sleep(0.5)
    raise AssertionError(f"Shell condition timed out: {js}: {last}")


STATE = """({pid: new imports.gi.Gio.Credentials().get_unix_pid(),
    locked: Main.screenShield.locked, active: Main.screenShield.active,
    mode: Main.sessionMode.currentMode,
    session: Main.screenShield._loginSession?.Id ?? null,
    starting: Main.layoutManager._startingUp})"""


def probe_record(backend):
    raw = machine.succeed(f"tail -n 1 /home/alice/{backend}.jsonl")
    return json.loads(raw)


def runtime_call(method):
    return alice(
        "gdbus call --session --dest org.gnome.Shell "
        "--object-path /org/gnome/Shell/TgnomeRuntime "
        "--method org.gnome.Shell.TgnomeRuntime." + method
    )


def runtime_status():
    raw = machine.succeed(runtime_call("Status"))
    return json.loads(ast.literal_eval(raw.strip())[0])


RELOAD_RPC = (
    "gdbus call --session --dest org.gnome.Shell "
    "--object-path /org/gnome/Shell/Extensions/Tgnome "
    "--method org.gnome.Shell.Extensions.Tgnome.ReloadDesktopUi"
)
RELOAD = alice(RELOAD_RPC)


def wait_native(predicate, timeout=10):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = runtime_status()
        if predicate(last):
            return last
        time.sleep(0.05)
    raise AssertionError(f"Native condition timed out: {last}")


def clients_unchanged(before):
    current = {b: probe_record(b) for b in before}
    for backend, old in before.items():
        new = current[backend]
        for key in ("pid", "backend", "fd", "inode", "windowId", "unsavedTextSha256"):
            assert old[key] == new[key], (backend, key, old, new)
        assert new["tick"] > old["tick"], (backend, old, new)
        machine.succeed(f"kill -0 {new['pid']}")
    return current


start_all()
report: dict[str, object] = {"classification": "RESEARCH PROTOTYPE", "passed": False,
          "authenticationFixtureOnly": True, "trueRestartDemonstrated": False,
          "desktopUiReloadDemonstrated": False}
try:
    patched = machine.succeed("cat /etc/tgnome-vm-fixture").strip() == "security-reload-v1"
    lock_race = machine.succeed("cat /etc/tgnome-vm-race").strip()
    assert lock_race in ("none", "preparation", "construction", "security-gap", "quarantine"), lock_race
    assert lock_race == "none" or patched
    report["lockRace"] = lock_race
    report["authenticationFixtureOnly"] = not patched
    with subtest("GDM Wayland login with real guest services"):
        machine.succeed("test -f /etc/tgnome-vm-fixture")
        machine.succeed("systemd-detect-virt --vm")
        machine.wait_for_unit("display-manager.service", timeout=180)
        machine.wait_for_file("/run/user/1000/wayland-0", timeout=180)
        machine.wait_for_unit("default.target", "alice", timeout=180)
        before = wait_value(STATE, lambda s: not s["starting"] and s["session"])
        assert not before["locked"] and before["mode"] == "user", before
        session = shlex.quote(before["session"])
        assert machine.succeed(f"loginctl show-session {session} -p Type --value").strip() == "wayland"
        report["before"] = before
        report["sessionBefore"] = machine.succeed(f"loginctl show-session {session}")
        machine.send_key("esc")

    with subtest("Original Wayland and XWayland connection probes"):
        for backend in ("wayland", "x11"):
            machine.succeed(alice(
                f"systemd-run --user --unit=tgnome-probe-{backend} "
                f"--property=StandardOutput=append:/home/alice/{backend}.jsonl "
                f"--property=StandardError=append:/home/alice/{backend}.log "
                f"--setenv=GDK_BACKEND={backend} --setenv=NO_AT_BRIDGE=1 "
                "--setenv=GTK_A11Y=none tgnome-client-probe"
            ))
            machine.wait_until_succeeds(f"test -s /home/alice/{backend}.jsonl")
        initial = {b: probe_record(b) for b in ("wayland", "x11")}
        report["clientsBefore"] = initial
        machine.screenshot("desktop-before-lock")

    if patched:
        with subtest("Reconstruct UI inside the native-backend security VM"):
            assert not evaluate("global.backend.is_headless()")
            assert runtime_status()["securityVm"] is True
            machine.succeed(alice("gnome-extensions enable restart-island@tgnome.local"))
            wait_value("!!Main.extensionManager.lookup('restart-island@tgnome.local')?.state", bool)
            machine.send_key("esc")
            wait_value("Main.overview.visible", lambda visible: not visible)
            journal_cursor = machine.succeed("journalctl -n 0 --show-cursor").strip().split("-- cursor: ")[-1]
            report["nativeBeforeReload"] = runtime_status()
            report["reloadAccepted"] = machine.succeed(RELOAD)
            wait_value("global._tgnomeUiGeneration ?? 0", lambda g: g == 1)
            native = runtime_status()
            assert native["state"] == "ui-ready" and native["uiCommits"] == 1, native
            report["nativeAfterReload"] = native
            report["clientsAfterReload"] = clients_unchanged(initial)
            state = wait_value(STATE, lambda s: not s["starting"] and s["session"])
            assert state["pid"] == before["pid"] and state["session"] == before["session"]
            machine.screenshot("desktop-after-ui-reload")

    with subtest("Lock via actual logind and reject an incorrect password"):
        if lock_race == "quarantine":
            evaluate("global._tgnomeUiFailureBudget = 1")
            evaluate("global._tgnomeUiFailureStage = 'startup-wait'")
            evaluate("global._tgnomeCleanupMode = 'delayed'")
            report["quarantineReloadAccepted"] = machine.succeed(RELOAD)
            quarantined = wait_native(lambda s: s["uiQuarantined"], timeout=15)
            assert quarantined["state"] == "ui-cancellation-timeout", quarantined
            assert not quarantined["uiActive"] and quarantined["uiCommits"] == 1, quarantined
            # The partially constructed Shell does not export Eval. Native
            # diagnostics must remain sufficient when all UI RPCs are absent.
            assert quarantined["securityBoundaryBits"] & 31 == 29, quarantined
            report["quarantinedBeforeLock"] = quarantined
        if lock_race in ("construction", "security-gap"):
            evaluate("global._tgnomeUiFailureBudget = 1")
            stage = "security-gap" if lock_race == "security-gap" else "startup-wait"
            evaluate("global._tgnomeUiFailureStage = " + json.dumps(stage))
            report["constructionRaceAccepted"] = machine.succeed(RELOAD)
            constructing = wait_native(lambda s: s["state"] == "same-context-ui-starting")
            # Shell's normal Eval object is not exported until after this
            # Main checkpoint. Observe the native endpoint and real logind,
            # rather than waiting for an unavailable UI-owned diagnostic RPC.
            if lock_race == "security-gap":
                constructing = wait_native(lambda s: s["securityBoundaryBits"] == 125)
                report["screenShieldAbsentAtLockRequest"] = True
            else:
                time.sleep(0.25)
            report["lockRaceConstructing"] = constructing
        if lock_race == "preparation":
            before_race = runtime_status()
            # VM-only Eval arms an await before the synchronous mutation gate.
            # No product API can request this delay on a physical backend.
            evaluate("global._tgnomeOwnedDelay = 3000")
            machine.succeed(alice(
                "systemd-run --user --unit=tgnome-lock-race "
                "--property=StandardOutput=append:/home/alice/lock-race.log "
                "--property=StandardError=append:/home/alice/lock-race.log " + RELOAD_RPC
            ))
            preparing = wait_native(lambda s: s["state"] == "ui-preparing")
            assert preparing["uiActive"] and preparing["attempts"] == before_race["attempts"] + 1, preparing
            report["lockRacePreparing"] = preparing
        machine.succeed(f"loginctl lock-session {session}")
        if lock_race == "quarantine":
            machine.wait_until_succeeds(
                f"test $(loginctl show-session {session} -p LockedHint --value) = yes", timeout=3
            )
            boundary = wait_native(lambda s: s["securityBoundaryBits"] & 31 == 31, timeout=3)
            report["lockAcceptedInQuarantine"] = boundary
            code, error = machine.execute(runtime_call("ReloadUiProbe") + " 2>&1")
            assert code != 0 and "quarantined" in error, error
            report["quarantineRecoveryRefusedBeforeCleanup"] = error
            machine.screenshot("locked-quarantine")
            machine.send_chars("x" * 150, delay=0.015)
            report["clientsDuringQuarantine"] = clients_unchanged(initial)
            cleaned = wait_native(lambda s: s["state"] == "ui-failed" and not s["uiQuarantined"], timeout=15)
            assert cleaned["uiFailures"] == 1 and cleaned["uiRetryAttempts"] == 0, cleaned
            assert cleaned["uiCommits"] == 1 and cleaned["attempts"] == 2, cleaned
            report["lateCleanupConfirmed"] = cleaned
            # Quarantine ends automatic retries permanently. Only this explicit
            # request may build a replacement, which must inherit lock intent.
            owner = ast.literal_eval(machine.succeed(alice(
                "gdbus call --session --dest org.freedesktop.DBus --object-path /org/freedesktop/DBus "
                "--method org.freedesktop.DBus.GetNameOwner org.gnome.Shell"
            )).strip())[0]
            assert owner.startswith(":"), owner
            recovery_reply = machine.succeed(alice(
                "env TGNOME_BUS_OWNER=" + shlex.quote(owner) + " tgnome recover-desktop-ui"
            ))
            report["explicitQuarantineRecovery"] = json.loads(recovery_reply)
            assert report["explicitQuarantineRecovery"]["recovered"], recovery_reply
            recovered = wait_native(lambda s: s["state"] == "ui-ready", timeout=30)
            assert recovered["uiCommits"] == 2 and recovered["attempts"] == 3, recovered
            assert recovered["uiRetryAttempts"] == 0 and recovered["uiQuarantines"] == 1, recovered
            locked = wait_value(STATE, lambda s: s["locked"] and s["active"])
            boundary = evaluate("global._tgnomeGetSecurityBoundary()")
            assert boundary["pendingLock"] and not boundary["curtainVisible"] and not boundary["grabbed"], boundary
            assert boundary["durableLockRequests"] == 1, boundary
            report["nativeAfterQuarantineRecovery"] = recovered
            report["securityAfterQuarantineRecovery"] = boundary
            report["clientsAfterQuarantineRecovery"] = clients_unchanged(initial)
        if lock_race in ("construction", "security-gap"):
            machine.wait_until_succeeds(
                f"test $(loginctl show-session {session} -p LockedHint --value) = yes", timeout=3
            )
            report["lockAcceptedDuringConstruction"] = True
            input_native_before = runtime_status()
            report["constructionInputNativeBefore"] = input_native_before
            assert input_native_before["state"] == "same-context-ui-starting"
            expected_mask = 127 if lock_race == "security-gap" else 31
            assert input_native_before["securityBoundaryBits"] == expected_mask, input_native_before
            machine.screenshot("curtain-during-construction")
            # Keep sending QEMU keyboard events across the deadline and retry.
            # Probe hashes reveal any observed delivery to original app entries.
            machine.send_chars("x" * 400, delay=0.015)
            input_native_after = runtime_status()
            report["constructionInputNativeAfter"] = input_native_after
            assert input_native_after["state"] == "ui-ready"
            assert input_native_after["securityBoundaryBits"] == 3, input_native_after
            recovered = wait_native(lambda s: s["state"] == "ui-ready" and s["uiCommits"] == 2)
            locked = evaluate(STATE)
            report["lockRaceAfterRecovery"] = locked
            report["nativeAfterConstructionRace"] = recovered
            assert locked["locked"] and locked["active"], locked
            boundary = evaluate("global._tgnomeGetSecurityBoundary()")
            assert boundary["durableLockRequests"] == 1, boundary
            assert boundary["screenShieldPresent"] and not boundary["pausedWithoutShield"], boundary
            report["securityBoundaryAfterRecovery"] = boundary
        else:
            locked = wait_value(STATE, lambda s: s["locked"] and s["active"])
        assert locked["pid"] == before["pid"], (before, locked)
        machine.wait_until_succeeds(
            f"test $(loginctl show-session {session} -p LockedHint --value) = yes"
        )
        report["clientsWhileLocked"] = clients_unchanged(initial)
        if lock_race in ("construction", "security-gap"):
            # A corrective candidate must preserve the accepted lock, not
            # silently return to an unlocked UI after discarding its actors.
            state_after_recovery = locked
            assert state_after_recovery["locked"] and state_after_recovery["active"], state_after_recovery
            assert state_after_recovery["mode"] == "unlock-dialog", state_after_recovery
            assert recovered["uiFailures"] == 1 and recovered["uiRetryAttempts"] == 1, recovered
            machine.send_chars("locked-client-input-must-not-leak")
            report["clientsDuringConstructionRace"] = clients_unchanged(initial)
        if lock_race == "preparation":
            cancelled = wait_native(lambda s: s["state"] == "ui-preparation-failed" and not s["uiActive"])
            assert cancelled["attempts"] == preparing["attempts"]
            for key in ("uiBuildSerial", "uiCommits", "uiFailures", "uiRetryAttempts", "uiTimeouts"):
                assert cancelled[key] == before_race[key], (key, before_race, cancelled)
            assert cancelled["preparationFailures"] == before_race["preparationFailures"] + 1
            assert cancelled["preparationTimeouts"] == before_race["preparationTimeouts"]
            assert evaluate("global._tgnomeUiGeneration") == 1
            assert not evaluate("global._tgnomeUiPreparing || global._tgnomeResetPrepared")
            machine.wait_until_succeeds(alice("sh -c " + shlex.quote(
                "test $(systemctl --user show tgnome-lock-race.service -p ExecMainStatus --value) = 1"
            )), timeout=15)
            error = machine.succeed("cat /home/alice/lock-race.log")
            assert "UI changed before preparation commit" in error, error
            time.sleep(1)
            stable = runtime_status()
            for key in ("attempts", "uiBuildSerial", "uiCommits", "uiRetryAttempts", "preparationFailures"):
                assert stable[key] == cancelled[key], (cancelled, stable)
            report["lockRaceCancelled"] = cancelled
            report["lockRaceError"] = error
            machine.screenshot("lock-interrupted-preparation")
        if patched:
            native_before_refusal = runtime_status()
            code, error = machine.execute(RELOAD + " 2>&1")
            assert code != 0, error
            code_native, error_native = machine.execute(runtime_call("ReloadUiProbe") + " 2>&1")
            expected_refusal = ("attempt limit reached" if native_before_refusal["attempts"] >= 3
                                else "not prepared")
            assert code_native != 0 and expected_refusal in error_native, error_native
            native_after_refusal = runtime_status()
            # Authentication lazily registers object types during this wait;
            # transaction state and all operation counters must remain intact.
            for key, value in native_before_refusal.items():
                if key not in ("registeredObjectTypes", "newObjectTypes"):
                    assert native_after_refusal[key] == value, (key, native_before_refusal, native_after_refusal)
            assert evaluate(STATE)["locked"]
            report["lockedReloadRefusal"] = {"public": error, "native": error_native}
        if not evaluate("!!Main.screenShield._dialog?._authPrompt"):
            machine.send_key("ret")
        wait_value("!!Main.screenShield._dialog?._authPrompt?._entry.reactive", bool)
        machine.send_key("ctrl-a")
        wrong_password_cursor = machine.succeed("journalctl -n 0 --show-cursor").strip().split("-- cursor: ")[-1]
        machine.send_chars("incorrect-vm-password")
        machine.send_key("ret")
        machine.wait_until_succeeds(
            "journalctl -b --after-cursor=" + shlex.quote(wrong_password_cursor)
            + " --no-pager | grep -F 'pam_unix(gdm-password:auth): authentication failure'", timeout=30
        )
        wait_value("!!Main.screenShield._dialog?._authPrompt?._entry.reactive", bool)
        time.sleep(0.2)
        rejected = evaluate(STATE)
        assert rejected["locked"] and rejected["active"], rejected
        report["afterWrongPassword"] = rejected
        machine.screenshot("wrong-password-still-locked")

    with subtest("Unlock through the real GDM password verifier"):
        wait_value("!!Main.screenShield._dialog?._authPrompt?._entry.reactive", bool)
        machine.send_key("ctrl-a")
        machine.send_chars("tgnome-vm-password")
        machine.send_key("ret")
        after = wait_value(STATE, lambda s: not s["locked"] and not s["active"] and s["mode"] == "user")
        assert after["pid"] == before["pid"] and after["session"] == before["session"]
        machine.wait_until_succeeds(
            f"test $(loginctl show-session {session} -p LockedHint --value) = no"
        )
        report["after"] = after
        report["clientsAfter"] = clients_unchanged(initial)
        if patched:
            if lock_race == "preparation":
                # The reservation consumes one laboratory request slot, but
                # leaves the old UI available and permits the final explicit slot.
                wait_value("Main.extensionManager.lookup('restart-island@tgnome.local')?.state === 1", bool)
                report["retryAfterUnlockAccepted"] = machine.succeed(RELOAD)
                wait_value("global._tgnomeUiGeneration", lambda g: g == 2)
                retry = runtime_status()
                assert retry["attempts"] == 3 and retry["uiCommits"] == 2 and retry["uiRetryAttempts"] == 0, retry
                report["nativeAfterExplicitRetry"] = retry
                report["clientsAfterExplicitRetry"] = clients_unchanged(initial)
                state = wait_value(STATE, lambda s: not s["starting"] and s["session"])
                assert state["pid"] == before["pid"] and state["session"] == before["session"]
            try:
                retired = wait_value(
                    "(() => { global._tgnomeCollectGarbage(); return Main.getTgnomeRetiredUiStatus(); })()",
                    lambda records: bool(records) and all(
                        r["collected"] == r["expectedCollected"] for r in records),
                    timeout=10,
                )
            except AssertionError:
                report["retiredUi"] = evaluate("Main.getTgnomeRetiredUiStatus()")
                heap = evaluate("global._tgnomeDumpUiHeap()")
                machine.succeed("mkdir -p /tmp/tgnome-evidence")
                machine.succeed("cp " + shlex.quote(heap) + " /tmp/tgnome-evidence/ui.heap")
                raise
            assert any(r["name"] == "screenShield" and r["collected"] for r in retired), retired
            report["retiredUi"] = retired
            journal = machine.succeed(
                f"journalctl -b _PID={before['pid']} --after-cursor={shlex.quote(journal_cursor)} --no-pager -o cat"
            )
            problems = [line for line in journal.splitlines() if any(
                text in line for text in ("JS ERROR", "already disposed", "Exception in callback",
                                          "CRITICAL", "TGNOME stale source", "TGNOME in-place UI startup failed"))]
            report["postReloadDiagnosticProblems"] = problems
            assert not problems, problems
            report["desktopUiReloadDemonstrated"] = True
            report["classification"] = "SHELL RELOAD"
        machine.screenshot("desktop-after-unlock")
        report["passed"] = True
finally:
    # Keep diagnostic artifacts even when a gate fails. VM teardown is owned by
    # the NixOS driver, including both guest probes and all guest services.
    machine.succeed("mkdir -p /tmp/tgnome-evidence")
    payload = shlex.quote(json.dumps(report, indent=2))
    machine.succeed(f"printf '%s\\n' {payload} > /tmp/tgnome-evidence/result.json")
    machine.succeed("journalctl -b --no-pager > /tmp/tgnome-evidence/journal.log")
    machine.succeed("cp /home/alice/*.jsonl /home/alice/*.log /tmp/tgnome-evidence/ 2>/dev/null || true")
    machine.copy_from_machine("/tmp/tgnome-evidence", "evidence")
