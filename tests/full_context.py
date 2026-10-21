"""End-to-end checks for complete Shell context replacement, never the host."""
import os
from pathlib import Path
import shutil
import signal
import struct
import subprocess
import sys
import time


def verify(*, call, native_call, wait_for, shell, output, work, report,
           backends, initial, processes, streams, records):
    proof = {'cycles': [], 'originalObjectiveAchieved': False}
    report['fullContextRecovery'] = proof
    report['passed'] = False
    report['classification'] = 'COMPLETE CONTEXT REPLACEMENT EXPERIMENT'
    report.pop('trueRestartDemonstrated', None)
    report['shellProcessRestarted'] = False
    report['reloadScope'] = 'entire Shell GJS context and module graph; original Mutter process retained'
    log_offset = (output / 'shell.log').stat().st_size

    def copy_frame(path, name):
        frame = Path(path).resolve()
        assert frame.is_relative_to((work / 'data').resolve())
        header = frame.read_bytes()[:24]
        assert header[:8] == b'\x89PNG\r\n\x1a\n'
        assert struct.unpack('!II', header[16:24]) == (1280, 720)
        shutil.copy2(frame, output / f'{name}.png')
        return f'{name}.png'

    try:
        arranged = call('ArrangeProbeWindows')['windows']
        def arranged_ready():
            frames = {w['id']: w['frame'] for w in call('Status')['desktop']['windows']}
            return all(frames.get(w['id']) == w['frame'] for w in arranged)
        wait_for(arranged_ready)
        baseline = call('Status')
        proof['desktopBefore'] = baseline['desktop']
        before_overview = call('ExerciseNativeOverview')
        copy_frame(before_overview['path'], 'full-overview-before')
        proof['frameBefore'] = copy_frame(call('CaptureTestFrame')['path'], 'full-desktop-before')
        call('ExerciseWindowMenu')
        proof['nativeBefore'] = native_call('Status')
        epochs = {baseline['runtimeEpoch']}
        for number in range(1, 4):
            before = call('Status')
            cycle = {'number': number, 'beforeEpoch': before['runtimeEpoch']}
            proof['cycles'].append(cycle)
            command = subprocess.run([sys.executable,
                str(Path(__file__).resolve().parents[1] / 'tgnome.py'),
                'restart-shell-context'], capture_output=True, text=True, timeout=40)
            assert command.returncode == 0, (command.stdout, command.stderr)
            import json
            cycle['command'] = json.loads(command.stdout)
            assert cycle['command']['wholeShellRestarted']
            def ready():
                assert shell.poll() is None, f'Compositor exited: {shell.returncode}'
                status = call('Status')
                return status if (status['runtimeEpoch'] not in epochs and
                                  not status['shellState']['startingUp']) else False
            after = wait_for(ready, timeout=25)
            epochs.add(after['runtimeEpoch'])
            cycle['afterEpoch'] = after['runtimeEpoch']
            assert after['pid'] == shell.pid
            assert cycle['command']['afterEpoch'] == after['runtimeEpoch']
            assert after['desktop'] == baseline['desktop']
            assert after['panel']['containerCount'] == 1
            assert after['windowGroupAttached']
            assert after['shellState']['mode'] == 'user'
            assert after['shellState']['modalCount'] == 0
            cycle['menus'] = call('ExercisePanel')
            cycle['overview'] = call('ExerciseNativeOverview')
            cycle['overviewFrame'] = copy_frame(cycle['overview']['path'], f'full-overview-{number}')
            cycle['windowMenu'] = call('ExerciseWindowMenu')
            native = native_call('Status')
            assert native['contextsFinalized'] == number, native
            assert native['pid'] == shell.pid
            assert native['attempts'] == number
            cycle['native'] = native
            cycle['clients'] = {}
            for backend in backends:
                last = records(output / f'{backend}.jsonl')[-1]
                assert last['tick'] > report[backend]['after']['tick']
                for value in records(output / f'{backend}.jsonl'):
                    assert all(value[k] == initial[backend][k] for k in
                               ['pid', 'fd', 'inode', 'windowId', 'unsavedTextSha256'])
                cycle['clients'][backend] = last
        assert len(epochs) == 4
        # Warmup can register lazily imported classes; repeated resets must not
        # allocate generation-specific types or additional native dispatchers.
        for key in ['registeredObjectTypes', 'vfuncBridges']:
            values = [cycle['native'][key] for cycle in proof['cycles']]
            assert len(set(values)) == 1, (key, values)
        seconds = int(os.environ.get('TGNOME_SOAK_SECONDS', '0'))
        for _ in range(seconds):
            time.sleep(1)
            assert shell.poll() is None
        proof['observationSeconds'] = seconds
        original_ids = {w['id'] for w in baseline['desktop']['windows']}
        proof['lateClients'] = {}
        for backend in backends:
            stream = open(output / f'full-late-{backend}.jsonl', 'w')
            err = open(output / f'full-late-{backend}.log', 'w')
            streams.extend([stream, err])
            client = subprocess.Popen([os.environ['TGNOME_PROBE']],
                                      env={**os.environ, 'GDK_BACKEND': backend},
                                      stdout=stream, stderr=err, start_new_session=True)
            processes.append(client)
            wait_for(lambda: len(records(output / f'full-late-{backend}.jsonl')) >= 2)
            def mapped():
                ids = {w['id'] for w in call('Status')['desktop']['windows']}
                return ids if original_ids < ids and len(ids) == len(original_ids) + 1 else False
            ids = wait_for(mapped)
            proof['lateClients'][backend] = sorted(ids - original_ids)
            os.killpg(client.pid, signal.SIGTERM)
            client.wait(timeout=10)
            wait_for(lambda: {w['id'] for w in call('Status')['desktop']['windows']} == original_ids)
        proof['input'] = {}
        for backend in backends:
            before_input = records(output / f'{backend}.jsonl')[-1]
            sent = call('TypeIntoProbe', str(initial[backend]['pid']))
            def typed():
                value = records(output / f'{backend}.jsonl')[-1]
                return value if value['unsavedTextSha256'] == value['expectedTypedSha256'] else False
            after_input = wait_for(typed, timeout=10)
            assert after_input['tick'] > before_input['tick']
            assert after_input['unsavedTextSha256'] != before_input['unsavedTextSha256']
            assert all(all(v[k] == initial[backend][k] for k in ['pid', 'fd', 'inode', 'windowId'])
                       for v in records(output / f'{backend}.jsonl'))
            proof['input'][backend] = {'before': before_input, 'after': after_input, 'sent': sent}
        proof['frameAfter'] = copy_frame(call('CaptureTestFrame')['path'], 'full-desktop-after')
        proof['nativeAfter'] = native_call('Status')
        callbacks = proof['nativeAfter']['callbacks']
        retired = {epoch: names for epoch, names in callbacks['epochs'].items()
                   if int(epoch) < callbacks['latestEpoch'] and names}
        proof['retiredCallbacks'] = retired
        assert not retired, retired
        try:
            native_call('ResetProbe')
        except RuntimeError as error:
            assert 'attempt limit' in str(error), str(error)
        else:
            raise AssertionError('The bounded laboratory reset limit was not enforced')
        assert native_call('Status') == proof['nativeAfter']
        proof['limitSafelyRejected'] = True
        proof['originalObjectiveAchieved'] = True
    except Exception as error:
        proof['error'] = f'{type(error).__name__}: {error}'
    finally:
        try:
            proof['nativeFinal'] = native_call('Status')
        except Exception as error:
            proof['nativeError'] = str(error)
        diagnostics = (output / 'shell.log').read_bytes()[log_offset:].decode(errors='replace')
        (output / 'full-context.log').write_text(diagnostics)
        problems = [line for line in diagnostics.splitlines() if any(word in line for word in
                    ['CRITICAL', 'JS ERROR', 'runtime startup failed', 'Trying to re-add keybinding',
                     'during garbage collection', 'disposed object'])]
        proof['diagnosticProblems'] = problems
        if problems:
            proof['originalObjectiveAchieved'] = False
        proof['shellProcessSurvived'] = shell.poll() is None
        report['passed'] = proof['originalObjectiveAchieved'] and proof['shellProcessSurvived']
        report['wholeShellReloadDemonstrated'] = report['passed']
        report['completeShellReinitializationDemonstrated'] = report['passed']
        report['originalObjectiveAchieved'] = report['passed']
        if not report['passed']:
            report['error'] = 'Complete context replacement did not pass its end-to-end checks'
