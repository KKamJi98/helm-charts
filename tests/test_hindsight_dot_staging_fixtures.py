import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('fixtures', ROOT / 'scripts/hindsight-dot/network_fixtures.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class FixtureTest(unittest.TestCase):
    def test_scoped_nonsecret_jobs(self):
        d = m.render('example.invalid/dot@sha256:' + 'a'*64, '10.0.0.8', '192.0.2.9')
        self.assertEqual(len(d['items']), 3)
        for job in d['items']:
            self.assertEqual(job['kind'], 'Job')
            self.assertEqual(job['metadata']['namespace'], 'hindsight-dot')
            self.assertEqual(job['spec']['backoffLimit'], 0)
            pod = job['spec']['template']['spec']
            self.assertFalse(pod['automountServiceAccountToken'])
            self.assertNotIn('volumes', pod)
            c = pod['containers'][0]
            self.assertNotIn('env', c)
            self.assertEqual(c['readinessProbe']['httpGet']['port'], 65534)
            self.assertIn('DNS FAILURE', c['command'][2])
            compile(c['command'][2], '<probe>', 'exec')

    def test_invalid_input(self):
        for image, ip in [('repo:latest', '10.0.0.8'), ('repo@sha256:'+'a'*64, 'unverified-host')]:
            with self.assertRaises(ValueError):
                m.render(image, ip, '192.0.2.9')

    def test_operator_no_shell_or_exec(self):
        source = (ROOT/'scripts/hindsight-dot/gate_control.py').read_text()
        self.assertNotIn('shell=True', source)
        self.assertNotIn("'exec'", source)
        self.assertIn('--address=127.0.0.1', source)
        self.assertIn('nx=True', source)
        self.assertIn('proc.terminate()', source)
        self.assertIn('getpass.getpass', source)

spec2 = importlib.util.spec_from_file_location('gate', ROOT / 'scripts/hindsight-dot/gate_control.py')
gate = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(gate)


class GateTest(unittest.TestCase):
    class RedisFake:
        def __init__(self, value=None):
            self.value = value
            self.race = False
        def get(self, key):
            return self.value
        def set(self, key, value, nx=False):
            if nx and self.value is not None:
                return None
            self.value = value
            return True
        def execute_command(self, command, key, new, condition, old):
            assert command == 'SET' and condition == 'IFEQ' and key == gate.KEY
            if self.race or self.value != old:
                return None
            self.value = new
            return True

    def test_security_epoch_monotonic_and_no_old_enable(self):
        c = self.RedisFake()
        gate.transition(c, 'initialize', 1)
        gate.transition(c, 'enable', 1, 1)
        self.assertEqual(gate.transition(c, 'security-stop', 1), {'enabled': False, 'epoch': 2})
        with self.assertRaises(RuntimeError):
            gate.transition(c, 'enable', 1, 1)
        with self.assertRaises(RuntimeError):
            gate.transition(c, 'enable', 2)
        self.assertEqual(gate.transition(c, 'enable', 2, 2), {'enabled': True, 'epoch': 2})

    def test_cas_race_and_malformed_fail_closed(self):
        c = self.RedisFake('{"enabled":true,"epoch":1}')
        c.race = True
        with self.assertRaises(RuntimeError):
            gate.transition(c, 'security-stop', 1)
        self.assertEqual(c.value, '{"enabled":true,"epoch":1}')
        for bad in [None, '{}', '[]', '{"enabled":true,"epoch":true}', '{"secret":"do-not-print"}']:
            c.value = bad
            with self.assertRaises(RuntimeError):
                gate.transition(c, 'security-stop', 1)

    def test_maintenance_explicitly_preserves_epoch(self):
        c = self.RedisFake('{"enabled":true,"epoch":4}')
        self.assertEqual(gate.transition(c, 'maintenance-pause', 4), {'enabled': False, 'epoch': 4})
        with self.assertRaises(RuntimeError):
            gate.transition(c, 'disable', 4)
