import importlib.util
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch as mock_patch

ROOT = Path(__file__).resolve().parents[1]
HELM = os.environ.get("HELM_BINARY") or shutil.which("helm")


class ArcFullContractTests(unittest.TestCase):
    def render(self, flags=(), local=False, json_flags=(), values_file=None):
        self.assertIsNotNone(
            HELM, "Use the existing Helm; no network/dependency installation"
        )
        args = [
            HELM,
            "template",
            "arc-full",
            str(ROOT / "charts/arc-full"),
            "-n",
            "ci-full",
            "--skip-crds",
        ]
        if values_file:
            args += ["-f", values_file]
        if local:
            args += ["-f", str(ROOT / "charts/arc-full/kkamji_local_values.yaml")]
        for flag in flags:
            args += ["--set", flag]
        for flag in json_flags:
            args += ["--set-json", flag]
        return subprocess.run(args, capture_output=True, text=True, check=False)

    def test_default_auth_off(self):
        r = self.render()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("kind: ExternalSecret", r.stdout)
        self.assertEqual(r.stdout.count("maxRunners: 0"), 1)
        self.assertNotIn("kind: Secret\n", r.stdout)
        self.assertNotIn("binance-quant-lab", r.stdout)

    def test_auth_source_reuse_requires_confirmation(self):
        r = self.render(["githubAuth.enabled=true"])
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("ARC full auth", r.stderr)

    def test_local_uses_existing_source_and_opens_platform_pool_only(self):
        r = self.render(local=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        # App auth plus the runner image pull credential.
        self.assertEqual(r.stdout.count("kind: ExternalSecret"), 2)
        self.assertNotIn("kind: Secret\n", r.stdout)
        for text in [
            "/kkamji/arc/github-app",
            "creationPolicy: Orphan",
            "deletionPolicy: Retain",
            "type: kubernetes.io/dockerconfigjson",
            "/kkamji/personal/kkamji-platform/ghcr/pull-token",
        ]:
            self.assertIn(text, r.stdout)
        self.assertEqual(
            len(
                re.findall(
                    r"imagePullSecrets:\s*\n\s*- name: ghcr-pull-secret", r.stdout
                )
            ),
            1,
        )
        self.assertNotRegex(r.stdout, r"imagePullPolicy:\s*Never")
        self.assertNotIn("docker.io/library/arc-platform-", r.stdout)
        self.assertNotIn("binance-quant-lab", r.stdout)
        self.assertEqual(r.stdout.count("maxRunners: 0"), 0)
        self.assertEqual(r.stdout.count("maxRunners: 2"), 1)
        self.assertEqual(
            len(re.findall(r"workingDir:\s+/home/runner/_work(?:\s|$)", r.stdout)), 1
        )
        self.assertNotRegex(r.stdout, r"workingDir:\s+/home/runner(?:\s|$)")
        self.assertNotIn("kind: ClusterRole\n", r.stdout)

    def test_sized_slots_hold_one_platform_runner_per_worker(self):
        r = self.render(local=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        sets = [
            doc for doc in r.stdout.split("---") if "kind: AutoscalingRunnerSet" in doc
        ]
        self.assertEqual(len(sets), 1)
        doc = sets[0]
        self.assertIn("name: kkamji-platform-full\n", doc)
        self.assertRegex(
            doc,
            r"key: kubernetes.io/hostname\s+operator: In\s+values:\s+- k8s-w1\s+- k8s-w2",
        )
        self.assertNotIn("nodeSelector:\n        kubernetes.io/hostname: k8s-w2", doc)
        self.assertRegex(
            doc,
            r"podAntiAffinity:\s+requiredDuringSchedulingIgnoredDuringExecution:"
            r"\s+- labelSelector:\s+matchLabels:"
            r"\s+actions.github.com/scale-set-name: kkamji-platform-full"
            r"\s+app.kubernetes.io/component: runner"
            r"\s+topologyKey: kubernetes.io/hostname",
        )
        self.assertRegex(doc, r"limits:\s+cpu: \"4\"\s+memory: 3584Mi")
        self.assertRegex(doc, r"requests:\s+cpu: 500m\s+memory: 3584Mi")
        self.assertRegex(doc, r"name: ARC_POD_MEMORY_MIB\s+value: \"3584\"")
        quota = next(
            doc for doc in r.stdout.split("---") if "kind: ResourceQuota" in doc
        )
        # Quota admits exactly two Platform runners (3584Mi/16Gi each; 500m/4 CPU,
        # 2Gi ephemeral request each) plus controller, listener and rollout surge.
        for line in [
            'pods: "5"',
            "requests.cpu: 1400m",
            'limits.cpu: "10"',
            "requests.memory: 7680Mi",
            "limits.memory: 8Gi",
            "requests.ephemeral-storage: 5Gi",
            "limits.ephemeral-storage: 34Gi",
            'requests.kkamji.net/arc-tun: "2"',
        ]:
            self.assertIn(line, quota)
        runtime = (ROOT / "charts/arc-runtime/templates/runtime.yaml").read_text()
        self.assertIn('{"name":"arc-tun","groups":[{"count":2,', runtime)

    def test_platform_storage_budget_uses_twelve_gib_docker_data_and_sdk_four_gib(self):
        r = self.render(local=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        sets = [
            doc for doc in r.stdout.split("---") if "kind: AutoscalingRunnerSet" in doc
        ]
        platform = next(doc for doc in sets if "name: kkamji-platform-full" in doc)
        self.assertRegex(platform, r"sizeLimit:\s+12Gi")
        self.assertRegex(platform, r"ephemeral-storage:\s+12Gi")
        self.assertRegex(platform, r"name: ARC_JOB_EPHEMERAL_GIB\s+value: ['\"]?16")
        self.assertRegex(platform, r"ephemeral-storage:\s+4Gi")
        self.assertRegex(platform, r"emptyDir:\s+sizeLimit: 512Mi\s+name: daemon-tmp")
        self.assertNotIn("medium: Memory", platform)
        self.assertNotRegex(platform, r"sizeLimit:\s+30Gi")
        self.assertIn("limits.ephemeral-storage: 34Gi", r.stdout)

    def test_platform_rejects_mismatched_docker_storage_budgets(self):
        values = (ROOT / "charts/arc-full/values.yaml").read_text()
        cases = [
            ("sizeLimit: 12Gi", "sizeLimit: 7Gi", "private Docker data must match"),
            ("sizeLimit: 12Gi", "sizeLimit: 30Gi", "private Docker data must match"),
            ("ephemeral-storage: 12Gi", "ephemeral-storage: 7Gi", "pool Docker budget"),
            (
                "name: ARC_JOB_EPHEMERAL_GIB\n          value: '16'",
                "name: ARC_JOB_EPHEMERAL_GIB\n          value: '11'",
                "startup budget",
            ),
            (
                "name: ARC_JOB_EPHEMERAL_GIB\n          value: '16'",
                "name: ARC_JOB_EPHEMERAL_GIB\n          value: '34'",
                "startup budget",
            ),
        ]
        for old, new, message in cases:
            with self.subTest(old=old, new=new):
                self.assertEqual(values.count(old), 1, old)
                with tempfile.NamedTemporaryFile("w", suffix=".yaml") as f:
                    f.write(values.replace(old, new))
                    f.flush()
                    r = self.render(flags=(), values_file=f.name)
                self.assertNotEqual(r.returncode, 0)
                self.assertIn("ARC full boundary", r.stderr)
                self.assertIn(message, r.stderr)

    def test_platform_budget_requires_one_literal_value(self):
        values = (ROOT / "charts/arc-full/values.yaml").read_text()
        image = re.search(r"&fullRunnerSDK\s+name: runner\s+image: (\S+)", values)
        self.assertIsNotNone(image)
        assert image is not None
        sdk = {
            "name": "runner",
            "image": image.group(1),
            "securityContext": {
                "runAsUser": 1001,
                "procMount": "Default",
                "allowPrivilegeEscalation": False,
                "readOnlyRootFilesystem": True,
                "capabilities": {"drop": ["ALL"], "add": []},
                "seccompProfile": {"type": "RuntimeDefault"},
            },
            "resources": {"limits": {"ephemeral-storage": "4Gi"}},
            "env": [
                {"name": "ARC_JOB_EPHEMERAL_GIB", "value": "16"},
                {"name": "ARC_POD_MEMORY_MIB", "value": "3584"},
            ],
        }
        literal = self.render(
            json_flags=["platform.template.spec.containers=" + json.dumps([sdk])]
        )
        self.assertEqual(literal.returncode, 0, literal.stderr)
        sdk["env"][0]["valueFrom"] = {
            "secretKeyRef": {"name": "not-read", "key": "unused"}
        }
        r = self.render(
            json_flags=["platform.template.spec.containers=" + json.dumps([sdk])]
        )
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("ARC full boundary", r.stderr)
        budget = {"name": "ARC_JOB_EPHEMERAL_GIB", "value": "16"}
        memory = {"name": "ARC_POD_MEMORY_MIB", "value": "3584"}
        for invalid in [
            [memory],
            [{**budget, "value": "11"}, {**budget, "value": "16"}, memory],
            [budget, budget, memory],
            [budget],
            [budget, {**memory, "value": "7168"}],
            [budget, memory, memory],
        ]:
            sdk["env"] = invalid
            r = self.render(
                json_flags=["platform.template.spec.containers=" + json.dumps([sdk])]
            )
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("ARC full boundary", r.stderr)

    def test_previously_excluded_or_outside_role_overrides_fail_closed(self):
        mutations = [
            "platform.template.spec.hostUsers=true",
            "platform.template.spec.hostPID=true",
            "platform.template.spec.containers[0].securityContext.procMount=Unmasked",
            "platform.template.spec.containers[0].securityContext.allowPrivilegeEscalation=true",
            "platform.template.spec.initContainers[1].securityContext.capabilities.add[3]=SYS_ADMIN",
            "platform.template.spec.resources.limits.memory=6Gi",
            "platform.template.spec.resources.requests.memory=5Gi",
            "platform.template.spec.containers[0].env[8].value=7168",
            "platform.template.spec.automountServiceAccountToken=true",
            "platform.template.spec.initContainers[1].resources.limits.ephemeral-storage=14Gi",
            "platform.template.spec.containers[0].resources.limits.ephemeral-storage=6Gi",
            "platform.template.spec.volumes[6].emptyDir.sizeLimit=20Gi",
            "platform.template.spec.containers[0].env[7].value=11",
            "platform.template.spec.containers[0].env[7].name=UNEXPECTED",
            "platform.template.spec.containers[0].env[8].name=ARC_JOB_EPHEMERAL_GIB",
            "platform.template.spec.volumes[6].emptyDir.sizeLimit=7Gi",
            "platform.template.spec.initContainers[1].resources.limits.ephemeral-storage=7Gi",
        ]
        for flag in mutations:
            with self.subTest(flag=flag):
                r = self.render([flag])
                self.assertNotEqual(r.returncode, 0)
                self.assertIn("ARC full boundary", r.stderr)

    def test_cilium_default_deny_policies_use_valid_empty_rule_objects(self):
        import yaml

        full = self.render(local=True)
        self.assertEqual(full.returncode, 0, full.stderr)
        full_docs = [d for d in yaml.safe_load_all(full.stdout) if d]
        full_deny = next(
            d
            for d in full_docs
            if d["kind"] == "CiliumNetworkPolicy"
            and d["metadata"]["name"] == "full-default-deny"
        )
        self.assertEqual(full_deny["spec"]["ingress"], [{}])
        self.assertEqual(full_deny["spec"]["egress"], [{}])

        rt = subprocess.run(
            [
                HELM,
                "template",
                "arc-runtime",
                str(ROOT / "charts/arc-runtime"),
                "-n",
                "arc-runtime",
                "-f",
                str(ROOT / "charts/arc-runtime/kkamji_local_values.yaml"),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(rt.returncode, 0, rt.stderr)
        rt_docs = [d for d in yaml.safe_load_all(rt.stdout) if d]
        rt_deny = next(
            d
            for d in rt_docs
            if d["kind"] == "CiliumNetworkPolicy"
            and d["metadata"]["name"] == "runtime-no-network"
        )
        self.assertEqual(rt_deny["spec"]["ingress"], [{}])
        self.assertEqual(rt_deny["spec"]["egress"], [{}])


class DiskReserveTests(unittest.TestCase):
    def test_memory_guard_holds_the_pool_pod_budget_plus_one_gib(self):
        spec = importlib.util.spec_from_file_location(
            "sdk_entry", ROOT / "charts/arc-full/files/sdk-entry.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        mib = 1024**2
        self.assertEqual(module.memory_required_bytes(3584), 4608 * mib)
        # Pods from the previous template carry no env and keep the old 6GiB guard.
        self.assertEqual(module.memory_required_bytes(), 6144 * mib)
        for unsupported in (0, 1024, 4096, 7168, 8192):
            with self.assertRaises(ValueError):
                module.memory_required_bytes(unsupported)

    def test_start_guard_accepts_every_rendered_pool_budget(self):
        # helm-charts #47 set Platform to 11 while sdk-entry.py accepted only
        # 16/34, so every Platform runner crash-looped at start.
        spec = importlib.util.spec_from_file_location(
            "sdk_entry", ROOT / "charts/arc-full/files/sdk-entry.py"
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        r = ArcFullContractTests.render(self, local=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        sets = [
            doc for doc in r.stdout.split("---") if "kind: AutoscalingRunnerSet" in doc
        ]
        self.assertEqual(len(sets), 1)
        gib = 1024**3
        for doc in sets:
            disk = re.search(r"name: ARC_JOB_EPHEMERAL_GIB\s+value: ['\"]?(\d+)", doc)
            memory = re.search(r"name: ARC_POD_MEMORY_MIB\s+value: ['\"]?(\d+)", doc)
            self.assertIsNotNone(disk)
            self.assertIsNotNone(memory)
            module.disk_required_bytes(155 * gib, int(disk.group(1)))
            module.memory_required_bytes(int(memory.group(1)))

    def test_disk_guard_retains_job_budget_and_imagefs_margin(self):
        spec = importlib.util.spec_from_file_location(
            "sdk_entry", ROOT / "charts/arc-full/files/sdk-entry.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        gib = 1024**3
        self.assertEqual(module.disk_required_bytes(100 * gib, 16), 32 * gib)
        self.assertEqual(module.disk_required_bytes(20 * gib, 16), 21 * gib)
        # Rolling rollout compatibility with the previous 11Gi Platform template.
        self.assertEqual(module.disk_required_bytes(100 * gib, 11), 27 * gib)
        self.assertEqual(module.disk_required_bytes(20 * gib, 11), 16 * gib)
        for unsupported in (0, 15, 20, 30, 34, 35):
            with self.assertRaises(ValueError):
                module.disk_required_bytes(100 * gib, unsupported)

    def test_runtime_has_bounded_platform_private_data(self):
        text = (ROOT / "charts/arc-full/values.yaml").read_text()
        self.assertNotIn("sizeLimit: 30Gi", text)
        self.assertNotIn("sizeLimit: 7Gi", text)
        self.assertEqual(text.count("sizeLimit: 12Gi"), 1)
        self.assertIn(
            "limits.ephemeral-storage: 34Gi",
            (ROOT / "charts/arc-full/templates/foundation.yaml").read_text(),
        )


class RuntimePinnedCliTests(unittest.TestCase):
    def test_runtime_uses_actual_pinned_plugin_listen_flag(self):
        r = subprocess.run(
            [
                HELM,
                "template",
                "arc-runtime",
                str(ROOT / "charts/arc-runtime"),
                "-n",
                "arc-runtime",
                "-f",
                str(ROOT / "charts/arc-runtime/kkamji_local_values.yaml"),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("--listen=:8080", r.stdout)
        self.assertNotIn("--listen-address", r.stdout)


class TrustedStartupReadinessTests(unittest.TestCase):
    def module(self):
        spec = importlib.util.spec_from_file_location(
            "trusted_runtime", ROOT / "charts/arc-full/files/trusted-runtime.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_bql_private_scratch_is_removed(self):
        source = (ROOT / "charts/arc-full/files/trusted-runtime.py").read_text()
        self.assertNotIn("arc-bql-scratch", source)

    def test_stale_ready_file_does_not_hide_failed_daemon(self):
        module = self.module()
        response = subprocess.CompletedProcess([], 1, stdout="", stderr="unreachable")
        with (
            mock_patch.object(module.sys, "argv", ["runtime", "--check-ready"]),
            mock_patch.object(module.Path, "exists", return_value=True),
            mock_patch.object(module.subprocess, "run", return_value=response),
        ):
            self.assertEqual(module.main(), 1)

    def test_startup_requires_rootless_not_any_daemon(self):
        module = self.module()
        response = subprocess.CompletedProcess(
            [], 0, stdout='["name=seccomp"]', stderr=""
        )
        with (
            mock_patch.object(module.sys, "argv", ["runtime", "--check-ready"]),
            mock_patch.object(module.Path, "exists", return_value=True),
            mock_patch.object(module.subprocess, "run", return_value=response),
        ):
            self.assertEqual(module.main(), 1)


if __name__ == "__main__":
    unittest.main()
