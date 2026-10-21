#!/usr/bin/env python3
"""Headless GNOME integration test. All spawned processes use a private bus."""
import argparse
import ast
import ctypes
from concurrent.futures import ThreadPoolExecutor
import json
import os
import resource
from pathlib import Path
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tgnome import call  # noqa: E402


def enable_private_subreaper():
    # Adopt orphaned descendants of this dedicated test launcher, including
    # D-Bus-activated helpers. This never adopts unrelated host processes.
    libc = ctypes.CDLL(None, use_errno=True)
    libc.prctl.argtypes = [ctypes.c_int] + [ctypes.c_ulong] * 4
    if libc.prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
        raise OSError(ctypes.get_errno(), 'Cannot contain private test descendants')


def private_shell_setup():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    if os.environ.get('TGNOME_DEBUG_SHELL') == '1':
        # Applies only to the isolated child across exec, allowing its sibling
        # debugger to attach under Yama. Never changes a host sysctl/session.
        libc = ctypes.CDLL(None, use_errno=True)
        libc.prctl.argtypes = [ctypes.c_int] + [ctypes.c_ulong] * 4
        if libc.prctl(0x59616D61, ctypes.c_ulong(-1).value, 0, 0, 0) != 0:
            raise OSError(ctypes.get_errno(), 'Cannot allow private debugger')


def reap_private_descendants():
    term_sent, kill_sent, exited = set(), set(), {}
    started = time.monotonic()
    child_file = Path(f'/proc/{os.getpid()}/task/{os.getpid()}/children')
    while True:
        children = [int(pid) for pid in child_file.read_text().split()]
        if not children:
            return {'terminated': sorted(term_sent), 'killed': sorted(kill_sent),
                    'exitCodes': exited}
        elapsed = time.monotonic() - started
        if elapsed > 10:
            raise RuntimeError(f'Private test descendants did not exit: {children}')
        for pid in children:
            try:
                waited, status = os.waitpid(pid, os.WNOHANG)
            except ChildProcessError:
                continue
            if waited:
                exited[pid] = os.waitstatus_to_exitcode(status)
                continue
            # A live direct child cannot have its PID reused before we reap it.
            # Identity is parentage, never a name, display or host bus address.
            chosen = signal.SIGKILL if elapsed >= 5 else signal.SIGTERM
            sent = kill_sent if chosen == signal.SIGKILL else term_sent
            if pid not in sent:
                try:
                    os.kill(pid, chosen)
                    sent.add(pid)
                except ProcessLookupError:
                    pass
        time.sleep(0.05)


def native_call(method, *arguments):
    result = subprocess.run(
        ['gdbus', 'call', '--session', '--dest', os.environ['TGNOME_BUS_OWNER'],
         '--object-path', '/org/gnome/Shell/TgnomeRuntime', '--method',
         f'org.gnome.Shell.TgnomeRuntime.{method}', *arguments],
        check=False, text=True, capture_output=True, timeout=15)
    if result.returncode:
        raise RuntimeError(result.stderr.strip())
    return json.loads(ast.literal_eval(result.stdout.strip())[0])


def wait_for(check, timeout=45):
    end = time.monotonic() + timeout
    last = None
    while time.monotonic() < end:
        try:
            result = check()
            if result:
                return result
        except (RuntimeError, OSError, ValueError) as error:
            last = error
        time.sleep(0.2)
    raise RuntimeError(f'Timed out: {last}')


def records(path):
    # Ignore an in-progress write of the final line.
    return [json.loads(line) for line in path.read_text().splitlines()
            if line.endswith('}')]


def xwayland_identity(shell_pid):
    children = Path(f'/proc/{shell_pid}/task/{shell_pid}/children').read_text().split()
    result = []
    for child in children:
        path = Path('/proc') / child
        try:
            if path.joinpath('comm').read_text().strip() != 'Xwayland':
                continue
            assert os.getpgid(int(child)) == shell_pid
            result.append({'pid': int(child), 'exe': os.readlink(path / 'exe'),
                           'startTime': path.joinpath('stat').read_text().split(') ')[1].split()[19]})
        except FileNotFoundError:
            continue
    assert len(result) == 1, result
    return result


def inner(work, output):
    assert os.environ['XDG_RUNTIME_DIR'] == str(work / 'runtime')
    # Nested Shell also creates agents on the system bus. Keep those on the
    # private bus too; never register test agents with host system services.
    os.environ['DBUS_SYSTEM_BUS_ADDRESS'] = os.environ['DBUS_SESSION_BUS_ADDRESS']
    def terminate(_signum, _frame):
        raise RuntimeError('Test supervisor requested termination')
    signal.signal(signal.SIGTERM, terminate)
    processes = []
    streams = []
    report = {'classification': 'RESEARCH PROTOTYPE', 'passed': False,
              'trueRestartDemonstrated': False, 'wholeShellReloadDemonstrated': False,
              'privateSystemBus': True}
    panel_realms = os.environ.get('TGNOME_ALLOW_UI_REALMS') == '1'
    try:
        subprocess.run(['dbus-update-activation-environment', 'DBUS_SYSTEM_BUS_ADDRESS'],
                       check=True, timeout=15)
        mock_log = open(output / 'logind.log', 'w')
        streams.append(mock_log)
        mock = subprocess.Popen([sys.executable, '-m', 'dbusmock', '--system',
                                 '--template', 'logind'], stdout=mock_log,
                                stderr=subprocess.STDOUT, start_new_session=True)
        processes.append(mock)
        def logind_call(method, *arguments):
            if mock.poll() is not None:
                raise AssertionError('Private logind mock exited; see logind.log')
            result = subprocess.run(['gdbus', 'call', '--system', '--dest', 'org.freedesktop.login1',
                                     '--object-path', '/org/freedesktop/login1', '--method',
                                     method, *arguments], text=True, capture_output=True,
                                    timeout=10)
            if result.returncode:
                raise RuntimeError(result.stderr.strip())
            return result.stdout
        wait_for(lambda: logind_call('org.freedesktop.DBus.Peer.Ping'), timeout=15)
        import pwd
        logind_call('org.freedesktop.DBus.Mock.AddSession', 'tgnome', 'seat0',
                    str(os.getuid()), pwd.getpwuid(os.getuid()).pw_name, 'true')
        logind_call('org.freedesktop.DBus.Mock.AddMethod', 'org.freedesktop.login1.Manager',
                    'GetUser', 'u', 'o',
                    'ret = "/org/freedesktop/login1/user/%s" % args[0]')
        os.environ['XDG_SESSION_ID'] = 'tgnome'
        report['mockLogind'] = True
        subprocess.run(['gsettings', 'set', 'org.gnome.shell', 'enabled-extensions',
                        "['restart-island@tgnome.local']"], check=True)
        # Compare an established desktop with its rebuilt generations. The
        # one-shot welcome dialog otherwise contributes an extra hidden modal
        # actor/monitor constraint only to the first generation's inventory.
        subprocess.run(['gsettings', 'set', 'org.gnome.shell',
                        'welcome-dialog-last-shown-version', '50.5'], check=True)
        report['welcomeTourAlreadyShown'] = True
        if os.environ.get('TGNOME_TRACK_TIME') == '1':
            for key, value in [('history-enabled', 'true'), ('daily-limit-enabled', 'false')]:
                subprocess.run(['gsettings', 'set', 'org.gnome.desktop.screen-time-limits',
                                key, value], check=True)
            report['timeTrackingEnabled'] = True
        log = open(output / 'shell.log', 'w')
        streams.append(log)
        shell = subprocess.Popen([os.environ['TGNOME_SHELL'], '--headless', '--wayland',
                                  '--virtual-monitor', '1280x720',
                                  '--wayland-display', 'tgnome-test'],
                                  stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
                                  preexec_fn=private_shell_setup)
        processes.append(shell)

        def ready():
            if shell.poll() is not None:
                raise AssertionError(f'Isolated Shell exited {shell.returncode}; see shell.log')
            return call('Status')

        before = wait_for(ready)
        assert before['pid'] == shell.pid, (before, shell.pid)
        owner = subprocess.run(
            ['gdbus', 'call', '--session', '--dest', 'org.freedesktop.DBus',
             '--object-path', '/org/freedesktop/DBus', '--method',
             'org.freedesktop.DBus.GetNameOwner', 'org.gnome.Shell'],
            text=True, capture_output=True, check=True, timeout=15)
        os.environ['TGNOME_BUS_OWNER'] = ast.literal_eval(owner.stdout.strip())[0]
        report['shellBefore'] = before
        report['busOwner'] = os.environ['TGNOME_BUS_OWNER']
        if os.environ.get('TGNOME_DEBUG_SHELL') == '1':
            debug_log = open(output / 'debugger.log', 'w')
            streams.append(debug_log)
            debug_commands = ([
                '-ex', 'break g_return_if_fail_warning',
            ] if os.environ.get('TGNOME_DEBUG_GLIB_ASSERTIONS') == '1' else [])
            if os.environ.get('TGNOME_DEBUG_RETIRED_CALLBACKS') == '1':
                debug_commands += ['-ex', 'break GjsCallbackTrampoline::warn_about_illegal_js_callback']
            debugger = subprocess.Popen([
                'gdb', '--nx', '--batch', '-iex', 'set auto-load off',
                '-ex', 'set pagination off', '-ex', 'handle SIGPIPE nostop noprint pass',
                '-p', str(shell.pid), *debug_commands,
                '-ex', 'continue', '-ex', 'thread apply all bt',
                '-ex', 'detach'], stdout=debug_log, stderr=subprocess.STDOUT,
                start_new_session=True)
            processes.append(debugger)
            def debugger_attached():
                status = Path(f'/proc/{shell.pid}/status').read_text()
                return f'TracerPid:\t{debugger.pid}\n' in status
            wait_for(debugger_attached, timeout=10)
            report['privateDebugger'] = debugger.pid
        os.environ['WAYLAND_DISPLAY'] = 'tgnome-test'
        # Only inspect this private Shell's log, never guess a host display.
        import re
        text = (output / 'shell.log').read_text()
        match = re.search(r'Using public X11 display (:[0-9]+)', text)
        backends = ['wayland']
        if match:
            os.environ['DISPLAY'] = match.group(1)
            auth = list((work / 'runtime').glob('.mutter-Xwaylandauth.*'))
            assert len(auth) == 1, auth
            os.environ['XAUTHORITY'] = str(auth[0])
            backends.append('x11')
        else:
            raise RuntimeError('Private XWayland display not found; refusing partial success')
        for backend in backends:
            stream = open(output / f'{backend}.jsonl', 'w')
            err = open(output / f'{backend}.log', 'w')
            streams.extend([stream, err])
            client = subprocess.Popen([os.environ['TGNOME_PROBE']],
                                      env={**os.environ, 'GDK_BACKEND': backend},
                                      stdout=stream, stderr=err, start_new_session=True)
            processes.append(client)
            wait_for(lambda: records(output / f'{backend}.jsonl'), timeout=20)

        initial = {b: records(output / f'{b}.jsonl')[-1] for b in backends}
        # Wait for placement/focus animations before comparing recoverable state.
        time.sleep(1)
        report['desktopBefore'] = call('Status')['desktop']
        report['xwaylandBefore'] = xwayland_identity(shell.pid)
        report['shellExecutable'] = os.readlink(f'/proc/{shell.pid}/exe')
        if os.environ.get('TGNOME_ALLOW_PANEL_RELOAD') == '1':
            call('SetTestOverview', 'true')
            wait_for(lambda: call('Status')['shellState']['overview'])
            try:
                call('ReloadPanel', 'false')
            except RuntimeError as error:
                assert 'Close menus and overview' in str(error), str(error)
            else:
                raise AssertionError('Panel reload should reject the overview')
            call('SetTestOverview', 'false')
            wait_for(lambda: not call('Status')['shellState']['overview'])
            time.sleep(1)
            report['desktopBefore'] = call('Status')['desktop']
            original = call('Status')['panel']
            assert original['supported'], original
            if panel_realms:
                realms = original['realms']['records']
                assert len(realms) == 1 and not realms[0]['disposed'], realms
                assert realms[0]['allocations'] > 0 and realms[0]['preferredWidths'] > 0, realms
                # Load native menu effects before counting registrations. The
                # first menu open lazily registers StScrollViewFade and its base.
                report['panelTypeWarmup'] = call('ExercisePanel')
                date_exercise = call('ExerciseDateMenuRealm')
                assert date_exercise['correctParent'] and date_exercise['mapped'] and date_exercise['clickedToday'], date_exercise
                assert date_exercise['typedDateEvents'] >= 2, date_exercise
                frame_path = Path(date_exercise['frame']).resolve()
                assert frame_path.is_relative_to((work / 'data').resolve())
                shutil.copyfile(frame_path, output / 'date-menu-before.png')
                date_exercise['frame'] = 'date-menu-before.png'
                report['dateMenuExerciseBefore'] = date_exercise
                date_realms = call('Status')['panel']['dateMenuRealms']['records']
                assert len(date_realms) == 1 and not date_realms[0]['retired'], date_realms
                date_classes = {'TodayButton', 'EventsSection', 'WorldClocksSection',
                    'WeatherSection', 'MessagesIndicator', 'FreezableBinLayout',
                    'CalendarColumnLayout', 'DateMenuButton'}
                assert set(date_realms[0]['classes']) == date_classes, date_realms
                assert date_realms[0]['instances'] == 8, date_realms
                assert date_realms[0]['calls'].get('FreezableBinLayout.vfunc_allocate', 0) > 0, date_realms
                assert date_realms[0]['calls'].get('DateMenuButton._sessionUpdated', 0) > 0, date_realms
                assert date_realms[0]['calls'].get('TodayButton.vfunc_clicked', 0) > 0, date_realms
                report['dateMenuRealmBefore'] = date_realms[0]
                report['panelNativeBefore'] = native_call('Status')
            for generation in range(1, 11):
                panel = call('ReloadPanel', 'false')['panel']
                assert panel['lifecycle']['generation'] == generation, panel
                assert panel['lifecycle']['destroyed'] == generation, panel
                assert panel['replaced'] and panel['retainedIndicators'], panel
                assert panel['containerCount'] == panel['focusGroupCount'] == 1, panel
                assert panel['totalFocusGroups'] == original['totalFocusGroups'], panel
                assert panel['menuCount'] == original['menuCount'], panel
                assert call('ExercisePanel')['modalCount'] == 0
                if panel_realms:
                    realms = call('Status')['panel']['realms']['records']
                    assert len(realms) == generation + 1, realms
                    assert sum(not record['disposed'] for record in realms) == 1, realms
                    current = next(record for record in realms if not record['disposed'])
                    assert current['generation'] == generation + 1, realms
                    assert current['allocations'] > 0 and current['preferredWidths'] > 0, realms
            try:
                call('ReloadPanel', 'true')
            except RuntimeError as error:
                assert 'Injected panel adoption failure' in str(error), str(error)
            else:
                raise AssertionError('Panel fault injection did not fail')
            panel = call('Status')['panel']
            assert panel['lifecycle']['generation'] == 10
            assert panel['retainedIndicators'] and panel['containerCount'] == 1
            assert panel['totalFocusGroups'] == original['totalFocusGroups']
            report['panelMenusAfterRollback'] = call('ExercisePanel')
            report['panelReload'] = panel
            if panel_realms:
                gc_started = time.monotonic()
                for gc_cycle in range(30):
                    call('CollectUiGarbage')
                    time.sleep(0.1)
                    realms = call('Status')['panel']['realms']['records']
                    if all(record['globalCollected'] and record['implementationCollected']
                           for record in realms if record['disposed']):
                        break
                realms = call('Status')['panel']['realms']['records']
                report['panelRealmGc'] = {'cycles': gc_cycle + 1,
                                         'seconds': time.monotonic() - gc_started}
                assert len(realms) == 12, realms
                retired = [record for record in realms if record['disposed']]
                assert len(retired) == 11, realms
                if not all(record['globalCollected'] and record['implementationCollected']
                           for record in retired):
                    heap_path = Path(call('DumpUiHeap')['path']).resolve()
                    assert heap_path.is_relative_to((work / 'data').resolve())
                    shutil.copyfile(heap_path, output / 'panel-realms.heap')
                assert all(record['globalCollected'] and record['implementationCollected']
                           for record in retired), realms
                current = next(record for record in realms if not record['disposed'])
                assert not current['globalCollected'] and not current['implementationCollected'], current
                report['panelRealms'] = realms
                native_after = native_call('Status')
                native_before = report['panelNativeBefore']
                added_types = sorted(set(native_after['newObjectTypes']) -
                                     set(native_before['newObjectTypes']))
                assert added_types in ([], ['GVfsMetadataProxy']), added_types
                assert native_after['registeredObjectTypes'] == (
                    native_before['registeredObjectTypes'] + len(added_types)), native_after
                report['panelNativeAfter'] = native_after
                date_realms = call('Status')['panel']['dateMenuRealms']['records']
                assert len(date_realms) == 1 and not date_realms[0]['retired'], date_realms
                assert not date_realms[0]['globalCollected'], date_realms
                report['dateMenuRealmAfterPanelReload'] = date_realms[0]
        else:
            try:
                call('ReloadPanel', 'false')
            except RuntimeError as error:
                assert 'requires the locally patched Shell' in str(error), str(error)
            else:
                raise AssertionError('Stock Shell unexpectedly supports panel replacement')
        for generation in range(1, 21):
            status = call('ReloadUI', 'false')
            assert status['generation'] == generation and status['active'], status
            assert status['pid'] == shell.pid
            assert status['liveOwnedActors'] == 1 and status['panelEntryMatches'], status
            assert not status['busy'], status
        try:
            call('ReloadUI', 'true')
        except RuntimeError as error:
            assert 'Injected construction failure' in str(error), str(error)
        else:
            raise AssertionError('Fault injection unexpectedly succeeded')
        restored = call('Status')
        assert restored['active'] and restored['failures'] == 1
        assert restored['generation'] == 20 and not restored['busy']
        assert restored['liveOwnedActors'] == 1 and restored['panelEntryMatches']
        assert call('ReloadTheme')['themeReloads'] == 1
        call('ReloadUI', 'false')
        report['reloadAfter'] = call('Status')
        # Exercise registration and actor teardown across actual extension
        # disable/enable cycles. This reuses cached JS; it is not a code reload.
        import dbus
        extension_bus = dbus.bus.BusConnection(os.environ['DBUS_SESSION_BUS_ADDRESS'])
        extension_manager = dbus.Interface(extension_bus.get_object(
            os.environ['TGNOME_BUS_OWNER'], '/org/gnome/Shell', introspect=False),
            'org.gnome.Shell.Extensions')
        def extension_state():
            info = extension_manager.GetExtensionInfo('restart-island@tgnome.local', timeout=3)
            return {'state': int(info['state']), 'enabled': bool(info['enabled'])}

        def toggle(method):
            # The extension can export its endpoint while still ACTIVATING.
            # Synchronize on GNOME's completed state, not just object presence.
            enabling = method == 'EnableExtension'
            before_expected = {'state': 2 if enabling else 1, 'enabled': not enabling}
            wait_for(lambda: extension_state() == before_expected, timeout=10)
            result = subprocess.run(['gdbus', 'call', '--session', '--dest', os.environ['TGNOME_BUS_OWNER'],
                            '--object-path', '/org/gnome/Shell', '--method',
                            f'org.gnome.Shell.Extensions.{method}',
                            'restart-island@tgnome.local'],
                           check=True, capture_output=True, text=True, timeout=15)
            assert result.stdout.strip() == '(true,)', result.stdout
            after_expected = {'state': 1 if enabling else 2, 'enabled': enabling}
            wait_for(lambda: extension_state() == after_expected, timeout=10)
            report.setdefault('extensionStateTransitions', []).append({
                'method': method, 'before': before_expected, 'after': after_expected})

        def unregistered():
            try:
                call('Status')
            except RuntimeError as error:
                if 'UnknownMethod' in str(error) or 'UnknownObject' in str(error):
                    return True
                raise
            return False

        for _ in range(3):
            toggle('DisableExtension')
            wait_for(unregistered, timeout=10)
            toggle('EnableExtension')
            status = wait_for(lambda: call('Status'), timeout=10)
            assert status['liveOwnedActors'] == 1 and status['panelEntryMatches']
        report['extensionLifecycleCycles'] = 3
        health = subprocess.run([sys.executable, str(ROOT / 'tgnome.py'), 'self-test'],
                                capture_output=True, text=True, timeout=20)
        assert health.returncode == 0, health.stderr
        for unsupported in ['reload-shell', 'reload-extensions', 'recover-session']:
            result = subprocess.run([sys.executable, str(ROOT / 'tgnome.py'), unsupported],
                                    capture_output=True, text=True)
            assert result.returncode == 2 and 'unsupported' in result.stderr
        time.sleep(1)
        for backend in backends:
            values = records(output / f'{backend}.jsonl')
            first, last = initial[backend], values[-1]
            assert last['tick'] > first['tick'], (first, last)
            assert all(all(v[key] == first[key] for key in
                           ['pid', 'fd', 'inode', 'windowId', 'unsavedTextSha256'])
                       for v in values), values
            report[backend] = {'before': first, 'after': last,
                               'originalConnectionRoundTrips': True}
        assert all(p.poll() is None for p in processes)
        report['shellAfter'] = call('Status')
        assert report['shellAfter']['liveOwnedActors'] == 1
        assert report['shellAfter']['desktop'] == report['desktopBefore']
        report['xwaylandAfter'] = xwayland_identity(shell.pid)
        assert report['xwaylandAfter'] == report['xwaylandBefore']
        report['xwaylandTested'] = 'x11' in backends
        if 'panelReload' in report:
            report['classification'] = 'SHELL RELOAD'
            report['reloadScope'] = 'panel actor/layout/gestures/menu manager; indicators, GJS and Mutter survive'
        report['passed'] = True
        if os.environ.get('TGNOME_ALLOW_RUNTIME_RESET') == '1':
            report['nativeLoop'] = native_call('Status')
            assert report['nativeLoop']['attempts'] == 0
            assert report['shellBefore']['runtimeEpoch']
        if os.environ.get('TGNOME_RUN_INPLACE_PROBE') == '1':
            if os.environ.get('TGNOME_PERSISTENT_CONTEXT') != '1':
                raise RuntimeError('In-place probe requires the stable development variant')
            report['baselinePassed'] = report['passed']
            report['passed'] = False
            report['classification'] = 'RESEARCH PROTOTYPE'
            keyboard_before = call('PrepareTestKeyboard')
            arranged = call('ArrangeProbeWindows')['windows']
            def arranged_windows_ready():
                frames = {window['id']: window['frame']
                          for window in call('Status')['desktop']['windows']}
                return all(frames.get(window['id']) == window['frame'] for window in arranged)
            wait_for(arranged_windows_ready, timeout=10)
            call('SetTestOverview', 'true')
            wait_for(lambda: call('Status')['shellState']['overview'])
            try:
                call('ExerciseNativeOverview')
            except RuntimeError as error:
                assert 'requires an idle desktop' in str(error), str(error)
            else:
                raise AssertionError('Native overview probe must reject an already open overview')
            assert call('Status')['shellState']['overview']
            call('SetTestOverview', 'false')
            wait_for(lambda: not call('Status')['shellState']['overview'])
            time.sleep(0.3)
            def copy_frame(path, name):
                frame = Path(path).resolve()
                assert frame.is_relative_to((work / 'data').resolve())
                header = frame.read_bytes()[:24]
                assert header[:8] == b'\x89PNG\r\n\x1a\n'
                assert struct.unpack('!II', header[16:24]) == (1280, 720)
                shutil.copy2(frame, output / f'{name}.png')
                return f'{name}.png'
            def capture_frame(name):
                return copy_frame(call('CaptureTestFrame')['path'], name)
            overview_before = call('ExerciseNativeOverview')
            overview_before_frame = copy_frame(overview_before['path'], 'overview-before')
            before_frame = capture_frame('desktop-before')
            log_offset = (output / 'shell.log').stat().st_size
            policy_retirement = call('ExercisePolicyRetirement')
            assert policy_retirement == {'policyDisposed': True, 'ownerDestroyed': True}
            call('ExerciseWindowMenu')
            baseline = call('Status')
            if os.environ.get('TGNOME_TRACK_TIME') == '1':
                def tracking_ready():
                    status = call('Status')
                    model = status['timeLimits']
                    return status if model['loginUserReady'] and model['transitions'] else False
                baseline = wait_for(tracking_ready)
                assert baseline['timeLimits']['state'] == 1, baseline['timeLimits']
                assert baseline['timeLimits']['clockSourceActive'], baseline['timeLimits']
            assert baseline['timeLimits']['retained'], baseline['timeLimits']
            assert baseline['timeLimits']['shutdownCalls'] == 0
            native_before = native_call('Status')
            expected_type_count = native_before['registeredObjectTypes']
            probe = {'before': baseline, 'nativeBefore': native_before, 'cycles': []}
            probe['policyRetirement'] = policy_retirement
            probe['frames'] = {'before': before_frame, 'overviewBefore': overview_before_frame}
            probe['overviewInputBefore'] = overview_before
            failure_scenario = os.environ.get('TGNOME_UI_FAILURE_SCENARIO', 'none')
            owned_request = os.environ.get('TGNOME_OWNED_REQUEST') == '1'
            interrupt_requester = os.environ.get('TGNOME_INTERRUPT_REQUESTER') == '1'
            preparation_fault = os.environ.get('TGNOME_PREPARATION_FAULT', 'none')
            cleanup_mode = os.environ.get('TGNOME_CLEANUP_MODE', 'none')
            interrupt_js = os.environ.get('TGNOME_RUN_INTERRUPT_PROBE') == '1'
            backend_finite = interrupt_js and os.environ.get('TGNOME_INTERRUPT_OPERATION', '').startswith('backend-')
            backend_delayed = backend_finite and os.environ['TGNOME_INTERRUPT_OPERATION'] != 'backend-finite'
            probe['ownedRequest'] = owned_request
            probe['failureStage'] = os.environ.get('TGNOME_UI_FAILURE_STAGE', 'post-construction')
            if not interrupt_js and os.environ.get('TGNOME_ALLOW_INTERRUPTION') == '1':
                probe['unarmedWatchdogBefore'] = native_call('InterruptUiStatus')
                assert probe['unarmedWatchdogBefore'] == {
                    'watchdog': {'delivered': 0, 'denied': 0, 'nativeResumptions': 0},
                    'fixtureFlags': 0, 'recoveryFailed': False, 'recoveryReply': None}
            def request_owned():
                result = subprocess.run(
                    [sys.executable, str(ROOT / 'tgnome.py'), 'reload-desktop-ui'],
                    capture_output=True, text=True, check=True, timeout=15)
                accepted = json.loads(result.stdout)
                assert accepted['accepted'] and accepted['classification'] == 'SHELL RELOAD'
                return accepted
            report['inPlaceReload'] = probe
            def recover_owned():
                recovered = subprocess.run(
                    [sys.executable, str(ROOT / 'tgnome.py'), 'recover-desktop-ui'],
                    capture_output=True, text=True, check=True, timeout=45)
                value = json.loads(recovered.stdout)
                assert value['recovered'] and not value['wholeShellRestarted'], value
                return value

            # The native recovery API is distinct from a normal reload and
            # cannot mutate a healthy desktop, even with a current serial.
            try:
                native_call('RecoverUi', str(native_before['uiBuildSerial']))
            except RuntimeError as error:
                assert 'current failed candidate' in str(error), str(error)
            else:
                raise AssertionError('Healthy desktop accepted failed-candidate recovery')
            assert native_call('Status') == native_before
            try:
                native_call('UiStarted', '0')
            except RuntimeError as error:
                assert 'must originate from this Shell connection' in str(error)
            else:
                raise AssertionError('An external client must not forge UI completion')
            assert native_call('Status') == native_before
            for method in ['BeginUiReload', 'StartUiReload', 'CancelUiReload']:
                try:
                    native_call(method)
                except RuntimeError as error:
                    assert 'requires this Shell connection' in str(error), str(error)
                else:
                    raise AssertionError(f'An external client must not coordinate {method}')
            assert native_call('Status') == native_before
            try:
                native_call('ReloadUiProbe')
            except RuntimeError as error:
                assert 'not prepared' in str(error), str(error)
            else:
                raise AssertionError('An unprepared request must not consume a UI transaction')
            assert native_call('Status') == native_before
            cancelled_preparation = preparation_fault in ['before-mutation', 'stalled']
            if cancelled_preparation:
                call('ArmPreparationFault', preparation_fault)
                before_cancel = call('Status')
                started = time.monotonic()
                try:
                    request_owned()
                except subprocess.CalledProcessError as error:
                    message = error.stderr
                    expected = ('deadline exceeded' if preparation_fault == 'stalled' else
                                'failure before mutation')
                    assert expected in message, message
                else:
                    raise AssertionError('A precommit fault must fail without reconstructing UI')
                cancelled = native_call('Status')
                assert cancelled['attempts'] == cancelled['preparationFailures'] == 1
                assert cancelled['preparationTimeouts'] == int(preparation_fault == 'stalled')
                assert cancelled['uiCommits'] == 0 and not cancelled['uiActive']
                assert cancelled['state'] == ('ui-preparation-timeout' if preparation_fault == 'stalled'
                                               else 'ui-preparation-failed')
                probe['cancelledPreparation'] = {'fault': preparation_fault, 'error': message,
                    'elapsedSeconds': time.monotonic() - started, 'native': cancelled}
                if preparation_fault == 'stalled':
                    # Let the original controlled async operation actually
                    # complete after cancellation. Its stale continuation must
                    # never commit or mutate the still-working old UI.
                    wait_for(lambda: call('Status')['latePreparationCompletions'] ==
                             before_cancel['latePreparationCompletions'] + 1, timeout=5)
                    assert native_call('Status') == cancelled
                    probe['cancelledPreparation']['lateCompletionObserved'] = True
                after_cancel = call('Status')
                for key in ['uiGeneration', 'uiBuildSerial', 'desktop', 'timeLimits', 'uiRegistrations',
                            'stageActions', 'retiredUi']:
                    assert after_cancel[key] == before_cancel[key], (key, after_cancel[key])
                assert after_cancel['active'] and after_cancel['liveOwnedActors'] == 1
                probe['cancelledPreparation']['menus'] = call('ExercisePanel')
                probe['cancelledPreparation']['windowMenu'] = call('ExerciseWindowMenu')
            for generation in range(1, 3 if cancelled_preparation else 4):
                if preparation_fault in ['after-bindings', 'after-disable'] and generation == 2:
                    probe['armedPreparationFault'] = call('ArmPreparationFault', preparation_fault)
                if failure_scenario != 'none' and generation == 2:
                    if cleanup_mode != 'none':
                        probe['armedCleanupMode'] = call('ArmCleanupMode', cleanup_mode)
                    probe['armedFailure'] = call('ArmUiFailureAt',
                        os.environ.get('TGNOME_UI_FAILURE_STAGE', 'post-construction'),
                        '2' if failure_scenario == 'twice' else '1')
                request_method = 'ReloadDesktopUi' if owned_request else 'PrepareRuntimeReset'
                parallel_generation = 2 if interrupt_requester else 1
                if backend_finite and generation == 1:
                    assert native_call('InterruptUiProbe') == {'scheduled': True}
                    if backend_delayed:
                        def delayed_watchdog_observed():
                            value = native_call('InterruptUiStatus')
                            return value if value['watchdog']['denied'] or value['watchdog']['delivered'] else False
                        observation = wait_for(delayed_watchdog_observed, timeout=10)
                        probe['delayedBackendObservation'] = {'native': observation}
                        try:
                            probe['delayedBackendObservation']['fixture'] = call('Status')['protectedBackendFixture']
                        except RuntimeError as error:
                            probe['delayedBackendObservation']['fixtureUnavailable'] = str(error)
                        assert observation['watchdog'] == {'delivered': 0, 'denied': 1,
                            'nativeResumptions': 0}, probe['delayedBackendObservation']
                    def protected_scope_finished():
                        value = call('Status')
                        proof = value['protectedBackendFixture']
                        return value if proof and proof['completed'] else False
                    protected_status = wait_for(protected_scope_finished, timeout=10)
                    proof = protected_status['protectedBackendFixture']
                    if backend_delayed:
                        assert proof['enteredJsDepth'] == 0 and proof['enteredNativeDepth'] > 0, proof
                        if os.environ['TGNOME_INTERRUPT_OPERATION'] == 'backend-source':
                            assert proof['invalidCallbackRejected'], proof
                        if os.environ['TGNOME_INTERRUPT_OPERATION'] in ['backend-async', 'backend-chain']:
                            assert proof['asyncCallFinished'], proof
                        if os.environ['TGNOME_INTERRUPT_OPERATION'] == 'backend-chain':
                            assert proof['followupCallFinished'] and proof['followupDone'], proof
                            assert proof['followupNativeDepth'] > 0 and proof['followupJsDepth'] == 0, proof
                    else:
                        assert proof['enteredJsDepth'] == proof['enteredNativeDepth'] == 2, proof
                    assert proof['signalStillConnected'], proof
                    assert protected_status['backendScopeDepth'] == protected_status['nativeBackendScopeDepth'] == 0
                    refused_interrupt = native_call('InterruptUiStatus')
                    assert refused_interrupt == {'watchdog': {'delivered': 0, 'denied': 1,
                        'nativeResumptions': 0}, 'fixtureFlags': 5,
                        'recoveryFailed': False, 'recoveryReply': None}, refused_interrupt
                    before_signals = baseline['uiRegistrations']['signals']
                    after_signals = protected_status['uiRegistrations']['signals']
                    assert after_signals['total'] == before_signals['total'] + 1
                    assert after_signals['permanent'] == before_signals['permanent']
                    probe['protectedBackendScope'] = {'during': proof, 'native': refused_interrupt}
                    result = request_owned()
                elif interrupt_js and generation == 1:
                    assert native_call('InterruptUiProbe') == {'scheduled': True}
                    if os.environ.get('TGNOME_TEST_HANDOFF') == '1':
                        def held_handoff():
                            value = native_call('InterruptHandoffStatus')
                            return value if value['held'] else False
                        held = wait_for(held_handoff, timeout=5)
                        held_ui = call('Status')
                        held_native = native_call('Status')
                        assert held_ui['panel']['transfer']['pending']
                        assert held_native['attempts'] == held_native['uiCommits'] == 0
                        rejected = {}
                        for method, arguments in [('ReloadPanel', ['false']),
                                                  ('ReloadUI', ['false']), ('ReloadTheme', []),
                                                  ('ReloadDesktopUi', []),
                                                  ('PrepareRuntimeReset', [])]:
                            try:
                                call(method, *arguments)
                            except RuntimeError as error:
                                assert 'panel transfer' in str(error).lower(), str(error)
                                rejected[method] = str(error)
                            else:
                                raise AssertionError(f'{method} entered the interrupted panel handoff')
                        after_refusal = call('Status')
                        for key in ['desktop', 'uiGeneration', 'timeLimits', 'uiRegistrations',
                                    'stageActions', 'stageChildren', 'liveOwnedActors', 'preparationFailures']:
                            assert after_refusal[key] == held_ui[key], key
                        for key in held_ui['panel']:
                            if key != 'transfer':
                                assert after_refusal['panel'][key] == held_ui['panel'][key], key
                        assert after_refusal['panel']['transfer']['pending']
                        assert native_call('Status') == held_native
                        assert native_call('InterruptHandoffStatus') == held
                        ticks_before = {b: records(output / f'{b}.jsonl')[-1]['tick'] for b in backends}
                        time.sleep(1)
                        assert all(records(output / f'{b}.jsonl')[-1]['tick'] > ticks_before[b]
                                   for b in backends)
                        expiry = os.environ.get('TGNOME_HANDOFF_EXPIRY') == '1'
                        if expiry:
                            def handoff_expired():
                                value = native_call('InterruptHandoffStatus')
                                return value if value['expired'] else False
                            wait_for(handoff_expired, timeout=10)
                        else:
                            assert native_call('ReleaseInterruptHandoff') == {'released': True}
                        probe['interruptionHandoff'] = {'held': held, 'native': held_native,
                                                       'refused': rejected, 'clientRoundTripsWhileHeld': True,
                                                       'releaseMode': 'deadline' if expiry else 'explicit'}
                    def interruption_recovered():
                        value = native_call('InterruptUiStatus')
                        assert not value['recoveryFailed'], value
                        return value if value['recoveryReply'] else False
                    interruption = wait_for(interruption_recovered, timeout=20)
                    assert interruption['fixtureFlags'] == 1, interruption
                    assert interruption['watchdog'] == {
                        'delivered': 1, 'denied': 0, 'nativeResumptions': 1}, interruption
                    result = interruption['recoveryReply']
                    assert result['accepted'] and result['classification'] == 'SHELL RELOAD'
                    probe['jsInterruption'] = interruption
                    if 'interruptionHandoff' in probe:
                        released = native_call('InterruptHandoffStatus')
                        assert released == {'held': False, 'expired':
                            os.environ.get('TGNOME_HANDOFF_EXPIRY') == '1', 'releases': 1}, released
                        probe['interruptionHandoff']['after'] = released
                elif owned_request and interrupt_requester and generation == 1:
                    call('ArmOwnedDelay', '1000')
                    caller_log = open(output / 'requester.log', 'w')
                    streams.append(caller_log)
                    requester = subprocess.Popen(
                        [sys.executable, str(ROOT / 'tgnome.py'), 'reload-desktop-ui'],
                        stdout=caller_log, stderr=subprocess.STDOUT, start_new_session=True)
                    processes.append(requester)
                    def preparation_owned():
                        native = native_call('Status')
                        return native if native['state'] == 'ui-preparing' else False
                    reserved = wait_for(preparation_owned, timeout=10)
                    assert requester.poll() is None
                    rejected_coordination = {}
                    for method in ['StartUiReload', 'CancelUiReload', 'ReloadUiProbe']:
                        try:
                            native_call(method)
                        except RuntimeError as error:
                            rejected_coordination[method] = str(error)
                        else:
                            raise AssertionError(f'External {method} stole an owned transaction')
                    assert native_call('Status') == reserved
                    assert requester.poll() is None
                    os.killpg(requester.pid, signal.SIGTERM)
                    requester.wait(timeout=5)
                    probe['disconnectedRequester'] = {'pid': requester.pid,
                        'exitCode': requester.returncode, 'nativeWhileAlive': reserved,
                        'externalCoordinationRejected': rejected_coordination}
                    result = {'preparation': {'callerDisconnected': True},
                              'native': native_call('Status')}
                elif os.environ.get('TGNOME_PARALLEL_PREPARE') == '1' and generation == parallel_generation:
                    if owned_request:
                        call('ArmOwnedDelay', '1000')
                    accepted, rejected = [], []
                    with ThreadPoolExecutor(max_workers=2) as executor:
                        futures = [executor.submit(request_owned) if owned_request else
                                   executor.submit(call, request_method) for _ in range(2)]
                        for future in futures:
                            try:
                                accepted.append(future.result())
                            except (RuntimeError, subprocess.CalledProcessError) as error:
                                rejected.append(error.stderr if isinstance(
                                    error, subprocess.CalledProcessError) else str(error))
                    assert len(accepted) == len(rejected) == 1, (accepted, rejected)
                    assert any(word in rejected[0] for word in
                               ['already preparing', 'UnknownObject', 'UnknownMethod'])
                    result = accepted[0]
                    probe['parallelPreparationRejected'] = rejected[0]
                else:
                    result = request_owned() if owned_request else call(request_method)
                if owned_request:
                    preparation, requested = result['preparation'], result['native']
                else:
                    preparation, requested = result, native_call('ReloadUiProbe')
                cycle = {'generation': generation, 'preparation': preparation, 'requested': requested}
                if preparation_fault in ['after-bindings', 'after-disable'] and generation == 2:
                    assert preparation['forwardRecovered'], preparation
                    assert 'Injected preparation failure' in preparation['preparationError']
                probe['cycles'].append(cycle)
                if cleanup_mode != 'none' and generation == 2:
                    def quarantined_transaction():
                        native = native_call('Status')
                        return native if native['state'] == 'ui-cancellation-timeout' else False
                    quarantined = wait_for(quarantined_transaction, timeout=15)
                    assert quarantined['uiQuarantined'] and not quarantined['uiActive']
                    assert quarantined['attempts'] == quarantined['uiBuildSerial'] == 2
                    assert quarantined['uiCommits'] == quarantined['uiTimeouts'] == 1
                    assert quarantined['uiQuarantines'] == 1
                    assert quarantined['uiFailures'] == quarantined['uiRetryAttempts'] == 0
                    status = call('Status')
                    assert status['uiGeneration'] == 1 and status['uiReloadState'] == 'failed'
                    assert status['cleanupWait']['entered'] and not status['cleanupWait']['released']
                    assert status['desktop'] == baseline['desktop']
                    assert status['timeLimits'] == baseline['timeLimits']
                    q = {'mode': cleanup_mode, 'native': quarantined,
                         'invalidAcknowledgements': call('ExerciseQuarantineRefusals')}
                    assert len(q['invalidAcknowledgements']['refused']) == 3
                    assert native_call('Status') == quarantined
                    try:
                        request_owned()
                    except subprocess.CalledProcessError as error:
                        assert 'quarantined' in error.stderr, error.stderr
                        q['cliRefused'] = error.stderr
                    else:
                        raise AssertionError('A quarantined UI must refuse a new CLI transaction')
                    try:
                        native_call('ReloadUiProbe')
                    except RuntimeError as error:
                        assert 'quarantined' in str(error), str(error)
                        q['nativeRefused'] = str(error)
                    else:
                        raise AssertionError('Quarantine must refuse the native debug entry point')
                    assert native_call('Status') == quarantined
                    before_ticks = {b: records(output / f'{b}.jsonl')[-1]['tick'] for b in backends}
                    started = time.monotonic()
                    duration = int(os.environ.get('TGNOME_SOAK_SECONDS', '0')) if cleanup_mode == 'never' else 2
                    for _ in range(max(2, duration)):
                        time.sleep(1)
                        assert shell.poll() is None
                        assert native_call('Status') == quarantined
                    q['stableSeconds'] = time.monotonic() - started
                    assert all(records(output / f'{b}.jsonl')[-1]['tick'] > before_ticks[b]
                               for b in backends)
                    probe['quarantine'] = q
                    if cleanup_mode == 'never':
                        terminal_ui = call('Status')
                        assert terminal_ui['cleanupWait']['entered']
                        assert not terminal_ui['cleanupWait']['released']
                        assert terminal_ui['lateUiOutcomes']
                        assert all(outcome['rejected'] and outcome['before']['uiQuarantined']
                                   for outcome in terminal_ui['lateUiOutcomes'])
                        q['lateUiOutcomes'] = terminal_ui['lateUiOutcomes']
                        probe['frames']['quarantined'] = capture_frame('desktop-quarantined')
                        for backend in backends:
                            values = records(output / f'{backend}.jsonl')
                            assert all(all(value[key] == initial[backend][key] for key in
                                ['pid', 'fd', 'inode', 'windowId', 'unsavedTextSha256']) for value in values)
                            probe[backend] = {'before': initial[backend], 'after': values[-1]}
                        probe['nativeAfter'] = native_call('Status')
                        diagnostics = (output / 'shell.log').read_bytes()[log_offset:].decode(errors='replace')
                        problems = [line for line in diagnostics.splitlines() if any(word in line for word in
                            ['CRITICAL', 'JS ERROR', 'startup failed', 'disposed object',
                             'already exported', 'Unhandled promise rejection'])]
                        probe['diagnosticProblemCount'] = len(problems)
                        assert not problems, '\n'.join(problems[:5])
                        report.update(passed=True, classification='RESEARCH PROTOTYPE',
                            reloadScope='Terminal quarantine; UI is not restored',
                            terminalQuarantineDemonstrated=True, desktopUiReloadDemonstrated=False,
                            wholeShellReloadDemonstrated=False, trueRestartDemonstrated=False,
                            unproven=['UI restoration after non-returning cleanup', 'lock/unlock security',
                                      'physical input and outputs', 'third-party extensions'])
                        return 0
                    def cleanup_confirmed():
                        native = native_call('Status')
                        return native if native['state'] == 'ui-failed' and not native['uiQuarantined'] else False
                    confirmed = wait_for(cleanup_confirmed, timeout=12)
                    assert confirmed['uiFailures'] == 1 and confirmed['uiRetryAttempts'] == 0
                    assert confirmed['attempts'] == 2 and confirmed['uiCommits'] == 1
                    assert confirmed['uiQuarantines'] == 1 and not confirmed['uiActive']
                    q['lateCleanupConfirmed'] = confirmed
                    time.sleep(1)
                    assert native_call('Status') == confirmed
                    cycle['manualRecoveryRequest'] = recover_owned()
                if failure_scenario == 'twice' and generation == 2:
                    def failed_transaction():
                        status = native_call('Status')
                        return status if status['state'] == 'ui-failed' else False
                    terminal = wait_for(failed_transaction, timeout=20)
                    assert terminal['uiFailures'] == 2 and terminal['uiRetryAttempts'] == 1
                    assert terminal['attempts'] == 2 and not terminal['uiActive']
                    before_ticks = {b: records(output / f'{b}.jsonl')[-1]['tick']
                                    for b in backends}
                    time.sleep(1)
                    later = native_call('Status')
                    for key in ['state', 'attempts', 'uiFailures', 'uiRetryAttempts', 'uiActive']:
                        assert later[key] == terminal[key], later
                    assert shell.poll() is None
                    assert all(records(output / f'{b}.jsonl')[-1]['tick'] > before_ticks[b]
                               for b in backends)
                    cycle['terminalBeforeManualRecovery'] = terminal
                    # The automatic retry cap is final until an explicit new
                    # native request. No extension endpoint is needed here.
                    try:
                        native_call('RecoverUi', str(terminal['uiBuildSerial'] - 1))
                    except RuntimeError as error:
                        assert 'current failed candidate' in str(error), str(error)
                    else:
                        raise AssertionError('Stale recovery serial was accepted')
                    assert native_call('Status') == later
                    cycle['manualRecoveryRequest'] = recover_owned()
                def same_context_ready():
                    if shell.poll() is not None:
                        raise AssertionError(f'Isolated Shell exited: {shell.returncode}')
                    status = call('Status')
                    if status['uiGeneration'] != generation or status['shellState']['startingUp']:
                        return False
                    if native_call('Status')['state'] != 'ui-ready':
                        return False
                    return status
                status = wait_for(same_context_ready, timeout=20)
                if interrupt_js and not backend_finite and generation == 1:
                    try:
                        native_call('InterruptUiProbe')
                    except RuntimeError as error:
                        assert 'one-shot limit' in str(error), str(error)
                    else:
                        raise AssertionError('A second interruption fixture must be refused')
                    assert native_call('InterruptUiStatus') == probe['jsInterruption']
                    probe['jsInterruptionRepeatRefused'] = True
                if probe['failureStage'] in ['startup-wait', 'layout-wait'] and generation >= 2:
                    expected_late = 2 if failure_scenario == 'twice' else 1
                    wait_for(lambda: len(call('Status')['lateUiOutcomes']) == expected_late,
                             timeout=5)
                    late_outcomes = call('Status')['lateUiOutcomes']
                    assert all(outcome['rejected'] for outcome in late_outcomes), late_outcomes
                    for outcome in late_outcomes:
                        if cleanup_mode != 'none':
                            assert outcome['before']['uiQuarantined'], outcome
                            assert outcome['before']['uiBuildSerial'] == outcome['serial'], outcome
                        else:
                            assert outcome['before']['uiBuildSerial'] != outcome['serial'], outcome
                            assert 'different UI candidate' in outcome['reason'], outcome
                        for key in ['uiBuildSerial', 'uiCommits', 'uiFailures', 'uiTimeouts',
                                    'uiActive', 'uiQuarantined', 'attempts', 'state']:
                            assert outcome['before'][key] == outcome['after'][key], (key, outcome)
                    if failure_scenario == 'twice':
                        assert any(outcome['before']['uiActive'] and outcome['before']['state'] ==
                                   'same-context-ui-starting' for outcome in late_outcomes)
                    cycle['lateUiOutcomes'] = late_outcomes
                # Menu constraints connect to work-area changes lazily on first
                # open. Compare equally exercised UI generations, and check the
                # replacement menus before taking the registration inventory.
                cycle['menus'] = call('ExercisePanel')
                if panel_realms:
                    exercise = call('ExerciseDateMenuRealm')
                    assert exercise['correctParent'] and exercise['mapped'] and exercise['clickedToday'], exercise
                    assert exercise['typedDateEvents'] >= 2, exercise
                    frame_path = Path(exercise['frame']).resolve()
                    assert frame_path.is_relative_to((work / 'data').resolve())
                    filename = f'date-menu-generation-{generation}.png'
                    shutil.copyfile(frame_path, output / filename)
                    exercise['frame'] = filename
                    cycle['dateMenuExercise'] = exercise
                cycle['windowMenu'] = call('ExerciseWindowMenu')
                call('SetTestOverview', 'true')
                wait_for(lambda: call('Status')['shellState']['overview'])
                call('SetTestOverview', 'false')
                wait_for(lambda: not call('Status')['shellState']['overview'])
                time.sleep(1)
                status = call('Status')
                cycle['after'] = status
                native = native_call('Status')
                cycle['nativeAfter'] = native
                expected_failures = (2 if failure_scenario == 'twice' else 1) if (
                    failure_scenario != 'none' and generation >= 2) else 0
                assert native['uiFailures'] == expected_failures, native
                assert native['uiTimeouts'] == (expected_failures if
                    probe['failureStage'] in ['startup-wait', 'layout-wait'] else 0), native
                assert not native['uiQuarantined'], native
                assert native['uiBuildSerial'] == status['uiBuildSerial'], native
                assert native['uiRetryAttempts'] == int(expected_failures > 0 and cleanup_mode == 'none'), native
                assert native['uiQuarantines'] == int(cleanup_mode != 'none' and generation >= 2), native
                assert native['uiCommits'] == generation, native
                assert not native['uiActive'], native
                assert len(status['uiFailures']) == expected_failures, status['uiFailures']
                assert all(failure['injected'] for failure in status['uiFailures'])
                assert all(failure['stage'] == os.environ.get(
                    'TGNOME_UI_FAILURE_STAGE', 'post-construction')
                    for failure in status['uiFailures'])
                assert status['runtimeEpoch'] == baseline['runtimeEpoch'], status
                assert status['pid'] == shell.pid
                assert status['windowManagerPreserved'], status
                assert status['timeLimits'] == baseline['timeLimits'], {
                    'before': baseline['timeLimits'], 'after': status['timeLimits']}
                expected_preparation_errors = int(cancelled_preparation or
                    (cleanup_mode != 'none' and generation >= 2) or
                    (preparation_fault in ['after-bindings', 'after-disable'] and generation >= 2))
                assert len(status['preparationFailures']) == expected_preparation_errors
                assert native['preparationFailures'] == int(cancelled_preparation)
                assert native['preparationTimeouts'] == int(preparation_fault == 'stalled')
                assert status['stageActions'] == baseline['stageActions'], status['stageActions']
                assert status['stageChildren'] == baseline['stageChildren'], status['stageChildren']
                assert status['windowGroupAttached'], status
                assert status['desktop'] == baseline['desktop']
                assert not status['shellState']['overview']
                assert status['panel']['containerCount'] == status['panel']['focusGroupCount'] == 1
                assert status['panel']['totalFocusGroups'] == baseline['panel']['totalFocusGroups']
                assert status['uiRegistrations'] == baseline['uiRegistrations'], {
                    'before': baseline['uiRegistrations'], 'after': status['uiRegistrations']}
                assert native['contextsFinalized'] == 0
                added_types = sorted(set(native['newObjectTypes']) -
                                     set(native_before['newObjectTypes']))
                if generation == 1 and added_types == ['GVfsMetadataProxy']:
                    # A native GVfs singleton is loaded on first metadata use;
                    # all later generations must preserve this exact count.
                    probe['nativeWarmupTypes'] = added_types
                    assert native['registeredObjectTypes'] == expected_type_count + 1
                    expected_type_count += 1
                assert native['registeredObjectTypes'] == expected_type_count, native
                for _ in range(3):
                    call('CollectUiGarbage')
                    time.sleep(0.1)
                if panel_realms:
                    def panel_realms_collected():
                        records = call('Status')['panel']['realms']['records']
                        if all(record['globalCollected'] and record['implementationCollected']
                               for record in records if record['disposed']):
                            return records
                        call('CollectUiGarbage')
                        return None
                    try:
                        cycle['panelRealms'] = wait_for(panel_realms_collected, timeout=5)
                    except RuntimeError:
                        failure_status = call('Status')['panel']
                        cycle['panelRealmGcFailure'] = failure_status['realms']['records']
                        cycle['dateMenuRealmGcFailure'] = failure_status['dateMenuRealms']['records']
                        heap_path = Path(call('DumpUiHeap')['path']).resolve()
                        assert heap_path.is_relative_to((work / 'data').resolve())
                        shutil.copyfile(heap_path, output / f'panel-generation-{generation}.heap')
                        raise
                    assert sum(not record['disposed'] for record in cycle['panelRealms']) == 1
                    def date_realms_collected():
                        records = call('Status')['panel']['dateMenuRealms']['records']
                        if all(record['globalCollected'] and record['implementationCollected']
                               and record['releasedInstances'] == record['instances']
                               and record['disconnected'] == record['connections']
                               and not record['disconnectFailures']
                               and record['collectedInstances'] == record['classes']
                               for record in records if record['retired']):
                            return records
                        call('CollectUiGarbage')
                        return None
                    try:
                        cycle['dateMenuRealms'] = wait_for(date_realms_collected, timeout=5)
                    except RuntimeError:
                        cycle['dateMenuRealmGcFailure'] = call('Status')['panel']['dateMenuRealms']['records']
                        heap_path = Path(call('DumpUiHeap')['path']).resolve()
                        assert heap_path.is_relative_to((work / 'data').resolve())
                        shutil.copyfile(heap_path, output / f'date-menu-generation-{generation}.heap')
                        raise
                    date_failure_stage = os.environ.get('TGNOME_UI_FAILURE_STAGE', 'post-construction')
                    date_failed_candidates = expected_failures if date_failure_stage in {
                        'after-panel', 'post-construction', 'startup-wait', 'layout-wait'} else 0
                    assert len(cycle['dateMenuRealms']) == generation + 1 + date_failed_candidates
                    assert sum(not record['retired'] for record in cycle['dateMenuRealms']) == 1
                    assert all(not record['failed'] and record['instances'] == 8
                               for record in cycle['dateMenuRealms'])
                retired = call('Status')['retiredUi']
                cycle['retiredUi'] = retired
                if expected_failures:
                    stage = os.environ.get('TGNOME_UI_FAILURE_STAGE', 'post-construction')
                    expected_targets = {
                        'after-layout': {'layoutManager'},
                        'overview-constructor': {'layoutManager', 'overview', 'xdndHandler'},
                        'after-panel': {'panel', 'layoutManager', 'overview', 'inputMethod',
                                        'xdndHandler', 'screenshotUI', 'messageTray', 'quickSettings',
                                        'screencastAreaIndicator'},
                        'post-construction': {'panel', 'layoutManager', 'overview', 'inputMethod',
                            'xdndHandler', 'screenshotUI', 'messageTray', 'quickSettings',
                            'extensionManager', 'keyboard', 'timeLimitsDispatcher', 'screencastAreaIndicator'},
                        'startup-wait': {'panel', 'layoutManager', 'overview', 'inputMethod',
                            'xdndHandler', 'screenshotUI', 'messageTray', 'quickSettings',
                            'extensionManager', 'keyboard', 'timeLimitsDispatcher', 'screencastAreaIndicator'},
                        'layout-wait': {'panel', 'layoutManager', 'overview', 'inputMethod',
                            'xdndHandler', 'screenshotUI', 'messageTray', 'quickSettings',
                            'extensionManager', 'keyboard', 'timeLimitsDispatcher', 'screencastAreaIndicator'},
                    }[stage]
                    failed_generations = {record['generation'] for record in retired
                                          if str(record['generation']).startswith('failed-')}
                    assert len(failed_generations) == expected_failures
                    for failed_generation in failed_generations:
                        targets = {record['name'] for record in retired
                            if record['generation'] == failed_generation and
                            record['name'] not in ['unreferenced-control', 'retained-backend-control']}
                        assert targets == expected_targets, (stage, targets)
                if not all(record['collected'] == record['expectedCollected']
                           for record in retired):
                    heap_path = Path(call('DumpUiHeap')['path']).resolve()
                    assert heap_path.is_relative_to((work / 'data').resolve())
                    shutil.copyfile(heap_path, output / f'ui-generation-{generation}.heap')
                assert all(record['destroyed'] is not False for record in retired), retired
                assert all(record['collected'] == record['expectedCollected']
                           for record in retired), retired
                if (failure_scenario == 'twice' or cleanup_mode != 'none') and generation == 2:
                    break  # Three external requests; two committed generations.
            for _ in range(3):
                toggle('DisableExtension')
                wait_for(unregistered, timeout=10)
                toggle('EnableExtension')
                status = wait_for(lambda: call('Status'), timeout=10)
                assert status['liveOwnedActors'] == 1 and status['panelEntryMatches']
                assert status['uiRegistrations'] == baseline['uiRegistrations']
            probe['postReloadExtensionLifecycleCycles'] = 3
            soak_seconds = int(os.environ.get('TGNOME_SOAK_SECONDS', '0'))
            soak_started = time.monotonic()
            for _ in range(soak_seconds):
                time.sleep(1)
                assert shell.poll() is None
            probe['soak'] = {'requestedSeconds': soak_seconds,
                             'elapsedSeconds': time.monotonic() - soak_started}
            # Retaining existing actors is insufficient: the persistent window
            # manager must also handle new clients after all UI generations.
            original_ids = {w['id'] for w in baseline['desktop']['windows']}
            probe['lateClients'] = {}
            for backend in backends:
                stream = open(output / f'late-{backend}.jsonl', 'w')
                err = open(output / f'late-{backend}.log', 'w')
                streams.extend([stream, err])
                client = subprocess.Popen([os.environ['TGNOME_PROBE']],
                                          env={**os.environ, 'GDK_BACKEND': backend},
                                          stdout=stream, stderr=err,
                                          start_new_session=True)
                processes.append(client)
                wait_for(lambda: len(records(output / f'late-{backend}.jsonl')) >= 2)
                def late_window_mapped():
                    ids = {w['id'] for w in call('Status')['desktop']['windows']}
                    return ids if original_ids < ids and len(ids) == len(original_ids) + 1 else False
                mapped = wait_for(late_window_mapped)
                probe['lateClients'][backend] = {
                    'connection': records(output / f'late-{backend}.jsonl')[-1],
                    'newWindowIds': sorted(mapped - original_ids)}
                os.killpg(client.pid, signal.SIGTERM)
                client.wait(timeout=10)
                wait_for(lambda: {w['id'] for w in call('Status')['desktop']['windows']}
                         == original_ids)
            for backend in backends:
                values = records(output / f'{backend}.jsonl')
                first, last = initial[backend], values[-1]
                assert last['tick'] > report[backend]['after']['tick']
                assert all(all(value[key] == first[key] for key in
                               ['pid', 'fd', 'inode', 'windowId', 'unsavedTextSha256'])
                           for value in values)
                probe[backend] = {'before': first, 'after': last}
            probe['nativeInput'] = {'keyboardBefore': keyboard_before, 'clients': {}}
            keyboard_after = call('PrepareTestKeyboard')
            assert keyboard_after == keyboard_before
            probe['nativeInput']['keyboardAfter'] = keyboard_after
            overview_after = call('ExerciseNativeOverview')
            assert overview_after['nativeAddress'] == keyboard_before['nativeAddress']
            probe['overviewInputAfter'] = overview_after
            probe['frames']['overviewAfter'] = copy_frame(overview_after['path'], 'overview-after')
            for backend in backends:
                before_input = records(output / f'{backend}.jsonl')[-1]
                sent = call('TypeIntoProbe', str(initial[backend]['pid']))
                assert sent['nativeAddress'] == keyboard_before['nativeAddress']
                def typed_record():
                    value = records(output / f'{backend}.jsonl')[-1]
                    return value if value['unsavedTextSha256'] == value['expectedTypedSha256'] else False
                after_input = wait_for(typed_record, timeout=10)
                assert after_input['unsavedTextSha256'] != before_input['unsavedTextSha256']
                assert after_input['tick'] > before_input['tick']
                assert all(all(value[key] == initial[backend][key] for key in
                               ['pid', 'fd', 'inode', 'windowId'])
                           for value in records(output / f'{backend}.jsonl'))
                probe['nativeInput']['clients'][backend] = {
                    'before': before_input, 'after': after_input, 'sent': sent}
            probe['frames']['after'] = capture_frame('desktop-after')
            probe['nativeAfter'] = native_call('Status')
            if interrupt_js and os.environ.get('TGNOME_INTERRUPT_OPERATION', '').startswith('panel-'):
                transfer = call('Status')['panel']['transfer']
                interrupted = [record for record in transfer['retired'] if record.get('interrupted')]
                assert not transfer['pending'] and len(interrupted) == 1, transfer
                record = interrupted[0]
                expected_phase = os.environ['TGNOME_INTERRUPT_OPERATION'].removeprefix('panel-')
                assert record['phase'] == expected_phase, record
                assert record['adoptedBeforeRecovery'] == int(expected_phase == 'adopting'), record
                assert record['entries'] > record['adoptedBeforeRecovery'], record
                assert all(record[key] for key in ['recovered', 'oldPanelRestored', 'destroyed', 'collected']), record
                probe['interruptedPanelTransfer'] = record
            if backend_finite:
                final_backend = call('Status')
                proof = final_backend['protectedBackendFixture']
                assert not proof['signalStillConnected'], proof
                if backend_delayed:
                    assert proof['returnObjectCollected'], proof
                assert final_backend['backendScopeDepth'] == final_backend['nativeBackendScopeDepth'] == 0
                assert native_call('InterruptUiStatus') == probe['protectedBackendScope']['native']
                probe['protectedBackendScope']['after'] = proof
            if 'unarmedWatchdogBefore' in probe:
                probe['unarmedWatchdogAfter'] = native_call('InterruptUiStatus')
                assert probe['unarmedWatchdogAfter'] == probe['unarmedWatchdogBefore']
            before_refusal = call('Status')
            try:
                call('ReloadDesktopUi' if owned_request else 'PrepareRuntimeReset')
            except RuntimeError as error:
                assert 'limit reached before preparation' in str(error), str(error)
            else:
                raise AssertionError('Exhausted preparation must fail before changing UI')
            after_refusal = call('Status')
            assert after_refusal['desktop'] == before_refusal['desktop']
            assert after_refusal['uiRegistrations'] == before_refusal['uiRegistrations']
            assert after_refusal['active'] and after_refusal['liveOwnedActors'] == 1
            probe['preparationLimitSafelyRejected'] = True
            try:
                native_call('ReloadUiProbe')
            except RuntimeError as error:
                assert 'attempt limit reached' in str(error)
                probe['repeatSafelyRejected'] = True
            else:
                raise AssertionError('Fourth in-place probe should be refused')
            assert native_call('Status') == probe['nativeAfter']
            diagnostics = (output / 'shell.log').read_bytes()[log_offset:].decode(errors='replace')
            (output / 'in-place.log').write_text(diagnostics)
            problems = [line for line in diagnostics.splitlines() if any(word in line for word in
                        ['CRITICAL', 'JS ERROR', 'startup failed', 'Trying to re-add keybinding',
                         'disposed object', 'already exported', 'Unhandled promise rejection'])]
            probe['diagnosticProblemCount'] = len(problems)
            if interrupt_js:
                expected = [line for line in problems if
                            'TGNOME explicit interruption at native boundary' in line]
                assert len(expected) == (0 if backend_finite else 1), problems
                problems = [line for line in problems if line not in expected]
                probe['expectedInterruptionDiagnostics'] = expected
                probe['diagnosticProblemCount'] = len(problems)
            assert not problems, '\n'.join(problems[:5])
            report['passed'] = True
            report['classification'] = 'SHELL RELOAD'
            report['reloadScope'] = 'UI instances rebuilt in the same GJS context; compositor retained'
            report['desktopUiReloadDemonstrated'] = True
            report['virtualKeyboardInputDemonstrated'] = True
            report['controlledBlockedJsRecovered'] = interrupt_js and not backend_finite
            report['protectedBackendInterruptionRefused'] = backend_finite
            report['controlledInterruptedPanelTransferRecovered'] = (
                interrupt_js and os.environ.get('TGNOME_INTERRUPT_OPERATION', '').startswith('panel-'))
            report['controlledUiFailureRecovered'] = (
                failure_scenario != 'none')
            report['partialUiConstructionRecoveryDemonstrated'] = (
                failure_scenario != 'none' and probe['failureStage'] != 'post-construction')
            report['preparationFailureHandlingDemonstrated'] = preparation_fault != 'none'
            report['terminalFailureThenManualRecoveryDemonstrated'] = (
                failure_scenario == 'twice' or cleanup_mode == 'delayed')
            report['quarantineThenExplicitRecoveryDemonstrated'] = cleanup_mode == 'delayed'
            # Authentication, physical input and failed-rebuild rollback are not
            # exercised by this headless fixture. Do not imply full coverage.
            report['wholeShellReloadDemonstrated'] = False
            report['unproven'] = ['lock/unlock security', 'physical input and outputs',
                                  'failed full-UI rebuild rollback', 'third-party extensions']
        if (os.environ.get('TGNOME_RUN_RESET_PROBE') == '1' and
                os.environ.get('TGNOME_REBIND_TYPES') == '1'):
            from full_context import verify
            verify(call=call, native_call=native_call, wait_for=wait_for, shell=shell,
                   output=output, work=work, report=report, backends=backends,
                   initial=initial, processes=processes, streams=streams, records=records)
        elif os.environ.get('TGNOME_RUN_RESET_PROBE') == '1':
            if os.environ.get('TGNOME_ALLOW_RUNTIME_RESET') != '1':
                raise RuntimeError('Reset probe requires the explicit runtime development shell')
            report['baselinePassed'] = report['passed']
            report['classification'] = 'RESEARCH PROTOTYPE'
            report['passed'] = False
            before_reset = call('Status')
            preparation = call('PrepareRuntimeReset')
            log_offset = (output / 'shell.log').stat().st_size
            probe = {'requested': native_call('ResetProbe'),
                     'preparation': preparation,
                     'beforeEpoch': before_reset['runtimeEpoch'],
                     'requiredBehaviorDemonstrated': False}
            report['runtimeReset'] = probe
            try:
                def new_context_ready():
                    if shell.poll() is not None:
                        raise AssertionError(f'Isolated Shell exited during reset: {shell.returncode}')
                    status = call('Status')
                    if (status['runtimeEpoch'] == before_reset['runtimeEpoch']
                            or status['shellState']['startingUp']):
                        return False
                    return status
                after_reset = wait_for(new_context_ready, timeout=20)
                probe['afterStatus'] = after_reset
                probe['nativeAfterBootstrap'] = native_call('Status')
                assert after_reset['pid'] == shell.pid
                assert after_reset['panel']['containerCount'] == 1
                assert after_reset['desktop'] == before_reset['desktop']
                assert not after_reset['shellState']['overview']
                probe['menusAfterReset'] = call('ExercisePanel')
                native = native_call('Status')
                assert native['contextsFinalized'] == 1, native
                probe['registeredTypesBefore'] = report['nativeLoop']['registeredProbeTypes']
                probe['registeredTypesAfter'] = native['registeredProbeTypes']
                soak_seconds = int(os.environ.get('TGNOME_SOAK_SECONDS', '0'))
                for _ in range(soak_seconds):
                    time.sleep(1)
                    assert shell.poll() is None, 'Compositor exited during the observation period'
                probe['observationSeconds'] = soak_seconds
                time.sleep(1)
                for backend in backends:
                    first = initial[backend]
                    last = records(output / f'{backend}.jsonl')[-1]
                    assert last['tick'] > report[backend]['after']['tick']
                    assert all(last[key] == first[key] for key in
                               ['pid', 'fd', 'inode', 'windowId', 'unsavedTextSha256'])
                probe['requiredBehaviorDemonstrated'] = True
                probe['testedUiChecksPassed'] = True
                if native['registeredProbeTypes'] > report['nativeLoop']['registeredProbeTypes']:
                    probe['requiredBehaviorDemonstrated'] = False
                    probe['error'] = 'Generation-specific GTypes remain registered; lifetime is not bounded across reloads'
            except (RuntimeError, AssertionError, subprocess.TimeoutExpired) as error:
                probe['error'] = f'{type(error).__name__}: {error}'
            # Even a failed JS bootstrap leaves a native diagnostic endpoint
            # when the compositor is still alive. Record it independently.
            try:
                probe['nativeAfter'] = native_call('Status')
                try:
                    native_call('ResetProbe')
                except RuntimeError as error:
                    probe['repeatSafelyRejected'] = 'Only one laboratory reset' in str(error)
                else:
                    probe['repeatSafelyRejected'] = False
                probe['nativeAfterRejectedRepeat'] = native_call('Status')
                assert probe['nativeAfterRejectedRepeat'] == probe['nativeAfter']
            except (RuntimeError, subprocess.TimeoutExpired) as error:
                probe['nativeError'] = str(error)
            probe['shellProcessSurvived'] = shell.poll() is None
            probe['shellExitCode'] = shell.poll()
            probe['clientsAfterReset'] = {
                backend: records(output / f'{backend}.jsonl')[-1] for backend in backends}
            diagnostics = (output / 'shell.log').read_bytes()[log_offset:].decode(errors='replace')
            (output / 'reset.log').write_text(diagnostics)
            problem_lines = [line for line in diagnostics.splitlines() if any(word in line for word in
                             ['CRITICAL', 'JS ERROR', 'runtime startup failed', 'Trying to re-add keybinding',
                              'during garbage collection', 'disposed object'])]
            probe['diagnosticProblemCount'] = len(problem_lines)
            if problem_lines:
                probe['requiredBehaviorDemonstrated'] = False
                probe['testedUiChecksPassed'] = False
            report['passed'] = (probe['requiredBehaviorDemonstrated']
                                and probe.get('repeatSafelyRejected', False))
            report['wholeShellReloadDemonstrated'] = report['passed']
            if not report['passed']:
                report['error'] = 'Native GJS reset probe did not demonstrate a complete safe Shell reload'
    except Exception as error:
        report['error'] = f'{type(error).__name__}: {error}'
        report['traceback'] = traceback.format_exc()
        if report.get('busOwner'):
            diagnostics = {}
            for name, command in [
                ('extension', ['gdbus', 'call', '--session', '--dest', report['busOwner'],
                    '--object-path', '/org/gnome/Shell', '--method',
                    'org.gnome.Shell.Extensions.GetExtensionInfo', 'restart-island@tgnome.local']),
                ('enabled', ['gsettings', 'get', 'org.gnome.shell', 'enabled-extensions'])]:
                try:
                    result = subprocess.run(command, capture_output=True, text=True, timeout=3)
                    diagnostics[name] = {'exitCode': result.returncode, 'stdout': result.stdout,
                                         'stderr': result.stderr}
                except Exception as diagnostic_error:
                    diagnostics[name] = str(diagnostic_error)
            report['failureDiagnostics'] = diagnostics
    finally:
        # Only private subprocess groups created above; never discover/kill a
        # process by name, host bus identity, physical display or system service.
        for process in reversed(processes):
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
        for process in reversed(processes):
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
        for stream in streams:
            stream.close()
        (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2))
    return 0 if report['passed'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inside', type=Path)
    parser.add_argument('--reset-runtime', action='store_true',
                        help='One potentially destructive GJS reset in the private headless Shell')
    parser.add_argument('--debug-shell', action='store_true',
                        help='Attach a private debugger to capture an isolated Shell crash')
    parser.add_argument('--debug-glib-assertions', action='store_true',
                        help='Stop the private debugger at the first GLib assertion')
    parser.add_argument('--debug-retired-callbacks', action='store_true',
                        help='Stop the private debugger at an invalid GJS callback')
    parser.add_argument('--reload-ui-in-place', action='store_true',
                        help='Rebuild UI three times in the stable-context private Shell')
    parser.add_argument('--unique-gtypes', action='store_true',
                        help='Research-only unique type names; retained registrations are a failure')
    parser.add_argument('--ui-failure', choices=['none', 'once', 'twice'], default='none',
                        help='Inject construction faults; twice also tests explicit recovery after the retry cap')
    parser.add_argument('--ui-failure-stage',
                        choices=['after-layout', 'overview-constructor', 'after-panel',
                                 'post-construction', 'startup-wait', 'layout-wait'],
                        default='post-construction', help='UI construction checkpoint to interrupt')
    parser.add_argument('--parallel-prepare', action='store_true',
                        help='Race two preparation calls; exactly one must be accepted')
    parser.add_argument('--owned-request', action='store_true',
                        help='Use the one-call Shell-owned UI reconstruction coordinator')
    parser.add_argument('--interrupt-requester', action='store_true',
                        help='Kill the CLI requester during an owned preparation')
    parser.add_argument('--interrupt-js', action='store_true',
                        help='Interrupt one blocked outer JS callback in the separate headless watchdog build')
    parser.add_argument('--interrupt-operation', choices=['callback', 'panel-detached', 'panel-adopting',
                        'backend-finite', 'backend-delayed', 'backend-source', 'backend-signal',
                        'backend-cancellable', 'backend-async', 'backend-chain'],
                        default='callback', help='Interrupt a callback or an actual incomplete panel transfer')
    parser.add_argument('--interrupt-handoff', action='store_true',
                        help='Hold the interrupted panel transaction and test competing reload requests')
    parser.add_argument('--handoff-expiry', action='store_true',
                        help='Let the private handoff deadline release recovery without an explicit acknowledgement')
    parser.add_argument('--track-time', action='store_true',
                        help='Enable private usage history and require its backend model to survive')
    parser.add_argument('--cleanup-mode', choices=['none', 'delayed', 'never'], default='none',
                        help='Hold failed-candidate cleanup past native quarantine, optionally forever')
    parser.add_argument('--preparation-fault',
                        choices=['none', 'before-mutation', 'after-bindings', 'after-disable', 'stalled'],
                        default='none', help='Inject a single preparation error or a non-mutating async stall')
    parser.add_argument('--soak-seconds', type=int, default=0,
                        help='Observe delayed callbacks after reset (0..70 seconds)')
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts' / 'latest')
    args = parser.parse_args()
    if not 0 <= args.soak_seconds <= 70:
        parser.error('--soak-seconds must be between 0 and 70')
    if args.debug_glib_assertions and not args.debug_shell:
        parser.error('--debug-glib-assertions requires --debug-shell')
    if args.debug_retired_callbacks and not args.debug_shell:
        parser.error('--debug-retired-callbacks requires --debug-shell')
    if args.ui_failure != 'none' and not args.reload_ui_in_place:
        parser.error('--ui-failure requires --reload-ui-in-place')
    if args.ui_failure_stage != 'post-construction' and args.ui_failure == 'none':
        parser.error('--ui-failure-stage requires --ui-failure once or twice')
    if args.parallel_prepare and not args.reload_ui_in_place:
        parser.error('--parallel-prepare requires --reload-ui-in-place')
    if args.owned_request and not args.reload_ui_in_place:
        parser.error('--owned-request requires --reload-ui-in-place')
    if args.interrupt_requester and not args.owned_request:
        parser.error('--interrupt-requester requires --owned-request')
    if args.interrupt_js and (not args.owned_request or args.interrupt_requester or
            args.parallel_prepare or args.ui_failure != 'none' or args.preparation_fault != 'none'):
        parser.error('--interrupt-js requires --owned-request and no other fault or concurrency scenario')
    if args.interrupt_operation != 'callback' and not args.interrupt_js:
        parser.error('--interrupt-operation requires --interrupt-js')
    if args.interrupt_handoff and not args.interrupt_operation.startswith('panel-'):
        parser.error('--interrupt-handoff requires a panel interruption operation')
    if args.handoff_expiry and not args.interrupt_handoff:
        parser.error('--handoff-expiry requires --interrupt-handoff')
    if args.track_time and not args.reload_ui_in_place:
        parser.error('--track-time requires --reload-ui-in-place')
    if args.cleanup_mode != 'none' and (not args.owned_request or args.ui_failure != 'once' or
                                        args.ui_failure_stage != 'startup-wait'):
        parser.error('--cleanup-mode requires --owned-request --ui-failure once --ui-failure-stage startup-wait')
    if args.preparation_fault != 'none' and (not args.owned_request or args.ui_failure != 'none'):
        parser.error('--preparation-fault requires --owned-request and --ui-failure none')
    output = args.output.resolve()
    if args.inside:
        return inner(args.inside, output)
    output.mkdir(parents=True, exist_ok=True)
    for name in ['TGNOME_SHELL', 'TGNOME_PROBE', 'TGNOME_EXTENSION']:
        if name not in os.environ:
            parser.error('Run with nix develop -c python3 tests/isolated.py')
    enable_private_subreaper()
    with tempfile.TemporaryDirectory(prefix='tgnome-') as tmp:
        work = Path(tmp)
        for name in ['runtime', 'config', 'data', 'cache', 'state']:
            (work / name).mkdir(mode=0o700)
        ext = work / 'data/gnome-shell/extensions/restart-island@tgnome.local'
        ext.parent.mkdir(parents=True)
        shutil.copytree(os.environ['TGNOME_EXTENSION'], ext)
        env = {k: v for k, v in os.environ.items() if k not in
               ['DBUS_SESSION_BUS_ADDRESS', 'DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY', 'TGNOME_BUS_OWNER',
                'SESSION_MANAGER', 'GNOME_DESKTOP_SESSION_ID', 'IBUS_ADDRESS', 'AT_SPI_BUS_ADDRESS']}
        env.update({f'XDG_{name.upper()}_HOME': str(work / name)
                    for name in ['config', 'data', 'cache', 'state']})
        env.update(XDG_RUNTIME_DIR=str(work / 'runtime'),
                   XDG_DATA_DIRS=env.get('XDG_DATA_DIRS', '/run/current-system/sw/share'),
                   GSETTINGS_BACKEND='keyfile', LIBGL_ALWAYS_SOFTWARE='1',
                   # This private bus has no AT-SPI service or user-systemd
                   # activation. Keep GTK helpers from targeting that absent
                   # service; accessibility needs its own complete fixture.
                   NO_AT_BRIDGE='1', GTK_A11Y='none',
                   TGNOME_TEST_FAILURES='1', XDG_SESSION_TYPE='wayland',
                   XDG_CURRENT_DESKTOP='GNOME')
        if args.reset_runtime:
            env['TGNOME_RUN_RESET_PROBE'] = '1'
        env['TGNOME_DEBUG_SHELL'] = '1' if args.debug_shell else '0'
        env['TGNOME_DEBUG_GLIB_ASSERTIONS'] = '1' if args.debug_glib_assertions else '0'
        env['TGNOME_DEBUG_RETIRED_CALLBACKS'] = '1' if args.debug_retired_callbacks else '0'
        if args.reload_ui_in_place:
            env['TGNOME_RUN_INPLACE_PROBE'] = '1'
        if args.unique_gtypes:
            env['TGNOME_UNIQUE_GTYPE_PROBE'] = '1'
        env['TGNOME_SOAK_SECONDS'] = str(args.soak_seconds)
        env['TGNOME_UI_FAILURE_SCENARIO'] = args.ui_failure
        env['TGNOME_UI_FAILURE_STAGE'] = args.ui_failure_stage
        env['TGNOME_PARALLEL_PREPARE'] = '1' if args.parallel_prepare else '0'
        env['TGNOME_OWNED_REQUEST'] = '1' if args.owned_request else '0'
        env['TGNOME_INTERRUPT_REQUESTER'] = '1' if args.interrupt_requester else '0'
        env['TGNOME_RUN_INTERRUPT_PROBE'] = '1' if args.interrupt_js else '0'
        env['TGNOME_INTERRUPT_OPERATION'] = args.interrupt_operation
        env['TGNOME_TEST_HANDOFF'] = '1' if args.interrupt_handoff else '0'
        env['TGNOME_HANDOFF_EXPIRY'] = '1' if args.handoff_expiry else '0'
        env['TGNOME_TRACK_TIME'] = '1' if args.track_time else '0'
        env['TGNOME_CLEANUP_MODE'] = args.cleanup_mode
        env['TGNOME_PREPARATION_FAULT'] = args.preparation_fault
        process = subprocess.Popen(['dbus-run-session', '--', sys.executable, __file__,
                                    '--inside', str(work), '--output', str(output)],
                                   env=env, start_new_session=True)
        try:
            worker_exit = process.wait(timeout=150)
        except (subprocess.TimeoutExpired, KeyboardInterrupt):
            # Give the inner supervisor time to clean its private compositor
            # and client groups before terminating the private bus wrapper.
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
            worker_exit = 1
        finally:
            descendants = reap_private_descendants()
    supervisor = {'workerExitCode': worker_exit, 'descendants': descendants,
                  'privateProfileRemoved': not work.exists()}
    (output / 'supervisor.json').write_text(json.dumps(supervisor, indent=2) + '\n')
    result_path = output / 'result.json'
    if result_path.exists():
        result = json.loads(result_path.read_text())
        result['supervisor'] = supervisor
        result['passed'] = result['passed'] and worker_exit == 0 and not work.exists()
        result_path.write_text(json.dumps(result, indent=2) + '\n')
    return worker_exit


if __name__ == '__main__':
    sys.exit(main())
