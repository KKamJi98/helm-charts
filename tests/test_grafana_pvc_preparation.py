"""Offline PVC preparation only; no backup, binding, copy or decryption proof."""
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from unittest import mock

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "charts/kube-prometheus-stack"
HELM = os.environ.get("HELM_BIN", "")


class HelmLoader(yaml.SafeLoader):
    """Pinned CRDs contain the unquoted enum scalar '='; keep loading safe."""


HelmLoader.add_constructor("tag:yaml.org,2002:value", HelmLoader.construct_scalar)

# Explicit legacy source fixture: these four native settings did not exist in
# prepared local values. Remove them only from that input fixture, never from
# an active render/result. Helm 4 retains null for absent upstream keys, so a
# null overlay cannot represent the original pinned persistence defaults.
PREPARED_KEYS = ("persistence", "deploymentStrategy", "initChownData", "replicas")


def helm_command(command):
    result = subprocess.run(command, capture_output=True, text=True, timeout=90)
    # Optional evidence sink: never write a render, even for failed entry points.
    if path := os.environ.get("GRAFANA_PVC_EVENTS"):
        with Path(path).open("a") as stream:
            stream.write(json.dumps({"argv": command, "native_exit": result.returncode,
                                    "stdout_sha256": hashlib.sha256(result.stdout.encode()).hexdigest(),
                                    "stderr_sha256": hashlib.sha256(result.stderr.encode()).hexdigest()}) + "\n")
    return result


PVC_KEY = ("v1", "PersistentVolumeClaim", "monitoring", "kube-prometheus-stack-grafana")
EXPECTED_PVC = {
    "apiVersion": "v1", "kind": "PersistentVolumeClaim",
    "metadata": {"name": "kube-prometheus-stack-grafana", "namespace": "monitoring",
                 "annotations": {"argocd.argoproj.io/sync-options": "Prune=false,Delete=false"}},
    "spec": {"accessModes": ["ReadWriteOnce"], "storageClassName": "local-path",
             "resources": {"requests": {"storage": "10Gi"}}},
}


def render(override=None, local=True, chart=CHART, release="kube-prometheus-stack", namespace="monitoring",
           prepared=True, include_crds=False):
    """Legacy tests explicitly render preparation; activation opts out of that fixture."""
    command = [HELM, "template", release, str(chart), "-n", namespace,
               "--kube-version", "1.36.1", "--skip-tests"]
    if include_crds:
        command += ["--include-crds"]
    with tempfile.TemporaryDirectory(prefix="grafana-pvc-") as temporary:
        if local:
            path = chart / "kkamji_local_values.yaml"
            if prepared:
                source = yaml.safe_load(path.read_text())
                grafana = source["kube-prometheus-stack"]["grafana"]
                for key in PREPARED_KEYS:
                    grafana.pop(key, None)
                path = Path(temporary) / "legacy-prepared.yaml"
                path.write_text(yaml.safe_dump(source))
            command += ["-f", str(path)]
        if override is not None:
            path = Path(temporary) / "override.json"
            path.write_text(json.dumps(override))
            command += ["-f", str(path)]
        return helm_command(command)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def load_documents(text):
    try:
        return list(yaml.load_all(text, Loader=HelmLoader))
    except yaml.YAMLError:
        raise AssertionError("Helm YAML parse refused (render withheld)") from None


def documents(result):
    if result.returncode:
        raise AssertionError("Helm render refused (stderr sha256=" + hashlib.sha256(result.stderr.encode()).hexdigest() + ")")
    objects = {}
    for obj in load_documents(result.stdout):
        if not obj:
            continue
        key = (obj["apiVersion"], obj["kind"], obj["metadata"].get("namespace", ""), obj["metadata"]["name"])
        if key in objects:
            raise AssertionError("duplicate rendered identity: " + repr(key))
        objects[key] = obj
    return objects


# Immutable base 7b83ff9a53d4b705422feb1c2b4e98f7bb6e64dc, real Helm 4.2.1.
# Default admin-password and its Pod checksum are random upstream. Only the
# default comparison uses a synthetic existingSecret reference; local uses the
# actual source values, including the unchanged grafana-auth reference.
FIXTURE = {"kube-prometheus-stack": {"grafana": {"admin": {"existingSecret": "grafana-pvc-offline-existing-admin"}}}}
GOLDENS = {
    False: (122, "4234c4430b0cebdb257b2dedd14a9718e9d7ae77b5380c72970788896da7c329",
            "3a513c8cf0ad1ccf56ca2596bf8270260c3f704ecb85c6c84ff73abf96e0e4d5",
            "ae17b0bc4b061b6329556965499d2ebd5b787843cc234dc64fb69755e1f14764",
            "d17e5da20c035dfcc13295337b7876f4d5146f881e2aa9a8919ece19439f943f"),
    True: (130, "999cba88bde24dd76912194c09a0463c3f67d8f0e01653e132b8afc85b6f3ac2",
           "bd8eb5fcda2fe14aa4db30eaf975f37a78f05385faca3485428bf56b53fd5aa4",
           "ef15c97feb93c63a8496da3cf883a3daa3d48ba08a51231b8d9f6976f19ea74b",
           "103bcdaae13906fec828674f5023a94a5d0a6cd466442632906e401fc5d85b11"),
}
GRAFANA_KEY = ("apps/v1", "Deployment", "monitoring", "kube-prometheus-stack-grafana")


def raw_documents(result):
    objects = documents(result)
    raw = {}
    for chunk in re.split(r"(?m)^---\s*\n", result.stdout):
        parsed = load_documents(chunk)
        obj = parsed[0] if parsed else None
        if not obj:
            continue
        key = (obj["apiVersion"], obj["kind"], obj["metadata"].get("namespace", ""), obj["metadata"]["name"])
        raw[key] = chunk
    return objects, raw


def assert_preserved(case, result, local, enabled):
    objects, raw = raw_documents(result)
    if enabled:
        case.assertIn(PVC_KEY, objects.keys())
        case.assertEqual(objects.pop(PVC_KEY), EXPECTED_PVC)
        raw.pop(PVC_KEY)
    else:
        case.assertNotIn(PVC_KEY, objects.keys())
    count, spec_hash, raw_hash, deployment_hash, pod_hash = GOLDENS[local]
    case.assertEqual(len(objects), count)
    # Fixed whole-object oracle, not selected-field or mutable-values equality.
    case.assertEqual(digest([objects[k] for k in sorted(objects)]), spec_hash)
    non_secret_raw = [(k, raw[k]) for k in sorted(raw) if k[1] != "Secret"]
    case.assertEqual(hashlib.sha256(json.dumps(non_secret_raw, separators=(",", ":")).encode()).hexdigest(), raw_hash)
    deployment = objects[GRAFANA_KEY]
    case.assertEqual(digest(deployment), deployment_hash)
    case.assertEqual(digest(deployment["spec"]["template"]), pod_hash)
    pod = deployment["spec"]["template"]["spec"]
    case.assertEqual(next(v for v in pod["volumes"] if v["name"] == "storage"), {"name": "storage", "emptyDir": {}})
    case.assertFalse(any("persistentVolumeClaim" in v for v in pod["volumes"]))
    grafana = next(c for c in pod["containers"] if c["name"] == "grafana")
    case.assertTrue(grafana["image"].endswith(":13.2.3-distroless"))
    case.assertIn({"name": "storage", "mountPath": "/var/lib/grafana"}, grafana["volumeMounts"])
    return objects, raw


class GrafanaPvcPreparationTests(unittest.TestCase):
    def test_enabled_adds_exactly_one_fixed_preparation_pvc(self):
        before = documents(render({"grafanaPvcPreparation": False}))
        after = documents(render({"grafanaPvcPreparation": True}))
        self.assertEqual(set(after) - set(before), {PVC_KEY})
        self.assertEqual(set(before) - set(after), set())
        self.assertEqual(after.pop(PVC_KEY), EXPECTED_PVC)
        # Hash equality avoids dumping any rendered Secret on a regression.
        self.assertEqual(digest(list(after.values())), digest(list(before.values())))

    def test_fixed_whole_monitoring_and_raw_body_contract_for_both_profiles(self):
        for local in (False, True):
            previous = None
            for enabled in (False, True):
                with self.subTest(local=local, enabled=enabled):
                    override: dict = {} if local else copy.deepcopy(FIXTURE)
                    override["grafanaPvcPreparation"] = enabled
                    current = assert_preserved(self, render(override, local=local), local, enabled)
                    if previous is not None:
                        for before, after in zip(previous, current):
                            self.assertEqual(digest([(k, before[k]) for k in sorted(before)]),
                                             digest([(k, after[k]) for k in sorted(after)]))
                    previous = current

    def test_default_disabled_local_opt_in_and_upstream_capacity(self):
        self.assertEqual(yaml.safe_load((CHART / "values.yaml").read_text()),
                         {"kube-prometheus-stack": {}, "grafanaPvcPreparation": False})
        self.assertIs(yaml.safe_load((CHART / "kkamji_local_values.yaml").read_text())["grafanaPvcPreparation"], True)
        self.assertNotIn(PVC_KEY, documents(render(local=False)).keys())
        self.assertEqual(documents(render())[PVC_KEY], EXPECTED_PVC)
        with tarfile.open(CHART / "charts/kube-prometheus-stack-92.3.0.tgz") as archive:
            member = archive.extractfile("kube-prometheus-stack/charts/grafana/values.yaml")
            assert member is not None
            upstream = yaml.safe_load(member)
        self.assertEqual(upstream["persistence"]["size"], "10Gi")
        self.assertIs(upstream["persistence"]["enabled"], False)
        self.assertEqual(upstream["persistence"]["accessModes"], ["ReadWriteOnce"])

    def test_preparation_boundary_rejects_non_boolean_and_extra_surfaces(self):
        unsafe = [None, "true", "false", 0, 1, [], {}, {"enabled": True},
                  {"storageClassName": "other"}, {"name": "other"},
                  {"size": "1Gi"}, {"dataSource": {"name": "snapshot"}},
                  {"accessModes": ["ReadWriteMany"]},
                  {"annotations": {"argocd.argoproj.io/sync-options": "Delete=true"}}]
        for value in unsafe:
            with self.subTest(value=value):
                result = render({"grafanaPvcPreparation": value})
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("only boolean grafanaPvcPreparation", result.stderr)

    def test_enabled_refuses_persistence_activation_or_unsafe_overrides(self):
        unsafe = [{"persistence": {key: value}} for key, value in [
            ("enabled", True), ("existingClaim", "other"), ("storageClassName", "other"),
            ("size", "1Gi"), ("accessModes", ["ReadWriteMany"]), ("volumeName", "pv"),
            ("dataSource", {"name": "snapshot"}), ("selectorLabels", {"app": "other"}),
            ("annotations", {"argocd.argoproj.io/sync-options": "Delete=true"}),
            ("extraPvcLabels", {"adopt": "other"}), ("finalizers", []),
            ("type", "statefulset"), ("inMemory", {"enabled": True}),
        ]]
        unsafe += [{"enabled": False}, {"useStatefulSet": True}, {"namespaceOverride": "other"},
                   {"fullnameOverride": "other"}, {"nameOverride": "other"}]
        for value in unsafe:
            with self.subTest(override=value):
                result = render({"grafanaPvcPreparation": True, "kube-prometheus-stack": {"grafana": value}})
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Grafana PVC preparation:", result.stderr)
        result = render({"kube-prometheus-stack": {"namespaceOverride": "other"}})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Grafana PVC preparation:", result.stderr)
        self.assertNotEqual(render(namespace="other").returncode, 0)

    def test_identity_uses_native_release_helper_including_actual_lint_release(self):
        # Helm lint supplies its own release name. No IsLint/test-release bypass.
        objects = documents(render(release="test-release"))
        pvc = objects[("v1", "PersistentVolumeClaim", "monitoring", "test-release-grafana")]
        deployment = objects[("apps/v1", "Deployment", "monitoring", "test-release-grafana")]
        self.assertEqual(pvc["metadata"]["name"], deployment["metadata"]["name"])
        self.assertEqual(pvc["metadata"]["namespace"], deployment["metadata"]["namespace"])
        self.assertNotIn(PVC_KEY, objects.keys())

    def test_real_helm_strict_lint_default_and_local(self):
        for local in (False, True):
            with self.subTest(local=local):
                args = [HELM, "lint", str(CHART), "--strict", "-n", "monitoring", "--kube-version", "1.36.1"]
                if local:
                    args += ["-f", str(CHART / "kkamji_local_values.yaml")]
                result = helm_command(args)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_pvc_presence_refusals_do_not_include_rendered_secret_data(self):
        for rendered, expected in ((False, True), (True, False)):
            with self.subTest(rendered=rendered, expected=expected):
                result = render({"grafanaPvcPreparation": rendered})
                objects = documents(result)
                sensitive = [str(value) for obj in objects.values() if obj["kind"] == "Secret"
                             for field in ("data", "stringData")
                             for value in obj.get(field, {}).values() if value]
                self.assertTrue(sensitive, "fixture must include rendered Secret data")
                with self.assertRaises(AssertionError) as refusal:
                    assert_preserved(self, result, True, expected)
                self.assertFalse(any(value in str(refusal.exception) for value in sensitive),
                                 "PVC presence refusal exposes rendered Secret data")

    def test_entry_point_refusals_do_not_include_rendered_secret_data(self):
        methods = (
            ("test_default_disabled_local_opt_in_and_upstream_capacity", "unconditional"),
            ("test_identity_uses_native_release_helper_including_actual_lint_release", "extra-canonical"),
        )
        real_render = render
        for method, mutation in methods:
            with self.subTest(method=method), tempfile.TemporaryDirectory(prefix="grafana-pvc-diagnostic-") as temporary:
                chart = Path(temporary) / CHART.name
                shutil.copytree(CHART, chart)
                template = chart / "templates/grafana-pvc-preparation.tpl"
                if mutation == "unconditional":
                    original = template.read_text()
                    marker = "{{- if .Values.grafanaPvcPreparation -}}"
                    self.assertEqual(original.count(marker), 1)
                    template.write_text(original.replace(marker, "{{- if true -}}", 1))
                else:
                    (chart / "templates/diagnostic-extra-pvc.yaml").write_text(yaml.safe_dump(EXPECTED_PVC))
                sensitive = []
                native_exits = []

                def fixture_render(*args, **kwargs):
                    kwargs["chart"] = chart
                    result = real_render(*args, **kwargs)
                    native_exits.append(result.returncode)
                    if result.returncode == 0:
                        sensitive.extend(str(value) for obj in documents(result).values()
                                         if obj["kind"] == "Secret" for field in ("data", "stringData")
                                         for value in obj.get(field, {}).values() if value)
                    return result

                with mock.patch(__name__ + ".CHART", chart), mock.patch(__name__ + ".render", fixture_render):
                    with self.assertRaises(AssertionError) as refusal:
                        getattr(GrafanaPvcPreparationTests(method), method)()
                self.assertEqual(native_exits, [0])
                self.assertTrue(sensitive, "actual refused render must include nonempty Secret data")
                self.assertFalse(any(value in str(refusal.exception) for value in sensitive),
                                 "test entry-point refusal exposes rendered Secret data")

    def test_contract_detects_unsafe_source_mutations_and_positive_control(self):
        with tempfile.TemporaryDirectory(prefix="grafana-pvc-source-") as temporary:
            chart = Path(temporary) / CHART.name
            shutil.copytree(CHART, chart)
            template = chart / "templates/grafana-pvc-preparation.tpl"
            original = template.read_text()
            for old, new in [("storageClassName: local-path", "storageClassName: other"),
                             ("Prune=false,Delete=false", "Prune=true,Delete=true"),
                             ("{{- if .Values.grafanaPvcPreparation -}}", "{{- if true -}}")]:
                with self.subTest(mutation=new):
                    self.assertIn(old, original)
                    template.write_text(original.replace(old, new, 1))
                    enabled = False if "if true" in new else True
                    with self.assertRaises(AssertionError):
                        assert_preserved(self, render({"grafanaPvcPreparation": enabled}, chart=chart), True, enabled)
            template.write_text(original)
            assert_preserved(self, render(chart=chart), True, True)


if __name__ == "__main__":
    unittest.main()
