"""Offline staged consumer contracts. No provider, credential or cluster access.

HELM=/path/to/helm uv run --no-project --with pyyaml --with jsonschema --with jmespath \
    python -m unittest discover -s tests -p test_keycloak_consumers.py -v
"""

import configparser
import copy
import functools
import hashlib
import json
import os
import re
import subprocess
import tarfile
import unittest
from pathlib import Path

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[1]
HELM = os.environ.get("HELM", "helm")
ISSUER = "https://sso.kkamji.net/realms/kkamji"
CHARTS = {"argocd": "argocd", "kube-prometheus-stack": "monitoring",
          "cilium": "kube-system", "hindsight": "hindsight"}
EDGE = {"hubble": "cilium", "prometheus": "kube-prometheus-stack",
        "alertmanager": "kube-prometheus-stack", "hindsight-ui": "hindsight"}


def mode_args(chart, mode):
    tls = ["--set", "keycloakSSO.backendTLSReady=true"] if mode != "legacy" else []
    if chart == "kube-prometheus-stack":
        return [*tls, "--set", f"keycloakSSO.prometheus.mode={mode}", "--set",
                f"keycloakSSO.alertmanager.mode={mode}"]
    return [*tls, "--set", f"keycloakSSO.mode={mode}"]


@functools.lru_cache(maxsize=None)
def render(chart, mode="legacy", *extra):
    cmd = [HELM, "template", chart, str(ROOT / "charts" / chart), "-n", CHARTS[chart],
           "--skip-tests", "--kube-version", "1.36.1", "-f",
           str(ROOT / "charts" / chart / "kkamji_local_values.yaml"),
           *mode_args(chart, mode), *extra]
    return subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=90)


def docs(result):
    if result.returncode:
        raise AssertionError("Helm render refused (stderr sha256=" + hashlib.sha256(result.stderr.encode()).hexdigest() + ")")
    try:
        return [d for d in yaml.safe_load_all(result.stdout) if d]
    except yaml.YAMLError:
        raise AssertionError("Helm YAML parse refused (render withheld)") from None


def index(chart, mode="legacy", *extra):
    return {(d["kind"], d["metadata"]["name"]): d for d in docs(render(chart, mode, *extra))}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def strict_schema(node):
    """OpenAPI structural fields plus explicit unknown-field rejection for owned spec."""
    node = copy.deepcopy(node)
    if isinstance(node, dict):
        for key, value in list(node.items()):
            if isinstance(value, dict):
                node[key] = {k: strict_schema(v) for k, v in value.items()} if key in ("properties", "$defs", "definitions") else strict_schema(value)
            elif isinstance(value, list):
                node[key] = [strict_schema(v) for v in value]
        if "properties" in node and "additionalProperties" not in node and not node.get("x-kubernetes-preserve-unknown-fields"):
            node["additionalProperties"] = False
    return node


class EdgeTests(unittest.TestCase):
    def test_canary_has_cookie_only_signed_group_policy_on_separate_route(self):
        for client, chart in EDGE.items():
            with self.subTest(client=client):
                objects = index(chart, "canary")
                policy = objects.get(("SecurityPolicy", f"{client}-keycloak"))
                self.assertIsNotNone(policy, "missing Keycloak canary policy")
                spec = policy["spec"]
                self.assertEqual(spec["targetRefs"], [{"group": "gateway.networking.k8s.io",
                    "kind": "HTTPRoute", "name": f"{client}-keycloak-canary"}])
                oidc = spec["oidc"]
                host = "hindsight" if client == "hindsight-ui" else client
                self.assertEqual(oidc["redirectURL"], f"https://{host}.kkamji.net/oauth2/keycloak-callback")
                self.assertEqual(oidc["clientID"], client)
                self.assertEqual(oidc["provider"]["issuer"], ISSUER)
                self.assertEqual(oidc["scopes"], ["openid", "profile", "groups"])
                self.assertNotIn("cookieDomain", oidc)
                self.assertFalse(oidc["forwardAccessToken"])
                self.assertFalse(oidc["passThroughAuthHeader"])
                self.assertFalse(oidc["disableTokenEncryption"])
                self.assertNotIn("forwardIDToken", oidc)
                jwt = spec["jwt"]
                self.assertFalse(jwt["optional"])
                provider, = jwt["providers"]
                self.assertEqual(provider["issuer"], ISSUER)
                self.assertEqual(provider["audiences"], [client])
                self.assertEqual(provider["remoteJWKS"]["uri"], ISSUER + "/protocol/openid-connect/certs")
                self.assertEqual(provider["extractFrom"], {"cookies": [oidc["cookieNames"]["idToken"]]})
                self.assertNotEqual(oidc["cookieNames"]["idToken"], "HindsightGoogleIdToken")
                authz = spec["authorization"]
                self.assertEqual(authz["defaultAction"], "Deny")
                allow, = authz["rules"]
                self.assertEqual(allow["action"], "Allow")
                self.assertEqual(allow["principal"], {"jwt": {"provider": provider["name"],
                    "claims": [{"name": "groups", "valueType": "StringArray", "values": ["/homelab-admins"]}]}})
                route = objects["HTTPRoute", f"{client}-keycloak-canary"]["spec"]
                self.assertEqual(route["hostnames"], [f"{host}.kkamji.net"])
                paths = [m["path"]["value"] for r in route["rules"] for m in r["matches"]]
                self.assertEqual(paths, ["/sso-canary", "/oauth2/keycloak-callback", "/oauth2/keycloak-logout"])

    def test_canary_preserves_existing_main_routes_policies_and_workloads(self):
        for chart in set(EDGE.values()):
            old, canary = index(chart), index(chart, "canary")
            for key, obj in old.items():
                with self.subTest(chart=chart, resource=key):
                    self.assertEqual(digest(obj), digest(canary[key]))

    def test_only_replaces_legacy_policy_not_machine_api(self):
        for client, chart in EDGE.items():
            with self.subTest(client=client):
                old, new = index(chart), index(chart, "only")
                active = "hindsight-ui" if client == "hindsight-ui" else client
                self.assertEqual(new["SecurityPolicy", f"{client}-keycloak"]["spec"]["targetRefs"][0]["name"], active)
                self.assertNotIn(("HTTPRoute", f"{client}-keycloak-canary"), new)
                legacy = "hindsight-ui-owner" if client == "hindsight-ui" else f"{client}-basic-auth"
                self.assertNotIn(("SecurityPolicy", legacy), new)
                before, after = copy.deepcopy(old["HTTPRoute", active]), copy.deepcopy(new["HTTPRoute", active])
                for rule in after["spec"]["rules"]:
                    filters = [f for f in rule.get("filters", []) if f["type"] != "RequestHeaderModifier"]
                    if filters:
                        rule["filters"] = filters
                    else:
                        rule.pop("filters", None)
                self.assertEqual(before, after)
                if chart == "hindsight":
                    for key in old:
                        if key not in (("SecurityPolicy", "hindsight-ui-owner"), ("HTTPRoute", "hindsight-ui")):
                            self.assertEqual(digest(new[key]), digest(old[key]), key)

    def test_modes_reject_typos_and_default_preserves_legacy(self):
        for chart in set(EDGE.values()):
            with self.subTest(chart=chart):
                self.assertNotEqual(render(chart, "typo").returncode, 0)
                self.assertFalse(any(name.endswith("-keycloak") for kind, name in index(chart) if kind == "SecurityPolicy"))

    def test_upstream_tls_uses_hostname_validated_backend_not_legacy_url_helper(self):
        for client, chart in EDGE.items():
            with self.subTest(client=client):
                objects = index(chart, "canary")
                spec = objects["SecurityPolicy", f"{client}-keycloak"]["spec"]
                backend = objects.get(("Backend", f"{client}-keycloak-provider"))
                self.assertIsNotNone(backend, "URL-only Gateway helper checks CA but lacks SAN validation")
                assert backend is not None
                self.assertEqual(backend["spec"], {"endpoints": [{"fqdn": {"hostname": "sso.kkamji.net", "port": 443}}],
                    "tls": {"sni": "sso.kkamji.net", "wellKnownCACertificates": "System", "insecureSkipVerify": False}})
                reference = [{"group": "gateway.envoyproxy.io", "kind": "Backend",
                              "name": f"{client}-keycloak-provider", "port": 443, "weight": 1}]
                self.assertEqual(spec["oidc"]["provider"]["backendRefs"], reference)
                self.assertEqual(spec["jwt"]["providers"][0]["remoteJWKS"]["backendRefs"], reference)
                self.assertEqual(spec["oidc"]["provider"]["authorizationEndpoint"], ISSUER + "/protocol/openid-connect/auth")
                self.assertEqual(spec["oidc"]["provider"]["tokenEndpoint"], ISSUER + "/protocol/openid-connect/token")

    def test_keycloak_ui_strips_forged_identity_headers_without_touching_machine_auth(self):
        for client, chart in EDGE.items():
            with self.subTest(client=client):
                for mode in ("canary", "only"):
                    route = f"{client}-keycloak-canary" if mode == "canary" else client
                    obj = index(chart, mode)["HTTPRoute", route]
                    removals = {name.lower() for rule in obj["spec"]["rules"]
                                for f in rule.get("filters", []) if f["type"] == "RequestHeaderModifier"
                                for name in f["requestHeaderModifier"].get("remove", [])}
                    self.assertTrue({"x-forwarded-user", "x-forwarded-email", "x-forwarded-groups",
                                     "x-auth-request-user", "x-auth-request-email", "x-auth-request-groups"} <= removals)
                    self.assertNotIn("authorization", removals)
                    self.assertNotIn("x-hindsight-client-key", removals)

    def test_source_secret_references_are_distinct_property_scoped_orphan_retain(self):
        for chart in CHARTS:
            for mode in ("canary", "only"):
                objects = NativeTests().native(chart, mode) if chart == "argocd" else index(chart, mode)
                if chart == "kube-prometheus-stack":
                    objects = {**objects, **NativeTests().native(chart, mode)}
                clients = {c for c, ch in EDGE.items() if ch == chart}
                clients |= {"argocd"} if chart == "argocd" else {"grafana"} if chart == "kube-prometheus-stack" else set()
                for client in clients:
                    es = objects["ExternalSecret", f"{client}-keycloak-oidc"]["spec"]
                    self.assertEqual(es["secretStoreRef"], {"name": "parameter-store", "kind": "ClusterSecretStore"})
                    self.assertEqual(es["target"]["creationPolicy"], "Orphan")
                    self.assertEqual(es["target"]["deletionPolicy"], "Retain")
                    self.assertEqual(es["data"], [{"secretKey": "client-secret", "remoteRef": {
                        "key": f"/kkamji/keycloak/clients/{client}", "property": "client_secret"}}])
                    self.assertNotIn(("Secret", f"{client}-keycloak-oidc"), objects)
                    self.assertNotIn("dataFrom", es)

    def test_security_policies_validate_against_pinned_vendor_schema(self):
        archive = ROOT / "charts/envoy-gateway/charts/gateway-helm-1.8.1.tgz"
        schemas = {}
        with tarfile.open(archive) as vendor:
            for member in vendor.getmembers():
                if any(member.name.endswith(suffix) for suffix in (
                    "gateway.envoyproxy.io_securitypolicies.yaml", "gateway.envoyproxy.io_backends.yaml",
                    "gateway.envoyproxy.io_httproutefilters.yaml", "gateway.envoyproxy.io_envoyextensionpolicies.yaml")):
                    stream = vendor.extractfile(member)
                    assert stream is not None
                    crd = yaml.safe_load(stream)
                    version = next(v for v in crd["spec"]["versions"] if v["name"] == "v1alpha1")
                    schemas[crd["spec"]["names"]["kind"]] = strict_schema(version["schema"]["openAPIV3Schema"]["properties"]["spec"])
        for chart in set(EDGE.values()):
            for mode in ("legacy", "canary", "only"):
                objects = index(chart, mode)
                if chart == "kube-prometheus-stack":
                    objects = {**objects, **NativeTests().native(chart, mode if mode != "legacy" else "canary")}
                for (kind, name), obj in objects.items():
                    if kind in schemas:
                        jsonschema.Draft7Validator(schemas[kind]).validate(obj["spec"])
        malformed = copy.deepcopy(index("cilium", "canary")["SecurityPolicy", "hubble-keycloak"]["spec"])
        malformed["oidc"]["enablePKCE"] = True
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.Draft7Validator(schemas["SecurityPolicy"]).validate(malformed)


class NativeTests(unittest.TestCase):
    def native(self, chart, mode="canary", *extra):
        path = ROOT / "charts" / chart
        flags = ["-f", str(path / "keycloak-canary-values.yaml")]
        if mode == "only":
            flags += ["-f", str(path / "keycloak-only-values.yaml"), "--set",
                      "keycloakSSO.adminTokenMigrationConfirmed=true" if chart == "argocd"
                      else "keycloakSSO.grafana.cutoverApproved=true"]
        if chart == "argocd":
            flags += ["--set", f"keycloakSSO.mode={mode}"]
        else:
            flags += ["--set", "keycloakSSO.backendTLSReady=true", "--set",
                      "keycloakSSO.grafana.dataPreservationReady=true", "--set",
                      "keycloakSSO.grafana.accessLogsSafe=true"]
        return index(chart, "legacy", *flags, *extra)

    def test_grafana_owner_predicate_is_private_and_not_a_public_role_mapping(self):
        from test_grafana_keycloak import grafana_ini
        ini = grafana_ini(self.native("kube-prometheus-stack"))
        self.assertEqual(ini["auth.jwt"]["username_attribute_path"], "$__env{KEYCLOAK_GRAFANA_USERNAME_ATTRIBUTE_PATH}")
        self.assertEqual(ini["auth.jwt"]["expect_claims"], "$__env{KEYCLOAK_GRAFANA_EXPECT_CLAIMS}")
        self.assertTrue(ini["auth.jwt"].getboolean("skip_org_role_sync"))
        self.assertFalse(ini["auth.generic_oauth"].getboolean("enabled"))

    def test_argocd_native_canary_and_final_are_fail_closed(self):
        for mode in ("canary", "only"):
            with self.subTest(mode=mode):
                objects = self.native("argocd", mode)
                cm = objects["ConfigMap", "argocd-cm"]["data"]
                oidc = yaml.safe_load(cm["oidc.config"])
                self.assertEqual(cm["url"], "https://argocd.kkamji.net")
                self.assertEqual(cm["admin.enabled"], "true" if mode == "canary" else "false")
                self.assertEqual(cm["users.anonymous.enabled"], "false")
                self.assertEqual(oidc["issuer"], ISSUER)
                self.assertEqual(oidc["clientID"], "argocd")
                self.assertEqual(oidc["clientSecret"], "$argocd-keycloak-oidc:client-secret")
                self.assertTrue(oidc["enablePKCEAuthentication"])
                rbac = objects["ConfigMap", "argocd-rbac-cm"]["data"]
                self.assertEqual(rbac["policy.default"], "role:no-access")
                self.assertEqual(rbac["policy.csv"].strip(), "g, /argocd-admins, role:admin")
                self.assertEqual(rbac["scopes"], "[groups]")
                secret = objects["ExternalSecret", "argocd-keycloak-oidc"]["spec"]
                self.assertEqual(secret["target"]["template"]["metadata"]["labels"]["app.kubernetes.io/part-of"], "argocd")
                old = index("argocd")
                for key in old:
                    if key[0] in ("Deployment", "StatefulSet", "Service", "HTTPRoute", "Secret", "ExternalSecret", "ClusterExternalSecret"):
                        before, after = copy.deepcopy(old[key]), copy.deepcopy(objects[key])
                        # Native CM changes cause the upstream checksum-triggered restart.
                        # Ignore ONLY that exact checksum; preserve every workload field.
                        if key[0] in ("Deployment", "StatefulSet"):
                            for workload in (before, after):
                                workload["spec"]["template"].get("metadata", {}).get("annotations", {}).pop("checksum/cm", None)
                        self.assertEqual(digest(before), digest(after), key)

    def test_grafana_native_jwt_preserves_sidecars_storage_resources_and_admin_inputs(self):
        from test_grafana_keycloak import grafana_ini
        for mode in ("canary", "only"):
            objects = self.native("kube-prometheus-stack", mode)
            ini = grafana_ini(objects)
            self.assertTrue(ini["auth.jwt"].getboolean("enabled"))
            self.assertFalse(ini["auth.jwt"].getboolean("auto_sign_up"))
            self.assertTrue(ini["auth.jwt"].getboolean("skip_org_role_sync"))
            self.assertEqual(ini["auth"].getboolean("disable_login_form"), mode == "only")
            self.assertTrue(ini["auth.basic"].getboolean("enabled"))
            deployment, = [d for (k, n), d in objects.items() if k == "Deployment" and n.endswith("-grafana")]
            old, = [d for (k, n), d in index("kube-prometheus-stack").items() if k == "Deployment" and n.endswith("-grafana")]
            old_containers = {c["name"]: c for c in old["spec"]["template"]["spec"]["containers"]}
            for container in deployment["spec"]["template"]["spec"]["containers"]:
                if container["name"] != "grafana":
                    self.assertEqual(container, old_containers[container["name"]], "machine sidecar changed")
                else:
                    self.assertEqual(container.get("resources"), old_containers["grafana"].get("resources"))
                    env = {e["name"]: e for e in container["env"]}
                    for e in old_containers["grafana"]["env"]:
                        self.assertEqual(env[e["name"]], e)
            self.assertEqual(deployment["spec"]["template"]["spec"]["volumes"], old["spec"]["template"]["spec"]["volumes"])
            if mode == "only":
                denied = objects["HTTPRoute", "grafana-public-basic-deny"]["spec"]["rules"][0]
                pattern = denied["matches"][0]["headers"][0]["value"]
                for value in ("Basic abc", "bAsIc abc", "BASIC abc"):
                    self.assertIsNotNone(re.fullmatch(pattern, value))
                self.assertIsNone(re.fullmatch(pattern, "Bearer service-account-token"))
                self.assertEqual(objects["HTTPRouteFilter", "grafana-deny-public-basic"]["spec"]["directResponse"]["statusCode"], 403)


class GuardTests(unittest.TestCase):
    def test_edges_require_backend_api_confirmation_and_exact_https_routes(self):
        for chart in set(EDGE.values()):
            with self.subTest(chart=chart):
                self.assertNotEqual(render(chart, "canary", "--set", "keycloakSSO.backendTLSReady=false").returncode, 0)
                override = "exposure.hostname=wrong.kkamji.net" if chart == "hindsight" else (
                    "gatewayRoutes.hubble.host=wrong.kkamji.net" if chart == "cilium"
                    else "gatewayRoutes.prometheus.host=wrong.kkamji.net")
                self.assertNotEqual(render(chart, "canary", "--set", override).returncode, 0)
                gateway = "exposure.gateway.sectionName=http" if chart == "hindsight" else "gatewayRef.sectionName=http"
                self.assertNotEqual(render(chart, "canary", "--set", gateway).returncode, 0)
        self.assertFalse(any(d["kind"] in ("HTTPRoute", "SecurityPolicy", "Backend")
                             for d in docs(render("hindsight", "canary", "--set", "exposure.enabled=false"))))

    def test_native_wrong_issuer_group_callback_tls_and_final_approval_are_rejected(self):
        argo = ROOT / "charts/argocd/keycloak-canary-values.yaml"
        oidc = yaml.safe_load(yaml.safe_load(argo.read_text())["argocd"]["configs"]["cm"]["oidc.config"])
        invalid_oidc = yaml.safe_dump({**oidc, "issuer": ISSUER + "/"})
        cases = [("argocd", "canary", ["--set-string", "argocd.configs.cm.oidc\\.config=" + invalid_oidc]),
                 ("argocd", "canary", ["--set-string", "argocd.configs.cm.url=https://wrong.kkamji.net"]),
                 ("argocd", "canary", ["--set-string", "argocd.configs.cm.oidc\\.tls\\.insecure\\.skip\\.verify=true"]),
                 ("argocd", "canary", ["--set-string", "argocd.configs.rbac.policy\\.default=role:admin"]),
                 ("argocd", "only", ["--set", "keycloakSSO.adminTokenMigrationConfirmed=false"]),
                 ("kube-prometheus-stack", "canary", ["--set-string", "kube-prometheus-stack.grafana.grafana\\.ini.server.root_url=https://wrong.kkamji.net"]),
                 ("kube-prometheus-stack", "canary", ["--set", "kube-prometheus-stack.grafana.grafana\\.ini.auth\\.jwt.tls_skip_verify_insecure=true"]),
                 ("kube-prometheus-stack", "canary", ["--set", "kube-prometheus-stack.grafana.grafana\\.ini.auth\\.jwt.auto_sign_up=true"]),
                 ("kube-prometheus-stack", "only", ["--set", "keycloakSSO.grafana.cutoverApproved=false"])]
        for chart, mode, flags in cases:
            with self.subTest(chart=chart, mode=mode, flags=flags):
                with self.assertRaises(AssertionError):
                    NativeTests().native(chart, mode, *flags)

    def test_native_enable_without_overlay_is_rejected(self):
        self.assertNotEqual(render("argocd", "canary").returncode, 0)
        self.assertNotEqual(render("kube-prometheus-stack", "legacy", "--set", "keycloakSSO.grafana.mode=canary").returncode, 0)


if __name__ == "__main__":
    unittest.main()
