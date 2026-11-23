"""Offline regression tests for homelab non-HA and resource optimizations."""

import os
from pathlib import Path
import shutil
import subprocess
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
HELM = (
    os.environ.get("HELM_BIN") or os.environ.get("HELM_BINARY") or shutil.which("helm")
)


def render_yaml(chart: str, namespace: str, values: str = "kkamji_local_values.yaml"):
    assert HELM, "HELM_BIN or helm in PATH is required"
    args = [
        HELM,
        "template",
        chart,
        str(ROOT / "charts" / chart),
        "-n",
        namespace,
        "--skip-tests",
        "--kube-version",
        "1.36.1",
        "-f",
        str(ROOT / "charts" / chart / values),
    ]
    res = subprocess.run(args, capture_output=True, text=True, check=False, timeout=120)
    assert res.returncode == 0, res.stderr
    return [doc for doc in yaml.safe_load_all(res.stdout) if doc]


class HomelabResourceOptimizationTests(unittest.TestCase):
    def test_metallb_is_l2_only_worker_only_without_frr(self):
        docs = render_yaml("metallb", "metallb-system")
        speaker = next(
            d
            for d in docs
            if d["kind"] == "DaemonSet" and d["metadata"]["name"] == "metallb-speaker"
        )
        spec = speaker["spec"]["template"]["spec"]
        self.assertEqual([c["name"] for c in spec["containers"]], ["speaker"])
        self.assertEqual(spec.get("tolerations", []), [])
        self.assertEqual(
            spec["containers"][0]["resources"],
            {
                "requests": {"cpu": "10m", "memory": "24Mi"},
                "limits": {"memory": "160Mi"},
            },
        )
        ctrl = next(
            d
            for d in docs
            if d["kind"] == "Deployment"
            and d["metadata"]["name"] == "metallb-controller"
        )
        self.assertEqual(
            ctrl["spec"]["template"]["spec"]["containers"][0]["resources"],
            {
                "requests": {"cpu": "5m", "memory": "32Mi"},
                "limits": {"memory": "256Mi"},
            },
        )

    def test_cilium_operator_single_worker_replica_and_ambient_compatibility(self):
        docs = render_yaml("cilium", "kube-system")
        cm = next(
            d
            for d in docs
            if d["kind"] == "ConfigMap" and d["metadata"]["name"] == "cilium-config"
        )
        self.assertEqual(cm["data"]["debug"], "false")
        self.assertNotEqual(cm["data"].get("enable-bgp-control-plane"), "true")
        self.assertEqual(cm["data"].get("enable-l7-proxy"), "true")
        # Istio Ambient Mode compatibility with Cilium KPR
        self.assertEqual(cm["data"].get("cni-exclusive"), "false")
        self.assertEqual(cm["data"].get("bpf-lb-sock-hostns-only"), "true")
        self.assertEqual(cm["data"].get("enable-bpf-masquerade"), "false")
        self.assertEqual(cm["data"].get("enable-ipv4-masquerade"), "true")
        self.assertEqual(cm["data"].get("install-no-conntrack-iptables-rules"), "false")
        op = next(
            d
            for d in docs
            if d["kind"] == "Deployment" and d["metadata"]["name"] == "cilium-operator"
        )
        self.assertEqual(op["spec"]["replicas"], 1)
        pod_spec = op["spec"]["template"]["spec"]
        self.assertIsNone(pod_spec.get("affinity"))
        tol_keys = [t.get("key") for t in pod_spec.get("tolerations", [])]
        self.assertNotIn("node-role.kubernetes.io/control-plane", tol_keys)
        self.assertNotIn("node-role.kubernetes.io/master", tol_keys)
        self.assertEqual(
            pod_spec["containers"][0]["resources"],
            {
                "requests": {"cpu": "10m", "memory": "32Mi"},
                "limits": {"memory": "256Mi"},
            },
        )

    def test_argocd_disables_dex_scales_applicationset_zero_and_bounds_resources(self):
        docs = render_yaml("argocd", "argocd")
        self.assertFalse([d for d in docs if "dex" in d["metadata"]["name"]])
        appset = next(
            d
            for d in docs
            if d["kind"] == "Deployment"
            and d["metadata"]["name"] == "argocd-applicationset-controller"
        )
        self.assertEqual(appset["spec"]["replicas"], 0)
        ctrl = next(
            d
            for d in docs
            if d["kind"] == "StatefulSet"
            and d["metadata"]["name"] == "argocd-application-controller"
        )
        self.assertEqual(
            ctrl["spec"]["template"]["spec"]["containers"][0]["resources"],
            {
                "requests": {"cpu": "50m", "memory": "640Mi"},
                "limits": {"memory": "1280Mi"},
            },
        )

    def test_istio_ambient_1314_worker_only_and_minimal_resources(self):
        base_docs = render_yaml("istio-base", "istio-system")
        self.assertGreaterEqual(
            sum(1 for d in base_docs if d["kind"] == "CustomResourceDefinition"), 14
        )

        istiod_docs = render_yaml("istio-istiod", "istio-system")
        self.assertEqual(
            [d for d in istiod_docs if d["kind"] == "HorizontalPodAutoscaler"], []
        )
        dep = next(
            d
            for d in istiod_docs
            if d["kind"] == "Deployment" and d["metadata"]["name"] == "istiod"
        )
        self.assertEqual(dep["spec"]["replicas"], 1)
        c0 = dep["spec"]["template"]["spec"]["containers"][0]
        self.assertIn("1.31.4-distroless", c0["image"])
        env = {e["name"]: e.get("value") for e in c0.get("env", [])}
        self.assertEqual(env.get("PILOT_ENABLE_AMBIENT"), "true")
        self.assertEqual(
            c0["resources"],
            {
                "requests": {"cpu": "10m", "memory": "160Mi"},
                "limits": {"memory": "320Mi"},
            },
        )

        cni_docs = render_yaml("istio-cni", "istio-system")
        cni_cm = next(
            d
            for d in cni_docs
            if d["kind"] == "ConfigMap" and d["metadata"]["name"] == "istio-cni-config"
        )
        self.assertEqual(cni_cm["data"]["AMBIENT_ENABLED"], "true")
        cni_ds = next(d for d in cni_docs if d["kind"] == "DaemonSet")
        cni_ps = cni_ds["spec"]["template"]["spec"]
        self.assertFalse(cni_ps.get("tolerations"))
        cni_c = cni_ps["containers"][0]
        self.assertEqual(
            cni_c["securityContext"]["appArmorProfile"], {"type": "Unconfined"}
        )
        self.assertEqual(
            cni_c["resources"],
            {
                "requests": {"cpu": "10m", "memory": "32Mi"},
                "limits": {"memory": "128Mi"},
            },
        )

        zt_docs = render_yaml("istio-ztunnel", "istio-system")
        zt_ds = next(d for d in zt_docs if d["kind"] == "DaemonSet")
        zt_ps = zt_ds["spec"]["template"]["spec"]
        self.assertEqual(zt_ps["serviceAccountName"], "ztunnel")
        self.assertFalse(zt_ps.get("tolerations"))
        zt_c = zt_ps["containers"][0]
        self.assertIn("1.31.4-distroless", zt_c["image"])
        self.assertEqual(
            zt_c["resources"],
            {
                "requests": {"cpu": "10m", "memory": "48Mi"},
                "limits": {"memory": "192Mi"},
            },
        )

    def test_observability_and_infra_addons_have_bounded_burstable_resources(self):
        checks = [
            (
                "metrics-server",
                "kube-system",
                "Deployment",
                "metrics-server",
                "metrics-server",
                "10m",
                "96Mi",
                "192Mi",
            ),
            (
                "loki",
                "monitoring",
                "StatefulSet",
                "loki",
                "loki",
                "15m",
                "480Mi",
                "896Mi",
            ),
            (
                "alloy",
                "monitoring",
                "DaemonSet",
                "alloy",
                "alloy",
                "10m",
                "288Mi",
                "512Mi",
            ),
            (
                "hindsight",
                "hindsight",
                "StatefulSet",
                "hindsight-api",
                "api",
                "150m",
                "2Gi",
                "4Gi",
            ),
            (
                "hindsight",
                "hindsight",
                "Deployment",
                "hindsight-control-plane",
                "control-plane",
                "10m",
                "96Mi",
                "256Mi",
            ),
            ("ci-cache", "ci-cache", "Deployment", "zot", "zot", "15m", "256Mi", "1Gi"),
            (
                "arc-controller",
                "arc-system",
                "Deployment",
                "arc-controller",
                "manager",
                "10m",
                "64Mi",
                "192Mi",
            ),
            (
                "arc-runtime",
                "arc-runtime",
                "DaemonSet",
                "arc-runtime",
                "tun-device-plugin",
                "5m",
                "24Mi",
                "64Mi",
            ),
            (
                "cert-manager",
                "cert-manager",
                "Deployment",
                "cert-manager",
                "cert-manager-controller",
                "5m",
                "32Mi",
                "192Mi",
            ),
            (
                "external-secrets",
                "external-secrets",
                "Deployment",
                "external-secrets",
                "external-secrets",
                "5m",
                "32Mi",
                "256Mi",
            ),
            (
                "external-dns",
                "external-dns",
                "Deployment",
                "external-dns",
                "external-dns",
                "5m",
                "32Mi",
                "256Mi",
            ),
        ]
        for chart, ns, kind, name, cname, req_c, req_m, lim_m in checks:
            with self.subTest(chart=chart, workload=name):
                docs = render_yaml(chart, ns)
                obj = next(
                    d
                    for d in docs
                    if d["kind"] == kind and d["metadata"]["name"] == name
                )
                c = next(
                    x
                    for x in obj["spec"]["template"]["spec"]["containers"]
                    if x["name"] == cname
                )
                res = c["resources"]
                self.assertEqual(res["requests"]["cpu"], req_c)
                self.assertEqual(res["requests"]["memory"], req_m)
                self.assertEqual(res["limits"]["memory"], lim_m)

    def test_tier3_envoy_gateway_kps_and_keycloak_right_sizing(self):
        eg_docs = render_yaml("envoy-gateway", "envoy-gateway-system")
        eg_dep = next(
            d
            for d in eg_docs
            if d["kind"] == "Deployment" and d["metadata"]["name"] == "envoy-gateway"
        )
        eg_res = eg_dep["spec"]["template"]["spec"]["containers"][0]["resources"]
        self.assertEqual(eg_res["requests"], {"cpu": "10m", "memory": "96Mi"})
        self.assertEqual(eg_res["limits"]["memory"], "384Mi")
        eg_proxy = next(
            d
            for d in eg_docs
            if d["kind"] == "EnvoyProxy" and d["metadata"]["name"] == "kkamji-public"
        )
        self.assertEqual(eg_proxy["spec"]["concurrency"], 1)
        proxy_res = eg_proxy["spec"]["provider"]["kubernetes"]["envoyDeployment"][
            "container"
        ]["resources"]
        self.assertEqual(proxy_res["requests"], {"cpu": "20m", "memory": "192Mi"})
        self.assertEqual(proxy_res["limits"]["memory"], "384Mi")
        gw = next(
            d
            for d in eg_docs
            if d["kind"] == "Gateway" and d["metadata"]["name"] == "kkamji"
        )
        self.assertEqual(
            gw["spec"]["infrastructure"]["parametersRef"],
            {
                "group": "gateway.envoyproxy.io",
                "kind": "EnvoyProxy",
                "name": "kkamji-public",
            },
        )

        kps_docs = render_yaml("kube-prometheus-stack", "monitoring")
        am = next(d for d in kps_docs if d["kind"] == "Alertmanager")
        self.assertEqual(
            am["spec"]["resources"],
            {
                "requests": {"cpu": "5m", "memory": "80Mi"},
                "limits": {"memory": "192Mi"},
            },
        )
        prom = next(d for d in kps_docs if d["kind"] == "Prometheus")
        self.assertEqual(
            prom["spec"]["resources"],
            {
                "requests": {"cpu": "25m", "memory": "768Mi"},
                "limits": {"memory": "1536Mi"},
            },
        )
        sm = next(
            d
            for d in kps_docs
            if d["kind"] == "ServiceMonitor"
            and d["metadata"]["name"] == "kube-prometheus-stack-apiserver"
        )
        relabels = sm["spec"]["endpoints"][0]["metricRelabelings"]
        self.assertEqual(len(relabels), 2)
        self.assertIn("watch_events_dispatch_duration_seconds", relabels[1]["regex"])

        kc_op = render_yaml("keycloak-operator", "keycloak")
        op_dep = next(d for d in kc_op if d["kind"] == "Deployment")
        self.assertEqual(
            op_dep["spec"]["template"]["spec"]["containers"][0]["resources"],
            {
                "requests": {"cpu": "10m", "memory": "256Mi"},
                "limits": {"cpu": "500m", "memory": "450Mi"},
            },
        )

    def test_istio_ambient_full_cutover_and_declarative_enrollment(self):
        istiod_docs = render_yaml("istio-istiod", "istio-system")
        inj_cm = next(
            d
            for d in istiod_docs
            if d["kind"] == "ConfigMap"
            and d["metadata"]["name"] == "istio-sidecar-injector"
        )
        inj_cfg = yaml.safe_load(inj_cm["data"]["config"])
        self.assertIn(
            {"matchLabels": {"istio.io/dataplane-mode": "ambient"}},
            inj_cfg.get("neverInjectSelector", []),
        )
        istiod_vals = yaml.safe_load(
            (ROOT / "charts/istio-istiod/kkamji_local_values.yaml").read_text(
                encoding="utf-8"
            )
        )
        self.assertNotIn("proxy", istiod_vals.get("global", {}))
        self.assertEqual(
            istiod_vals["global"]["waypoint"]["resources"]["requests"],
            {"cpu": "25m", "memory": "64Mi"},
        )

        cni_docs = render_yaml("istio-cni", "istio-system")
        cni_cm = next(
            d
            for d in cni_docs
            if d["kind"] == "ConfigMap" and d["metadata"]["name"] == "istio-cni-config"
        )
        self.assertEqual(cni_cm["data"]["AMBIENT_ENABLED"], "true")
        self.assertEqual(cni_cm["data"]["AMBIENT_DNS_CAPTURE"], "true")
        self.assertIn("envoy-gateway-system", cni_cm["data"]["EXCLUDE_NAMESPACES"])
        self.assertIn("kube-system", cni_cm["data"]["EXCLUDE_NAMESPACES"])

        kps_docs = render_yaml("kube-prometheus-stack", "monitoring")
        prom_secret = next(
            d
            for d in kps_docs
            if d["kind"] == "Secret"
            and d["metadata"]["name"] == "kube-prometheus-stack-prometheus-scrape-confg"
        )
        import base64

        scrape_yaml = base64.b64decode(
            prom_secret["data"]["additional-scrape-configs.yaml"]
        ).decode("utf-8")
        scrape_jobs = [
            j["job_name"] for j in yaml.safe_load(scrape_yaml) if isinstance(j, dict)
        ]
        self.assertNotIn("envoy-stats", scrape_jobs)
        self.assertIn("istiod", scrape_jobs)

        personal_docs = render_yaml(
            "argo-applications",
            "argocd",
            values="personal_local_values.yaml",
        )
        by_name = {d["metadata"]["name"]: d for d in personal_docs}
        for app_name in ("real-life-rpg", "kkamji-platform"):
            labels = by_name[app_name]["spec"]["syncPolicy"][
                "managedNamespaceMetadata"
            ]["labels"]
            self.assertEqual(labels.get("istio.io/dataplane-mode"), "ambient")


if __name__ == "__main__":
    unittest.main()
