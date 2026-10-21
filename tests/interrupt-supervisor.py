"""Own-process supervisor for the standalone GJS interrupt experiments."""
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import tempfile


def run_child(binary, mode, timeout, profile):
    environment = {k: v for k, v in os.environ.items() if k not in (
        "DBUS_SESSION_BUS_ADDRESS", "DBUS_SYSTEM_BUS_ADDRESS", "DISPLAY",
        "WAYLAND_DISPLAY", "XAUTHORITY", "GNOME_SHELL_JS", "G_DEBUG")}
    # Explicit absent addresses prevent GIO's optional monitor backends from
    # discovering or autolaunching a host bus, even outside a Nix build sandbox.
    environment.update({
        "DBUS_SESSION_BUS_ADDRESS": "unix:path=" + str(Path(profile) / "absent-session-bus"),
        "DBUS_SYSTEM_BUS_ADDRESS": "unix:path=" + str(Path(profile) / "absent-system-bus"),
        "XDG_RUNTIME_DIR": profile,
        "XDG_CACHE_HOME": str(Path(profile) / "cache"),
        "XDG_CONFIG_HOME": str(Path(profile) / "config"),
        "XDG_DATA_HOME": str(Path(profile) / "data"),
        "TGNOME_INTERRUPT_ISOLATED": "1",
    })
    process = subprocess.Popen([binary, mode], env=environment, start_new_session=True,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        os.killpg(process.pid, signal.SIGTERM)
        try:
            stdout, stderr = process.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate(timeout=2)
    records = [json.loads(line) for line in stdout.splitlines() if line.startswith("{")]
    return {"mode": mode, "returnCode": process.returncode, "timedOut": timed_out,
            "records": records, "stderr": stderr, "processReaped": process.poll() is not None}


def run(binary, mode, timeout):
    with tempfile.TemporaryDirectory(prefix="tgnome-interrupt-") as profile:
        result = run_child(binary, mode, timeout, profile)
    result["runtimeProfileRemoved"] = not Path(profile).exists()
    return result


def main():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    binary, output, variant = sys.argv[1:]
    assert variant in ("baseline", "patched"), variant
    runs = [run(binary, "hard", 10)]
    if variant == "patched":
        runs.extend([run(binary, "recoverable", 10), run(binary, "recover-then-hard", 10)])
        for mode in ("nested", "nested-loop", "promise", "module", "raw-nested", "unscoped", "protected"):
            runs.append(run(binary, mode, 2))
        runs.append(run(binary, "foreign-thread", 5))
        runs.append(run(binary, "native-closure", 10))
    hard = runs[0]
    hard_sync = [r for r in hard["records"] if r.get("case") == "synchronous-spin"]
    passed = (
        hard["returnCode"] == -signal.SIGABRT and not hard["timedOut"]
        and len(hard_sync) == 3 and all(r["passed"] for r in hard_sync)
        and "terminated with uncatchable exception" in hard["stderr"]
        and all(r["processReaped"] and r["runtimeProfileRemoved"] for r in runs)
    )
    recovered_callbacks = False
    if variant == "patched":
        recovered = runs[1]
        cases = [r for r in recovered["records"] if "case" in r]
        summaries = [r for r in recovered["records"] if "classification" in r]
        recovered_callbacks = (
            recovered["returnCode"] == 0 and not recovered["timedOut"]
            and len(cases) == 8 and all(r["passed"] for r in cases)
            and len(summaries) == 1 and summaries[0]["passed"]
            and summaries[0]["interruptions"] == 5
            and recovered["stderr"].count("TGNOME explicit interruption at native boundary") == 2
            and "already disposed" not in recovered["stderr"]
        )
        passed = passed and recovered_callbacks
        restored = runs[2]
        restored_cases = [r for r in restored["records"] if "case" in r]
        passed = passed and restored["returnCode"] == -signal.SIGABRT and not restored["timedOut"]
        passed = passed and len(restored_cases) == 8 and all(r["passed"] for r in restored_cases)
        passed = passed and "terminated with uncatchable exception" in restored["stderr"]
        for unsupported in runs[3:-2]:
            passed = passed and unsupported["timedOut"]
            passed = passed and any(r.get("event") == "interrupt-denied" for r in unsupported["records"])
            passed = passed and not any(r.get("event") == "interrupt-delivered" for r in unsupported["records"])
        foreign = runs[-2]
        passed = passed and foreign["returnCode"] == 0 and any(
            r.get("case") == "foreign-thread-refused" and r["passed"] for r in foreign["records"])
        native = runs[-1]
        native_cases = [r for r in native['records'] if 'case' in r]
        passed = passed and native['returnCode'] == 0 and not native['timedOut']
        passed = passed and len(native_cases) == 4 and all(r['passed'] for r in native_cases)
        passed = passed and sum(r.get('event') == 'interrupt-denied' for r in native['records']) == 2
        passed = passed and 'TGNOME tagged expected exception' in native['stderr']
    hard_observed = hard["returnCode"] == -signal.SIGABRT and "terminated with uncatchable exception" in hard["stderr"]
    report = {"classification": "RESEARCH PROTOTYPE", "passed": passed,
              "variant": variant, "shellRecoveryDemonstrated": False, "runs": runs,
              "hardCallbackAbortsProcess": hard_observed,
              "markedNativeCallbacksRecovered": recovered_callbacks}
    Path(output).write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "runs"}))
    if not passed:
        for run_result in runs:
            print(json.dumps({**{k: run_result[k] for k in ("mode", "returnCode", "timedOut", "records")},
                              "stderrTail": run_result["stderr"][-1000:]}))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
