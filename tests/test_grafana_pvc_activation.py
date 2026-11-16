"""Native storage candidate only; no live copy, recovery, crypto or SSO proof."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import tarfile
import tempfile
import unittest

import yaml

import test_grafana_pvc_preparation as prep

# Pristine 9c8ea6fb84e474095a62c34013d5644f7fa5d0f6, Helm 4.2.1,
# Kube 1.36.1, monitoring, --skip-tests --include-crds. Default alone uses FIXTURE.
# All four legacy no-CRD goldens remain unchanged in the preparation tests.
ARGO_GOLDENS = {
    False: (132, "06d9dbd91278b3e4d92727b1a1ced777f4556ea413ab531e6acec35f6309f9cd",
            "8c94924add936fe5fe34b8fb0cc01917a9fb96fbad76bcfdf786c355f436451a"),
    True: (140, "59eb71febcac1bfec6a9e23fa89e27df86b46f689c3bc655bfbc128aa19e4d70",
           "10b6110b7475b488f344aaa6eb8dbbdb62f3a263242c3d257326e067265775a7"),
}
CLAIM = '{{ include "grafana.fullname" . }}'
ACTIVE_STORAGE = {"name": "storage", "persistentVolumeClaim": {"claimName": "kube-prometheus-stack-grafana"}}
ALLOWED_PATHS = {
    "/spec/strategy/rollingUpdate",
    "/spec/strategy/type",
    "/spec/template/spec/volumes/2/emptyDir",
    "/spec/template/spec/volumes/2/persistentVolumeClaim",
}
RAW_DELTA = (
    ("  strategy:\n    rollingUpdate: null\n    type: Recreate\n", "  strategy:\n    type: RollingUpdate\n"),
    ("        - name: storage\n          persistentVolumeClaim:\n            claimName: kube-prometheus-stack-grafana\n",
     "        - name: storage\n          emptyDir: {}\n"),
)


def active_render(override=None, **kwargs):
    return prep.render(override, prepared=False, **kwargs)


def paths(before, after, prefix=""):
    """Exact recursive differences, including additions/removals, without values."""
    if type(before) is not type(after):
        return {prefix}
    if isinstance(before, dict):
        result = {prefix + "/" + k for k in before.keys() ^ after.keys()}
        for key in before.keys() & after.keys():
            result |= paths(before[key], after[key], prefix + "/" + key)
        return result
    if isinstance(before, list):
        if len(before) != len(after):
            return {prefix}
        result = set()
        for index, (left, right) in enumerate(zip(before, after)):
            result |= paths(left, right, prefix + "/" + str(index))
        return result
    return set() if before == after else {prefix}


def raw_hash(raw):
    return hashlib.sha256(json.dumps([(k, raw[k]) for k in sorted(raw) if k[1] != "Secret"],
                                     separators=(",", ":")).encode()).hexdigest()


def assert_whole_baseline(case, objects, raw, local=True, include_crds=True):
    if include_crds:
        count, spec_hash, nonsecret_hash = ARGO_GOLDENS[local]
    else:
        count, spec_hash, nonsecret_hash = prep.GOLDENS[local][:3]
    case.assertEqual(len(objects), count)
    case.assertEqual(prep.digest([objects[k] for k in sorted(objects)]), spec_hash)
    case.assertEqual(raw_hash(raw), nonsecret_hash)
    deployment = objects[prep.GRAFANA_KEY]
    case.assertEqual(prep.digest(deployment), prep.GOLDENS[local][3])
    case.assertEqual(prep.digest(deployment["spec"]["template"]), prep.GOLDENS[local][4])


def assert_active(case, result, include_crds=True):
    objects, raw = prep.raw_documents(result)
    case.assertIn(prep.PVC_KEY, objects.keys())
    case.assertEqual(objects[prep.PVC_KEY], prep.EXPECTED_PVC)
    # Invert exactly the intended two native deltas, then use immutable whole
    # baseline hashes. Do not compare only to a second mutable configuration.
    reverted = copy.deepcopy(objects)
    reverted_raw = dict(raw)
    del reverted[prep.PVC_KEY]
    del reverted_raw[prep.PVC_KEY]
    deployment = reverted[prep.GRAFANA_KEY]
    pod = deployment["spec"]["template"]["spec"]
    case.assertEqual(deployment["spec"]["replicas"], 1)
    case.assertEqual(deployment["spec"]["strategy"], {"type": "Recreate", "rollingUpdate": None})
    case.assertEqual(pod["volumes"][2], ACTIVE_STORAGE)
    case.assertFalse(any(c["name"] == "init-chown-data" for c in pod.get("initContainers", [])))
    deployment["spec"]["strategy"] = {"type": "RollingUpdate"}
    pod["volumes"][2] = {"name": "storage", "emptyDir": {}}
    for active, prepared in RAW_DELTA:
        case.assertEqual(reverted_raw[prep.GRAFANA_KEY].count(active), 1)
        reverted_raw[prep.GRAFANA_KEY] = reverted_raw[prep.GRAFANA_KEY].replace(active, prepared, 1)
    assert_whole_baseline(case, reverted, reverted_raw, include_crds=include_crds)
    return objects, raw


def check_candidate(case, chart=prep.CHART):
    """Real CI entry-point contract, also exercised with actual source fixtures."""
    return assert_active(case, active_render(chart=chart, include_crds=True))


class GrafanaPvcActivationTests(unittest.TestCase):
    def test_canonical_native_activation(self):
        check_candidate(self)
        assert_active(self, active_render(), include_crds=False)

    def test_recreate_explicitly_clears_api_defaulted_rolling_update(self):
        values = yaml.safe_load((prep.CHART / "kkamji_local_values.yaml").read_text())
        result = active_render(include_crds=True)
        self.assertEqual(result.returncode, 0)
        native = prep.documents(result)[prep.GRAFANA_KEY]["spec"]["strategy"]
        source = values["kube-prometheus-stack"]["grafana"]["deploymentStrategy"]
        for profile, strategy in (("source", source), ("native", native)):
            self.assertIn("rollingUpdate", strategy.keys(), profile)
            self.assertIs(strategy["rollingUpdate"], None, profile)
            self.assertEqual(strategy, {"type": "Recreate", "rollingUpdate": None})
        with tempfile.TemporaryDirectory(prefix="grafana-recreate-clear-") as temporary:
            chart = Path(temporary) / prep.CHART.name
            shutil.copytree(prep.CHART, chart)
            path = chart / "kkamji_local_values.yaml"
            original = path.read_text()
            marker = "      rollingUpdate: null\n"
            self.assertEqual(original.count(marker), 1)
            path.write_text(original.replace(marker, "", 1))
            refused = active_render(chart=chart, include_crds=True)
            self.assertEqual(refused.returncode, 1)
            self.assertIn("Grafana PVC preparation:", refused.stderr)
            path.write_text(original)
            check_candidate(self, chart)

    def test_source_defaults_remain_disabled_and_fixed_for_both_render_profiles(self):
        self.assertEqual(yaml.safe_load((prep.CHART / "values.yaml").read_text()),
                         {"kube-prometheus-stack": {}, "grafanaPvcPreparation": False})
        for crds in (False, True):
            with self.subTest(include_crds=crds):
                objects, raw = prep.raw_documents(active_render(copy.deepcopy(prep.FIXTURE), local=False, include_crds=crds))
                self.assertNotIn(prep.PVC_KEY, objects.keys())
                assert_whole_baseline(self, objects, raw, local=False, include_crds=crds)

    def test_legacy_preparation_full_argo_goldens_are_fixed_not_active_defaults(self):
        for local in (False, True):
            override: dict = {} if local else copy.deepcopy(prep.FIXTURE)
            override["grafanaPvcPreparation"] = True
            objects, raw = prep.raw_documents(prep.render(override, local=local, include_crds=True))
            self.assertIn(prep.PVC_KEY, objects.keys())
            self.assertEqual(objects.pop(prep.PVC_KEY), prep.EXPECTED_PVC)
            raw.pop(prep.PVC_KEY)
            assert_whole_baseline(self, objects, raw, local=local)

    def test_all_identities_whole_objects_raw_and_exact_deployment_path_allowlist(self):
        active, active_raw = check_candidate(self)
        prepared, prepared_raw = prep.raw_documents(prep.render(include_crds=True))
        self.assertEqual(set(active), set(prepared))
        self.assertEqual(len(active), 141)
        changed = {k for k in active if prep.digest(active[k]) != prep.digest(prepared[k])}
        self.assertEqual(changed, {prep.GRAFANA_KEY})
        self.assertEqual(paths(prepared[prep.GRAFANA_KEY], active[prep.GRAFANA_KEY]), ALLOWED_PATHS)
        for key in sorted(active):
            if key != prep.GRAFANA_KEY:
                self.assertEqual(prep.digest(active[key]), prep.digest(prepared[key]))
                if key[1] != "Secret":
                    self.assertEqual(hashlib.sha256(active_raw[key].encode()).hexdigest(),
                                     hashlib.sha256(prepared_raw[key].encode()).hexdigest())

    def test_native_source_profile_and_pinned_vendor_chown_conditions(self):
        values = yaml.safe_load((prep.CHART / "kkamji_local_values.yaml").read_text())
        grafana = values["kube-prometheus-stack"]["grafana"]
        self.assertIs(values["grafanaPvcPreparation"], True)
        self.assertEqual(grafana["persistence"], {"enabled": True, "type": "pvc", "existingClaim": CLAIM,
                         "storageClassName": "local-path", "accessModes": ["ReadWriteOnce"], "size": "10Gi"})
        self.assertEqual(grafana["initChownData"], {"enabled": False})
        self.assertEqual(grafana["deploymentStrategy"], {"type": "Recreate", "rollingUpdate": None})
        self.assertEqual(grafana["replicas"], 1)
        self.assertEqual(grafana["admin"], {"existingSecret": "grafana-auth", "userKey": "admin-user", "passwordKey": "admin-password"})
        with tarfile.open(prep.CHART / "charts/kube-prometheus-stack-92.3.0.tgz") as archive:
            base = "kube-prometheus-stack/charts/grafana/"
            def read(name):
                member = archive.extractfile(base + name)
                assert member is not None
                return member.read().decode()
            defaults = yaml.safe_load(read("values.yaml"))
            metadata = yaml.safe_load(read("Chart.yaml"))
            pod = read("templates/_pod.tpl")
            pvc = read("templates/pvc.yaml")
            deployment = read("templates/deployment.yaml")
        self.assertEqual(metadata["version"], "13.5.0")
        self.assertEqual(metadata["appVersion"], "13.2.3")
        self.assertIs(defaults["initChownData"]["enabled"], True)
        self.assertEqual(defaults["initChownData"]["securityContext"]["runAsUser"], 0)
        self.assertIn('{{- if ( and .Values.persistence.enabled .Values.initChownData.enabled ) }}', pod)
        self.assertIn('{{- if and .Values.persistence.enabled (eq .Values.persistence.type "pvc") }}', pod)
        self.assertIn('claimName: {{ tpl (.Values.persistence.existingClaim | default (include "grafana.fullname" .)) . }}', pod)
        self.assertIn('(not .Values.persistence.existingClaim)', pvc)
        self.assertIn('(not .Values.useStatefulSet)', deployment)

    def test_active_guard_refuses_unsafe_values_and_arbitrary_claim_adoption(self):
        persistence = [
            ("enabled", False), ("enabled", "true"), ("enabled", None),
            ("existingClaim", "other"), ("existingClaim", "kube-prometheus-stack-grafana"),
            ("existingClaim", "test-release-grafana"), ("existingClaim", '{{ print "other" }}'),
            ("existingClaim", ""), ("existingClaim", None),
            ("storageClassName", "other"), ("storageClassName", None),
            ("size", "1Gi"), ("accessModes", ["ReadWriteMany"]),
            ("volumeName", "pv"), ("dataSource", {"name": "snapshot"}),
            ("selectorLabels", {"app": "other"}),
            ("annotations", {"argocd.argoproj.io/sync-options": "Delete=true"}),
            ("extraPvcLabels", {"adopt": "other"}), ("finalizers", []),
            ("type", "statefulset"), ("type", "sts"), ("type", "StatefulSet"),
            ("inMemory", {"enabled": True}), ("lookupVolumeName", False),
            ("subPath", "other"), ("extraStorageSurface", True),
        ]
        unsafe = [{"persistence": {key: value}} for key, value in persistence]
        unsafe += [{"enabled": False}, {"useStatefulSet": True}, {"namespaceOverride": "other"},
                   {"fullnameOverride": "other"}, {"nameOverride": "other"},
                   {"replicas": 2}, {"replicas": 0}, {"replicas": "1"},
                   {"autoscaling": {"enabled": True}},
                   {"deploymentStrategy": {"type": "RollingUpdate"}},
                   {"deploymentStrategy": {"type": "Recreate", "rollingUpdate": {"maxSurge": 0}}},
                   {"initChownData": {"enabled": True}}, {"initChownData": {"enabled": "false"}},
                   {"initChownData": {"enabled": None}}]
        for value in unsafe:
            with self.subTest(override=value):
                result = active_render({"kube-prometheus-stack": {"grafana": value}})
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Grafana PVC preparation:", result.stderr)
        for override in ({"grafanaPvcPreparation": False},
                         {"kube-prometheus-stack": {"namespaceOverride": "other"}}):
            self.assertNotEqual(active_render(override).returncode, 0)
        check_candidate(self)

    def test_release_helper_has_no_lint_bypass_or_wrong_canonical_adoption(self):
        for release in ("test-release", "offline-grafana"):
            objects = prep.documents(active_render(release=release))
            name = release if "grafana" in release else release + "-grafana"
            pvc_key = ("v1", "PersistentVolumeClaim", "monitoring", name)
            deployment_key = ("apps/v1", "Deployment", "monitoring", name)
            self.assertIn(pvc_key, objects.keys())
            storage = objects[deployment_key]["spec"]["template"]["spec"]["volumes"][2]
            self.assertEqual(storage, {"name": "storage", "persistentVolumeClaim": {"claimName": name}})
            self.assertNotIn(prep.PVC_KEY, objects.keys())
        result = active_render(namespace="other")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Grafana PVC preparation:", result.stderr)

    def test_unsafe_actual_source_and_unrelated_template_mutations_restore_positive(self):
        with tempfile.TemporaryDirectory(prefix="grafana-active-source-") as temporary:
            chart = Path(temporary) / prep.CHART.name
            shutil.copytree(prep.CHART, chart)
            values = chart / "kkamji_local_values.yaml"
            guard = chart / "templates/grafana-pvc-preparation.tpl"
            priority = chart / "templates/priorityclass.yaml"
            originals = {p: p.read_text() for p in (values, guard, priority)}
            mutations = [
                (values, "existingClaim: '" + CLAIM + "'", "existingClaim: other", 1),
                (values, "initChownData:\n      enabled: false", "initChownData:\n      enabled: true", 1),
                (values, "    admin:\n", "    env:\n      GF_SECURITY_SECRET_KEY: synthetic-offline-not-a-credential\n    admin:\n", 0),
                (guard, "Prune=false,Delete=false", "Prune=true,Delete=true", 0),
                (guard, "storageClassName: local-path", "storageClassName: other", 0),
                (priority, "globalDefault: false", "globalDefault: true", 0),
                (priority, "# 관측 스택", "# raw-only mutation 관측 스택", 0),
            ]
            for file, before, after, native_exit in mutations:
                with self.subTest(path=file.name, mutation=after):
                    self.assertEqual(originals[file].count(before), 1)
                    file.write_text(originals[file].replace(before, after, 1))
                    result = active_render(chart=chart, include_crds=True)
                    self.assertEqual(result.returncode, native_exit)
                    with self.assertRaises(AssertionError):
                        assert_active(self, result)
                    file.write_text(originals[file])
            check_candidate(self, chart)

    def test_pod_auth_crypto_resources_sidecars_and_init_changes_fail_whole_contract(self):
        unsafe = [
            {"env": {"GF_SECURITY_SECRET_KEY": "synthetic-offline-not-a-credential"}},
            {"grafana.ini": {"auth.generic_oauth": {"enabled": True}}},
            {"securityContext": {"runAsUser": 0}},
            {"containerSecurityContext": {"privileged": True}},
            {"image": {"tag": "other"}}, {"resources": {"requests": {"memory": "1Gi"}}},
            {"extraInitContainers": [{"name": "unsafe-extra-init", "image": "synthetic.invalid/fixture:1"}]},
            {"sidecar": {"resources": {"requests": {"cpu": "1m"}}}},
        ]
        for value in unsafe:
            with self.subTest(override=value):
                result = active_render({"kube-prometheus-stack": {"grafana": value}}, include_crds=True)
                self.assertEqual(result.returncode, 0)
                with self.assertRaises(AssertionError):
                    assert_active(self, result)
        check_candidate(self)

    def test_real_active_entry_point_failure_keeps_secret_data_private(self):
        with tempfile.TemporaryDirectory(prefix="grafana-active-privacy-") as temporary:
            chart = Path(temporary) / prep.CHART.name
            shutil.copytree(prep.CHART, chart)
            path = chart / "templates/priorityclass.yaml"
            original = path.read_text()
            path.write_text(original.replace("globalDefault: false", "globalDefault: true", 1))
            result = active_render(chart=chart, include_crds=True)
            self.assertEqual(result.returncode, 0)
            sensitive = [str(v) for obj in prep.documents(result).values() if obj["kind"] == "Secret"
                         for field in ("data", "stringData") for v in obj.get(field, {}).values() if v]
            self.assertTrue(sensitive, "real negative render must include nonempty Secret data")
            with self.assertRaises(AssertionError) as refusal:
                check_candidate(self, chart)
            self.assertFalse(any(v in str(refusal.exception) for v in sensitive),
                             "active entry-point refusal exposes rendered Secret data")
            path.write_text(original)
            check_candidate(self, chart)

    def test_lint_info_exit_zero_does_not_replace_actual_template_refusal(self):
        override = {"kube-prometheus-stack": {"grafana": {"initChownData": {"enabled": True}}}}
        with tempfile.TemporaryDirectory(prefix="grafana-active-lint-") as temporary:
            path = Path(temporary) / "unsafe.json"
            path.write_text(json.dumps(override))
            lint = prep.helm_command([prep.HELM, "lint", str(prep.CHART), "--strict", "-n", "monitoring",
                                      "--kube-version", "1.36.1", "-f", str(prep.CHART / "kkamji_local_values.yaml"),
                                      "-f", str(path)])
        self.assertIn("Grafana PVC preparation:", lint.stdout + lint.stderr)
        if lint.returncode == 0:
            self.assertIn("INFO", lint.stdout + lint.stderr)
        result = active_render(override)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Grafana PVC preparation:", result.stderr)


if __name__ == "__main__":
    unittest.main()
