"""Offline tests exercise the actual rendered KubeJobFailed, not a copied expression."""
import copy
import io
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "charts/kube-prometheus-stack"
HELM = os.environ.get("HELM_BIN", "helm")
PROMTOOL = os.environ.get("PROMTOOL_BIN", "promtool")
# Immutable source anchor, not a mutable second copy of candidate values.
BASELINE = "fc09262727ab1cd6e6bd9f7247166a70f8b601e2"


class HelmLoader(yaml.SafeLoader):
    """Pinned CRDs contain the unquoted enum scalar '='."""


HelmLoader.add_constructor("tag:yaml.org,2002:value", HelmLoader.construct_scalar)


def command(argv):
    result = subprocess.run(argv, capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise AssertionError(f"command failed ({result.returncode}): {argv}\n{result.stderr}")
    return result.stdout


def render(chart=CHART):
    # Keep all render data in memory: it can contain Secret objects.
    text = command([HELM, "template", "kube-prometheus-stack", str(chart),
                    "-n", "monitoring", "--kube-version", "1.36.1", "--skip-tests",
                    "--include-crds", "-f", str(chart / "kkamji_local_values.yaml")])
    return [obj for obj in yaml.load_all(text, Loader=HelmLoader) if obj]


def job_failed_rules(objects):
    return [rule for obj in objects if obj["kind"] == "PrometheusRule"
            for group in obj["spec"]["groups"] for rule in group["rules"]
            if rule.get("alert") == "KubeJobFailed"]


def object_map(objects):
    result = {}
    for obj in objects:
        key = (obj["apiVersion"], obj["kind"], obj["metadata"].get("namespace", ""),
               obj["metadata"]["name"])
        if key in result:
            raise AssertionError(f"duplicate object identity: {key}")
        result[key] = obj
    return result


class KubeJobFailedRules(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.objects = render()
        cls.rules = job_failed_rules(cls.objects)
        if len(cls.rules) != 1:
            raise AssertionError(f"expected exactly one KubeJobFailed, got {len(cls.rules)}")

    def test_complete_render_changes_only_the_job_failed_rule(self):
        archive = subprocess.check_output(["git", "-C", str(ROOT), "archive", BASELINE,
                                           "charts/kube-prometheus-stack"])
        with tempfile.TemporaryDirectory(prefix="job-failed-baseline-") as tmp:
            with tarfile.open(fileobj=io.BytesIO(archive)) as source:
                source.extractall(tmp, filter="data")
            chart = Path(tmp) / "charts/kube-prometheus-stack"
            baseline = render(chart)
            for relative in ["Chart.yaml", "Chart.lock", "charts/kube-prometheus-stack-92.3.0.tgz"]:
                self.assertEqual((CHART / relative).read_bytes(), (chart / relative).read_bytes())
        upstream = job_failed_rules(baseline)
        self.assertEqual(len(upstream), 1)
        self.assertEqual({k: v for k, v in self.rules[0].items() if k != "expr"},
                         {k: v for k, v in upstream[0].items() if k != "expr"})
        before = object_map(baseline)
        after = object_map(copy.deepcopy(self.objects))
        extra = ("monitoring.coreos.com/v1", "PrometheusRule", "monitoring",
                 "kube-prometheus-stack-kkamji-job-failed")
        self.assertEqual(set(after) - set(before), {extra})
        self.assertEqual(set(before) - set(after), set())
        self.assertEqual(after[extra]["spec"]["groups"],
                         [{"name": "kkamji.job-failed", "rules": self.rules}])
        del after[extra]
        for obj in before.values():
            if obj["kind"] == "PrometheusRule":
                for group in obj["spec"]["groups"]:
                    group["rules"] = [r for r in group["rules"] if r.get("alert") != "KubeJobFailed"]
        # Compare Secret objects privately, with no values in assertion output.
        for key in before:
            self.assertTrue(before[key] == after[key], f"unexpected object change: {key}")
        print(f"render contract: {len(baseline)} -> {len(self.objects)} objects; "
              "only KubeJobFailed relocation/expression changed; vendor/pins identical")

    def test_all_rendered_rules_parse_with_target_promtool(self):
        groups = [group for obj in self.objects if obj["kind"] == "PrometheusRule"
                  for group in obj["spec"]["groups"]]
        with tempfile.TemporaryDirectory(prefix="all-rendered-rules-") as tmp:
            path = Path(tmp) / "rules.yaml"
            path.write_text(yaml.safe_dump({"groups": groups}))
            print(command([PROMTOOL, "check", "rules", str(path)]).strip())

    def test_promtool_lifecycle(self):
        with tempfile.TemporaryDirectory(prefix="kube-job-failed-") as tmp:
            tmp = Path(tmp)
            rule_path = tmp / "rules.yaml"
            rule_path.write_text(yaml.safe_dump({"groups": [{"name": "rendered-job-failed",
                                                            "rules": self.rules}]}))
            fixture = yaml.safe_load((ROOT / "tests/prometheus/kube-job-failed.test.yaml").read_text())
            fixture["rule_files"] = [str(rule_path)]
            fixture_path = tmp / "test.yaml"
            fixture_path.write_text(yaml.safe_dump(fixture))
            command([PROMTOOL, "check", "rules", str(rule_path)])
            result = subprocess.run([PROMTOOL, "test", "rules", str(fixture_path)],
                                    capture_output=True, text=True, timeout=120)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
