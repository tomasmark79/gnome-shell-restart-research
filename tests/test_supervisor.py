"""Exercise containment of a real orphaned private helper on Linux."""
import signal
import subprocess
import sys
import unittest

from isolated import enable_private_subreaper, reap_private_descendants


class SupervisorTest(unittest.TestCase):
    def test_reaps_helper_after_its_launcher_exits(self):
        enable_private_subreaper()
        script = (
            'import subprocess,sys; '
            'child=subprocess.Popen([sys.executable,"-c",'
            '"import time; time.sleep(60)"],'
            'stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); '
            'print(child.pid,flush=True)'
        )
        try:
            launcher = subprocess.run([sys.executable, '-c', script],
                                      text=True, capture_output=True,
                                      check=True, timeout=5)
        finally:
            cleanup = reap_private_descendants()
        orphan = int(launcher.stdout.strip())
        self.assertIn(orphan, cleanup['terminated'])
        self.assertEqual(cleanup['exitCodes'][orphan], -signal.SIGTERM)
        self.assertEqual(cleanup['killed'], [])


if __name__ == '__main__':
    unittest.main()
