"""Offline validation tests for homelab security & SBOM Helm charts."""

import json
import os
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
HELM = os.environ.get("HELM_BIN", "helm")


def run_helm(args):
    result = subprocess.run([HELM, *args], capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise AssertionError(
            f"helm {' '.join(args)} failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    return result.stdout


class SecuritySbomChartsTests(unittest.TestCase):
    def test_trivy_operator_lint_and_render(self):
        chart = ROOT / "charts/trivy-operator"
        values = chart / "kkamji_local_values.yaml"
        run_helm(["lint", str(chart), "-f", str(values)])
        rendered = run_helm(
            [
                "template",
                "trivy-operator",
                str(chart),
                "-n",
                "security",
                "--kube-version",
                "1.36.1",
                "-f",
                str(values),
            ]
        )
        self.assertIn('OPERATOR_SBOM_GENERATION_ENABLED: "true"', rendered)
        self.assertIn('OPERATOR_CONCURRENT_SCAN_JOBS_LIMIT: "1"', rendered)
        self.assertIn("ci-pr,ci-full", rendered)
        self.assertIn("kind: ServiceMonitor", rendered)
        self.assertIn("release: kube-prometheus-stack", rendered)

    def test_tetragon_worker_only_and_audit_policy(self):
        chart = ROOT / "charts/tetragon"
        values = chart / "kkamji_local_values.yaml"
        run_helm(["lint", str(chart), "-f", str(values)])
        rendered = run_helm(
            [
                "template",
                "tetragon",
                str(chart),
                "-n",
                "security",
                "--kube-version",
                "1.36.1",
                "-f",
                str(values),
            ]
        )
        # CRITICAL guard: k8s-m1 sits at 94% RAM, so upstream operator: Exists must NOT appear.
        self.assertNotIn("operator: Exists", rendered)
        self.assertIn("kind: TracingPolicy", rendered)
        self.assertIn("homelab-sensitive-file-read-audit", rendered)
        self.assertNotIn("action: Sigkill", rendered)
        self.assertIn("release: kube-prometheus-stack", rendered)
        self.assertIn("export-stdout", rendered)

    def test_security_observability_dashboards_rules_and_gated_publisher(self):
        chart = ROOT / "charts/security-observability"
        values = chart / "kkamji_local_values.yaml"
        run_helm(["lint", str(chart), "-f", str(values)])
        rendered = run_helm(
            [
                "template",
                "security-observability",
                str(chart),
                "-n",
                "security",
                "--kube-version",
                "1.36.1",
                "-f",
                str(values),
            ]
        )
        self.assertIn("kind: ServiceMonitor", rendered)
        self.assertIn("security-observability-hubble-metrics", rendered)
        self.assertIn("kind: PrometheusRule", rendered)
        self.assertIn("TrivyCriticalVulnerabilityDetected", rendered)
        self.assertIn("HubbleHighDropRate", rendered)
        self.assertIn("TetragonEnforcementSigkill", rendered)
        self.assertIn("EnvoyEdge4xxSpike", rendered)
        self.assertIn('grafana_dashboard: "1"', rendered)
        self.assertIn('grafana_folder: "Security"', rendered)
        # Posture publisher must remain disabled by default until explicitly enabled.
        self.assertNotIn("kind: CronJob", rendered)
        self.assertNotIn("kind: ExternalSecret", rendered)

        # Verify publisher renders cleanly with ExternalSecret when explicitly opted in.
        enabled = run_helm(
            [
                "template",
                "security-observability",
                str(chart),
                "-n",
                "security",
                "--kube-version",
                "1.36.1",
                "-f",
                str(values),
                "--set",
                "posturePublisher.enabled=true",
            ]
        )
        self.assertIn("kind: CronJob", enabled)
        self.assertIn("kind: ExternalSecret", enabled)
        self.assertIn(
            "https://platform.kkamji.net/api/ingest/security-posture", enabled
        )

    def test_grafana_dashboard_json_validity(self):
        dashboards_dir = ROOT / "charts/security-observability/dashboards"
        files = sorted(dashboards_dir.glob("*.json"))
        self.assertEqual(len(files), 3)
        seen_uids = set()
        for path in files:
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertNotIn(data["uid"], seen_uids)
            seen_uids.add(data["uid"])
            self.assertGreaterEqual(data["schemaVersion"], 39)
            panel_ids = [p["id"] for p in data["panels"]]
            self.assertEqual(
                len(panel_ids),
                len(set(panel_ids)),
                f"duplicate panel ID in {path.name}",
            )
            for p in data["panels"]:
                pos = p["gridPos"]
                self.assertLessEqual(
                    pos["x"] + pos["w"], 24, f"panel overflow in {path.name}"
                )

    def test_loki_retention_extension_renders_cleanly(self):
        chart = ROOT / "charts/loki"
        values = chart / "kkamji_local_values.yaml"
        run_helm(["lint", str(chart), "-f", str(values)])
        rendered = run_helm(
            [
                "template",
                "loki",
                str(chart),
                "-n",
                "monitoring",
                "--kube-version",
                "1.36.1",
                "-f",
                str(values),
            ]
        )
        self.assertIn("retention_period: 168h", rendered)
        self.assertIn("reject_old_samples_max_age: 168h", rendered)

    def test_staged_argo_applications_default_disabled(self):
        chart = ROOT / "charts/argo-applications"
        values = chart / "security_local_values.yaml"
        rendered = run_helm(
            [
                "template",
                "security-root",
                str(chart),
                "-n",
                "argocd",
                "--kube-version",
                "1.36.1",
                "-f",
                str(values),
            ]
        )
        # All 3 security apps default to enabled: false so merge never auto-deploys unapproved workloads.
        self.assertEqual(rendered.strip(), "")


if __name__ == "__main__":
    unittest.main()
