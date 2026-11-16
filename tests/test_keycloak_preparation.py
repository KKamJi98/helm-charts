"""Offline preparation contract tests. No network, cluster, image or credential access.

Run with HELM_BIN pointing explicitly to verified Helm 4.2.1 and TMPDIR inside
this task's evidence root. Requires the already available PyYAML/jsonschema.
Structural validation and source-derived models are not admission/runtime proof.
"""
import copy
import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[1]
OPERATOR = ROOT / "charts/keycloak-operator"
APP = ROOT / "charts/keycloak-idp"
EXAMPLES = ROOT / "examples/keycloak-preparation"
HELM = os.environ.get("HELM_BIN", "")
SERVER_IMAGE = "quay.io/keycloak/keycloak@sha256:c68e286cacd87b942ac1939a0a1481461109d6acd3a57dc496969a319a76bbf0"
OPERATOR_IMAGE = "quay.io/keycloak/keycloak-operator@sha256:df890db951b595fe46f3f985301a38b76fcfcc264f06201c54dfaf28adeba19e"
POSTGRES_IMAGE = "ghcr.io/cloudnative-pg/postgresql:18.4-system-trixie@sha256:42708a75345b7a48fdd9257b071830783a97fd228529196b6313187a7198e185"
SOURCE_COMMIT = "e514445f9dcdabc5bdcf67cab56c1e49655de067"
RESOURCE_COMMIT = "79ba77fd65bb05a8300cd1396d6be9806a0f290f"
VENDOR_HASHES = {
    "vendor/README.md": "697ea8fde0c0621131b6cb3aaba32bf9c26320dfe16087deed5ac015da2a905e",
    "vendor/LICENSE.txt": "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30",
    "vendor/kubernetes/kubernetes.yml": "e1da7dd96a3f4bcea806ad67f13b695fc813d5f37257266bc037dcb21321e6e5",
    "vendor/kubernetes/kustomization.yml": "fd702341f6442d432190e6c83b82c2f105f8ba91b635a99bc300af29343265ac",
    "crds/keycloaks.k8s.keycloak.org-v1.yml": "20c51247cb6cbc6158098caabeaf6b429dc8c016e35829f5ddd9c468b7582667",
    "crds/keycloakrealmimports.k8s.keycloak.org-v1.yml": "8d552e1864d78117a07e535479ddb36e16a42b2695726c875f44828e1323edd4",
    "crds/keycloakoidcclients.k8s.keycloak.org-v1.yml": "15d9199822d1918438bd1d093eee3ec8406e7f9d0837c4527fd6da99c63b058a",
    "crds/keycloaksamlclients.k8s.keycloak.org-v1.yml": "7c69d146f610f3c40acf4466518e89615b6fce7ee2a03d75cd93b7a9a7bf259e",
}
SCHEMA_HASHES = {
    "schemas/cnpg-1.30-cluster.schema.json": "44ee1d0632632a5f3351de37114e35db92fc2b4ff07572546085dd578f6466cb",
    "schemas/eso-2.4.1-externalsecret.schema.json": "85cf677155c82d85032611d4d622b1e6efd09cbdd6731d8f1c65daad7ee161ff",
}
SERVER_LABELS = {
    "app": "keycloak",
    "app.kubernetes.io/instance": "keycloak",
    "app.kubernetes.io/managed-by": "keycloak-operator",
    "app.kubernetes.io/component": "server",
}
GATEWAY_LABELS = {
    "app.kubernetes.io/component": "proxy",
    "gateway.envoyproxy.io/owning-gateway-name": "kkamji",
    "gateway.envoyproxy.io/owning-gateway-namespace": "envoy-gateway-system",
}
CNPG_LABELS = {
    "app.kubernetes.io/name": "cloudnative-pg",
    "app.kubernetes.io/instance": "cloudnative-pg",
}


def documents(text):
    return [x for x in yaml.safe_load_all(text) if x]


def identity(obj):
    return obj["kind"], obj["metadata"]["name"]


def strict_schema(schema):
    """Offline unknown-field detection, not Kubernetes pruning or admission."""
    result = copy.deepcopy(schema)

    def walk(node):
        if isinstance(node, dict):
            if node.get("properties") and not node.get("x-kubernetes-preserve-unknown-fields"):
                node.setdefault("additionalProperties", False)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(result)
    return result


def crd_schema(crd, version):
    return next(v for v in crd["spec"]["versions"] if v["name"] == version)["schema"]["openAPIV3Schema"]


def validate_document(schema, document):
    # Kubernetes implicitly owns these envelope fields; Keycloak's generated
    # CRDs only declare spec/status at the root. Do not alter spec validation.
    schema = strict_schema(schema)
    envelope = schema.setdefault("properties", {})
    for field in ("apiVersion", "kind"):
        envelope.setdefault(field, {"type": "string"})
    envelope.setdefault("metadata", {"type": "object"})
    error = next(jsonschema.Draft7Validator(schema).iter_errors(document), None)
    if error is not None:
        # Never dump full rendered objects or gigantic upstream schemas.
        path = "/".join(str(x) for x in error.absolute_path)
        raise jsonschema.ValidationError(f"{path}: {error.validator}") from None


def selector_matches(selector, labels):
    if not all(labels.get(k) == v for k, v in selector.get("matchLabels", {}).items()):
        return False
    for exp in selector.get("matchExpressions", []):
        key, op, values = exp["key"], exp["operator"], exp.get("values", [])
        if op == "In" and labels.get(key) not in values:
            return False
        if op == "NotIn" and labels.get(key) in values:
            return False
        if op == "Exists" and key not in labels:
            return False
        if op == "DoesNotExist" and key in labels:
            return False
    return True


def ingress_allowed(policies, target, source, namespace, port):
    """Model only selected additive Kubernetes ingress policy semantics."""
    selected = [p for p in policies if "Ingress" in p["spec"]["policyTypes"]
                and selector_matches(p["spec"]["podSelector"], target)]
    if not selected:
        return True
    for policy in selected:
        for rule in policy["spec"].get("ingress", []):
            if rule.get("ports") and not any(p["port"] == port and p.get("protocol", "TCP") == "TCP" for p in rule["ports"]):
                continue
            for peer in rule.get("from", [{}]):
                if "ipBlock" in peer:
                    raise AssertionError("No invented IP ranges in preparation policies")
                if "namespaceSelector" in peer:
                    if not selector_matches(peer["namespaceSelector"], {"kubernetes.io/metadata.name": namespace}):
                        continue
                elif namespace != "keycloak":
                    continue
                if selector_matches(peer.get("podSelector", {}), source):
                    return True
    return False


def cpu_m(value):
    value = str(value)
    return Decimal(value[:-1]) if value.endswith("m") else Decimal(value) * 1000


def memory_mi(value):
    value = str(value)
    if value.endswith("Gi"):
        return Decimal(value[:-2]) * 1024
    if value.endswith("Mi"):
        return Decimal(value[:-2])
    raise AssertionError("Unexpected resource quantity")


def resource_vector(resources):
    return tuple(fn(resources[side][resource]) for side, resource, fn in [
        ("requests", "cpu", cpu_m), ("requests", "memory", memory_mi),
        ("limits", "cpu", cpu_m), ("limits", "memory", memory_mi)])


def sum_vectors(*vectors):
    return tuple(sum(x) for x in zip(*vectors))


class KeycloakPreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not HELM:
            raise AssertionError("Set HELM_BIN explicitly to the verified Helm 4.2.1 binary")
        version = subprocess.run([HELM, "version", "--short"], capture_output=True, text=True, check=True).stdout.strip()
        if version != "v4.2.1+gd591a19":
            raise AssertionError("Final renderer must be v4.2.1+gd591a19, got " + version)
        cls.op = cls.render(OPERATOR)
        cls.app = cls.render(APP)
        cls.op_by = {identity(x): x for x in cls.op}
        cls.app_by = {identity(x): x for x in cls.app}
        cls.kc = cls.app_by[("Keycloak", "keycloak")]
        cls.db = cls.app_by[("Cluster", "keycloak-db")]
        cls.realm = yaml.safe_load((EXAMPLES / "realm-import.yaml.inactive").read_text())
        cls.policies = [o for o in cls.app if o["kind"] == "NetworkPolicy"]

    @staticmethod
    def command(chart, override=None, namespace="keycloak", release=None, skip_schema=False):
        release = release or ("keycloak-operator" if chart == OPERATOR else "keycloak")
        args = [HELM, "template", release, str(chart), "--namespace", namespace,
                "-f", str(chart / "kkamji_local_values.yaml"), "--include-crds", "--skip-tests", "--kube-version", "1.36.1"]
        if skip_schema:
            args += ["--skip-schema-validation"]
        if override is None:
            return subprocess.run(args, capture_output=True, text=True, check=False)
        with tempfile.TemporaryDirectory(prefix="keycloak-negative-") as tmp:
            path = Path(tmp) / "override.json"
            path.write_text(json.dumps(override))
            return subprocess.run(args + ["-f", str(path)], capture_output=True, text=True, check=False)

    @classmethod
    def render(cls, chart):
        result = cls.command(chart)
        if result.returncode:
            raise AssertionError(result.stderr)
        return documents(result.stdout)

    def test_lint_both_actual_charts(self):
        for chart in (OPERATOR, APP):
            with self.subTest(chart=chart.name):
                result = subprocess.run([HELM, "lint", str(chart), "-f", str(chart / "kkamji_local_values.yaml"), "--strict"], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertNotIn("dependencies", yaml.safe_load((chart / "Chart.yaml").read_text()))
                self.assertFalse((chart / "Chart.lock").exists(), "Do not invent dependency locks")

    def test_defaults_local_values_and_immutable_profiles_identical(self):
        for chart in (OPERATOR, APP):
            default = yaml.safe_load((chart / "values.yaml").read_text())
            self.assertEqual(default, yaml.safe_load((chart / "kkamji_local_values.yaml").read_text()))
            self.assertEqual(default, yaml.safe_load((chart / "files/preparation-profile.yaml").read_text()))
            args = [HELM, "template", chart.name if chart == OPERATOR else "keycloak", str(chart), "-n", "keycloak", "--include-crds", "--skip-tests", "--kube-version", "1.36.1"]
            rendered = subprocess.run(args, capture_output=True, text=True)
            self.assertEqual(rendered.returncode, 0, rendered.stderr)
            self.assertEqual(documents(rendered.stdout), self.op if chart == OPERATOR else self.app)

    def test_vendor_bytes_and_source_identity(self):
        manifest = json.loads((OPERATOR / "vendor-manifest.json").read_text())
        self.assertEqual(manifest["resourcesCommit"], RESOURCE_COMMIT)
        self.assertEqual(manifest["sourceCommit"], SOURCE_COMMIT)
        self.assertEqual({a["path"]: a["sha256"] for a in manifest["artifacts"]}, VENDOR_HASHES)
        for path, expected in VENDOR_HASHES.items():
            with self.subTest(path=path):
                self.assertEqual(hashlib.sha256((OPERATOR / path).read_bytes()).hexdigest(), expected)
        for artifact in manifest["artifacts"]:
            self.assertIn(RESOURCE_COMMIT, artifact["url"])
        self.assertEqual(manifest["images"], {"operator": OPERATOR_IMAGE, "keycloak": SERVER_IMAGE})

    def test_all_four_crds_preserved_and_structurally_valid(self):
        crds = [o for o in self.op if o["kind"] == "CustomResourceDefinition"]
        self.assertEqual(len(crds), 4)
        for path in (OPERATOR / "crds").glob("*.yml"):
            original = yaml.safe_load(path.read_text())
            self.assertEqual(self.op_by[identity(original)], original)
            self.assertEqual(original["spec"]["scope"], "Namespaced")
            self.assertNotIn("namespace", original["metadata"])
            for version in original["spec"]["versions"]:
                jsonschema.Draft7Validator.check_schema(version["schema"]["openAPIV3Schema"])
            storage = [v["name"] for v in original["spec"]["versions"] if v["storage"]]
            expected = "v2beta1" if original["spec"]["names"]["kind"] in ("Keycloak", "KeycloakRealmImport") else "v2alpha1"
            self.assertEqual(storage, [expected])
        upstream = yaml.safe_load((OPERATOR / "vendor/kubernetes/kustomization.yml").read_text())
        self.assertEqual(upstream["namespace"], "keycloak")
        self.assertEqual(len(upstream["resources"]), 5)
        self.assertIn("setRoleBindingSubjects: allServiceAccounts", upstream["transformers"][0])

    def test_only_explicit_namespace_subject_image_overlays(self):
        original = documents((OPERATOR / "vendor/kubernetes/kubernetes.yml").read_text())
        self.assertEqual(len(original), 14)
        for obj in original:
            expected = copy.deepcopy(obj)
            if obj["kind"] in ("ServiceAccount", "RoleBinding", "Service", "Deployment"):
                expected["metadata"]["namespace"] = "keycloak"
            if obj["kind"] in ("RoleBinding", "ClusterRoleBinding"):
                for subject in expected["subjects"]:
                    if subject["kind"] == "ServiceAccount":
                        subject["namespace"] = "keycloak"
            if obj["kind"] == "Deployment":
                for container in expected["spec"]["template"]["spec"]["containers"]:
                    container["image"] = OPERATOR_IMAGE
                    for env in container["env"]:
                        if env["name"] in ("kc.operator.keycloak.image", "RELATED_IMAGE_KEYCLOAK"):
                            env["value"] = SERVER_IMAGE
            self.assertEqual(self.op_by[identity(obj)], expected, identity(obj))

    def test_namespace_watch_rbac_subject_references_and_actual_cluster_authority(self):
        dep = self.op_by[("Deployment", "keycloak-operator")]
        self.assertEqual(dep["spec"]["replicas"], 1)
        self.assertEqual(dep["spec"]["template"]["spec"]["serviceAccountName"], "keycloak-operator")
        env = dep["spec"]["template"]["spec"]["containers"][0]["env"]
        watches = [x for x in env if x["name"].endswith("_NAMESPACES")]
        self.assertEqual(len(watches), 4)
        self.assertTrue(all(x["value"] == "JOSDK_WATCH_CURRENT" for x in watches))
        self.assertEqual(next(x for x in env if x["name"] == "KUBERNETES_NAMESPACE")["valueFrom"]["fieldRef"]["fieldPath"], "metadata.namespace")
        roles = [o for o in self.op if o["kind"] == "ClusterRole"]
        bindings = [o for o in self.op if o["kind"] == "ClusterRoleBinding"]
        local = [o for o in self.op if o["kind"] == "RoleBinding"]
        self.assertEqual((len(roles), len(bindings), len(local)), (5, 1, 5))
        narrow = self.op_by[("ClusterRole", "keycloak-operator-clusterrole")]
        self.assertEqual(narrow["rules"], [{"apiGroups": ["config.openshift.io"], "resources": ["ingresses"], "verbs": ["get"]}])
        self.assertEqual(bindings[0]["roleRef"]["name"], narrow["metadata"]["name"])
        for binding in bindings + local:
            self.assertEqual(binding["subjects"], [{"kind": "ServiceAccount", "name": "keycloak-operator", "namespace": "keycloak"}])
            if binding["kind"] == "ClusterRoleBinding":
                self.assertNotIn("namespace", binding["metadata"])
            else:
                self.assertEqual(binding["metadata"]["namespace"], "keycloak")
            self.assertIn(binding["roleRef"]["name"], {r["metadata"]["name"] for r in roles} | {"view"})
        secret_rules = [rule for role in roles for rule in role["rules"] if "secrets" in rule["resources"]]
        self.assertTrue(any({"get", "list", "watch", "create", "delete", "patch", "update"}.issubset(rule["verbs"]) for rule in secret_rules))

    def test_no_default_exposure_generated_secrets_or_preview_custom_resources(self):
        forbidden = {"Namespace", "Application", "HTTPRoute", "Ingress", "Secret", "SecretStore", "ClusterSecretStore", "KeycloakRealmImport", "KeycloakOIDCClient", "KeycloakSAMLClient", "CronJob"}
        self.assertFalse(forbidden & {o["kind"] for o in self.op + self.app})
        self.assertEqual(len(self.op), 18)
        self.assertEqual(len(self.app), 8)
        for obj in self.op + self.app:
            self.assertNotIn("helm.sh/hook", obj["metadata"].get("annotations", {}))
            if obj["kind"] not in ("CustomResourceDefinition", "ClusterRole", "ClusterRoleBinding"):
                self.assertEqual(obj["metadata"]["namespace"], "keycloak")
        self.assertEqual(self.op_by[("Service", "keycloak-operator")]["spec"]["type"], "ClusterIP")
        for path in (ROOT / "charts/argo-applications").glob("*local_values.yaml"):
            apps = yaml.safe_load(path.read_text()).get("applications", {})
            for name, app in apps.items():
                if app.get("source", {}).get("path") == "charts/keycloak-operator":
                    self.assertEqual(path.name, "management_local_values.yaml")
                    self.assertEqual(name, "keycloak-operator")
                    self.assertEqual(app, {
                        "enabled": True, "name": "keycloak-operator", "project": "management",
                        "destination": {"namespace": "keycloak"},
                        "source": {
                            "repoURL": "https://github.com/KKamJi98/helm-charts.git",
                            "targetRevision": "main", "path": "charts/keycloak-operator",
                            "helm": {"releaseName": "keycloak-operator", "valueFiles": ["kkamji_local_values.yaml"]},
                        },
                    })
                if app.get("source", {}).get("path") == "charts/keycloak-idp":
                    self.assertEqual(path.name, "management_local_values.yaml")
                    self.assertEqual(name, "keycloak-idp")
                    self.assertEqual(app, {
                        "enabled": True, "name": "keycloak-idp", "project": "management",
                        "destination": {"namespace": "keycloak"},
                        "source": {
                            "repoURL": "https://github.com/KKamJi98/helm-charts.git",
                            "targetRevision": "main", "path": "charts/keycloak-idp",
                            "helm": {
                                "releaseName": "keycloak",
                                "valueFiles": ["kkamji_local_values.yaml", "production-values.yaml"],
                                "parameters": [{"name": "productionPhase", "value": "application", "forceString": True}],
                            },
                        },
                    })

    def test_images_nonoptimized_start_and_edge_only_supported_fields(self):
        spec = self.kc["spec"]
        self.assertEqual(spec["image"], SERVER_IMAGE)
        self.assertIs(spec["startOptimized"], False)
        self.assertIs(spec["automountServiceAccountToken"], False)
        self.assertNotIn("unsupported", spec)
        self.assertEqual(spec["hostname"], {"hostname": "https://sso.kkamji.net", "strict": True})
        self.assertEqual(spec["http"], {"httpEnabled": True, "httpPort": 8080})
        self.assertEqual(spec["httpManagement"], {"port": 9000})
        self.assertEqual(spec["proxy"], {"headers": "xforwarded"})
        self.assertEqual(spec["ingress"], {"enabled": False})
        self.assertEqual(spec["networkPolicy"], {"enabled": False})
        self.assertEqual(spec["bootstrapAdmin"], {"user": {"secret": "keycloak-bootstrap-admin"}})
        self.assertEqual(spec["update"]["strategy"], "RecreateOnImageChange")
        self.assertEqual(self.db["spec"]["imageName"], POSTGRES_IMAGE)

    def test_exact_database_credentials_and_public_only_trust_reference(self):
        db = self.kc["spec"]["db"]
        self.assertEqual(db, {"vendor": "postgres", "host": "keycloak-db-rw.keycloak.svc.cluster.local", "port": 5432, "database": "keycloak", "usernameSecret": {"name": "keycloak-db-app", "key": "username"}, "passwordSecret": {"name": "keycloak-db-app", "key": "password"}})
        self.assertEqual(self.kc["spec"]["additionalOptions"], [{"name": "db-tls-mode", "value": "verify-server"}])
        self.assertEqual(self.kc["spec"]["truststores"], {"database": {"secret": {"name": "keycloak-db-client-trust", "optional": False}}})
        self.assertEqual(self.db["spec"]["certificates"]["serverAltDNSNames"], [db["host"]])
        self.assertEqual(self.db["spec"]["bootstrap"]["initdb"], {"database": "keycloak", "owner": "keycloak", "secret": {"name": "keycloak-db-app"}})
        self.assertIs(self.db["spec"]["enableSuperuserAccess"], False)
        self.assertEqual(self.db["metadata"]["annotations"]["argocd.argoproj.io/sync-options"], "Prune=false,Delete=false")

    def test_explicit_ssm_properties_orphan_retain_and_no_source_values(self):
        expected = {
            "keycloak-db-app": ("/kkamji/keycloak/database", {"username": "username", "password": "password"}, "kubernetes.io/basic-auth"),
            "keycloak-bootstrap-admin": ("/kkamji/keycloak/bootstrap", {"username": "username", "password": "password"}, "Opaque"),
            "keycloak-oidc-client": ("/kkamji/keycloak/clients/kkamji-platform", {"client-secret": "client_secret"}, "Opaque"),
        }
        for name, (source, props, typ) in expected.items():
            spec = self.app_by[("ExternalSecret", name)]["spec"]
            self.assertEqual(spec["secretStoreRef"], {"name": "parameter-store", "kind": "ClusterSecretStore"})
            self.assertEqual(spec["target"], {"name": name, "creationPolicy": "Orphan", "deletionPolicy": "Retain", "template": {"type": typ}})
            self.assertNotIn("dataFrom", spec)
            self.assertEqual({x["secretKey"]: x["remoteRef"]["property"] for x in spec["data"]}, props)
            self.assertTrue(all(x["remoteRef"]["key"] == source for x in spec["data"]))
            self.assertNotIn("data", spec["target"]["template"])

    def test_candidate_does_not_broaden_namespace_egress(self):
        egress_policies = [p for p in self.policies if "Egress" in p["spec"]["policyTypes"]]
        self.assertEqual(
            egress_policies, [],
            "Preparation must not add namespace-wide allow-all egress or defeat existing controls",
        )

    def test_ingress_policy_positive_paths_and_negative_source_port_matrix(self):
        allowed = lambda target, source, ns, port: ingress_allowed(self.policies, target, source, ns, port)
        self.assertTrue(allowed(SERVER_LABELS, GATEWAY_LABELS, "envoy-gateway-system", 8080))
        self.assertTrue(allowed(SERVER_LABELS, {"app.kubernetes.io/name": "keycloak-operator"}, "keycloak", 9000))
        for port in (7800, 57800):
            self.assertTrue(allowed(SERVER_LABELS, SERVER_LABELS, "keycloak", port))
        for ns, labels, port in [
            ("default", GATEWAY_LABELS, 8080), ("keycloak", {}, 8080),
            ("envoy-gateway-system", {**GATEWAY_LABELS, "gateway.envoyproxy.io/owning-gateway-name": "other"}, 8080),
            ("envoy-gateway-system", GATEWAY_LABELS, 9000), ("keycloak", SERVER_LABELS, 9000),
            ("keycloak", {"app.kubernetes.io/name": "keycloak-operator"}, 8080),
            ("default", SERVER_LABELS, 7800), ("keycloak", SERVER_LABELS, 8443)]:
            with self.subTest(namespace=ns, port=port):
                self.assertFalse(allowed(SERVER_LABELS, labels, ns, port))
        target = {"cnpg.io/cluster": "keycloak-db"}
        for app in ("keycloak", "keycloak-realm-import"):
            self.assertTrue(allowed(target, {**SERVER_LABELS, "app": app}, "keycloak", 5432))
        for port in (5432, 8000):
            self.assertTrue(allowed(target, CNPG_LABELS, "cnpg-system", port))
            self.assertTrue(allowed(target, target, "keycloak", port))
        for ns, labels, port in [("keycloak", {}, 5432), ("cnpg-system", {}, 5432), ("default", CNPG_LABELS, 8000), ("keycloak", {**SERVER_LABELS, "app": "keycloak-update-job"}, 5432), ("envoy-gateway-system", GATEWAY_LABELS, 5432), ("keycloak", SERVER_LABELS, 8000), ("keycloak", target, 9187)]:
            self.assertFalse(allowed(target, labels, ns, port))
        self.assertFalse(allowed({"app.kubernetes.io/name": "keycloak-operator"}, {}, "keycloak", 8080))
        egress = [x for x in self.policies if "Egress" in x["spec"]["policyTypes"]]
        self.assertEqual(egress, [], "Do not override pre-existing egress controls")

    def test_server_antiaffinity_excludes_import_and_job_override_replaces_inheritance(self):
        spec = self.kc["spec"]
        hard = spec["scheduling"]["affinity"]["podAntiAffinity"]["requiredDuringSchedulingIgnoredDuringExecution"]
        self.assertEqual(len(hard), 1)
        self.assertEqual(hard[0]["topologyKey"], "kubernetes.io/hostname")
        self.assertEqual(hard[0]["labelSelector"]["matchLabels"], SERVER_LABELS)
        self.assertTrue(selector_matches(hard[0]["labelSelector"], SERVER_LABELS))
        for app in ("keycloak-realm-import", "keycloak-update-job"):
            job = {**SERVER_LABELS, "app": app}
            self.assertFalse(selector_matches(hard[0]["labelSelector"], job), "Existing server anti-affinity must not repel Job labels")
        for scheduling in [spec["scheduling"], spec["import"]["scheduling"], spec["update"]["scheduling"]]:
            terms = scheduling["affinity"]["nodeAffinity"]["requiredDuringSchedulingIgnoredDuringExecution"]["nodeSelectorTerms"]
            self.assertEqual(terms, [{"matchExpressions": [{"key": "kubernetes.io/hostname", "operator": "In", "values": ["k8s-w1", "k8s-w2"]}]}])
            self.assertEqual(scheduling["tolerations"], [], "No control-plane NoSchedule toleration")
        self.assertNotIn("podAntiAffinity", spec["import"]["scheduling"]["affinity"])
        self.assertNotIn("podAntiAffinity", spec["update"]["scheduling"]["affinity"])
        # Source handle: handleJobScheduling replaces all scheduling fields when the override exists.
        # Without it the incoming Job inherits a hard rule against the server on EACH worker.
        occupied_workers = {"k8s-w1": SERVER_LABELS, "k8s-w2": SERVER_LABELS}
        self.assertTrue(all(selector_matches(hard[0]["labelSelector"], labels) for labels in occupied_workers.values()))
        db_affinity = self.db["spec"]["affinity"]
        self.assertEqual(db_affinity["podAntiAffinityType"], "preferred")
        self.assertIs(db_affinity["enablePodAntiAffinity"], True)
        self.assertEqual(db_affinity["nodeAffinity"], spec["scheduling"]["affinity"]["nodeAffinity"])
        self.assertNotIn("tolerations", db_affinity)

    def test_render_derived_steady_import_operator_surge_and_update_model(self):
        op = resource_vector(self.op_by[("Deployment", "keycloak-operator")]["spec"]["template"]["spec"]["containers"][0]["resources"])
        server = resource_vector(self.kc["spec"]["resources"])
        db = resource_vector(self.db["spec"]["resources"])
        imp = resource_vector(self.realm["spec"]["resources"])
        self.assertEqual(op, (300, 450, 700, 450))
        self.assertEqual(server, (1000, 2048, 2000, 2048))
        self.assertEqual(db, (250, 1024, 1000, 1024))
        self.assertEqual(imp, server, "Explicit RealmImport resources avoid upstream fallback ambiguity")
        self.assertEqual((self.kc["spec"]["instances"], self.db["spec"]["instances"]), (2, 3))
        steady = sum_vectors(op, server, server, db, db, db)
        self.assertEqual(steady, (3050, 7618, 7700, 7618))
        self.assertEqual(sum_vectors(steady, imp), (4050, 9666, 9700, 9666))
        self.assertEqual(sum_vectors(steady, op), (3350, 8068, 8400, 8068))
        self.assertEqual(sum_vectors(steady, op, imp), (4350, 10116, 10400, 10116))
        # CNPG regular init and main each use Cluster resources: serial max.
        effective_cnpg = tuple(max(main, init) for main, init in zip(db, db))
        self.assertEqual(effective_cnpg, db)
        self.assertEqual(sum_vectors(steady, effective_cnpg), (3300, 8642, 8700, 8642))
        self.assertEqual(sum_vectors(steady, imp, op, effective_cnpg), (4600, 11140, 11400, 11140))
        self.assertNotIn("plugins", self.db["spec"])
        self.assertNotIn("initContainers", self.op_by[("Deployment", "keycloak-operator")]["spec"]["template"]["spec"])
        # Default Deployment RollingUpdate maxSurge=25% rounds UP for one Operator.
        self.assertNotIn("strategy", self.op_by[("Deployment", "keycloak-operator")]["spec"])
        self.assertEqual(self.db["spec"]["storage"], {"size": "10Gi", "storageClass": "local-path"})
        self.assertEqual(self.db["spec"]["instances"] * 10, 30)
        # Recreate image update: two servers is an upper bound, with accepted downtime.
        # Future Auto, NOT SELECTED: one normal init + one app container execute serially.
        effective_update = tuple(max(a, b) for a, b in zip(server, server))
        self.assertEqual(effective_update, server)
        self.assertEqual(sum_vectors(steady, effective_update), (4050, 9666, 9700, 9666))
        # Feasible request-only example, NOT scheduler/runtime proof: 2 DB + KC + op + import on w1.
        w1 = sum_vectors(server, db, db, op, imp)
        w2 = sum_vectors(server, db)
        self.assertEqual((w1[0], w1[1], w2[0], w2[1]), (2800, 6594, 1250, 3072))
        self.assertLess(w1[0], Decimal("6575"))
        self.assertLess(w1[1], Decimal("8240.712890625"))
        self.assertLess(w2[0], Decimal("4795"))
        self.assertLess(w2[1], Decimal("3882.705078125"))
        # 2 KC + 2 DB alone cannot fit w2's request-memory headroom.
        self.assertGreater(sum_vectors(server, server, db, db)[1], Decimal("3882.705078125"))

    def test_actual_supported_field_guards_fail_closed_even_without_schema(self):
        app_negatives = [
            {"preparationProfile": "deployment"}, {"namespaceOverride": "default"},
            {"keycloak": {"instances": 1}}, {"keycloak": {"image": "quay.io/keycloak/keycloak:26.8.2"}},
            {"keycloak": {"resources": {"requests": {"cpu": "250m"}}}},
            {"keycloak": {"startOptimized": True}}, {"keycloak": {"automountServiceAccountToken": True}},
            {"keycloak": {"db": {"url": "jdbc:postgresql://keycloak-db-rw/keycloak?sslmode=disable"}}},
            {"keycloak": {"db": {"usernameSecret": {"name": "other"}}}},
            {"keycloak": {"db": {"passwordSecret": {"key": "other"}}}},
            {"keycloak": {"db": {"passwordSecret": {"optional": True}}}},
            {"keycloak": {"truststores": {"database": {"secret": {"name": "keycloak-db-ca"}}}}},
            {"keycloak": {"truststores": {"database": {"secret": {"optional": True}}}}},
            {"keycloak": {"additionalOptions": [{"name": "db-tls-mode", "value": "disabled"}]}},
            {"keycloak": {"additionalOptions": [{"name": "db-url-properties", "value": "?sslmode=require"}]}},
            {"keycloak": {"additionalOptions": [{"name": "proxy-trusted-addresses", "value": "0.0.0.0/0"}]}},
            {"keycloak": {"hostname": {"strict": False}}}, {"keycloak": {"http": {"httpPort": 80}}},
            {"keycloak": {"ingress": {"enabled": True}}}, {"keycloak": {"networkPolicy": {"enabled": True}}},
            {"keycloak": {"update": {"strategy": "Auto"}}},
            {"keycloak": {"bootstrapAdmin": {"user": {"secret": "other"}}}},
            {"keycloak": {"scheduling": {"tolerations": [{"operator": "Exists"}]}}},
            {"keycloak": {"import": {"scheduling": {"affinity": {"podAntiAffinity": {}}}}}},
            {"keycloak": {"unsupported": {"podTemplate": {"spec": {"hostNetwork": True}}}}},
            {"database": {"bootstrap": {"initdb": {"owner": "platform"}}}},
            {"database": {"instances": 1}}, {"database": {"storage": {"size": "1Gi"}}},
            {"database": {"affinity": {"podAntiAffinityType": "required"}}},
            {"database": {"enableSuperuserAccess": True}},
        ]
        operator_negatives = [{"images": {"operator": "quay.io/keycloak/keycloak-operator:26.8.2"}}, {"images": {"keycloak": "quay.io/keycloak/keycloak:26.8.2"}}, {"watchNamespaces": ["*"]}]
        for chart, negatives in [(APP, app_negatives), (OPERATOR, operator_negatives)]:
            for index, override in enumerate(negatives):
                for skip_schema in (False, True):
                    with self.subTest(chart=chart.name, case=index, skip_schema=skip_schema):
                        result = self.command(chart, override=override, skip_schema=skip_schema)
                        self.assertNotEqual(result.returncode, 0)
                        if skip_schema:
                            self.assertIn("immutable supported-field profile mismatch", result.stderr)
        for chart in (OPERATOR, APP):
            for namespace, release in (("default", None), ("keycloak", "other")):
                result = self.command(chart, namespace=namespace, release=release)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("exact namespace/release identity required", result.stderr)

    def test_pinned_public_cnpg_eso_schemas_and_keycloak_cr_schema(self):
        manifest = json.loads((EXAMPLES / "schemas/manifest.json").read_text())
        self.assertEqual(len(manifest["schemas"]), 2)
        self.assertEqual({x["path"]: x["sha256"] for x in manifest["schemas"]}, SCHEMA_HASHES)
        for entry in manifest["schemas"]:
            self.assertEqual(hashlib.sha256((EXAMPLES / entry["path"]).read_bytes()).hexdigest(), entry["sha256"])
        schemas = {
            "Keycloak": crd_schema(self.op_by[("CustomResourceDefinition", "keycloaks.k8s.keycloak.org")], "v2beta1"),
            "KeycloakRealmImport": crd_schema(self.op_by[("CustomResourceDefinition", "keycloakrealmimports.k8s.keycloak.org")], "v2beta1"),
            "Cluster": json.loads((EXAMPLES / "schemas/cnpg-1.30-cluster.schema.json").read_text()),
            "ExternalSecret": json.loads((EXAMPLES / "schemas/eso-2.4.1-externalsecret.schema.json").read_text()),
        }
        for obj in self.app + [self.realm, yaml.safe_load((EXAMPLES / "platform-client-reader.yaml.inactive").read_text())]:
            if obj["kind"] in schemas:
                with self.subTest(kind=obj["kind"], name=obj["metadata"]["name"]):
                    validate_document(schemas[obj["kind"]], obj)
        invalids = [
            (self.kc, ("spec", "db", "sslMode"), "verify-full"),
            (self.kc, ("spec", "unsupported_typo"), {}),
            (self.kc, ("spec", "instances"), "two"),
            (self.kc, ("spec", "update", "strategy"), "RollingUpdate"),
            (self.realm, ("spec", "realm", "webAuthnPolicyUserVerificationRequirement"), True),
            (self.realm, ("spec", "realm", "clients", 0, "enabled"), "false"),
            (self.db, ("spec", "instances"), "three"),
            (self.app_by[("ExternalSecret", "keycloak-db-app")], ("spec", "target", "creationPolicy"), "KeepForever"),
        ]
        for obj, path, value in invalids:
            with self.subTest(kind=obj["kind"], path=path):
                invalid = copy.deepcopy(obj)
                target = invalid
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = value
                with self.assertRaises(jsonschema.ValidationError):
                    validate_document(schemas[obj["kind"]], invalid)

    def test_source_handles_and_serial_init_resource_inventory(self):
        contracts = json.loads((EXAMPLES / "upstream-contracts.json").read_text())
        self.assertEqual(contracts["keycloakSourceCommit"], SOURCE_COMMIT)
        self.assertEqual(contracts["resourcesCommit"], RESOURCE_COMMIT)
        self.assertEqual(contracts["cnpgSchemaCommit"], "ec38e6ef0cb37186ac5c4922fd8da1a768e5c9bf")
        sources = contracts["sources"]
        self.assertEqual(sources["supported-databases"]["supportedPostgresqlMajors"], [18, 17, 16, 15, 14])
        self.assertEqual(sources["supported-databases"]["gitBlobSha1"], "a083383c4e9cbb28c3cfc6394ed1eecb4ff53643")
        self.assertEqual(sources["pkg_specs_containers.go"]["sha256"], "13678669c301a896dcceb8a58ed254127acf164591ba7ea20f6fd9bb20337b27")
        for source in sources.values():
            self.assertEqual(len(source["sha256"]), 64)
            self.assertTrue(source["url"].startswith("https://"))
        self.assertIn("per-resource max", contracts["derivations"]["cnpgResources"])
        model = json.loads((EXAMPLES / "resource-model.json").read_text())
        self.assertEqual(model["logicalStorageGi"], 30)
        self.assertEqual(model["scenarios"]["steady"]["pods"], 6)
        self.assertEqual(model["scenarios"]["oneInactiveImport"]["pods"], 7)
        self.assertEqual(model["scenarios"]["importOperatorSurgeAndOneCnpgReserve"]["pods"], 9)
        expected = {
            "steady": (3050, 7618, 7700, 7618),
            "oneInactiveImport": (4050, 9666, 9700, 9666),
            "operatorDefaultSurge": (3350, 8068, 8400, 8068),
            "importAndOperatorSurge": (4350, 10116, 10400, 10116),
            "oneExtraCnpgPodReserve": (3300, 8642, 8700, 8642),
            "importOperatorSurgeAndOneCnpgReserve": (4600, 11140, 11400, 11140),
            "futureAutoCheckNotSelected": (4050, 9666, 9700, 9666),
            "futureAutoAndImportNotSelected": (5050, 11714, 11700, 11714),
        }
        for name, values in expected.items():
            self.assertEqual(tuple(model["scenarios"][name][key] for key in model["columns"]), values)

    def test_inactive_gitops_route_namespace_and_existing_project_only(self):
        files = list(EXAMPLES.glob("*.inactive"))
        self.assertEqual(len(files), 6)
        for path in files:
            obj = yaml.safe_load(path.read_text())
            self.assertEqual(obj["metadata"]["annotations"]["argocd.argoproj.io/skip-reconcile"], "true")
            self.assertEqual(obj["metadata"]["annotations"]["preparation.kkamji.net/reviewed-commit"], "UNRESOLVED_REVIEWED_COMMIT")
            self.assertNotIn("finalizers", obj["metadata"])
        projects = yaml.safe_load((ROOT / "charts/argocd/kkamji_local_values.yaml").read_text())["argo-projects"]["projects"]
        for name, chart in [("keycloak-operator", "charts/keycloak-operator"), ("keycloak", "charts/keycloak-idp")]:
            app = yaml.safe_load((EXAMPLES / (name + "-application.yaml.inactive")).read_text())
            self.assertEqual(app["spec"]["source"]["path"], chart)
            self.assertEqual(app["spec"]["source"]["targetRevision"], "UNRESOLVED_REVIEWED_COMMIT")
            self.assertEqual(app["spec"]["source"]["helm"]["releaseName"], name)
            self.assertEqual(app["spec"]["project"], "management")
            self.assertIn(app["spec"]["project"], projects)
            self.assertNotIn("automated", app["spec"]["syncPolicy"])
            self.assertFalse(any(x.startswith("CreateNamespace=") for x in app["spec"]["syncPolicy"]["syncOptions"]))
        route = yaml.safe_load((EXAMPLES / "https-route.yaml.inactive").read_text())
        self.assertEqual(route["spec"]["parentRefs"], [{"group": "gateway.networking.k8s.io", "kind": "Gateway", "name": "kkamji", "namespace": "envoy-gateway-system", "sectionName": "https"}])
        self.assertEqual(route["spec"]["hostnames"], ["sso.kkamji.net"])
        self.assertEqual(route["spec"]["rules"][0]["matches"], [
            {"path": {"type": "PathPrefix", "value": "/realms/kkamji"}},
            {"path": {"type": "PathPrefix", "value": "/resources"}},
        ], "Public route must not expose the master realm or admin console/API")
        self.assertEqual(route["spec"]["rules"][0]["backendRefs"], [{"group": "", "kind": "Service", "name": "keycloak-service", "port": 8080, "weight": 1}])

    def test_inactive_realm_client_pkce_placeholder_and_mfa_manual_gate(self):
        spec, realm = self.realm["spec"], self.realm["spec"]["realm"]
        self.assertEqual(spec["keycloakCRName"], "keycloak")
        self.assertEqual(spec["placeholders"], {"OIDC_CLIENT_SECRET": {"secret": {"name": "keycloak-oidc-client", "key": "client-secret"}}})
        for field in ("enabled", "registrationAllowed", "resetPasswordAllowed"):
            self.assertIs(realm[field], False)
        self.assertEqual(realm["realm"], "kkamji")
        self.assertEqual(realm["identityProviders"], [])
        self.assertNotIn("users", realm)
        self.assertNotIn("browserFlow", realm)
        self.assertNotIn("authenticationFlows", realm, "No fabricated or bound MFA flow")
        self.assertEqual(realm["webAuthnPolicyUserVerificationRequirement"], "required")
        self.assertEqual(realm["webAuthnPolicyRpId"], "sso.kkamji.net")
        self.assertEqual(realm["webAuthnPolicyRpEntityName"], "KKamJi")
        self.assertIs(realm["webAuthnPolicyPasswordlessPasskeysEnabled"], False)
        self.assertEqual(len(realm["clients"]), 1)
        client = realm["clients"][0]
        self.assertEqual(client["clientId"], "kkamji-platform")
        for field in ("enabled", "publicClient", "directAccessGrantsEnabled", "implicitFlowEnabled", "serviceAccountsEnabled"):
            self.assertIs(client[field], False)
        self.assertIs(client["standardFlowEnabled"], True)
        self.assertEqual(client["secret"], "${OIDC_CLIENT_SECRET}")
        self.assertEqual(client["redirectUris"], ["https://platform.kkamji.net/api/auth/oidc/callback"])
        self.assertEqual(client["authenticationFlowBindingOverrides"], {})
        self.assertEqual(client["attributes"]["pkce.code.challenge.method"], "S256")
        self.assertTrue(all(v == "false" for k, v in client["attributes"].items() if k != "pkce.code.challenge.method"))
        readme = (EXAMPLES / "README.md").read_text()
        for phrase in ("CREATE-ONLY", "verify-full", "ca.key", "UNIMPLEMENTED", "Cookie", "owner sub", "RecreateOnImageChange", "not physical-failure HA", "110%", "Java default", "UNRESOLVED_REVIEWED_COMMIT", "manual", "does NOT rotate", "namespace-admin"):
            self.assertIn(phrase, readme)


if __name__ == "__main__":
    unittest.main()
