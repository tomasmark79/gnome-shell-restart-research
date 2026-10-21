"""Run actual context/type reattachment in private, busless native processes."""
import json
import os
from pathlib import Path
import resource
import shutil
import signal
import subprocess
import sys
import tempfile


def disable_core():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


probe = shutil.which(sys.argv[1]) or str(Path(sys.argv[1]).resolve())
cases = []
for mode in ('native', 'valgrind'):
    with tempfile.TemporaryDirectory(prefix='tgnome-type-rebind-') as directory:
        profile = Path(directory)
        env = {k: v for k, v in os.environ.items() if k not in (
            'DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY', 'G_DEBUG',
            'DBUS_STARTER_ADDRESS', 'DBUS_STARTER_BUS_TYPE')}
        env.update(HOME=directory, XDG_RUNTIME_DIR=directory,
                   XDG_CONFIG_HOME=directory, XDG_CACHE_HOME=directory,
                   XDG_DATA_HOME=directory, XDG_STATE_HOME=directory,
                   DBUS_SESSION_BUS_ADDRESS=f'unix:path={directory}/absent-session',
                   DBUS_SYSTEM_BUS_ADDRESS=f'unix:path={directory}/absent-system')
        command = [probe]
        if mode == 'valgrind':
            command = ['valgrind', '--quiet', '--error-exitcode=97', '--leak-check=no',
                       '--undef-value-errors=no', '--smc-check=all-non-file'] + command
        process = subprocess.Popen(command, env=env, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True,
                                   start_new_session=True, preexec_fn=disable_core)
        timed_out = False
        try:
            stdout, stderr = process.communicate(timeout=60 if mode == 'valgrind' else 20)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate()
        events = [json.loads(line) for line in stdout.splitlines() if line.startswith('{')]
        generations = [e for e in events if 'generation' in e]
        passed = (process.returncode == 0 and not timed_out and not stderr.strip()
                  and len(generations) == 3 and all(e['released'] and e.get('nativeChildReaped') for e in generations)
                  and len({e['native'] for e in generations}) == 1
                  and len({e['gtype'] for e in generations}) == 1
                  and len({e['objectTypes'] for e in generations}) == 1
                  and len({e['bridges'] for e in generations}) == 1
                  and any(e.get('passed') and e['contextsFinalized'] == 3 for e in events))
    case = dict(mode=mode, passed=passed and not profile.exists(),
                privateProfileRemoved=not profile.exists(), exitCode=process.returncode,
                timedOut=timed_out, events=events, stdout=stdout, stderr=stderr)
    cases.append(case)
    print(f'{mode}: passed={case["passed"]}, exit={process.returncode}', flush=True)
report = dict(classification='REATTACHED JS-REGISTERED GTYPE; NOT SHELL RESTART',
              passed=all(c['passed'] for c in cases), cases=cases)
Path(sys.argv[2]).write_text(json.dumps(report, indent=2) + '\n')
sys.exit(0 if report['passed'] else 1)
