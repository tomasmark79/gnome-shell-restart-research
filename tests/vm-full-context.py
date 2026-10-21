"""Complete-context replacement with real guest GDM, PAM and logind."""
import ast
import json
import shlex
import time


def alice(command):
    return ('runuser -u alice -- env XDG_RUNTIME_DIR=/run/user/1000 '
            'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus ' + command)


def evaluate(js):
    raw = machine.succeed(alice('gdbus call --session --dest org.gnome.Shell '
        '--object-path /org/gnome/Shell --method org.gnome.Shell.Eval ' + shlex.quote(js))).strip()
    ok, quoted = raw[1:-1].split(',', 1)
    assert ok == 'true', raw
    return json.loads(ast.literal_eval(quoted.strip()))


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
    raise AssertionError(f'Shell condition timed out: {js}: {last}')


def native():
    raw = machine.succeed(alice('gdbus call --session --dest org.gnome.Shell '
        '--object-path /org/gnome/Shell/TgnomeRuntime '
        '--method org.gnome.Shell.TgnomeRuntime.Status'))
    return json.loads(ast.literal_eval(raw.strip())[0])


def client_record(backend):
    return json.loads(machine.succeed(f'tail -n 1 /home/alice/{backend}.jsonl'))


def clients_unchanged():
    result = {b: client_record(b) for b in initial}
    for backend, old in initial.items():
        new = result[backend]
        assert all(new[k] == old[k] for k in
                   ('pid', 'backend', 'fd', 'inode', 'windowId', 'unsavedTextSha256')), (old, new)
        assert new['tick'] > old['tick']
    return result


STATE = '''({pid:new imports.gi.Gio.Credentials().get_unix_pid(),
    epoch:global._tgnomeRuntimeEpoch,locked:Main.screenShield.locked,
    active:Main.screenShield.active,mode:Main.sessionMode.currentMode,
    session:Main.screenShield._loginSession?.Id ?? null,
    starting:Main.layoutManager._startingUp})'''

start_all()
report: dict[str, object] = {'passed': False, 'originalObjectiveAchieved': False, 'cycles': [],
          'classification': 'COMPLETE SHELL CONTEXT REPLACEMENT'}
try:
    machine.wait_for_unit('display-manager.service', timeout=180)
    machine.wait_for_file('/run/user/1000/wayland-0', timeout=180)
    machine.wait_for_unit('default.target', 'alice', timeout=180)
    before = wait_value(STATE, lambda s: not s['starting'] and s['session'])
    assert not before['locked'] and before['mode'] == 'user'
    session = shlex.quote(before['session'])
    assert machine.succeed(f'loginctl show-session {session} -p Type --value').strip() == 'wayland'
    report['before'] = before
    assert native()['securityVm'] is True
    machine.succeed(alice('gnome-extensions enable restart-island@tgnome.local'))
    wait_value("Main.extensionManager.lookup('restart-island@tgnome.local')?.state === 1", bool)
    machine.send_key('esc')
    wait_value('Main.overview.visible', lambda visible: not visible)
    machine.send_key('meta_l')
    wait_value('Main.overview.visible && !Main.overview.animationInProgress', bool)
    machine.send_key('esc')
    wait_value('Main.overview.visible', lambda visible: not visible)
    for backend in ('wayland', 'x11'):
        machine.succeed(alice(f'systemd-run --user --unit=tgnome-probe-{backend} '
            f'--property=StandardOutput=append:/home/alice/{backend}.jsonl '
            f'--property=StandardError=append:/home/alice/{backend}.log '
            f'--setenv=GDK_BACKEND={backend} --setenv=NO_AT_BRIDGE=1 '
            '--setenv=GTK_A11Y=none tgnome-client-probe'))
        machine.wait_until_succeeds(f'test -s /home/alice/{backend}.jsonl')
    initial = {b: client_record(b) for b in ('wayland', 'x11')}
    report['clientsBefore'] = initial
    owner = evaluate('imports.gi.Gio.DBus.session.get_unique_name()')
    cursor = machine.succeed('journalctl -n 0 --show-cursor').strip().split('-- cursor: ')[-1]
    epochs = {before['epoch']}
    for number in range(1, 4):
        with subtest(f'Complete context replacement {number} with native backend'):
            raw = machine.succeed(alice('env TGNOME_REBIND_TYPES=1 '
                'TGNOME_ALLOW_RUNTIME_RESET=1 TGNOME_BUS_OWNER=' + shlex.quote(owner) +
                ' tgnome restart-shell-context'))
            command = json.loads(raw)
            state = wait_value(STATE, lambda s: not s['starting'] and s['session'])
            assert state['pid'] == before['pid'] and state['session'] == before['session']
            assert state['epoch'] not in epochs and not state['locked']
            epochs.add(state['epoch'])
            current = native()
            assert current['contextsFinalized'] == number
            machine.send_key('meta_l')
            wait_value('Main.overview.visible && !Main.overview.animationInProgress', bool)
            machine.screenshot(f'overview-after-context-{number}')
            machine.send_key('esc')
            wait_value('Main.overview.visible', lambda visible: not visible)
            report['cycles'].append({'command': command, 'state': state,
                                     'native': current, 'clients': clients_unchanged()})
    with subtest('Real logind lock and PAM authentication after complete replacement'):
        machine.succeed(f'loginctl lock-session {session}')
        locked = wait_value(STATE, lambda s: s['locked'] and s['active'])
        assert locked['pid'] == before['pid']
        machine.wait_until_succeeds(f'test $(loginctl show-session {session} -p LockedHint --value) = yes')
        report['clientsWhileLocked'] = clients_unchanged()
        if not evaluate('!!Main.screenShield._dialog?._authPrompt'):
            machine.send_key('ret')
        wait_value('!!Main.screenShield._dialog?._authPrompt?._entry.reactive', bool)
        wrong_cursor = machine.succeed('journalctl -n 0 --show-cursor').strip().split('-- cursor: ')[-1]
        machine.send_key('ctrl-a')
        machine.send_chars('incorrect-vm-password')
        machine.send_key('ret')
        machine.wait_until_succeeds('journalctl -b --after-cursor=' + shlex.quote(wrong_cursor) +
            " --no-pager | grep -F 'pam_unix(gdm-password:auth): authentication failure'", timeout=30)
        wait_value('!!Main.screenShield._dialog?._authPrompt?._entry.reactive', bool)
        assert evaluate(STATE)['locked']
        report['wrongPasswordRejected'] = True
        machine.send_key('ctrl-a')
        machine.send_chars('tgnome-vm-password')
        machine.send_key('ret')
        after = wait_value(STATE, lambda s: not s['locked'] and not s['active'] and s['mode'] == 'user')
        assert after['pid'] == before['pid'] and after['session'] == before['session']
        machine.wait_until_succeeds(f'test $(loginctl show-session {session} -p LockedHint --value) = no')
        report['afterUnlock'] = after
        report['clientsAfterUnlock'] = clients_unchanged()
        machine.screenshot('desktop-after-context-replacement-and-unlock')
    time.sleep(65)
    report['clientsAfterObservation'] = clients_unchanged()
    final = native()
    report['nativeFinal'] = final
    callbacks = final['callbacks']
    retired = {e: names for e, names in callbacks['epochs'].items()
               if int(e) < callbacks['latestEpoch'] and names}
    assert not retired, retired
    journal = machine.succeed(f"journalctl -b _PID={before['pid']} --after-cursor=" +
                              shlex.quote(cursor) + ' --no-pager -o cat')
    problems = [line for line in journal.splitlines() if any(text in line for text in
        ('JS ERROR', 'already disposed', 'Exception in callback', 'CRITICAL', 'runtime startup failed'))]
    report['diagnosticProblems'] = problems
    assert not problems, problems
    report['passed'] = report['originalObjectiveAchieved'] = True
finally:
    print('TGNOME_FULL_CONTEXT_RESULT=' + json.dumps(report))
    machine.succeed('mkdir -p /tmp/tgnome-evidence')
    payload = shlex.quote(json.dumps(report, indent=2))
    machine.succeed(f"printf '%s\\n' {payload} > /tmp/tgnome-evidence/result.json")
    machine.succeed('journalctl -b --no-pager > /tmp/tgnome-evidence/journal.log')
    machine.succeed('cp /home/alice/*.jsonl /home/alice/*.log /tmp/tgnome-evidence/ 2>/dev/null || true')
    machine.copy_from_machine('/tmp/tgnome-evidence', 'evidence')
