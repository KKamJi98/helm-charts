import os
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELM = os.environ.get("HELM_BINARY") or shutil.which("helm")
GATES = (
    "enabled",
    "namespaceTrustAccepted",
    "existingStoreTrustAccepted",
    "keyChoiceApproved",
    "secureInputMetadataVerified",
)


class ArcAuthenticationRenderTests(unittest.TestCase):
    def render(self, flags=()):
        self.assertIsNotNone(
            HELM, "Helm is required; do not install or fetch charts in this test"
        )
        args = [
            HELM,
            "template",
            "arc-foundation",
            str(ROOT / "charts/arc-foundation"),
            "-n",
            "arc-system",
            "-f",
            str(ROOT / "charts/arc-foundation/kkamji_local_values.yaml"),
        ]
        for flag in flags:
            args += ["--set", flag]
        return subprocess.run(args, capture_output=True, text=True, check=False)

    def ready_flags(self):
        return ["githubAuth.enabled=true"] + [
            f"arcSsmReuse.{gate}=true" for gate in GATES
        ]

    def test_default_does_not_render_auth_or_secret(self):
        result = self.render()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("kind: ExternalSecret", result.stdout)
        self.assertNotIn("kind: Secret\n", result.stdout)

    def test_enable_without_confirmation_is_refused(self):
        result = self.render(["githubAuth.enabled=true"])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ARC auth blocked", result.stderr)

    def test_each_required_confirmation_is_enforced(self):
        for gate in GATES:
            with self.subTest(gate=gate):
                result = self.render(self.ready_flags() + [f"arcSsmReuse.{gate}=false"])
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("ARC auth blocked", result.stderr)

    def test_review_fixture_renders_one_canonical_external_secret_only(self):
        result = self.render(self.ready_flags())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.count("kind: ExternalSecret"), 1)
        for expected in [
            "name: arc-github-app-auth",
            "namespace: ci-pr",
            "name: parameter-store",
            "/kkamji/arc/github-app",
            "creationPolicy: Orphan",
            "deletionPolicy: Retain",
        ]:
            self.assertIn(expected, result.stdout)
        for forbidden in [
            "kind: Secret\n",
            "kind: SecretStore\n",
            "kind: ClusterSecretStore\n",
        ]:
            self.assertNotIn(forbidden, result.stdout)

    def test_two_light_consumers_use_the_canonical_secret(self):
        for chart in ["arc-light", "arc-bql-light"]:
            with self.subTest(chart=chart):
                text = (ROOT / f"charts/{chart}/kkamji_local_values.yaml").read_text()
                self.assertIn("githubConfigSecret: arc-github-app-auth", text)

    def test_confirmation_schema_rejects_non_boolean(self):
        result = self.render(["arcSsmReuse.keyChoiceApproved=not-a-boolean"])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("keyChoiceApproved", result.stderr)


if __name__ == "__main__":
    unittest.main()
