"""Fixed discovery-only source contract. No DNS/CNI/HTTPS or enrollment runtime proof."""
import copy
import json
import subprocess
from pathlib import Path
import unittest

import yaml

import test_keycloak_private_admin as admin

ROOT = Path(__file__).resolve().parents[1]
NAME = "keycloak-owner-enrollment"
FLAG = "keycloakOwnerDiscovery"
NAMESPACE = "envoy-gateway-system"
EXPECTED = {
    (obj["kind"], obj["metadata"]["namespace"], obj["metadata"]["name"]): obj
    for obj in json.loads((ROOT / "tests/fixtures/keycloak-owner-discovery/approved.json").read_text())
}


def render(chart, override=None, **kwargs):
    return admin.render(chart, override={FLAG: {"enabled": True}, **(override or {})}, **kwargs)


def discovery(objects):
    return {key: obj for key, obj in objects.items() if key[2].startswith(NAME)}


class OwnerDiscoveryTests(unittest.TestCase):
    def test_local_values_add_exact_approved_six_objects_with_existing_owners(self):
        platform = admin.documents(render(admin.PLATFORM))
        service = admin.documents(render(admin.SERVICE))
        self.assertEqual(discovery(platform), {key: obj for key, obj in EXPECTED.items()
                                             if key[0] in ("EnvoyProxy", "Gateway") or key[2].endswith("-deny-ingress")})
        self.assertEqual(discovery(service), {key: obj for key, obj in EXPECTED.items()
                                            if key[0] in ("HTTPRoute", "CiliumNetworkPolicy") or key[2].endswith("-server-ingress")})
        self.assertEqual({**discovery(platform), **discovery(service)}, EXPECTED)
        admin.assert_contract(self, {**admin.private(platform), **admin.private(service)})

    def test_defaults_off_and_explicit_disable_preserve_all_prior_objects(self):
        for chart, expected_delta in ((admin.PLATFORM, 3), (admin.SERVICE, 3)):
            with self.subTest(chart=chart.name):
                values = yaml.safe_load((chart / "values.yaml").read_text())
                self.assertEqual(values[FLAG], {"enabled": False})
                local = yaml.safe_load((chart / "kkamji_local_values.yaml").read_text())
                self.assertEqual(local[FLAG], {"enabled": True})
                # Raw defaults do not supply the public platform gateway config.
                # Retain that config while selecting both security features' defaults.
                defaults = {"keycloakAdminPrivate": {"enabled": False}, FLAG: {"enabled": False}}
                off = admin.documents(render(chart, defaults))
                self.assertFalse(discovery(off))
                if chart == admin.SERVICE:
                    self.assertEqual(admin.documents(admin.render(chart, local=False)), {})
                before = admin.documents(render(chart, {FLAG: {"enabled": False}}))
                after = admin.documents(render(chart))
                self.assertEqual(len(after) - len(before), expected_delta)
                self.assertEqual({key: obj for key, obj in after.items() if key not in discovery(after)}, before)
                self.assertFalse(discovery(before))
                # Sealed old contracts remain exact even alongside enrollment.
                if chart == admin.PLATFORM:
                    legacy = admin.private(after)
                    self.assertEqual({key: obj["spec"] for key, obj in legacy.items()},
                                     {key: spec for key, spec in admin.EXPECTED.items() if key in legacy})
                    old = [obj for key, obj in after.items() if key not in legacy and key not in discovery(after)]
                    self.assertEqual(len(old), 44)
                    self.assertEqual(admin.digest(old), "4dad73ddc2577124334104085ebfcfc2a8e0c8349c76ffd0b265ad7fe75a95a8")
                else:
                    self.assertEqual(admin.private(after), before)
        # No new app-of-apps entry is needed: both current owners already select local values.
        for path in (ROOT / "charts").glob("**/*values*.yaml"):
            if path.parent not in (admin.PLATFORM, admin.SERVICE):
                self.assertNotIn(FLAG, path.read_text(), str(path.relative_to(ROOT)))

    def test_exact_get_discovery_only_not_login_or_admin(self):
        route = admin.documents(render(admin.SERVICE))["HTTPRoute", NAMESPACE, NAME]
        self.assertEqual(route["spec"]["rules"][0]["matches"], [{"method": "GET", "path": {
            "type": "Exact", "value": "/realms/kkamji/.well-known/openid-configuration"}}])
        matches = route["spec"]["rules"][0]["matches"]
        allowed = lambda method, path: any(m["method"] == method and m["path"]["value"] == path for m in matches)
        path = "/realms/kkamji/.well-known/openid-configuration"
        self.assertTrue(allowed("GET", path))
        for method in ("HEAD", "POST", "PUT", "DELETE", "OPTIONS", "get"):
            self.assertFalse(allowed(method, path))
        for wrong in ("/", "/admin", "/realms/master", "/resources", "/realms/kkamji", path + "/",
                      path + "-extra", "/prefix" + path,
                      "/realms/kkamji/protocol/openid-connect/auth", "/realms/kkamji/protocol/openid-connect/token",
                      "/realms/kkamji/login-actions/authenticate", "/realms/kkamji/account"):
            self.assertFalse(allowed("GET", wrong))

    def test_existing_named_service_grant_reused_not_broadened(self):
        enabled = admin.documents(render(admin.SERVICE))
        grants = {key: obj for key, obj in enabled.items() if key[0] == "ReferenceGrant"}
        self.assertEqual(set(grants), {("ReferenceGrant", "keycloak", admin.NAME)})
        grant = next(iter(grants.values()))
        self.assertEqual(grant["spec"], admin.EXPECTED["ReferenceGrant", "keycloak", admin.NAME])
        route = enabled["HTTPRoute", NAMESPACE, NAME]
        self.assertEqual(route["spec"]["rules"][0]["backendRefs"], [{"group": "", "kind": "Service",
                         "name": "keycloak-service", "namespace": "keycloak", "port": 8080, "weight": 1}])
        for skip_schema in (False, True):
            result = render(admin.SERVICE, {"keycloakAdminPrivate": {"enabled": False}}, skip_schema=skip_schema)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("existing private admin named Service ReferenceGrant is required", result.stderr)

    def test_only_boolean_flag_no_scope_overrides_even_without_schema(self):
        invalid = [{"enabled": value} for value in ("true", "false", 0, 1, [], {}, None)]
        invalid += [value for value in (None, True, "true", [], "")]
        invalid += [{"enabled": enabled, field: value} for enabled in (False, True) for field, value in (
            ("hostname", "*.kkamji.net"), ("path", "/"), ("method", "POST"),
            ("backendPort", 9000), ("parentRef", "kkamji"), ("mergeGateways", True),
            ("envoyService", {"type": "LoadBalancer"}), ("podLabels", {}),
            ("accessLog", {"disable": False}), ("extraObjects", []), ("unknown", True))]
        for chart in (admin.PLATFORM, admin.SERVICE):
            for payload in invalid:
                for skip_schema in (False, True):
                    with self.subTest(chart=chart.name, payload=payload, skip_schema=skip_schema):
                        result = render(chart, {FLAG: payload}, skip_schema=skip_schema)
                        self.assertNotEqual(result.returncode, 0)
                        if skip_schema:
                            self.assertIn("only boolean keycloakOwnerDiscovery.enabled is supported", result.stderr)
                        else:
                            self.assertIn(FLAG, result.stderr)

    def test_enabled_refuses_wrong_namespace_and_release(self):
        for chart in (admin.PLATFORM, admin.SERVICE):
            for namespace, release in (("default", chart.name), (NAMESPACE, "other")):
                for skip_schema in (False, True):
                    with self.subTest(chart=chart.name, namespace=namespace, release=release, skip_schema=skip_schema):
                        result = render(chart, namespace=namespace, release=release, skip_schema=skip_schema,
                                        override={"keycloakAdminPrivate": {"enabled": chart == admin.SERVICE}})
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn("exact namespace/release identity required", result.stderr)

    def test_additive_server_policy_requires_all_labels_namespace_and_tcp8080(self):
        import test_keycloak_preparation as prep
        service = admin.documents(render(admin.SERVICE))
        policy = service["NetworkPolicy", "keycloak", NAME + "-server-ingress"]
        proxy = {**admin.PROXY, "gateway.envoyproxy.io/owning-gateway-name": NAME, "kkamji.net/access": NAME}
        old = prep.KeycloakPreparationTests.render(prep.APP)
        policies = [obj for obj in old if obj["kind"] == "NetworkPolicy"]
        policies += [obj for obj in admin.private(service).values() if obj["kind"] == "NetworkPolicy"]
        self.assertFalse(prep.ingress_allowed(policies, admin.SERVER, proxy, NAMESPACE, 8080))
        policies.append(policy)
        self.assertTrue(prep.ingress_allowed(policies, admin.SERVER, proxy, NAMESPACE, 8080))
        self.assertEqual(policy["spec"]["ingress"][0]["ports"], [{"port": 8080, "protocol": "TCP"}])
        for field in proxy:
            wrong = {key: value for key, value in proxy.items() if key != field}
            self.assertFalse(prep.ingress_allowed(policies, admin.SERVER, wrong, NAMESPACE, 8080), field)
        for namespace in ("default", "keycloak", "monitoring"):
            self.assertFalse(prep.ingress_allowed(policies, admin.SERVER, proxy, namespace, 8080))
        for port in (80, 443, 5432, 9000, 10443, 19000, 19001):
            self.assertFalse(prep.ingress_allowed(policies, admin.SERVER, proxy, NAMESPACE, port))
        self.assertTrue(prep.ingress_allowed(policies, admin.SERVER, prep.GATEWAY_LABELS, NAMESPACE, 8080))
        platform = admin.documents(render(admin.PLATFORM))
        deny = platform["NetworkPolicy", NAMESPACE, NAME + "-deny-ingress"]
        self.assertTrue(prep.selector_matches(deny["spec"]["podSelector"], proxy))
        for target in (prep.GATEWAY_LABELS, admin.PROXY):
            self.assertFalse(prep.selector_matches(deny["spec"]["podSelector"], target))
        for port in (443, 10443, 19000, 19001):
            self.assertFalse(prep.ingress_allowed([deny], proxy, {}, "default", port))

    def test_pinned_envoyproxy_schema_and_clusterip_dns_logging_contract(self):
        import test_keycloak_preparation as prep
        rendered = admin.documents(render(admin.PLATFORM))
        proxy = rendered["EnvoyProxy", NAMESPACE, NAME]
        crd = rendered["CustomResourceDefinition", "", "envoyproxies.gateway.envoyproxy.io"]
        prep.validate_document(prep.crd_schema(crd, "v1alpha1"), proxy)
        for kind, crd_name, document in (
            ("Gateway", "gateways.gateway.networking.k8s.io", rendered["Gateway", NAMESPACE, NAME]),
            ("HTTPRoute", "httproutes.gateway.networking.k8s.io",
             admin.documents(render(admin.SERVICE))["HTTPRoute", NAMESPACE, NAME]),
        ):
            with self.subTest(kind=kind):
                schema = prep.crd_schema(rendered["CustomResourceDefinition", "", crd_name], "v1")
                prep.validate_document(schema, document)
        self.assertEqual(proxy["spec"]["provider"]["kubernetes"]["envoyService"], {
            "type": "ClusterIP", "annotations": {admin.DNS_KEY: "keycloak-owner-disabled"}})
        self.assertEqual(proxy["spec"]["telemetry"], {"accessLog": {"disable": True}})
        self.assertEqual(proxy["spec"]["logging"], {"level": {"default": "warn"}})
        service = admin.documents(render(admin.SERVICE))
        for kind, objects in (("Gateway", rendered), ("HTTPRoute", service)):
            self.assertEqual(objects[kind, NAMESPACE, NAME]["metadata"]["annotations"],
                             {admin.DNS_KEY: "keycloak-owner-disabled"})

    def test_fixed_contract_rejects_broadened_or_extra_objects(self):
        source = {**discovery(admin.documents(render(admin.PLATFORM))),
                  **discovery(admin.documents(render(admin.SERVICE)))}
        self.assertEqual(source, EXPECTED)
        mutations = [
            (("HTTPRoute", NAMESPACE, NAME), ("spec", "rules", 0, "matches", 0, "method"), "POST"),
            (("HTTPRoute", NAMESPACE, NAME), ("spec", "rules", 0, "matches", 0, "path", "type"), "PathPrefix"),
            (("HTTPRoute", NAMESPACE, NAME), ("spec", "rules", 0, "matches", 0, "path", "value"), "/"),
            (("HTTPRoute", NAMESPACE, NAME), ("spec", "rules", 0, "matches"), [{}]),
            (("HTTPRoute", NAMESPACE, NAME), ("spec", "parentRefs", 0, "name"), "kkamji"),
            (("EnvoyProxy", NAMESPACE, NAME), ("spec", "provider", "kubernetes", "envoyService", "type"), "NodePort"),
            (("EnvoyProxy", NAMESPACE, NAME), ("spec", "mergeGateways"), True),
            (("EnvoyProxy", NAMESPACE, NAME), ("spec", "telemetry", "accessLog", "disable"), False),
            (("Gateway", NAMESPACE, NAME), ("spec", "listeners", 0, "allowedRoutes", "namespaces", "from"), "All"),
            (("NetworkPolicy", NAMESPACE, NAME + "-deny-ingress"), ("spec", "podSelector"), {}),
            (("NetworkPolicy", NAMESPACE, NAME + "-deny-ingress"), ("spec", "ingress"), [{}]),
            (("NetworkPolicy", "keycloak", NAME + "-server-ingress"), ("spec", "ingress", 0, "from"), [{}]),
            (("NetworkPolicy", "keycloak", NAME + "-server-ingress"), ("spec", "ingress", 0, "ports", 0, "port"), 9000),
            (("CiliumNetworkPolicy", NAMESPACE, NAME + "-prometheus-ingress"), ("spec", "ingress", 0, "fromEndpoints"), [{}]),
            (("CiliumNetworkPolicy", NAMESPACE, NAME + "-prometheus-ingress"), ("spec", "ingress", 0, "toPorts", 0, "ports", 0, "port"), "19000"),
            (("CiliumNetworkPolicy", NAMESPACE, NAME + "-prometheus-ingress"), ("spec", "ingress", 0, "toPorts", 0, "rules", "http", 0, "path"), "/stats"),
        ]
        mutations += [(key, ("metadata", "annotations"), value)
                      for key in (("Gateway", NAMESPACE, NAME), ("HTTPRoute", NAMESPACE, NAME))
                      for value in ({}, {admin.DNS_KEY: "dns-controller"}, {"external-dns.alpha.kubernetes.io/exclude": "true"})]
        for extra in (True, False):
            changed = copy.deepcopy(source)
            if extra:
                changed["Ingress", NAMESPACE, NAME + "-unexpected"] = {}
            else:
                changed.pop(("HTTPRoute", NAMESPACE, NAME))
            with self.assertRaises(AssertionError):
                self.assertEqual(changed, EXPECTED)
        for key, path, value in mutations:
            with self.subTest(identity=key, path=path):
                changed = copy.deepcopy(source)
                target = changed[key]
                for field in path[:-1]:
                    target = target[field]
                target[path[-1]] = value
                with self.assertRaises(AssertionError):
                    self.assertEqual(changed, EXPECTED)

    def test_metrics_policy_requires_exact_prometheus_identity_and_http_get(self):
        policy = admin.documents(render(admin.SERVICE))["CiliumNetworkPolicy", NAMESPACE, NAME + "-prometheus-ingress"]
        proxy = {**admin.PROXY, "gateway.envoyproxy.io/owning-gateway-name": NAME, "kkamji.net/access": NAME}
        self.assertTrue(admin.metrics_exception_allows(policy, proxy, admin.PROMETHEUS))
        for field in admin.PROMETHEUS:
            for value in (None, "default", "other"):
                with self.subTest(source_field=field, value=value):
                    self.assertFalse(admin.metrics_exception_allows(policy, proxy, {**admin.PROMETHEUS, field: value}))
        for field in proxy:
            for value in (None, "kkamji", admin.NAME):
                with self.subTest(target_field=field, value=value):
                    self.assertFalse(admin.metrics_exception_allows(policy, {**proxy, field: value}, admin.PROMETHEUS))
        for port in (80, 443, 8080, 10443, 19000, 19002):
            self.assertFalse(admin.metrics_exception_allows(policy, proxy, admin.PROMETHEUS, port=port))
        for method in ("HEAD", "POST", "PUT", "DELETE", "get"):
            self.assertFalse(admin.metrics_exception_allows(policy, proxy, admin.PROMETHEUS, method=method))
        for path in ("/", "/config_dump", "/ready", "/stats", "/stats/prometheus/", "/stats/prometheus?format=json"):
            self.assertFalse(admin.metrics_exception_allows(policy, proxy, admin.PROMETHEUS, path=path))

    def test_existing_ci_covers_discovery_templates_schema_fixture_and_suite(self):
        workflow = yaml.load((ROOT / ".github/workflows/keycloak-lint.yml").read_text(), Loader=yaml.BaseLoader)
        paths = {
            "charts/envoy-gateway/templates/keycloak-owner-discovery.tpl",
            "charts/envoy-gateway/values.schema.json",
            "charts/keycloak-admin-access/**",
            "tests/test_keycloak*.py",
            "tests/fixtures/keycloak-owner-discovery/**",
        }
        for event in ("pull_request", "push"):
            self.assertTrue(paths.issubset(workflow["on"][event]["paths"]), event)
        steps = workflow["jobs"]["validate"]["steps"]
        self.assertIn({"uses": "azure/setup-helm@v4", "with": {"version": "v4.2.1"}}, steps)
        self.assertIn("test_keycloak*.py", "\n".join(step.get("run", "") for step in steps))

    def test_targeted_lint_enabled_disabled_and_negative_template_guard(self):
        for chart in (admin.PLATFORM, admin.SERVICE):
            for enabled in (False, True):
                result = subprocess.run([admin.HELM, "lint", str(chart), "--strict", "-n", NAMESPACE,
                                         "--kube-version", "1.36.1", "-f", str(chart / "kkamji_local_values.yaml"),
                                         "--set", FLAG + ".enabled=" + str(enabled).lower()],
                                        capture_output=True, text=True, timeout=90)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            for subcommand in ("lint", "template"):
                command = [admin.HELM, subcommand]
                if subcommand == "template":
                    command.append(chart.name)
                command += [str(chart), "-n", NAMESPACE, "-f", str(chart / "kkamji_local_values.yaml"),
                            "--set", FLAG + ".path=/"]
                # Helm lint may log template fail() as INFO, so its negative gate
                # is the values schema. Template must also fail with schema bypassed.
                if subcommand == "template":
                    command.append("--skip-schema-validation")
                result = subprocess.run(command, capture_output=True, text=True, timeout=90)
                self.assertNotEqual(result.returncode, 0)
                if subcommand == "template":
                    self.assertIn("only boolean keycloakOwnerDiscovery.enabled is supported", result.stderr)
                else:
                    self.assertIn(FLAG, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
