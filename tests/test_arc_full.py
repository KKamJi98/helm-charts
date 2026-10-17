import importlib.util
import json
import os
import re
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch as mock_patch

ROOT = Path(__file__).resolve().parents[1]
HELM = os.environ.get("HELM_BINARY") or shutil.which("helm")


class ArcFullContractTests(unittest.TestCase):
    def render(self, flags=(), local=False, json_flags=()):
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
        self.assertEqual(r.stdout.count("maxRunners: 0"), 2)
        self.assertNotIn("kind: Secret\n", r.stdout)

    def test_auth_source_reuse_requires_confirmation(self):
        r = self.render(["githubAuth.enabled=true"])
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("ARC full auth", r.stderr)

    def test_local_uses_existing_source_and_opens_qualified_repository_pools(self):
        r = self.render(local=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.count("kind: ExternalSecret"), 1)
        self.assertNotIn("kind: Secret\n", r.stdout)
        for text in [
            "/kkamji/arc/github-app",
            "creationPolicy: Orphan",
            "deletionPolicy: Retain",
        ]:
            self.assertIn(text, r.stdout)
        self.assertEqual(r.stdout.count("maxRunners: 0"), 0)
        self.assertEqual(r.stdout.count("maxRunners: 1"), 2)
        self.assertEqual(
            len(re.findall(r"workingDir:\s+/home/runner/_work(?:\s|$)", r.stdout)), 2
        )
        self.assertNotRegex(r.stdout, r"workingDir:\s+/home/runner(?:\s|$)")
        self.assertNotIn("kind: ClusterRole\n", r.stdout)

    def test_bql_storage_growth_keeps_platform_template_and_sdk_budget(self):
        r = self.render(local=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        sets = [
            doc for doc in r.stdout.split("---") if "kind: AutoscalingRunnerSet" in doc
        ]
        bql = next(doc for doc in sets if "name: binance-quant-lab-full" in doc)
        platform = next(doc for doc in sets if "name: kkamji-platform-full" in doc)
        self.assertRegex(bql, r"sizeLimit:\s+16Gi")
        self.assertRegex(bql, r"ephemeral-storage:\s+16Gi")
        self.assertRegex(bql, r"name: ARC_JOB_EPHEMERAL_GIB\s+value: ['\"]?20")
        self.assertRegex(bql, r"ephemeral-storage:\s+4Gi")
        self.assertRegex(platform, r"sizeLimit:\s+12Gi")
        self.assertNotIn("ARC_JOB_EPHEMERAL_GIB", platform)
        self.assertIn("limits.ephemeral-storage: 22Gi", r.stdout)

    def test_bql_private_scratch_is_disk_backed_within_same_twenty_gib(self):
        r = self.render(local=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        bql = next(
            doc
            for doc in r.stdout.split("---")
            if "kind: AutoscalingRunnerSet" in doc
            and "name: binance-quant-lab-full" in doc
        )
        self.assertRegex(bql, r"emptyDir:\s+sizeLimit: 3Gi\s+name: daemon-tmp")
        self.assertNotIn("medium: Memory", bql)
        self.assertIn('value: "20"', bql)
        self.assertIn("limits.ephemeral-storage: 22Gi", r.stdout)

    def test_bql_budget_requires_one_literal_twenty_gib_value(self):
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
            "env": [{"name": "ARC_JOB_EPHEMERAL_GIB", "value": "20"}],
        }
        literal = self.render(
            json_flags=["bql.template.spec.containers=" + json.dumps([sdk])]
        )
        self.assertEqual(literal.returncode, 0, literal.stderr)
        sdk["env"][0]["valueFrom"] = {
            "secretKeyRef": {"name": "not-read", "key": "unused"}
        }
        r = self.render(
            json_flags=["bql.template.spec.containers=" + json.dumps([sdk])]
        )
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("ARC full boundary", r.stderr)
        budget = {"name": "ARC_JOB_EPHEMERAL_GIB", "value": "20"}
        for invalid in [[], [{**budget, "value": "16"}], [budget, budget]]:
            sdk["env"] = invalid
            r = self.render(
                json_flags=["bql.template.spec.containers=" + json.dumps([sdk])]
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
            "bql.template.spec.automountServiceAccountToken=true",
            "platform.template.spec.initContainers[1].resources.limits.ephemeral-storage=14Gi",
            "platform.template.spec.containers[0].resources.limits.ephemeral-storage=6Gi",
            "platform.template.spec.volumes[6].emptyDir.sizeLimit=20Gi",
            "bql.template.spec.initContainers[1].resources.limits.ephemeral-storage=18Gi",
            "bql.template.spec.containers[0].env[7].value=16",
            "bql.template.spec.containers[0].env[7].name=UNEXPECTED",
            "bql.template.spec.containers[0].env[8].name=ARC_JOB_EPHEMERAL_GIB",
            "bql.template.spec.volumes[6].emptyDir.sizeLimit=20Gi",
            "platform.template.spec.containers[0].env[7].name=ARC_JOB_EPHEMERAL_GIB",
        ]
        for flag in mutations:
            with self.subTest(flag=flag):
                r = self.render([flag])
                self.assertNotEqual(r.returncode, 0)
                self.assertIn("ARC full boundary", r.stderr)


class DiskReserveTests(unittest.TestCase):
    def test_bql_twenty_gib_budget_retains_full_pressure_margin(self):
        spec = importlib.util.spec_from_file_location(
            "sdk_entry", ROOT / "charts/arc-full/files/sdk-entry.py"
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        gib = 1024**3
        self.assertEqual(module.disk_required_bytes(100 * gib, 20), 36 * gib)
        self.assertEqual(module.disk_required_bytes(20 * gib, 20), 25 * gib)
        for unsupported in (0, 15, 19, 21):
            with self.assertRaises(ValueError):
                module.disk_required_bytes(100 * gib, unsupported)

    def test_disk_guard_retains_job_budget_and_imagefs_margin(self):
        spec = importlib.util.spec_from_file_location(
            "sdk_entry", ROOT / "charts/arc-full/files/sdk-entry.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        gib = 1024**3
        required = module.disk_required_bytes(100 * gib)
        self.assertEqual(required, 32 * gib)
        self.assertGreater(required, 25 * gib)
        self.assertEqual(module.disk_required_bytes(20 * gib), 21 * gib)

    def test_runtime_has_bounded_twelve_gib_private_data(self):
        text = (ROOT / "charts/arc-full/values.yaml").read_text()
        self.assertIn("sizeLimit: 12Gi", text)
        self.assertIn("ephemeral-storage: 12Gi", text)
        self.assertIn(
            "limits.ephemeral-storage: 22Gi",
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

    def test_private_scratch_is_sticky_and_restart_preserves_caller_data(self):
        import tempfile

        module = self.module()
        with tempfile.TemporaryDirectory() as parent:
            path = Path(parent) / "private-scratch"
            module.prepare_private_scratch(path)
            self.assertEqual(path.stat().st_mode & 0o7777, 0o1777)
            self.assertEqual(path.stat().st_uid, os.getuid())
            sentinel = path / "caller-data"
            sentinel.write_text("preserve")
            module.prepare_private_scratch(path)
            self.assertEqual(sentinel.read_text(), "preserve")

    def test_private_scratch_rejects_symlink_without_changing_target(self):
        import tempfile

        module = self.module()
        with tempfile.TemporaryDirectory() as parent:
            target = Path(parent) / "target"
            target.mkdir(mode=0o700)
            link = Path(parent) / "private-scratch"
            link.symlink_to(target, target_is_directory=True)
            with self.assertRaises(OSError):
                module.prepare_private_scratch(link)
            self.assertEqual(target.stat().st_mode & 0o7777, 0o700)

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
