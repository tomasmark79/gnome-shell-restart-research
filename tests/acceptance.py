#!/usr/bin/env python3
"""Run the complete isolated recovery alternative and its architectural control.

Exit zero means the documented alternative passed, not a whole-Shell restart.
Every run uses fresh evidence directories; the NixOS VM result may be cached
under its content-addressed derivation, which is recorded explicitly.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from isolated import enable_private_subreaper, reap_private_descendants

ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify_recovery(report, manual=False, interrupted=False):
    require(report['passed'] and report['baselinePassed'], 'Recovery harness failed')
    require(report['desktopUiReloadDemonstrated'] and report['virtualKeyboardInputDemonstrated'],
            'Missing UI or real virtual-input verification')
    require(not report['wholeShellReloadDemonstrated'] and not report['trueRestartDemonstrated'],
            'Unexpected whole-Shell claim: reassess this acceptance contract')
    require(report['supervisor']['privateProfileRemoved'], 'Private profile leaked')
    probe = report['inPlaceReload']
    native = probe['nativeAfter']
    require(native['state'] == 'ui-ready' and native['contextsFinalized'] == 0,
            'Expected ready Shell in the retained context')
    require(probe['diagnosticProblemCount'] == 0 and not native['uiQuarantined'],
            'Recovery diagnostics or terminal quarantine')
    for backend in ('wayland', 'x11'):
        first, last = probe[backend]['before'], probe[backend]['after']
        for key in ('pid', 'fd', 'inode', 'windowId'):
            require(first[key] == last[key], f'{backend}: changed {key}')
        require(last['tick'] > first['tick'], f'{backend}: no post-recovery roundtrip')
    if manual:
        recoveries = [c['manualRecoveryRequest'] for c in probe['cycles']
                      if 'manualRecoveryRequest' in c]
        require(len(recoveries) == 1 and recoveries[0]['recovered'],
                'The extension-independent recovery command was not exercised')
    if interrupted:
        require(report['controlledInterruptedPanelTransferRecovered'], 'No interrupted panel recovery')
    return dict(uiCommits=native['uiCommits'], uiBuilds=native['uiBuildSerial'],
                failures=native['uiFailures'], retries=native['uiRetryAttempts'],
                contextsFinalized=native['contextsFinalized'])


def verify_blocker(report, directory):
    reset = report['runtimeReset']
    require(report['baselinePassed'] and not report['passed'], 'Expected a healthy baseline and failed reset')
    require(reset['nativeAfter']['contextsFinalized'] == 1 and reset['shellProcessSurvived'],
            'Failure did not occur after actual context disposal with Mutter alive')
    require('Gjs_TransientSignalHolder is already registered' in (directory / 'reset.log').read_text(),
            'Expected static GType registration blocker did not reproduce')
    require(report['supervisor']['privateProfileRemoved'], 'Blocker test profile leaked')
    for backend in ('wayland', 'x11'):
        first, last = report[backend]['before'], reset['clientsAfterReset'][backend]
        for key in ('pid', 'fd', 'inode', 'windowId', 'unsavedTextSha256'):
            require(first[key] == last[key], f'{backend}: blocker control lost {key}')
        require(last['tick'] > report[backend]['after']['tick'], f'{backend}: no roundtrip after reset')
    return dict(contextsFinalized=1, compositorSurvived=True,
                blocker='Gjs_TransientSignalHolder remains registered after GjsContext disposal')


def run_step(command, directory, expected_exit=0, timeout=1800):
    directory.mkdir()
    started = time.monotonic()
    with (directory / 'console.log').open('w') as console:
        process = subprocess.Popen(command, cwd=ROOT, stdout=console, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        try:
            code = process.wait(timeout=timeout)
        except BaseException:
            # The inner harness owns cleanup. Give it a chance before reaping
            # only descendants adopted by this explicitly isolated supervisor.
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGINT)
                try:
                    process.wait(timeout=35)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
            raise
        finally:
            descendants = reap_private_descendants()
    metadata = dict(command=command, exitCode=code, expectedExitCode=expected_exit,
                    seconds=round(time.monotonic() - started, 2), descendants=descendants)
    (directory / 'execution.json').write_text(json.dumps(metadata, indent=2) + '\n')
    require(code == expected_exit, f'Unexpected exit {code}: see {directory / "console.log"}')
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='New, nonexistent evidence directory')
    parser.add_argument('--repeat', type=int, default=2, help='Independent recovery repetitions (2..5)')
    args = parser.parse_args()
    require(2 <= args.repeat <= 5, 'Repeat must be between 2 and 5')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    enable_private_subreaper()
    source_files = [ROOT / 'flake.nix', ROOT / 'flake.lock', ROOT / 'tgnome.py',
                    *sorted((ROOT / 'shell').glob('*')), *sorted((ROOT / 'tests').glob('*.py')),
                    *sorted((ROOT / 'tests').glob('*.nix')), *sorted((ROOT / 'extension').glob('*'))]
    manifest = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in source_files if p.is_file()}
    report = dict(classification='VERIFIED RECOVERY ALTERNATIVE', passed=False,
                  originalObjectiveAchieved=False, wholeShellRestartDemonstrated=False,
                  startedAt=datetime.now(timezone.utc).isoformat(), sourceSha256=manifest, cases=[])
    try:
        for repeat in range(args.repeat):
            for label, extra in (
                ('failed-construction', ['--ui-failure', 'twice', '--ui-failure-stage', 'after-panel']),
                ('quarantine', ['--ui-failure', 'once', '--ui-failure-stage', 'startup-wait',
                                '--cleanup-mode', 'delayed']),
            ):
                name = f'{label}-{repeat + 1}'
                directory = output / name
                command = ['nix', 'develop', '--cores', '0', '.#stable', '-c', 'python3',
                           'tests/isolated.py', '--reload-ui-in-place', '--owned-request',
                           '--track-time', '--soak-seconds', '65', '--output', str(directory), *extra]
                print(f'Running {name}', flush=True)
                step = run_step(command, directory)
                data = json.loads((directory / 'result.json').read_text())
                step.update(name=name, evidence=verify_recovery(data, manual=True))
                report['cases'].append(step)
        name = 'interrupted-panel'
        directory = output / name
        print(f'Running {name}', flush=True)
        step = run_step(['nix', 'develop', '--cores', '0', '.#interruption', '-c', 'python3',
                         'tests/isolated.py', '--reload-ui-in-place', '--owned-request',
                         '--interrupt-js', '--interrupt-operation', 'panel-adopting',
                         '--interrupt-handoff', '--soak-seconds', '65', '--output', str(directory)], directory)
        step.update(name=name, evidence=verify_recovery(json.loads((directory / 'result.json').read_text()),
                                                       interrupted=True))
        report['cases'].append(step)
        name = 'context-blocker'
        directory = output / name
        print(f'Running {name} (expected failure)', flush=True)
        step = run_step(['nix', 'develop', '--cores', '0', '.#runtime', '-c', 'python3',
                         'tests/isolated.py', '--reset-runtime', '--output', str(directory)],
                        directory, expected_exit=1)
        step.update(name=name, evidence=verify_blocker(json.loads((directory / 'result.json').read_text()),
                                                      directory))
        report['cases'].append(step)
        name = 'native-context-control'
        directory = output / name
        print(f'Running {name}', flush=True)
        step = run_step(['nix', 'develop', '--cores', '0', '.#native-type', '-c', 'python3',
                         'tests/native-type-supervisor.py', 'tgnome-native-type-probe',
                         str(directory / 'result.json')], directory)
        control = json.loads((directory / 'result.json').read_text())
        require(control['passed'] and len(control['cases']) == 3,
                'Native GType control/Valgrind/JS-owned negative control failed')
        step.update(name=name, evidence={c['mode']: c['exitCode'] for c in control['cases']})
        report['cases'].append(step)
        name = 'security-quarantine-vm'
        directory = output / name
        print(f'Building/verifying {name}', flush=True)
        step = run_step(['nix', 'build', '--cores', '0', '.#security-quarantine-vm',
                         '--out-link', str(directory / 'result')], directory)
        vm = json.loads((directory / 'result/evidence/tgnome-evidence/result.json').read_text())
        require(vm['passed'] and vm['desktopUiReloadDemonstrated'], 'VM recovery/authentication failed')
        require(vm['explicitQuarantineRecovery']['recovered'] and vm['afterWrongPassword']['locked']
                and not vm['after']['locked'], 'Missing real quarantine recovery and PAM lock/unlock')
        step.update(name=name, storePath=str((directory / 'result').resolve()),
                    execution='Nix derivation check; may reuse a cached successful VM run')
        report['cases'].append(step)
        # A source edit during the suite invalidates the aggregate claim.
        require(all(hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest
                    for path, digest in manifest.items()), 'Sources changed during acceptance run')
        report['passed'] = True
        report['scope'] = ('Desktop UI reconstruction and explicit failure recovery in a retained Main/GJS/Mutter; '
                           'real guest PAM/logind; original Wayland/XWayland clients preserved')
        report['limitations'] = ['Main/module graph/backend services/GjsContext are retained',
                                 'No recovery from native crashes or arbitrary protected/native hangs',
                                 'No production deployment or physical-device/third-party-extension validation']
    except Exception as error:
        report['error'] = f'{type(error).__name__}: {error}'
    finally:
        report['finishedAt'] = datetime.now(timezone.utc).isoformat()
        (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(str(output / 'result.json'), flush=True)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
