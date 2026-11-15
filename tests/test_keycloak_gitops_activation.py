"""Offline management-root activation boundary; no credentials or cluster access."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml

import test_keycloak_preparation as preparation

ROOT = Path(__file__).resolve().parents[1]
HELM = os.environ.get("HELM_BIN", "helm")
VALUES = ROOT / "charts/argo-applications/management_local_values.yaml"


def objects(command):
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise AssertionError(result.stderr)
    documents = [item for item in yaml.safe_load_all(result.stdout) if item]
    keyed = {(item["kind"], item["metadata"]["name"]): item for item in documents}
    if len(keyed) != len(documents):
        raise AssertionError("duplicate rendered identity")
    return keyed


def management(values=VALUES):
    return objects([HELM, "template", "management-root", str(ROOT / "charts/argo-applications"),
                    "-n", "argocd", "--kube-version", "1.36.1", "-f", str(values)])


def application_command(application, namespace=None, release=None):
    source = application["spec"]["source"]
    chart = ROOT / source["path"]
    command = [HELM, "template", release or source["helm"]["releaseName"], str(chart),
               "-n", namespace or application["spec"]["destination"]["namespace"],
               "--kube-version", "1.36.1", "--include-crds", "--skip-tests"]
    for value_file in source["helm"]["valueFiles"]:
        command.extend(["-f", str(chart / value_file)])
    return command


class ManagementDatabaseActivationTests(unittest.TestCase):
    def application(self):
        application = management().get(("Application", "keycloak-idp"))
        if application is None:
            raise AssertionError("management root must declare the explicit Keycloak database phase")
        return application

    def test_database_application_uses_exact_release_and_profile(self):
        application = self.application()
        self.assertEqual(application["metadata"]["namespace"], "argocd")
        spec = application["spec"]
        self.assertEqual(spec["project"], "management")
        self.assertEqual(spec["destination"], {"namespace": "keycloak", "server": "https://kubernetes.default.svc"})
        self.assertEqual(spec["source"], {
            "repoURL": "https://github.com/KKamJi98/helm-charts.git",
            "targetRevision": "main", "path": "charts/keycloak-idp",
            "helm": {"releaseName": "keycloak", "valueFiles": ["kkamji_local_values.yaml", "production-values.yaml"]},
        })
        self.assertTrue(spec["syncPolicy"]["automated"]["selfHeal"])
        self.assertIn("CreateNamespace=true", spec["syncPolicy"]["syncOptions"])
        self.assertIn("ServerSideApply=true", spec["syncPolicy"]["syncOptions"])

    def test_existing_management_applications_are_unchanged(self):
        original = yaml.safe_load(VALUES.read_text())
        self.assertIn("keycloak-idp", original["applications"])
        original["applications"].pop("keycloak-idp")
        with tempfile.TemporaryDirectory() as temporary:
            before_values = Path(temporary) / "management-values.yaml"
            before_values.write_text(yaml.safe_dump(original, sort_keys=False))
            before, after = management(before_values), management()
        self.assertEqual(set(after) - set(before), {("Application", "keycloak-idp")})
        for identity, document in before.items():
            self.assertEqual(after[identity], document, identity)

    def test_application_values_render_database_without_idp_or_public_route(self):
        rendered = objects(application_command(self.application()))
        self.assertEqual(len(rendered), 16)
        self.assertIn(("Cluster", "keycloak-db"), rendered)
        self.assertIn(("ScheduledBackup", "keycloak-db-backup"), rendered)
        self.assertIn(("ExternalSecret", "keycloak-db-client-trust"), rendered)
        self.assertFalse(any(kind in {"Keycloak", "KeycloakRealmImport", "HTTPRoute", "Deployment"} for kind, _ in rendered))
        for document in rendered.values():
            self.assertEqual(document["metadata"]["namespace"], "keycloak")
        self.assertEqual(rendered["Cluster", "keycloak-db"]["metadata"]["annotations"]["argocd.argoproj.io/sync-options"], "Prune=false,Delete=false")


class ManagementOperatorActivationTests(unittest.TestCase):
    def application(self):
        application = management().get(("Application", "keycloak-operator"))
        if application is None:
            raise AssertionError("management root must declare the explicit Keycloak Operator-only stage")
        return application

    def test_operator_application_uses_exact_source_release_and_namespace(self):
        application = self.application()
        self.assertEqual(application["metadata"]["namespace"], "argocd")
        spec = application["spec"]
        self.assertEqual(spec["project"], "management")
        self.assertEqual(spec["destination"], {"namespace": "keycloak", "server": "https://kubernetes.default.svc"})
        self.assertEqual(spec["source"], {
            "repoURL": "https://github.com/KKamJi98/helm-charts.git",
            "targetRevision": "main", "path": "charts/keycloak-operator",
            "helm": {"releaseName": "keycloak-operator", "valueFiles": ["kkamji_local_values.yaml"]},
        })
        self.assertEqual(spec["syncPolicy"], yaml.safe_load(VALUES.read_text())["syncPolicy"])
        self.assertEqual(application["metadata"]["finalizers"], ["resources-finalizer.argocd.argoproj.io"])

    def test_operator_declaration_does_not_change_existing_factory_objects(self):
        values = yaml.safe_load(VALUES.read_text())
        self.assertIn("keycloak-operator", values["applications"])
        values["applications"].pop("keycloak-operator")
        with tempfile.TemporaryDirectory() as temporary:
            before_values = Path(temporary) / "management-values.yaml"
            before_values.write_text(yaml.safe_dump(values, sort_keys=False))
            before, after = management(before_values), management()
        self.assertEqual(set(after) - set(before), {("Application", "keycloak-operator")})
        self.assertEqual({identity: after[identity] for identity in before}, before)
        self.assertIn(("Application", "keycloak-idp"), before)

    def test_operator_application_renders_pinned_bundle_separate_from_idp(self):
        operator = objects(application_command(self.application()))
        expected = preparation.KeycloakPreparationTests.command(preparation.OPERATOR)
        self.assertEqual(expected.returncode, 0, expected.stderr)
        self.assertEqual(operator, {preparation.identity(obj): obj for obj in preparation.documents(expected.stdout)})
        self.assertEqual(len(operator), 18)
        counts = {kind: sum(identity[0] == kind for identity in operator) for kind, _ in operator}
        self.assertEqual(counts, {
            "CustomResourceDefinition": 4, "ClusterRole": 5, "ClusterRoleBinding": 1,
            "RoleBinding": 5, "ServiceAccount": 1, "Service": 1, "Deployment": 1,
        })
        deployment = operator["Deployment", "keycloak-operator"]
        self.assertEqual(deployment["spec"]["template"]["spec"]["containers"][0]["image"], preparation.OPERATOR_IMAGE)
        for (kind, _), document in operator.items():
            if kind in {"CustomResourceDefinition", "ClusterRole", "ClusterRoleBinding"}:
                self.assertNotIn("namespace", document["metadata"])
            else:
                self.assertEqual(document["metadata"]["namespace"], "keycloak")
        database = objects(application_command(management()["Application", "keycloak-idp"]))
        self.assertEqual(len(database), 16)
        self.assertFalse(set(operator) & set(database))
        forbidden = {"Keycloak", "KeycloakRealmImport", "KeycloakOIDCClient", "KeycloakSAMLClient",
                     "HTTPRoute", "Ingress", "Secret", "Job", "CronJob", "Application"}
        self.assertFalse(forbidden & {kind for kind, _ in operator.keys() | database.keys()})
        self.assertEqual({name for kind, name in operator.keys() | database.keys() if kind == "Deployment"},
                         {"keycloak-operator"})

    def test_operator_application_refuses_namespace_release_and_profile_overrides(self):
        application = self.application()
        for arguments, message in [
            ({"namespace": "default"}, "exact namespace/release identity required"),
            ({"release": "other"}, "exact namespace/release identity required"),
        ]:
            for skip_schema in (False, True):
                with self.subTest(arguments=arguments, skip_schema=skip_schema):
                    command = application_command(application, **arguments)
                    if skip_schema:
                        command.append("--skip-schema-validation")
                    result = subprocess.run(command, capture_output=True, text=True)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(message, result.stderr)
        for skip_schema in (False, True):
            with self.subTest(namespaceOverride=True, skip_schema=skip_schema):
                command = application_command(application) + ["--set", "namespaceOverride=default"]
                if skip_schema:
                    command.append("--skip-schema-validation")
                result = subprocess.run(command, capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                if skip_schema:
                    self.assertIn("immutable supported-field profile mismatch", result.stderr)


if __name__ == "__main__":
    unittest.main()
