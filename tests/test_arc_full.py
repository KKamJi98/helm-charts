import importlib.util
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
    def render(self, flags=(), local=False):
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

    def test_previously_excluded_or_outside_role_overrides_fail_closed(self):
        mutations = [
            "platform.template.spec.hostUsers=true",
            "platform.template.spec.hostPID=true",
            "platform.template.spec.containers[0].securityContext.procMount=Unmasked",
            "platform.template.spec.containers[0].securityContext.allowPrivilegeEscalation=true",
            "platform.template.spec.initContainers[1].securityContext.capabilities.add[3]=SYS_ADMIN",
            "platform.template.spec.resources.limits.memory=6Gi",
            "bql.template.spec.automountServiceAccountToken=true",
        ]
        for flag in mutations:
            with self.subTest(flag=flag):
                r = self.render([flag])
                self.assertNotEqual(r.returncode, 0)
                self.assertIn("ARC full boundary", r.stderr)


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
