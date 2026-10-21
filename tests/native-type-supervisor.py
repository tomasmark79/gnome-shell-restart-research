"""Two bounded processes; neither can connect to the active desktop/session bus."""
import json
import os
from pathlib import Path
import resource
import shutil
import signal
import subprocess
import sys
import tempfile


def limit_core():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


probe = shutil.which(sys.argv[1]) or str(Path(sys.argv[1]).resolve())
results = []
for mode in ("native", "native-valgrind", "js-owned"):
    with tempfile.TemporaryDirectory(prefix="tgnome-native-type-") as directory:
        profile = Path(directory)
        env = {k: v for k, v in os.environ.items() if k not in (
            "DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY", "G_DEBUG",
            "DBUS_STARTER_ADDRESS", "DBUS_STARTER_BUS_TYPE")}
        env.update(HOME=directory, XDG_RUNTIME_DIR=directory,
                   XDG_CONFIG_HOME=directory, XDG_CACHE_HOME=directory,
                   XDG_DATA_HOME=directory,
                   DBUS_SESSION_BUS_ADDRESS=f"unix:path={directory}/absent-session",
                   DBUS_SYSTEM_BUS_ADDRESS=f"unix:path={directory}/absent-system")
        command = [probe, "native" if mode.startswith("native") else mode]
        if mode == "native-valgrind":
            command = ["valgrind", "--quiet", "--error-exitcode=97", "--leak-check=no",
                       "--undef-value-errors=no", "--smc-check=all-non-file"] + command
        process = subprocess.Popen(command, env=env,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, start_new_session=True, preexec_fn=limit_core)
        timed_out = False
        try:
            stdout, stderr = process.communicate(timeout=60 if mode == "native-valgrind" else 20)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate()
        events = [json.loads(line) for line in stdout.splitlines() if line.startswith('{')]
        if mode.startswith("native"):
            generations = [e for e in events if e.get("event") == "generation"]
            passed = (process.returncode == 0 and not stderr.strip() and
                      len(generations) == 3 and all(e["released"] for e in generations) and
                      len({e["native"] for e in generations}) == 1 and
                      any(e.get("event") == "native-result" and e["passed"] for e in events))
        else:
            # Require the exact failing operation, not an arbitrary startup
            # crash. Reproduce under gdb in the same private environment.
            disposed = next((e for e in events if e.get("event") == "negative-disposed"), {})
            passed = (process.returncode == -signal.SIGSEGV and
                      disposed.get("contextsFinalized") == 1 and
                      disposed.get("globalCleared") is True and
                      disposed.get("callbackCleared") is True and
                      events[-1].get("event") == "negative-vfunc-entry")
            debug = subprocess.Popen(
                ["gdb", "--nx", "--batch", "-iex", "set auto-load off",
                 "-ex", "set pagination off", "-ex", "run",
                 "-ex", "bt", "--args", probe, mode],
                env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, start_new_session=True, preexec_fn=limit_core)
            try:
                backtrace, _ = debug.communicate(timeout=20)
            except subprocess.TimeoutExpired:
                os.killpg(debug.pid, signal.SIGKILL)
                backtrace, _ = debug.communicate()
                passed = False
            passed = passed and "SIGSEGV" in backtrace and "expect_name" in backtrace
    result = dict(mode=mode, passed=passed and not timed_out and not profile.exists(),
                  exitCode=process.returncode, timedOut=timed_out,
                  privateProfileRemoved=not profile.exists(), events=events,
                  stderr=stderr, stdout=stdout)
    if mode == "js-owned":
        result["backtrace"] = backtrace
    results.append(result)
report = dict(classification="RESEARCH PROTOTYPE", passed=all(r["passed"] for r in results),
              cases=results)
Path(sys.argv[2]).write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report), flush=True)
sys.exit(0 if report["passed"] else 1)
