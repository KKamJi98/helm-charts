"""Current-main composition, not runtime/data acceptance. Synthetic guards only."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import yaml

import test_grafana_pvc_preparation as prep

ROOT = Path(__file__).resolve().parents[1]
ORACLE = json.loads((ROOT / 'tests/fixtures/keycloak-consumers/main9a.json').read_text())
# Preserve the immutable main9a storage/crypto and other-chart oracles. Only the
# monitoring whole-render counts/hashes change for the Job alert relocation;
# test_kube_job_failed_rules verifies its exact delta against immutable fc09262.
MONITORING_JOB_FAILED_ORACLE = {
    'local': {'count': 132, 'objectsSha256':
              '9131f4a4774effb9c19fa601fc05db34de5508f5bc13b1bc3ae1031edc0c4774'},
    'includeCRDs': {'count': 142, 'objectsSha256':
                    '3cd44fcc35fbd40291f099ad1ac9beeeccf7d1bfe1e1c89e0b149807e2d03d2a'},
}
SSO_DEFAULTS = {
    'backendTLSReady': False,
    'grafana': {'mode': 'legacy', 'cutoverApproved': False,
                'dataPreservationReady': False, 'accessLogsSafe': False},
    'prometheus': {'mode': 'legacy'}, 'alertmanager': {'mode': 'legacy'},
}
IDENTITY_REFS = {
    'KEYCLOAK_GRAFANA_USERNAME_ATTRIBUTE_PATH': 'username_attribute_path',
    'KEYCLOAK_GRAFANA_EXPECT_CLAIMS': 'expect_claims',
}


def merge(left, right):
    result = copy.deepcopy(left)
    for key, value in right.items():
        result[key] = merge(result[key], value) if isinstance(value, dict) and isinstance(result.get(key), dict) else copy.deepcopy(value)
    return result


def synthetic_overlay(mode, chart=prep.CHART):
    """Acknowledgements are synthetic test inputs, never a source/runtime verdict."""
    overlay = yaml.safe_load((chart / 'keycloak-canary-values.yaml').read_text())
    if mode == 'only':
        overlay = merge(overlay, yaml.safe_load((chart / 'keycloak-only-values.yaml').read_text()))
    return merge(overlay, {'keycloakSSO': {'backendTLSReady': True, 'grafana': {
        'dataPreservationReady': True, 'accessLogsSafe': True, 'cutoverApproved': mode == 'only'}}})


def composition(mode, override=None, chart=prep.CHART):
    return prep.render(merge(synthetic_overlay(mode, chart), override or {}), prepared=False, chart=chart)


def assert_composed(case, result, chart=prep.CHART):
    objects = prep.documents(result)
    source = yaml.safe_load((chart / 'kkamji_local_values.yaml').read_text())
    native = source['kube-prometheus-stack']['grafana']
    case.assertIs(source.get('grafanaPvcPreparation'), True)
    case.assertEqual(native.get('replicas'), 1)
    case.assertEqual(native.get('deploymentStrategy'), {'type': 'Recreate', 'rollingUpdate': None})
    case.assertEqual(native.get('persistence'), {'enabled': True, 'type': 'pvc',
        'existingClaim': '{{ include "grafana.fullname" . }}', 'storageClassName': 'local-path',
        'accessModes': ['ReadWriteOnce'], 'size': '10Gi'})
    case.assertEqual(native.get('initChownData'), {'enabled': False})
    # Guard existence/bytes have an immutable oracle too. Dropping enforcement is
    # not allowed even if a particular render happens to preserve storage.
    guard = chart / 'templates/grafana-pvc-preparation.tpl'
    case.assertTrue(guard.is_file(), 'retained-PVC guard must remain present')
    case.assertEqual(hashlib.sha256(guard.read_bytes()).hexdigest(), ORACLE['storageGuardSha256'])
    case.assertIn(prep.PVC_KEY, objects.keys())
    case.assertEqual(prep.digest(objects[prep.PVC_KEY]), prep.digest(prep.EXPECTED_PVC))
    dep = copy.deepcopy(objects[prep.GRAFANA_KEY])
    case.assertEqual(dep['spec']['replicas'], 1)
    case.assertEqual(dep['spec']['strategy'], {'type': 'Recreate', 'rollingUpdate': None})
    pod = dep['spec']['template']['spec']
    case.assertEqual(next(v for v in pod['volumes'] if v['name'] == 'storage'),
                     {'name': 'storage', 'persistentVolumeClaim': {'claimName': 'kube-prometheus-stack-grafana'}})
    grafana, = [c for c in pod['containers'] if c['name'] == 'grafana']
    env = {e['name']: e for e in grafana['env']}
    for name, prop in IDENTITY_REFS.items():
        case.assertEqual(env[name], {'name': name, 'valueFrom': {'secretKeyRef': {
            'name': 'grafana-keycloak-identity', 'key': prop}}})
    grafana['env'] = [e for e in grafana['env'] if e['name'] not in IDENTITY_REFS]
    # Only two explicit Secret refs and the config checksum may differ. Immutable
    # full Deployment hash still covers crypto inputs, sidecars, init, ownership,
    # images, resources, volumes, strategy and replicas; no mutable-baseline copy.
    dep['spec']['template']['metadata']['annotations'].pop('checksum/config')
    case.assertEqual(prep.digest(dep), ORACLE['local']['kube-prometheus-stack']['grafanaWithoutConfigChecksumSha256'])
    return objects


class CurrentMainTests(unittest.TestCase):
    def test_additive_defaults_explicitly_keep_all_cutover_gates_closed(self):
        self.assertEqual(yaml.safe_load((prep.CHART / 'values.yaml').read_text()),
                         {'kube-prometheus-stack': {}, 'grafanaPvcPreparation': False, 'keycloakSSO': SSO_DEFAULTS})

    def test_legacy_objects_match_immutable_current_main_not_mutable_values(self):
        namespaces = {'argocd': 'argocd', 'cilium': 'kube-system', 'hindsight': 'hindsight', 'kube-prometheus-stack': 'monitoring'}
        for chart, namespace in namespaces.items():
            with self.subTest(chart=chart):
                path = ROOT / 'charts' / chart
                args = [prep.HELM, 'template', chart, str(path), '-n', namespace, '--skip-tests',
                        '--kube-version', '1.36.1', '-f', str(path / 'kkamji_local_values.yaml')]
                objects = prep.documents(prep.helm_command(args))
                oracle = (MONITORING_JOB_FAILED_ORACLE['local'] if chart == 'kube-prometheus-stack'
                          else ORACLE['local'][chart])
                self.assertEqual(len(objects), oracle['count'])
                self.assertEqual(prep.digest([objects[k] for k in sorted(objects)]), oracle['objectsSha256'])
        objects = prep.documents(prep.render(prepared=False, include_crds=True))
        self.assertEqual(len(objects), MONITORING_JOB_FAILED_ORACLE['includeCRDs']['count'])
        self.assertEqual(prep.digest([objects[k] for k in sorted(objects)]),
                         MONITORING_JOB_FAILED_ORACLE['includeCRDs']['objectsSha256'])

    def test_retained_pvc_composes_with_canary_and_final_synthetic_only(self):
        for mode in ('canary', 'only'):
            with self.subTest(mode=mode):
                assert_composed(self, composition(mode))
        for name in ('keycloak-canary-values.yaml', 'keycloak-only-values.yaml'):
            sso = yaml.safe_load((prep.CHART / name).read_text())['keycloakSSO']['grafana']
            for gate in ('accessLogsSafe', 'dataPreservationReady', 'cutoverApproved'):
                self.assertFalse(sso.get(gate, False), 'source overlay cannot acknowledge a runtime gate')

    def test_composed_storage_and_acknowledgement_negative_inputs_refused(self):
        unsafe = [
            {'grafanaPvcPreparation': False},
            *[{'kube-prometheus-stack': {'grafana': g}} for g in (
                {'persistence': {'enabled': False}}, {'persistence': {'existingClaim': 'other'}},
                {'replicas': 2}, {'deploymentStrategy': {'type': 'RollingUpdate'}},
                {'initChownData': {'enabled': True}})],
            *[{'keycloakSSO': {'grafana': {gate: value}}} for gate in ('accessLogsSafe', 'dataPreservationReady') for value in (False, 'true')],
            {'keycloakSSO': {'backendTLSReady': False}},
        ]
        for mode in ('canary', 'only'):
            for index, override in enumerate(unsafe):
                with self.subTest(mode=mode, case=index):
                    self.assertNotEqual(composition(mode, override).returncode, 0)
        for value in (False, 'true'):
            self.assertNotEqual(composition('only', {'keycloakSSO': {'grafana': {'cutoverApproved': value}}}).returncode, 0)

    def test_current_source_mutations_cannot_change_both_sides_of_oracle(self):
        with tempfile.TemporaryDirectory(prefix='consumer-main-mutation-') as temporary:
            chart = Path(temporary) / prep.CHART.name
            shutil.copytree(prep.CHART, chart)
            path = chart / 'kkamji_local_values.yaml'
            original = path.read_bytes()
            data = yaml.safe_load(original)
            for key in ('persistence', 'replicas', 'deploymentStrategy'):
                with self.subTest(missing=key):
                    mutated = copy.deepcopy(data)
                    del mutated['kube-prometheus-stack']['grafana'][key]
                    path.write_text(yaml.safe_dump(mutated))
                    with self.assertRaises(AssertionError):
                        assert_composed(self, composition('canary', chart=chart), chart)
                    path.write_bytes(original)
            guard = chart / 'templates/grafana-pvc-preparation.tpl'
            guard.unlink()
            with self.assertRaises(AssertionError):
                assert_composed(self, composition('canary', chart=chart), chart)

    def test_composed_crypto_sidecar_ownership_mutations_fail_fixed_oracle(self):
        unsafe = [
            {'env': {'GF_SECURITY_SECRET_KEY': 'synthetic-offline-not-a-credential'}},
            {'sidecar': {'resources': {'requests': {'cpu': '1m'}}}},
            {'securityContext': {'runAsUser': 0}},
            {'extraInitContainers': [{'name': 'offline-mutation', 'image': 'synthetic.invalid/fixture:1'}]},
        ]
        for index, grafana in enumerate(unsafe):
            with self.subTest(case=index):
                result = composition('canary', {'kube-prometheus-stack': {'grafana': grafana}})
                self.assertEqual(result.returncode, 0)
                with self.assertRaises(AssertionError):
                    assert_composed(self, result)

    def test_consumer_render_refusals_withhold_untrusted_diagnostics(self):
        import secrets
        from types import SimpleNamespace
        from unittest.mock import patch
        import test_keycloak_consumers as consumers
        import test_grafana_keycloak as grafana
        marker = secrets.token_hex(32)
        failed = SimpleNamespace(returncode=1, stderr=marker, stdout='')
        with self.assertRaises(AssertionError) as refused:
            consumers.docs(failed)
        self.assertFalse(marker in str(refused.exception), 'consumer refusal must withhold native diagnostics')
        with patch.object(grafana, 'render', return_value=failed):
            with self.assertRaises(AssertionError) as refused:
                grafana.objects()
        self.assertFalse(marker in str(refused.exception), 'Grafana refusal must withhold native diagnostics')

    def test_bare_legacy_edge_defaults_do_not_require_local_gateway_values(self):
        for chart, namespace in (('cilium', 'kube-system'), ('kube-prometheus-stack', 'monitoring')):
            with self.subTest(chart=chart):
                args = [prep.HELM, 'template', chart, str(ROOT / 'charts' / chart), '-n', namespace,
                        '--skip-tests', '--kube-version', '1.36.1']
                self.assertEqual(prep.helm_command(args).returncode, 0, 'legacy must not dereference optional Gateway configuration')

    def test_real_argocd_comparison_refusal_digests_secret_data(self):
        import secrets
        from unittest.mock import patch
        import test_keycloak_consumers as consumers
        real_native = consumers.NativeTests.native
        marker = secrets.token_hex(32)
        sensitive = []

        def altered_native(case, *args, **kwargs):
            objects = real_native(case, *args, **kwargs)
            target = next(obj for (kind, _), obj in objects.items() if kind == 'Secret')
            target.setdefault('stringData', {})['offline-comparison-probe'] = marker
            sensitive.extend(str(value) for (kind, _), obj in objects.items() if kind == 'Secret'
                             for field in ('data', 'stringData') for value in obj.get(field, {}).values() if value)
            return objects

        with patch.object(consumers.NativeTests, 'native', altered_native):
            with self.assertRaises(AssertionError) as refused:
                consumers.NativeTests().test_argocd_native_canary_and_final_are_fail_closed()
        self.assertTrue(sensitive, 'real entry-point comparison must include Secret data')
        self.assertFalse(any(v in str(refused.exception) for v in sensitive), 'real entry-point comparison leaked Secret data')

    def test_focused_consumer_ci_covers_composition_and_seven_client_contracts(self):
        workflow = ROOT / '.github/workflows/keycloak-consumer-lint.yml'
        self.assertTrue(workflow.is_file(), 'focused source-only consumer CI is required')
        data = yaml.load(workflow.read_text(), Loader=yaml.BaseLoader)
        self.assertEqual(data['permissions'], {'contents': 'read'})
        job = data['jobs']['validate']
        self.assertEqual(job['runs-on'], 'ubuntu-latest')
        steps = job['steps']
        self.assertIn({'uses': 'actions/checkout@v4', 'with': {'persist-credentials': 'false'}}, steps)
        self.assertIn({'uses': 'azure/setup-helm@v4', 'with': {'version': 'v4.2.1'}}, steps)
        run = next(s['run'] for s in steps if s.get('name') == 'Focused offline consumer contracts')
        for module in ('test_keycloak_consumers', 'test_grafana_keycloak', 'test_keycloak_current_main', 'test_keycloak_seven_clients'):
            self.assertIn(module, run)
        for token in ('HELM=', 'HELM_BIN=', 'PYTHONDONTWRITEBYTECODE=1', '--python 3.12', '--with lupa'):
            self.assertIn(token, run)
        required = {'charts/argocd/**', 'charts/cilium/**', 'charts/hindsight/**', 'charts/kube-prometheus-stack/**',
                    'tests/test_grafana_pvc_preparation.py', 'tests/fixtures/keycloak-consumers/**',
                    'examples/keycloak-preparation/consumer-contract/**'}
        for trigger in ('pull_request', 'push'):
            self.assertTrue(required <= set(data['on'][trigger]['paths']))

    def test_actual_composed_refusal_does_not_disclose_rendered_secrets(self):
        result = composition('canary', {'kube-prometheus-stack': {'grafana': {'resources': {'requests': {'memory': '1Gi'}}}}})
        objects = prep.documents(result)
        sensitive = [str(v) for obj in objects.values() if obj['kind'] == 'Secret'
                     for field in ('data', 'stringData') for v in obj.get(field, {}).values() if v]
        self.assertTrue(sensitive, 'negative render must exercise nonempty Secret data')
        with self.assertRaises(AssertionError) as refused:
            assert_composed(self, result)
        self.assertFalse(any(v in str(refused.exception) for v in sensitive), 'unsafe test diagnostics')


if __name__ == '__main__':
    unittest.main()
