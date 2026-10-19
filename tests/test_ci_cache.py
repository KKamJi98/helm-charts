import json
import os
import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELM = os.environ.get("HELM_BINARY") or shutil.which("helm")
REGISTRY = "zot.ci-cache.svc.cluster.local:5000"


def render(chart, namespace, *args):
    r = subprocess.run(
        [
            HELM,
            "template",
            chart,
            str(ROOT / "charts" / chart),
            "-n",
            namespace,
            "-f",
            str(ROOT / "charts" / chart / "kkamji_local_values.yaml"),
            *args,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0, r.stderr
    return r.stdout


def doc(stdout, kind, name):
    found = [
        d
        for d in stdout.split("\n---")
        if re.search(rf"^kind: {kind}$", d, re.M)
        and re.search(rf"^  name: \"?{re.escape(name)}\"?$", d, re.M)
    ]
    assert len(found) == 1, (kind, name, len(found))
    return found[0]


class CiCacheChartTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = render("ci-cache", "ci-cache")
        # Helm emits the file as a double-quoted YAML scalar, which is a JSON string.
        quoted = re.search(r'^  config.json: (".*")$', doc(cls.out, "ConfigMap", "ci-cache-config"), re.M)
        cls.config = json.loads(json.loads(quoted.group(1)))
        cls.deploy = doc(cls.out, "Deployment", "zot")

    def test_image_is_pinned_by_digest(self):
        self.assertRegex(
            self.deploy,
            r'image: "ghcr\.io/project-zot/zot:v2\.1\.22@sha256:[0-9a-f]{64}"',
        )

    def test_registry_is_cluster_internal(self):
        self.assertIn("type: ClusterIP", doc(self.out, "Service", "zot"))
        self.assertNotIn("nodePort", doc(self.out, "Service", "zot"))

    def test_anonymous_clients_read_and_add_ci_tags_but_never_overwrite(self):
        http = self.config["http"]
        self.assertNotIn("auth", http)
        # create without update: a pushed content-addressed tag is immutable.
        self.assertEqual(
            http["accessControl"],
            {
                "repositories": {
                    "**": {"anonymousPolicy": ["read"]},
                    "ci/**": {"anonymousPolicy": ["read", "create"]},
                }
            },
        )
        ci = next(p for p in self.config["storage"]["retention"]["policies"] if p["repositories"] == ["ci/**"])
        self.assertEqual(ci["keepTags"], [{"pulledWithin": "336h"}, {"pushedWithin": "336h"}])

    def test_docker_hub_mirror_is_on_demand_only_and_keeps_digests(self):
        self.assertEqual(self.config["http"]["compat"], ["docker2s2"])
        [upstream] = self.config["extensions"]["sync"]["registries"]
        self.assertEqual(upstream["urls"], ["https://registry-1.docker.io"])
        self.assertTrue(upstream["onDemand"])
        # Periodic sync needs content and pollInterval; without pollInterval
        # content only filters on-demand requests.
        self.assertNotIn("pollInterval", upstream)
        self.assertEqual(upstream["content"], [{"prefix": "library/**"}])
        self.assertEqual(set(self.config["extensions"]), {"sync"})

    def test_store_is_the_bounded_volume(self):
        self.assertEqual(self.config["storage"]["rootDirectory"], "/var/lib/zot-store")
        self.assertTrue(self.config["storage"]["gc"])
        self.assertRegex(self.deploy, r"- mountPath: /var/lib/zot-store\n\s+name: store")
        self.assertRegex(self.deploy, r"- emptyDir:\n\s+sizeLimit: 30Gi\n\s+name: store")
        self.assertRegex(self.deploy, r"limits:\n(?:\s+\S.*\n)*?\s+ephemeral-storage: 31Gi")

    def test_runs_restricted(self):
        self.assertIn("runAsNonRoot: true", self.deploy)
        self.assertIn("allowPrivilegeEscalation: false", self.deploy)
        self.assertIn("readOnlyRootFilesystem: true", self.deploy)
        self.assertRegex(self.deploy, r"drop:\n\s+- ALL")
        self.assertIn(
            "pod-security.kubernetes.io/enforce: restricted",
            doc(self.out, "Namespace", "ci-cache"),
        )

    def test_only_ci_full_job_pods_reach_the_registry(self):
        self.assertIn("arc.kkamji.net/role: cache", self.deploy)
        deny = doc(self.out, "CiliumNetworkPolicy", "cache-default-deny")
        # Cilium rejects `ingress: []` as a rule with no sections.
        self.assertRegex(deny, r"endpointSelector: \{\}\n\s+ingress: \[\{\}\]\n\s+egress: \[\{\}\]")
        ingress = doc(self.out, "CiliumNetworkPolicy", "cache-from-full-jobs")
        self.assertEqual(ingress.count("fromEndpoints:"), 1)
        self.assertRegex(
            ingress,
            r"k8s:io.kubernetes.pod.namespace: ci-full\n\s+arc.kkamji.net/role: job\n"
            r'\s+toPorts:\n\s+- ports: \[\{port: "5000", protocol: TCP\}\]',
        )
        self.assertNotIn("egress", ingress)

    def test_upstream_egress_is_docker_hub_only(self):
        egress = doc(self.out, "CiliumNetworkPolicy", "cache-upstream")
        dns, fqdns = egress.split("- toFQDNs:")
        names = re.findall(r"matchName: (\S+)\}", fqdns)
        self.assertEqual(re.findall(r"matchName: (\S+)\}", dns), names)
        self.assertTrue(
            all(n.endswith(("docker.io", "docker.com", "r2.cloudflarestorage.com")) for n in names)
        )
        self.assertNotIn("matchPattern", egress)
        self.assertIn('ports: [{port: "443", protocol: TCP}]', fqdns)

    def test_argo_project_allows_only_what_the_chart_renders(self):
        # The argocd umbrella renders the live AppProjects; argo-projects keeps
        # the same definition.
        rendered_projects = subprocess.run(
            [HELM, "template", "argocd", str(ROOT / "charts/argocd"), "-n", "argocd",
             "-f", str(ROOT / "charts/argocd/kkamji_local_values.yaml"),
             "--show-only", "charts/argo-projects/templates/appproject.yaml"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(rendered_projects.returncode, 0, rendered_projects.stderr)
        self.assertIn("  name: ci-cache\n", rendered_projects.stdout)
        live = (ROOT / "charts/argocd/kkamji_local_values.yaml").read_text()
        copy = (ROOT / "charts/argo-projects/kkamji_local_values.yaml").read_text()
        project = live.split("\n    ci-cache:\n", 1)[1].split("\nrootApplications:", 1)[0]
        copied = copy.split("\n  ci-cache:\n", 1)[1]
        self.assertEqual(
            re.sub(r"\s+", " ", project.replace("enabled: true", "", 1)).strip(),
            re.sub(r"\s+", " ", copied).strip(),
        )
        allowed = set(re.findall(r"- group: '?([\w.]*)'?\n\s+kind: (\w+)", project))
        rendered = set()
        for d in self.out.split("\n---"):
            if "helm.sh/hook" in d or "kind:" not in d:
                continue
            api = re.search(r"^apiVersion: (\S+)$", d, re.M).group(1)
            kind = re.search(r"^kind: (\w+)$", d, re.M).group(1)
            rendered.add((api.rpartition("/")[0], kind))
        self.assertEqual(rendered, allowed)
        self.assertEqual(re.findall(r"namespace: (\S+)", project), ["ci-cache"])


class ArcFullUsesTheMirrorTests(unittest.TestCase):
    def test_job_egress_reaches_only_the_registry_inside_the_cluster(self):
        jobs = doc(render("arc-full", "ci-full", "--skip-crds"), "CiliumNetworkPolicy", "full-jobs")
        self.assertEqual(jobs.count("k8s:io.kubernetes.pod.namespace: ci-cache"), 1)
        self.assertRegex(
            jobs,
            r"k8s:io.kubernetes.pod.namespace: ci-cache\n\s+arc.kkamji.net/role: cache\n"
            r'\s+toPorts:\n\s+- ports: \[\{port: "5000", protocol: TCP\}\]',
        )
        self.assertIn("except: [0.0.0.0/8, 10.0.0.0/8,", jobs)

    def test_daemon_mirrors_docker_hub_through_the_registry(self):
        source = (ROOT / "charts/arc-full/files/trusted-runtime.py").read_text()
        self.assertIn(f'LAN_REGISTRY = "{REGISTRY}"', source)
        self.assertIn('f"--registry-mirror=http://{LAN_REGISTRY}"', source)
        self.assertIn('f"--insecure-registry={LAN_REGISTRY}"', source)


if __name__ == "__main__":
    unittest.main()
