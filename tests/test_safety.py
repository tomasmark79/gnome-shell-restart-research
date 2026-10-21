import contextlib
import io
import os
import sys
import unittest
from unittest.mock import patch

import tgnome


class SafetyTests(unittest.TestCase):
    def test_complete_context_restart_requires_explicit_private_build(self):
        for env in ({}, {'TGNOME_REBIND_TYPES': '1', 'TGNOME_ALLOW_RUNTIME_RESET': '1'}):
            with self.subTest(env=env), patch.dict(os.environ, env, clear=True), \
                    patch('subprocess.run') as run:
                with self.assertRaisesRegex(RuntimeError, 'isolated rebind build'):
                    tgnome.restart_shell_context()
                run.assert_not_called()

    def test_unsupported_operations_never_spawn_a_command(self):
        for operation in ['reload-shell', 'reload-extensions', 'recover-session']:
            with self.subTest(operation=operation), patch.object(sys, 'argv', ['tgnome', operation]), \
                    patch('subprocess.run') as run, contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    tgnome.main()
                self.assertEqual(error.exception.code, 2)
                run.assert_not_called()

    def test_status_does_not_discover_or_autolaunch_host_bus(self):
        with patch.dict(os.environ, {}, clear=True), patch('subprocess.run') as run:
            with self.assertRaisesRegex(RuntimeError, 'explicit session bus'):
                tgnome.call('Status')
            run.assert_not_called()

    def test_timeout_is_bounded(self):
        result = type('Result', (), {'returncode': 0, 'stdout': '(\'{"active":true}\',)', 'stderr': ''})()
        with patch.dict(os.environ, {'DBUS_SESSION_BUS_ADDRESS': 'unix:path=/private/test'}), \
                patch('subprocess.run', return_value=result) as run:
            self.assertEqual(tgnome.call('Status'), {'active': True})
            self.assertEqual(run.call_args.kwargs['timeout'], 15)
            self.assertIn('org.gnome.Shell.Extensions.Tgnome.Status', run.call_args.args[0])

    def test_pinned_owner_prevents_well_known_name_autostart(self):
        result = type('Result', (), {'returncode': 0, 'stdout': '(\'{"active":true}\',)', 'stderr': ''})()
        with patch.dict(os.environ, {'DBUS_SESSION_BUS_ADDRESS': 'unix:path=/private/test',
                                     'TGNOME_BUS_OWNER': ':1.42'}), \
                patch('subprocess.run', return_value=result) as run:
            tgnome.call('Status')
            command = run.call_args.args[0]
            self.assertEqual(command[command.index('--dest') + 1], ':1.42')

    def test_invalid_pinned_owner_is_rejected_without_spawning(self):
        with patch.dict(os.environ, {'DBUS_SESSION_BUS_ADDRESS': 'unix:path=/private/test',
                                     'TGNOME_BUS_OWNER': 'another.application'}), \
                patch('subprocess.run') as run:
            with self.assertRaisesRegex(RuntimeError, 'unique D-Bus name'):
                tgnome.call('Status')
            run.assert_not_called()

    def test_recovery_requires_unique_owner_before_native_rpc(self):
        with patch.dict(os.environ, {'DBUS_SESSION_BUS_ADDRESS': 'unix:path=/private/test'}, clear=True), \
                patch('subprocess.run') as run:
            with self.assertRaisesRegex(RuntimeError, 'pinned to a unique'):
                tgnome.recover_desktop_ui()
            run.assert_not_called()

    def test_recovery_refuses_healthy_active_and_quarantined_ui(self):
        for state in [dict(state='ui-ready', uiActive=False, uiQuarantined=False),
                      dict(state='ui-failed', uiActive=True, uiQuarantined=False),
                      dict(state='ui-failed', uiActive=False, uiQuarantined=True)]:
            with self.subTest(state=state), patch.object(tgnome, 'call', return_value=state) as call:
                with self.assertRaisesRegex(RuntimeError, 'confirmed cleanup'):
                    tgnome.recover_desktop_ui()
                call.assert_called_once_with('Status', native=True)

    def test_recovery_waits_for_final_publication_without_extension_rpc(self):
        before = dict(state='ui-failed', uiActive=False, uiQuarantined=False,
                      uiBuildSerial=4, uiCommits=1, pid=123, publishedUiGeneration=0)
        acknowledged = dict(state='ui-ready', uiActive=False, uiBuildSerial=5, uiCommits=2,
                            pid=123, publishedUiGeneration=0)
        published = dict(acknowledged, publishedUiGeneration=2)
        with patch.object(tgnome, 'call', side_effect=[before, {}, acknowledged, published]) as call, \
                patch.object(tgnome.time, 'sleep'):
            result = tgnome.recover_desktop_ui()
            self.assertTrue(result['recovered'])
            self.assertFalse(result['wholeShellRestarted'])
            self.assertEqual(call.call_args_list[1].args, ('RecoverUi', '4'))
            self.assertEqual(call.call_args_list[1].kwargs, {'native': True})
            self.assertTrue(all(c.kwargs == {'native': True} for c in call.call_args_list))

    def test_recovery_reports_terminal_failure_without_resubmitting(self):
        before = dict(state='ui-failed', uiActive=False, uiQuarantined=False,
                      uiBuildSerial=4, uiCommits=1)
        failed = dict(state='ui-failed', uiActive=False, uiBuildSerial=6)
        with patch.object(tgnome, 'call', side_effect=[before, {}, failed]) as call:
            with self.assertRaisesRegex(RuntimeError, 'ended in ui-failed'):
                tgnome.recover_desktop_ui()
            self.assertEqual(call.call_count, 3)


if __name__ == '__main__':
    unittest.main()
