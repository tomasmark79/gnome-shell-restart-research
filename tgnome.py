#!/usr/bin/env python3
"""Explicitly scoped GNOME recovery commands for isolated patched builds."""
import argparse
import ast
import json
import os
import subprocess
import sys
import time

INTERFACE = 'org.gnome.Shell.Extensions.Tgnome'
PATH = '/org/gnome/Shell/Extensions/Tgnome'


def call(method, *args, native=False):
    if not os.environ.get('DBUS_SESSION_BUS_ADDRESS'):
        raise RuntimeError('No explicit session bus address; refusing implicit host discovery')
    destination = os.environ.get('TGNOME_BUS_OWNER', 'org.gnome.Shell')
    if destination != 'org.gnome.Shell' and not destination.startswith(':'):
        raise RuntimeError('Pinned bus owner must be a unique D-Bus name')
    if native and not destination.startswith(':'):
        raise RuntimeError('Native recovery requires TGNOME_BUS_OWNER pinned to a unique D-Bus name')
    path = '/org/gnome/Shell/TgnomeRuntime' if native else PATH
    interface = 'org.gnome.Shell.TgnomeRuntime' if native else INTERFACE
    result = subprocess.run(
        ['gdbus', 'call', '--session', '--dest', destination,
         '--object-path', path, '--method', f'{interface}.{method}', *args],
        text=True, capture_output=True, timeout=15, check=False)
    if result.returncode:
        raise RuntimeError(result.stderr.strip())
    return json.loads(ast.literal_eval(result.stdout.strip())[0])


def recover_desktop_ui():
    """Recover a cleaned failed candidate without its extension endpoint."""
    before = call('Status', native=True)
    if before['state'] != 'ui-failed' or before['uiActive'] or before['uiQuarantined']:
        raise RuntimeError('Recovery requires a failed UI with confirmed cleanup')
    call('RecoverUi', str(before['uiBuildSerial']), native=True)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        native = call('Status', native=True)
        if native['uiBuildSerial'] > before['uiBuildSerial']:
            if (native['state'] == 'ui-ready' and native['uiCommits'] == before['uiCommits'] + 1
                    and native['pid'] == before['pid']):
                if native['publishedUiGeneration'] > before['publishedUiGeneration']:
                    return {'classification': 'SHELL RELOAD', 'recovered': True,
                            'wholeShellRestarted': False, 'pid': native['pid'],
                            'uiGeneration': native['publishedUiGeneration'], 'native': native}
            if not native['uiActive'] and native['state'] != 'ui-ready':
                raise RuntimeError(f"Recovery ended in {native['state']}")
        time.sleep(0.1)
    raise RuntimeError('Recovery readiness timed out; inspect native Status before retrying')


def restart_shell_context():
    """Replace all Shell JS in the explicitly selected private rebind build."""
    if (os.environ.get('TGNOME_REBIND_TYPES') != '1' or
            os.environ.get('TGNOME_ALLOW_RUNTIME_RESET') != '1' or
            not os.environ.get('TGNOME_BUS_OWNER', '').startswith(':')):
        raise RuntimeError('Complete context restart requires the isolated rebind build and pinned owner')
    native_before = call('Status', native=True)
    if 'callbacks' not in native_before or native_before['attempts'] >= 3:
        raise RuntimeError('Matching native rebind supervisor with remaining attempts is required')
    before = call('Status')
    preparation = call('PrepareRuntimeReset')
    requested = call('ResetProbe', native=True)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        native = call('Status', native=True)
        if native['pid'] != native_before['pid']:
            raise RuntimeError('Compositor identity changed during complete context restart')
        if native['contextsFinalized'] == native_before['contextsFinalized'] + 1:
            try:
                status = call('Status')
            except RuntimeError:
                status = None  # New context has not exported its extension yet.
            if (status and status['runtimeEpoch'] != before['runtimeEpoch'] and
                    status['pid'] == before['pid'] and
                    not status['shellState']['startingUp'] and
                    status['panel']['containerCount'] == 1):
                return {'classification': 'COMPLETE SHELL CONTEXT REPLACEMENT',
                        'wholeShellRestarted': True, 'compositorPreserved': True,
                        'pid': native['pid'], 'beforeEpoch': before['runtimeEpoch'],
                        'afterEpoch': status['runtimeEpoch'], 'preparation': preparation,
                        'requested': requested, 'native': native}
        time.sleep(0.1)
    raise RuntimeError('Complete Shell context readiness timed out; inspect the private native Status')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=[
        'status', 'reload-ui', 'reload-theme', 'reload-panel', 'reload-shell',
        'reload-extensions', 'recover-session', 'self-test', 'reload-desktop-ui',
        'recover-desktop-ui', 'restart-shell-context'])
    args = parser.parse_args()
    if args.operation in ('reload-shell', 'reload-extensions', 'recover-session'):
        parser.exit(2, f'{args.operation}: unsupported; no process or session was changed. '
                    'reload-ui only rebuilds the experimental indicator; '
                    'reload-desktop-ui requires the isolated patched headless Shell.\n')
    try:
        if args.operation == 'restart-shell-context':
            print(json.dumps(restart_shell_context()))
            return
        if args.operation == 'recover-desktop-ui':
            print(json.dumps(recover_desktop_ui()))
            return
        if args.operation == 'self-test':
            status = call('Status')
            healthy = (status['active'] and status['liveOwnedActors'] == 1
                       and status['panelEntryMatches'] and not status['busy']
                       and not status['shellRestartSupported'])
            print(json.dumps({'classification': 'RESEARCH PROTOTYPE',
                              'endpointHealthy': healthy,
                              'scope': 'read-only endpoint check; no client survival experiment',
                              'shellRestartSupported': False}))
            sys.exit(0 if healthy else 1)
        method = {'status': 'Status', 'reload-ui': 'ReloadUI',
                  'reload-theme': 'ReloadTheme', 'reload-panel': 'ReloadPanel',
                  'reload-desktop-ui': 'ReloadDesktopUi'}[args.operation]
        print(json.dumps(call(method, *(['false'] if method in ('ReloadUI', 'ReloadPanel') else []))))
    except (RuntimeError, subprocess.TimeoutExpired, ValueError, SyntaxError) as error:
        print(f'tgnome: {error}', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
