import os
import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELM = os.environ.get("HELM_BINARY") or shutil.which("helm")


def render(chart, values, namespace):
    assert HELM, "Use the existing Helm; no network/dependency installation"
    r = subprocess.run(
        [HELM, "template", chart, str(ROOT / "charts" / chart), "-n", namespace,
         "-f", str(ROOT / "charts" / chart / values)],
        capture_output=True, text=True, check=False,
    )
    assert r.returncode == 0, r.stderr
    return r.stdout


class TerraformLabRunnerTests(unittest.TestCase):
    def test_scale_set_is_terraform_lab_only_without_docker_or_api_token(self):
        out = render("arc-light", "terraform_lab_values.yaml", "ci-pr")
        runner_set = next(d for d in out.split("---") if "kind: AutoscalingRunnerSet" in d)
        for line in [
            "githubConfigUrl: https://github.com/KKamJi98/terraform-lab",
            "name: terraform-lab-light",
            "maxRunners: 1",
            "arc.kkamji.net/egress: terraform",
            "ghcr.io/kkamji98/arc-runner-web-tools@sha256:",
            "memory: 2Gi",
            "sizeLimit: 3Gi",
        ]:
            self.assertIn(line, runner_set)
        self.assertRegex(runner_set, r"automountServiceAccountToken:\s+false")
        self.assertNotIn("docker.sock\n", runner_set.replace("test ! -S /run/user/1001/docker.sock\n", ""))
        self.assertNotIn("privileged: true", runner_set)

    def test_light_pools_do_not_get_the_terraform_egress_label(self):
        for chart in ("arc-light", "arc-bql-light"):
            out = render(chart, "kkamji_local_values.yaml", "ci-pr")
            self.assertNotIn("arc.kkamji.net/egress", out, chart)

    def test_foundation_opens_aws_and_hashicorp_only_to_terraform_pods(self):
        out = render("arc-foundation", "kkamji_local_values.yaml", "arc-system")
        policy = next(d for d in out.split("---") if "name: arc-terraform-egress" in d)
        self.assertIn("arc.kkamji.net/egress: terraform", policy)
        self.assertIn("arc.kkamji.net/role: job", policy)
        names = set(re.findall(r"\{match(?:Name|Pattern): [^}]+\}", policy))
        self.assertEqual(
            names,
            {
                '{matchPattern: "**.amazonaws.com"}',
                "{matchName: releases.hashicorp.com}",
                "{matchName: registry.terraform.io}",
                "{matchName: app.terraform.io}",
            },
        )
        for other in out.split("---"):
            if "CiliumNetworkPolicy" in other and "arc-terraform-egress" not in other:
                self.assertNotIn("amazonaws", other)

    def test_ci_pr_quota_admits_one_light_pod_plus_terraform(self):
        out = render("arc-foundation", "kkamji_local_values.yaml", "arc-system")
        quota = next(d for d in out.split("---") if "name: arc-job-budget" in d)
        for line in [
            "requests.cpu: 750m",
            "requests.memory: 1536Mi",
            "limits.cpu: '3'",
            "limits.memory: 3584Mi",
            "requests.ephemeral-storage: 1536Mi",
            "limits.ephemeral-storage: 8Gi",
            "pods: '2'",
        ]:
            self.assertIn(line, quota)

    def test_control_budget_keeps_a_controller_surge_with_three_listeners(self):
        out = render("arc-foundation", "kkamji_local_values.yaml", "arc-system")
        quota = next(d for d in out.split("---") if "name: arc-control-budget" in d)
        for line in [
            "requests.cpu: 350m",
            "requests.memory: 448Mi",
            "limits.cpu: 1750m",
            "limits.memory: 896Mi",
            "requests.ephemeral-storage: 320Mi",
            "limits.ephemeral-storage: 640Mi",
            "pods: '5'",
        ]:
            self.assertIn(line, quota)

    def test_argo_application_points_at_the_terraform_values(self):
        values = (ROOT / "charts/argo-applications/automation_local_values.yaml").read_text()
        block = values.split("  arc-terraform-lab-light:\n", 1)[1].split("\n  arc-", 1)[0]
        self.assertIn("path: charts/arc-light", block)
        self.assertIn("- terraform_lab_values.yaml", block)
        self.assertIn("namespace: ci-pr", block)


if __name__ == "__main__":
    unittest.main()
