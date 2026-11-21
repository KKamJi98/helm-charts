"""Offline private admin source contracts; not HTTPS/DNS/CNI/runtime evidence."""
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
HELM = os.environ.get("HELM_BIN", "")
PLATFORM = ROOT / "charts/envoy-gateway"
SERVICE = ROOT / "charts/keycloak-admin-access"
NAME = "keycloak-admin-private"
NAMESPACE = "envoy-gateway-system"
DNS_KEY = "external-dns.alpha.kubernetes.io/controller"
DNS_IGNORE = "keycloak-admin-private-disabled"
ACCESS = {"kkamji.net/access": NAME}


def render(chart, override=None, release=None, namespace=NAMESPACE, local=True, skip_schema=False):
    command = [HELM, "template", release or chart.name, str(chart), "-n", namespace,
               "--include-crds", "--skip-tests", "--kube-version", "1.36.1"]
    if local:
        command += ["-f", str(chart / "kkamji_local_values.yaml")]
    if skip_schema:
        command.append("--skip-schema-validation")
    with tempfile.TemporaryDirectory(prefix="keycloak-private-") as temporary:
        if override is not None:
            path = Path(temporary) / "override.json"
            path.write_text(json.dumps(override))
            command += ["-f", str(path)]
        return subprocess.run(command, capture_output=True, text=True, timeout=90)


def documents(result):
    if result.returncode:
        raise AssertionError(result.stderr)
    objects = [item for item in yaml.safe_load_all(result.stdout) if item]
    keyed = {(obj["kind"], obj["metadata"].get("namespace", ""), obj["metadata"]["name"]): obj for obj in objects}
    if len(keyed) != len(objects):
        raise AssertionError("duplicate identity")
    return keyed


def private(objects):
    return {key: obj for key, obj in objects.items() if key[2].startswith(NAME)}


SERVER = {
    "app": "keycloak", "app.kubernetes.io/component": "server",
    "app.kubernetes.io/instance": "keycloak", "app.kubernetes.io/managed-by": "keycloak-operator",
}
PROXY = {
    "app.kubernetes.io/component": "proxy",
    "gateway.envoyproxy.io/owning-gateway-name": NAME,
    "gateway.envoyproxy.io/owning-gateway-namespace": NAMESPACE,
    **ACCESS,
}
METRICS = ("CiliumNetworkPolicy", NAMESPACE, NAME + "-prometheus-ingress")
PROMETHEUS = {
    "k8s:io.kubernetes.pod.namespace": "monitoring",
    "k8s:io.cilium.k8s.policy.serviceaccount": "kube-prometheus-stack-prometheus",
}
METRICS_SPEC = {
    "endpointSelector": {"matchLabels": {"k8s:" + key: value for key, value in PROXY.items()}},
    "ingress": [{
        "fromEndpoints": [{"matchLabels": PROMETHEUS}],
        "toPorts": [{"ports": [{"port": "19001", "protocol": "TCP"}],
                     "rules": {"http": [{"method": "GET", "path": "^/stats/prometheus$"}]}}],
    }],
}
# Fixed security assertions, not projections of mutable values/profile files.
EXPECTED = {
    METRICS: METRICS_SPEC,
    ("EnvoyProxy", NAMESPACE, NAME): {
        "mergeGateways": False, "concurrency": 1,
        "provider": {"type": "Kubernetes", "kubernetes": {
            "envoyService": {"type": "ClusterIP", "annotations": {DNS_KEY: DNS_IGNORE}},
            "envoyDeployment": {"replicas": 1, "pod": {"labels": ACCESS}, "container": {
                "resources": {"requests": {"cpu": "100m", "memory": "128Mi"},
                              "limits": {"cpu": "500m", "memory": "256Mi"}}}},
        }},
        "telemetry": {"accessLog": {"disable": True}},
    },
    ("Gateway", NAMESPACE, NAME): {
        "gatewayClassName": "envoy",
        "infrastructure": {"parametersRef": {"group": "gateway.envoyproxy.io", "kind": "EnvoyProxy", "name": NAME}},
        "listeners": [{"name": "https", "hostname": "sso.kkamji.net", "port": 443, "protocol": "HTTPS",
                       "tls": {"mode": "Terminate", "certificateRefs": [
                           {"group": "", "kind": "Secret", "name": "wildcard-kkamji-net-tls"}]},
                       "allowedRoutes": {"namespaces": {"from": "Same"}, "kinds": [
                           {"group": "gateway.networking.k8s.io", "kind": "HTTPRoute"}]}}],
    },
    ("NetworkPolicy", NAMESPACE, NAME + "-deny-ingress"): {
        "podSelector": {"matchLabels": ACCESS}, "policyTypes": ["Ingress"], "ingress": [],
    },
    ("HTTPRoute", NAMESPACE, NAME): {
        "hostnames": ["sso.kkamji.net"], "parentRefs": [
            {"group": "gateway.networking.k8s.io", "kind": "Gateway", "name": NAME,
             "namespace": NAMESPACE, "sectionName": "https"}],
        "rules": [{"matches": [{"path": {"type": "PathPrefix", "value": "/"}}], "backendRefs": [
            {"group": "", "kind": "Service", "name": "keycloak-service", "namespace": "keycloak", "port": 8080, "weight": 1}]}],
    },
    ("ReferenceGrant", "keycloak", NAME): {
        "from": [{"group": "gateway.networking.k8s.io", "kind": "HTTPRoute", "namespace": NAMESPACE}],
        "to": [{"group": "", "kind": "Service", "name": "keycloak-service"}],
    },
    ("NetworkPolicy", "keycloak", NAME + "-server-ingress"): {
        "podSelector": {"matchLabels": SERVER}, "policyTypes": ["Ingress"],
        "ingress": [{"from": [{"namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": NAMESPACE}},
                               "podSelector": {"matchLabels": PROXY}}],
                     "ports": [{"protocol": "TCP", "port": 8080}]}],
    },
}


def combined():
    return {**private(documents(render(PLATFORM))), **documents(render(SERVICE))}


def assert_contract(case, objects):
    case.assertEqual(set(objects), set(EXPECTED))
    for key, expected in EXPECTED.items():
        obj = objects[key]
        case.assertEqual(obj["spec"], expected, key)
        annotations = {DNS_KEY: DNS_IGNORE} if key[0] in ("Gateway", "HTTPRoute") else {}
        case.assertEqual(obj["metadata"], {"name": key[2], "namespace": key[1],
                         **({"annotations": annotations} if annotations else {})})
        case.assertEqual(set(obj), {"apiVersion", "kind", "metadata", "spec"})
        case.assertEqual(obj["apiVersion"], {
            "EnvoyProxy": "gateway.envoyproxy.io/v1alpha1", "Gateway": "gateway.networking.k8s.io/v1",
            "HTTPRoute": "gateway.networking.k8s.io/v1", "ReferenceGrant": "gateway.networking.k8s.io/v1beta1",
            "NetworkPolicy": "networking.k8s.io/v1",
            "CiliumNetworkPolicy": "cilium.io/v2",
        }[key[0]])


def metrics_exception_allows(policy, target, source, port=19001, protocol="TCP",
                             method="GET", path="/stats/prometheus"):
    """Only the added allow rule's source model, not Cilium execution or total policy evaluation."""
    matches = lambda selector, labels: all(labels.get(k) == v for k, v in selector["matchLabels"].items())
    if not matches(policy["spec"]["endpointSelector"], {"k8s:" + k: v for k, v in target.items()}):
        return False
    for ingress in policy["spec"]["ingress"]:
        if not any(matches(peer, source) for peer in ingress["fromEndpoints"]):
            continue
        for to_ports in ingress["toPorts"]:
            if not any(p["port"] == str(port) and p["protocol"] == protocol for p in to_ports["ports"]):
                continue
            if any(re.fullmatch(rule["method"], method) and re.fullmatch(rule["path"], path)
                   for rule in to_ports["rules"]["http"]):
                return True
    return False


class PrivateServiceTests(unittest.TestCase):
    def test_metrics_requires_exact_prometheus_identity_and_http_get(self):
        objects = documents(render(SERVICE))
        self.assertIn(METRICS, objects, "private Envoy metrics require a narrow Cilium L7 allow")
        self.assertEqual(objects[METRICS]["spec"], METRICS_SPEC)

    def test_metrics_model_rejects_wrong_identity_and_non_private_targets(self):
        policy = documents(render(SERVICE))[METRICS]
        self.assertTrue(metrics_exception_allows(policy, PROXY, PROMETHEUS))
        for field in PROMETHEUS:
            for value in (None, "default", "other"):
                with self.subTest(source_field=field, value=value):
                    source = {**PROMETHEUS, field: value}
                    self.assertFalse(metrics_exception_allows(policy, PROXY, source))
        for field in PROXY:
            for value in (None, "kkamji"):
                with self.subTest(target_field=field, value=value):
                    self.assertFalse(metrics_exception_allows(policy, {**PROXY, field: value}, PROMETHEUS))
        self.assertFalse(metrics_exception_allows(policy, PROXY, {}))

    def test_metrics_model_rejects_admin_paths_methods_and_other_ports(self):
        policy = documents(render(SERVICE))[METRICS]
        self.assertTrue(metrics_exception_allows(policy, PROXY, PROMETHEUS))
        for port in (80, 443, 8080, 9000, 10443, 19000, 19002):
            with self.subTest(port=port):
                self.assertFalse(metrics_exception_allows(policy, PROXY, PROMETHEUS, port=port))
        self.assertFalse(metrics_exception_allows(policy, PROXY, PROMETHEUS, protocol="UDP"))
        for method in ("HEAD", "POST", "PUT", "DELETE", "GETTING", "get"):
            with self.subTest(method=method):
                self.assertFalse(metrics_exception_allows(policy, PROXY, PROMETHEUS, method=method))
        for path in ("/", "/config_dump", "/server_info", "/ready", "/stats", "/quitquitquit",
                     "/stats/prometheus/", "/stats/prometheus-extra", "/prefix/stats/prometheus",
                     "/stats/prometheus?format=json", "/stats/prometheus%2f", "/Stats/prometheus"):
            with self.subTest(path=path):
                self.assertFalse(metrics_exception_allows(policy, PROXY, PROMETHEUS, path=path))

    def test_service_defaults_disabled_and_local_adds_four_objects(self):
        self.assertEqual(documents(render(SERVICE, local=False)), {})
        enabled = documents(render(SERVICE))
        self.assertEqual(set(enabled), {
            ("HTTPRoute", NAMESPACE, NAME), ("ReferenceGrant", "keycloak", NAME),
            ("NetworkPolicy", "keycloak", NAME + "-server-ingress"),
            METRICS,
        })
        self.assertEqual(yaml.safe_load((SERVICE / "values.yaml").read_text()), {"keycloakAdminPrivate": {"enabled": False}})
        self.assertEqual(yaml.safe_load((SERVICE / "kkamji_local_values.yaml").read_text()), {"keycloakAdminPrivate": {"enabled": True}})
        self.assertNotIn("dependencies", yaml.safe_load((SERVICE / "Chart.yaml").read_text()))
        self.assertFalse((SERVICE / "Chart.lock").exists())

    def test_combined_exact_seven_resource_security_contract(self):
        assert_contract(self, combined())


class PrivatePlatformTests(unittest.TestCase):
    def test_private_opt_in_adds_only_three_native_platform_objects(self):
        before = documents(render(PLATFORM, {"keycloakAdminPrivate": {"enabled": False}}))
        after = documents(render(PLATFORM))
        added = private(after)
        self.assertEqual(set(added), {
            ("Gateway", NAMESPACE, NAME), ("EnvoyProxy", NAMESPACE, NAME),
            ("NetworkPolicy", NAMESPACE, NAME + "-deny-ingress"),
        })
        self.assertEqual({key: obj for key, obj in after.items() if key not in added}, before)
        self.assertFalse(private(before))
        self.assertEqual(yaml.safe_load((PLATFORM / "values.yaml").read_text()),
                         {"keycloakAdminPrivate": {"enabled": False}})


def digest(objects):
    return hashlib.sha256(json.dumps(objects, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class PrivateActivationTests(unittest.TestCase):
    def test_management_adds_one_application_preserving_all_sixteen(self):
        chart = ROOT / "charts/argo-applications"
        args = [HELM, "template", "management-root", str(chart), "-n", "argocd",
                "--include-crds", "--skip-tests", "--kube-version", "1.36.1",
                "-f", str(chart / "management_local_values.yaml")]
        rendered = documents(subprocess.run(args, capture_output=True, text=True, timeout=90))
        app = rendered.pop(("Application", "argocd", "keycloak-admin-access"), None)
        self.assertIsNotNone(app, "explicit private access Application required")
        self.assertEqual(len(rendered), 16)
        self.assertEqual(digest(list(rendered.values())), "a6b42482e2c4385696df25e8897b08967d0074a4cdf9282660a819fb274b470e")
        self.assertEqual(app["spec"], {
            "project": "management", "destination": {"namespace": NAMESPACE, "server": "https://kubernetes.default.svc"},
            "source": {"repoURL": "https://github.com/KKamJi98/helm-charts.git", "targetRevision": "main",
                       "path": "charts/keycloak-admin-access", "helm": {
                           "releaseName": "keycloak-admin-access", "valueFiles": ["kkamji_local_values.yaml"]}},
            "syncPolicy": {"automated": {"prune": True, "selfHeal": True}, "syncOptions": [
                "CreateNamespace=true", "ApplyOutOfSyncOnly=true", "ServerSideApply=true"]},
        })
        self.assertEqual(app["metadata"], {"name": "keycloak-admin-access", "namespace": "argocd",
                         "finalizers": ["resources-finalizer.argocd.argoproj.io"],
                         "labels": {"app.kubernetes.io/name": "argo-applications",
                                    "app.kubernetes.io/instance": "management-root",
                                    "app.kubernetes.io/managed-by": "Helm", "helm.sh/chart": "argo-applications-0.1.0"},
                         "annotations": {"argocd.argoproj.io/manifest-generate-paths": "."}})
        for root, count, expected in [
            ("automation", 9, "3c6c7fb11b7f1db85368183f31eaa338857b2b2adfe531db0286424a38a6bd71"),
            ("personal", 1, "1d978181ac405ff5c821b96954ce48565e20c34e296f41ab638dc74ef27886d7"),
        ]:
            args[2] = root + "-root"
            args[-1] = str(chart / (root + "_local_values.yaml"))
            other = documents(subprocess.run(args, capture_output=True, text=True, timeout=90))
            self.assertEqual(len(other), count)
            self.assertEqual(digest(list(other.values())), expected)


class PrivateRefusalTests(unittest.TestCase):
    def test_only_boolean_flag_is_supported_with_and_without_schema(self):
        flags = ["true", "false", 0, 1, [], {}, None]
        unsafe = [{"keycloakAdminPrivate": {"enabled": value}} for value in flags]
        # Security fields are literals, not configurable profiles; additions must fail.
        unsafe += [{"keycloakAdminPrivate": {"enabled": True, field: value}} for field, value in [
            ("hostname", "*.kkamji.net"), ("gatewayClassName", "public"), ("parentRef", "kkamji"),
            ("envoyService", {"type": "LoadBalancer"}), ("externalIPs", ["192.0.2.1"]),
            ("hostNetwork", True), ("mergeGateways", True), ("podLabels", {}),
            ("accessLog", {"disable": False}), ("backendPort", 9000), ("egress", [{}]),
            ("referenceGrant", {"to": [{"kind": "Secret"}]}), ("unknown", True),
            ("metricsPort", 19000), ("metricsPath", "/.*"), ("metricsServiceAccount", "default"),
            ("metricsNamespace", "default"), ("metricsL7", False), ("metricsPeers", [{}]),
        ]]
        for chart in (PLATFORM, SERVICE):
            cases = unsafe + ([{"namespaceOverride": "default"}, {"fullnameOverride": "other"},
                               {"extraObjects": []}] if chart == SERVICE else [])
            for index, override in enumerate(cases):
                for skip_schema in (False, True):
                    with self.subTest(chart=chart.name, index=index, skip_schema=skip_schema):
                        result = render(chart, override=override, skip_schema=skip_schema)
                        self.assertNotEqual(result.returncode, 0)
                        if skip_schema or chart == PLATFORM:
                            self.assertIn("only boolean keycloakAdminPrivate.enabled is supported", result.stderr)

    def test_private_enabled_refuses_other_namespace_or_release(self):
        for chart in (PLATFORM, SERVICE):
            for namespace, release in (("default", chart.name), (NAMESPACE, "other")):
                for skip_schema in (False, True):
                    with self.subTest(chart=chart.name, namespace=namespace, release=release, skip_schema=skip_schema):
                        result = render(chart, namespace=namespace, release=release, skip_schema=skip_schema)
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn("exact namespace/release identity required", result.stderr)

    def test_fixed_contract_detects_dangerous_render_mutations(self):
        source = combined()
        gateway = ("Gateway", NAMESPACE, NAME)
        proxy = ("EnvoyProxy", NAMESPACE, NAME)
        route = ("HTTPRoute", NAMESPACE, NAME)
        grant = ("ReferenceGrant", "keycloak", NAME)
        deny = ("NetworkPolicy", NAMESPACE, NAME + "-deny-ingress")
        ingress = ("NetworkPolicy", "keycloak", NAME + "-server-ingress")
        mutations = [
            (gateway, ("spec", "gatewayClassName"), "public"),
            (gateway, ("spec", "listeners", 0, "hostname"), "*.kkamji.net"),
            (gateway, ("spec", "listeners", 0, "tls", "certificateRefs", 0, "namespace"), "keycloak"),
            (gateway, ("spec", "listeners", 0, "allowedRoutes", "namespaces", "from"), "All"),
            (proxy, ("spec", "provider", "kubernetes", "envoyService", "type"), "LoadBalancer"),
            (proxy, ("spec", "provider", "kubernetes", "envoyService", "type"), "NodePort"),
            (proxy, ("spec", "provider", "kubernetes", "envoyService", "externalIPs"), ["192.0.2.1"]),
            (proxy, ("spec", "provider", "kubernetes", "envoyService", "annotations"), {}),
            (proxy, ("spec", "provider", "kubernetes", "envoyDeployment", "pod", "labels"), {}),
            (proxy, ("spec", "mergeGateways"), True),
            (proxy, ("spec", "telemetry", "accessLog", "disable"), False),
            (route, ("spec", "parentRefs", 0, "name"), "kkamji"),
            (route, ("spec", "hostnames"), ["*.kkamji.net"]),
            (route, ("spec", "rules", 0, "backendRefs", 0, "port"), 9000),
            (route, ("spec", "rules", 0, "backendRefs", 0, "name"), "other"),
            (grant, ("spec", "to"), [{"group": "", "kind": "Service"}]),
            (grant, ("spec", "to"), [{"group": "", "kind": "Secret"}]),
            (grant, ("spec", "from", 0, "namespace"), "default"),
            (deny, ("spec", "podSelector"), {}), (deny, ("spec", "ingress"), [{}]),
            (ingress, ("spec", "podSelector"), {}),
            (ingress, ("spec", "ingress", 0, "from", 0, "podSelector"), {}),
            (ingress, ("spec", "ingress", 0, "ports", 0, "port"), 5432),
            (ingress, ("spec", "egress"), [{}]),
            (METRICS, ("spec", "endpointSelector"), {}),
            (METRICS, ("spec", "endpointSelector", "matchLabels"), {"k8s:kkamji.net/access": NAME}),
            (METRICS, ("spec", "ingress", 0, "fromEndpoints"), [{"matchLabels": {}}]),
            (METRICS, ("spec", "ingress", 0, "fromEndpoints", 0, "matchLabels"),
             {"k8s:io.kubernetes.pod.namespace": "monitoring"}),
            (METRICS, ("spec", "ingress", 0, "fromEndpoints", 0, "matchLabels"),
             {"k8s:io.cilium.k8s.policy.serviceaccount": "kube-prometheus-stack-prometheus"}),
            (METRICS, ("spec", "ingress", 0, "toPorts", 0, "ports", 0, "port"), "19000"),
            (METRICS, ("spec", "ingress", 0, "toPorts", 0, "rules"), {}),
            (METRICS, ("spec", "ingress", 0, "toPorts", 0, "rules", "http", 0), {}),
            (METRICS, ("spec", "ingress", 0, "toPorts", 0, "rules", "http", 0, "method"), ".*"),
            (METRICS, ("spec", "ingress", 0, "toPorts", 0, "rules", "http", 0, "path"), "^/stats/.*$"),
            (METRICS, ("spec", "egress"), [{}]),
        ]
        mutations += [(key, ("metadata", "annotations"), annotations) for key in (gateway, route)
                      for annotations in ({}, {DNS_KEY: "dns-controller"}, {"external-dns.alpha.kubernetes.io/exclude": "true"})]
        for key, path, value in mutations:
            with self.subTest(identity=key, path=path):
                changed = copy.deepcopy(source)
                target = changed[key]
                for field in path[:-1]:
                    target = target[field]
                target[path[-1]] = value
                with self.assertRaises(AssertionError):
                    assert_contract(self, changed)

    def test_dns_controller_absence_and_mismatch_fixed_controls(self):
        # Model of the pinned v0.21.0 IsControllerMismatch branch, not a Go/runtime execution.
        mismatch = lambda annotations: DNS_KEY in annotations and annotations[DNS_KEY] != "dns-controller"
        for annotations, skipped in [({}, False), ({DNS_KEY: "dns-controller"}, False),
                                      ({DNS_KEY: DNS_IGNORE}, True), ({DNS_KEY: ""}, True),
                                      ({"external-dns.alpha.kubernetes.io/exclude": "true"}, False)]:
            self.assertEqual(mismatch(annotations), skipped)
        source = combined()
        for key in (("Gateway", NAMESPACE, NAME), ("HTTPRoute", NAMESPACE, NAME)):
            self.assertTrue(mismatch(source[key]["metadata"]["annotations"]))
        service = source["EnvoyProxy", NAMESPACE, NAME]["spec"]["provider"]["kubernetes"]["envoyService"]
        self.assertTrue(mismatch(service["annotations"]))

    def test_additive_ingress_model_preserves_existing_public_and_denies_wrong_sources(self):
        import test_keycloak_preparation as preparation
        objects = combined()
        service_policy = objects["NetworkPolicy", "keycloak", NAME + "-server-ingress"]
        old = preparation.KeycloakPreparationTests.render(preparation.APP)
        policies = [obj for obj in old if obj["kind"] == "NetworkPolicy"]
        self.assertEqual(len(policies), 3)
        self.assertFalse(preparation.ingress_allowed(policies, SERVER, PROXY, NAMESPACE, 8080))
        all_policies = policies + [service_policy]
        self.assertTrue(preparation.ingress_allowed(all_policies, SERVER, PROXY, NAMESPACE, 8080))
        self.assertTrue(preparation.ingress_allowed(all_policies, SERVER, preparation.GATEWAY_LABELS, NAMESPACE, 8080))
        self.assertTrue(preparation.ingress_allowed(all_policies, SERVER,
                        {"app.kubernetes.io/name": "keycloak-operator"}, "keycloak", 9000))
        for field in PROXY:
            wrong = {key: value for key, value in PROXY.items() if key != field}
            self.assertFalse(preparation.ingress_allowed(all_policies, SERVER, wrong, NAMESPACE, 8080))
        for namespace in ("default", "keycloak"):
            self.assertFalse(preparation.ingress_allowed(all_policies, SERVER, PROXY, namespace, 8080))
        for port in (443, 9000, 5432):
            self.assertFalse(preparation.ingress_allowed(all_policies, SERVER, PROXY, NAMESPACE, port))
        deny = objects["NetworkPolicy", NAMESPACE, NAME + "-deny-ingress"]
        self.assertTrue(preparation.selector_matches(deny["spec"]["podSelector"], PROXY))
        self.assertFalse(preparation.selector_matches(deny["spec"]["podSelector"], preparation.GATEWAY_LABELS))
        self.assertFalse(preparation.ingress_allowed([deny], PROXY, {}, "default", 443))

    def test_envoyproxy_fields_against_pristine_pinned_vendor_schema(self):
        import test_keycloak_preparation as preparation
        rendered = documents(render(PLATFORM))
        crd = rendered["CustomResourceDefinition", "", "envoyproxies.gateway.envoyproxy.io"]
        schema = preparation.crd_schema(crd, "v1alpha1")
        preparation.validate_document(schema, rendered["EnvoyProxy", NAMESPACE, NAME])
        invalid = copy.deepcopy(rendered["EnvoyProxy", NAMESPACE, NAME])
        invalid["spec"]["provider"]["kubernetes"]["envoyService"]["unsupportedField"] = True
        import jsonschema
        with self.assertRaises(jsonschema.ValidationError):
            preparation.validate_document(schema, invalid)

    def test_platform_public_whole_object_baseline_is_preserved(self):
        rendered = documents(render(PLATFORM))
        old = [obj for key, obj in rendered.items() if not key[2].startswith(NAME)]
        self.assertEqual(len(old), 43)
        self.assertEqual(digest(old), "a42c644bf2f08c34b3fae24cf7d084891c0719143f537b7a02feddeaa1af7eb0")
        self.assertEqual(hashlib.sha256((PLATFORM / "charts/gateway-helm-1.8.1.tgz").read_bytes()).hexdigest(),
                         "5a632f35e784ba58938d7a360745c3d3e71a290244ee01aa22584dba8c5b06d8")
        self.assertNotIn("parametersRef", rendered["GatewayClass", "", "envoy"]["spec"])

    def test_lint_platform_service_and_management_root(self):
        for chart, values, namespace in [
            (PLATFORM, "kkamji_local_values.yaml", NAMESPACE),
            (SERVICE, "kkamji_local_values.yaml", NAMESPACE),
            (ROOT / "charts/argo-applications", "management_local_values.yaml", "argocd"),
        ]:
            result = subprocess.run([HELM, "lint", str(chart), "--strict", "--namespace", namespace,
                                     "-f", str(chart / values)], capture_output=True, text=True, timeout=90)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
