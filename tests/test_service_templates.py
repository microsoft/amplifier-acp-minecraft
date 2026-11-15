"""The controller unit template must bring the controller back after an outside SIGTERM."""
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


def service_settings(name):
    lines = (ROOT / 'ops' / name).read_text().splitlines()
    section = lines[lines.index('[Service]') + 1:lines.index('[Install]')]
    return [tuple(line.split('=', 1)) for line in section]


class ServiceTemplates(unittest.TestCase):
    def test_controller_restarts_after_a_crash_or_an_outside_termination_signal(self):
        settings = service_settings('minecraft-agent@.service')
        # on-failure alone treats SIGTERM as a clean exit. The service manager's
        # own stop is never restarted, whatever these settings say.
        self.assertEqual([v for k, v in settings if k == 'Restart'], ['on-failure'])
        self.assertEqual([v for k, v in settings if k == 'RestartForceExitStatus'], ['SIGTERM'])

    @unittest.skipIf(os.name == 'nt', 'POSIX signal status')
    def test_running_controller_is_ended_by_sigterm_rather_than_exiting_cleanly(self):
        # RestartForceExitStatus=SIGTERM matches a main process killed by the
        # signal. A handler that turned it into exit status 0 would silently
        # disable the template's rule.
        with tempfile.TemporaryDirectory() as tmp, socket.socket() as body:
            body.bind(('127.0.0.1', 0)); body.listen(1); body.settimeout(30)
            home = Path(tmp)
            (home / 'config.json').write_text(json.dumps({'control_port': body.getsockname()[1], 'token': 'fixture'}))
            (home / 'endpoint.json').write_text(json.dumps({'command': ['unused'], 'cwd': tmp}))
            controller = subprocess.Popen([sys.executable, str(ROOT / 'adapter.py'), '--home', tmp], cwd=ROOT,
                                          stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
            try:
                # Its first body request proves the controller reached its loop.
                request, _ = body.accept(); request.close(); time.sleep(.2)
                controller.send_signal(signal.SIGTERM)
                status = controller.wait(20)
            finally:
                if controller.poll() is None:
                    controller.kill(); controller.wait(10)
                errors = controller.stderr.read(); controller.stderr.close()
            self.assertEqual(status, -signal.SIGTERM, errors)
