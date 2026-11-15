"""Offline public-CA projection contract; no API, credentials or real certificates.

Run with HELM_BIN=verified Helm 4.2.1, TMPDIR=owned private scratch, and the
existing PyYAML/jsonschema environment. Structural checks are not admission or
runtime proof. ESO schemas are derived offline from the unchanged pinned chart.
"""
import copy
import hashlib
import json
import subprocess
import unittest

import jsonschema
import yaml

import test_keycloak_preparation as preparation


READER = "keycloak-db-ca-reader"
SOURCE = "keycloak-db-ca"
TARGET = "keycloak-db-client-trust"
TOKEN_ROLE = "keycloak-db-ca-token-request"
EXTRA_IDENTITIES = {
    ("ServiceAccount", READER), ("Role", READER), ("RoleBinding", READER),
    ("Role", TOKEN_ROLE), ("RoleBinding", TOKEN_ROLE),
    ("SecretStore", SOURCE), ("ExternalSecret", TARGET),
}


def projected_permission(objects, subject, namespace, resource, name, verb):
    """Model ONLY new local Role grants, not effective cluster authorization."""
    by = {preparation.identity(obj): obj for obj in objects}
    for binding in (obj for obj in objects if obj["kind"] == "RoleBinding"):
        if binding["metadata"]["namespace"] != namespace or subject not in binding["subjects"]:
            continue
        role = by[("Role", binding["roleRef"]["name"])]
        for rule in role["rules"]:
            if ("" in rule["apiGroups"] and resource in rule["resources"]
                    and verb in rule["verbs"] and name in rule["resourceNames"]):
                return True
    return False


class KeycloakCaProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not preparation.HELM:
            raise AssertionError("Set HELM_BIN to verified Helm 4.2.1")
        version = subprocess.run([preparation.HELM, "version", "--short"],
                                 capture_output=True, text=True, check=True).stdout.strip()
        if version != "v4.2.1+gd591a19":
            raise AssertionError("Expected v4.2.1+gd591a19")
        cls.base = cls.render()
        cls.active = cls.render({"publicCaProjection": {"enabled": True}})
        cls.by = {preparation.identity(obj): obj for obj in cls.active}
        archive = preparation.ROOT / "charts/external-secrets/charts/external-secrets-2.4.1.tgz"
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        if digest != "d432db5dd4935cc8032f6fbc1c3f33b4baaa08db2be76de41e6cf3ea651fe574":
            raise AssertionError("Pinned ESO archive changed")
        cls.schemas = {}
        for kind, filename in [("SecretStore", "secretstore"), ("ExternalSecret", "externalsecret")]:
            result = subprocess.run(
                [preparation.HELM, "template", "eso-schema", str(archive), "--show-only",
                 f"templates/crds/{filename}.yaml"], capture_output=True, text=True, check=True)
            crd = yaml.safe_load(result.stdout)
            cls.schemas[kind] = preparation.crd_schema(crd, "v1")

    @classmethod
    def render(cls, override=None):
        result = preparation.KeycloakPreparationTests.command(preparation.APP, override=override)
        if result.returncode:
            raise AssertionError(result.stderr)
        return preparation.documents(result.stdout)

    def test_activation_adds_only_seven_fixed_objects(self):
        self.assertEqual(len(self.base), 8)
        self.assertEqual(len(self.active), 15)
        baseline = {preparation.identity(obj): obj for obj in self.base}
        self.assertEqual(set(self.by) - set(baseline), EXTRA_IDENTITIES)
        self.assertEqual({key: self.by[key] for key in baseline}, baseline)
        self.assertEqual(self.render({"publicCaProjection": {"enabled": False}}), self.base)
        for obj in self.active:
            self.assertEqual(obj["metadata"]["namespace"], "keycloak")
        self.assertFalse({"ClusterRole", "ClusterRoleBinding", "ClusterSecretStore", "Secret",
                          "Deployment", "CronJob", "Job", "HTTPRoute", "Ingress"}
                         & {obj["kind"] for obj in self.active})

    def test_tokenless_reader_only_gets_exact_source_secret(self):
        account = self.by[("ServiceAccount", READER)]
        self.assertIs(account["automountServiceAccountToken"], False)
        self.assertNotIn("secrets", account)
        self.assertEqual(self.by[("Role", READER)]["rules"], [{
            "apiGroups": [""], "resources": ["secrets"],
            "resourceNames": [SOURCE], "verbs": ["get"],
        }])
        self.assertEqual(self.by[("RoleBinding", READER)]["subjects"], [
            {"kind": "ServiceAccount", "name": READER, "namespace": "keycloak"}])
        for name in (READER, TOKEN_ROLE):
            self.assertEqual(self.by[("RoleBinding", name)]["roleRef"], {
                "apiGroup": "rbac.authorization.k8s.io", "kind": "Role", "name": name})

    def test_only_existing_controller_gets_named_token_subresource_grant(self):
        self.assertEqual(self.by[("Role", TOKEN_ROLE)]["rules"], [{
            "apiGroups": [""], "resources": ["serviceaccounts/token"],
            "resourceNames": [READER], "verbs": ["create"],
        }])
        self.assertEqual(self.by[("RoleBinding", TOKEN_ROLE)]["subjects"], [{
            "kind": "ServiceAccount", "name": "external-secrets", "namespace": "external-secrets",
        }])
        reader = {"kind": "ServiceAccount", "name": READER, "namespace": "keycloak"}
        controller = {"kind": "ServiceAccount", "name": "external-secrets", "namespace": "external-secrets"}
        allow = lambda *args: projected_permission(self.active, *args)
        self.assertTrue(allow(reader, "keycloak", "secrets", SOURCE, "get"))
        self.assertTrue(allow(controller, "keycloak", "serviceaccounts/token", READER, "create"))
        for subject in (reader, controller, {**reader, "name": "other"}, {**controller, "namespace": "other"}):
            for namespace in ("keycloak", "default", "external-secrets"):
                for resource in ("secrets", "serviceaccounts/token", "serviceaccounts"):
                    for name in (SOURCE, READER, "keycloak-db-app", "keycloak-bootstrap-admin", "other", ""):
                        for verb in ("get", "list", "watch", "create", "update", "patch", "delete"):
                            expected = (
                                subject == reader and namespace == "keycloak" and resource == "secrets"
                                and name == SOURCE and verb == "get"
                            ) or (
                                subject == controller and namespace == "keycloak" and resource == "serviceaccounts/token"
                                and name == READER and verb == "create"
                            )
                            self.assertEqual(allow(subject, namespace, resource, name, verb), expected)

    def test_store_has_fixed_same_namespace_https_ca_and_short_lived_auth(self):
        store = self.by[("SecretStore", SOURCE)]
        self.assertEqual(store["spec"], {"provider": {"kubernetes": {
            "remoteNamespace": "keycloak",
            "server": {"url": "https://kubernetes.default.svc", "caProvider": {
                "type": "ConfigMap", "name": "kube-root-ca.crt", "key": "ca.crt"}},
            "auth": {"serviceAccount": {"name": READER}},
        }}})
        # A namespaced CAProvider must omit namespace (ESO ValidateStore).
        self.assertNotIn("namespace", store["spec"]["provider"]["kubernetes"]["server"]["caProvider"])

    def test_projection_maps_only_public_property_without_extraction_or_private_keys(self):
        spec = self.by[("ExternalSecret", TARGET)]["spec"]
        self.assertEqual(spec, {
            "refreshPolicy": "Periodic", "refreshInterval": "1m",
            "secretStoreRef": {"name": SOURCE, "kind": "SecretStore"},
            "target": {"name": TARGET, "creationPolicy": "Orphan", "deletionPolicy": "Retain",
                       "template": {"type": "Opaque"}},
            "data": [{"secretKey": "ca.crt", "remoteRef": {
                "key": SOURCE, "property": "ca.crt", "conversionStrategy": "Default",
                "decodingStrategy": "None", "metadataPolicy": "None"}}],
        })
        # Exact mapping is intentional: no dataFrom/find, whole JSON, templateFrom,
        # arbitrary properties or prior-root key that ESO could later overwrite.
        for key in EXTRA_IDENTITIES:
            self.assertNotIn("ca.key", json.dumps(self.by[key]))
        wave = self.by[("ExternalSecret", TARGET)]["metadata"].get("annotations", {}).get(
            "argocd.argoproj.io/sync-wave", "0")
        self.assertEqual(int(wave), 0, "CA cannot depend on an uncreated later-wave Cluster")

    def test_app_mount_and_tls_identity_are_unchanged_and_never_source_secret(self):
        spec = self.by[("Keycloak", "keycloak")]["spec"]
        self.assertEqual(spec["truststores"], {"database": {"secret": {"name": TARGET, "optional": False}}})
        self.assertEqual(spec["additionalOptions"], [{"name": "db-tls-mode", "value": "verify-server"}])
        self.assertEqual(spec["db"]["host"], "keycloak-db-rw.keycloak.svc.cluster.local")
        self.assertNotIn(SOURCE, json.dumps(spec))
        self.assertNotIn("unsupported", spec)
        self.assertFalse([obj for obj in self.active if obj["kind"] == "NetworkPolicy"
                          and "Egress" in obj["spec"]["policyTypes"]])

    def test_pinned_eso_v1_schemas_validate_and_reject_unknown_or_malformed_fields(self):
        for kind, name in (("SecretStore", SOURCE), ("ExternalSecret", TARGET)):
            schema = self.schemas[kind]
            jsonschema.Draft7Validator.check_schema(schema)
            preparation.validate_document(schema, self.by[(kind, name)])
        cases = [
            ("SecretStore", SOURCE, ("spec", "provider", "kubernetes", "server", "insecureSkipTLSVerify"), True),
            ("SecretStore", SOURCE, ("spec", "provider", "kubernetes", "auth", "serviceAccount", "token"), "forbidden"),
            ("SecretStore", SOURCE, ("spec", "provider", "kubernetes", "server", "caProvider", "type"), "SecretStore"),
            ("SecretStore", SOURCE, ("spec", "provider", "kubernetes", "remoteNamespace"), 123),
            ("ExternalSecret", TARGET, ("spec", "data", 0, "remoteRef", "propertyTypo"), "ca.crt"),
            ("ExternalSecret", TARGET, ("spec", "target", "creationPolicy"), "KeepForever"),
        ]
        for kind, name, path, value in cases:
            with self.subTest(kind=kind, path=path):
                invalid = copy.deepcopy(self.by[(kind, name)])
                cursor = invalid
                for part in path[:-1]:
                    cursor = cursor[part]
                cursor[path[-1]] = value
                with self.assertRaises(jsonschema.ValidationError):
                    preparation.validate_document(self.schemas[kind], invalid)

    def test_unsafe_value_overrides_fail_with_and_without_values_schema(self):
        cases = [
            {"publicCaProjection": {"enabled": "true"}},
            {"publicCaProjection": {"enabled": 1}},
            {"publicCaProjection": {"enabled": None}},
            {"publicCaProjection": {"sourceSecret": "keycloak-db-app"}},
            {"publicCaProjection": {"sourceProperty": "ca.key"}},
            {"publicCaProjection": {"targetSecret": SOURCE}},
            {"publicCaProjection": {"remoteNamespace": "default"}},
            {"publicCaProjection": {"server": {"url": "https://example.invalid"}}},
            {"publicCaProjection": {"server": {"url": "http://kubernetes.default.svc"}}},
            {"publicCaProjection": {"auth": {"token": {}}}},
            {"publicCaProjection": {"reader": {"resourceNames": ["*"]}}},
            {"publicCaProjection": {"controllerNamespace": "default"}},
            {"publicCaProjection": {"dataFrom": [{"extract": {"key": SOURCE}}]}},
            {"keycloak": {"truststores": {"database": {"secret": {"name": SOURCE}}}}},
            {"keycloak": {"truststores": {"database": {"secret": {"optional": True}}}}},
            {"keycloak": {"additionalOptions": [{"name": "db-tls-mode", "value": "disabled"}]}},
        ]
        for override in cases:
            override = copy.deepcopy(override)
            override.setdefault("publicCaProjection", {}).setdefault("enabled", True)
            for skip_schema in (False, True):
                with self.subTest(override=override, skip_schema=skip_schema):
                    result = preparation.KeycloakPreparationTests.command(
                        preparation.APP, override=override, skip_schema=skip_schema)
                    self.assertNotEqual(result.returncode, 0)
                    if skip_schema:
                        self.assertIn("immutable supported-field profile mismatch", result.stderr)
        for namespace, release in (("default", "keycloak"), ("keycloak", "other")):
            result = preparation.KeycloakPreparationTests.command(
                preparation.APP, override={"publicCaProjection": {"enabled": True}},
                namespace=namespace, release=release)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("exact namespace/release identity required", result.stderr)

    def test_helm_strict_lint_default_and_activated(self):
        for activated in (False, True):
            args = [preparation.HELM, "lint", str(preparation.APP), "--strict", "-f",
                    str(preparation.APP / "kkamji_local_values.yaml"), "--set",
                    "publicCaProjection.enabled=" + str(activated).lower()]
            result = subprocess.run(args, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
