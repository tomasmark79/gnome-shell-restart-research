"""Bounded standalone GJS realm experiments with no graphical/session access."""
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import tempfile


def limit_core():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def main():
    executable = str(Path(sys.argv[1]).resolve())
    entry = str((Path(sys.argv[2]) / "entry.js").resolve())
    results = []
    for mode in ("plain", "gtype", "delegate", "delegate-held"):
        with tempfile.TemporaryDirectory(prefix="tgnome-realm-") as directory:
            profile = Path(directory)
            env = {key: value for key, value in os.environ.items() if key not in (
                "DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY", "G_DEBUG",
                "DBUS_STARTER_ADDRESS", "DBUS_STARTER_BUS_TYPE")}
            env.update(HOME=directory, XDG_RUNTIME_DIR=directory,
                       XDG_CONFIG_HOME=directory, XDG_CACHE_HOME=directory,
                       XDG_DATA_HOME=directory,
                       DBUS_SESSION_BUS_ADDRESS=f"unix:path={directory}/absent-session",
                       DBUS_SYSTEM_BUS_ADDRESS=f"unix:path={directory}/absent-system")
            process = subprocess.Popen([executable, mode, entry], env=env,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       text=True, start_new_session=True,
                                       preexec_fn=limit_core)
            timed_out = False
            try:
                stdout, stderr = process.communicate(timeout=20)
            except subprocess.TimeoutExpired:
                timed_out = True
                os.killpg(process.pid, signal.SIGKILL)
                stdout, stderr = process.communicate()
            events = [json.loads(line) for line in stdout.splitlines()
                      if line.startswith("{")]
            result = next((item for item in events
                           if item.get("event") == "realm-result"), {})
            expected_types = (["absent"] * 3 if mode == "plain" else
                              ["delegated"] * 3 if mode.startswith("delegate") else
                              ["registered", "duplicate", "duplicate"])
            passed = (process.returncode == 0 and not timed_out and not stderr.strip() and
                      len([e for e in events if e.get("event") == "realm-generation"]) == 3 and
                      result.get("types") == expected_types and
                      result.get("backendAlive") is True and
                      result.get("freshModuleGraphs") is True and
                      result.get("canonicalNativeBindings") is True and
                      result.get("esmBootstrap") is True and
                      result.get("promiseTimerCompleted") is True and
                      result.get("typedSignalCompleted") is True and
                      len(result.get("gc", [])) == 3)
            if mode in ("plain", "delegate"):
                passed = passed and all(all(item.values()) for item in result.get("gc", []))
            elif mode == "gtype":
                # The first real registered GType is expected to retain its
                # prototype/global: evidence of a missing restart boundary.
                passed = passed and bool(result.get("gc")) and not any(
                    result["gc"][0].values()) and all(
                        all(item.values()) for item in result["gc"][1:])
            else:
                # Intentionally keep the last UI delegate: the same observer
                # must detect this known native-to-JS retention path.
                passed = passed and bool(result.get("gc")) and all(
                    all(item.values()) for item in result["gc"][:2]) and not any(
                        result["gc"][2].values())
        record = dict(mode=mode, passed=passed, exitCode=process.returncode,
                      timedOut=timed_out, privateProfileRemoved=not profile.exists(),
                      events=events, stderr=stderr)
        results.append(record)
        print(json.dumps(record), flush=True)
    Path(sys.argv[3]).write_text(json.dumps({
        "classification": "RESEARCH PROTOTYPE",
        "passed": all(item["passed"] and item["privateProfileRemoved"] for item in results),
        "cases": results,
    }, indent=2) + "\n")
    return 0 if all(item["passed"] and item["privateProfileRemoved"] for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
