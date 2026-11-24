"""Offline management-root activation boundary; no credentials or cluster access."""
import copy
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

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
    for parameter in source["helm"].get("parameters", []):
        if parameter.get("forceString") is not True:
            raise AssertionError("offline fixture requires explicit forceString parameters")
        command.extend(["--set-string", parameter["name"] + "=" + parameter["value"]])
    return command


class ManagementServerActivationTests(unittest.TestCase):
    def application(self):
        application = management().get(("Application", "keycloak-idp"))
        if application is None:
            raise AssertionError("management root must declare the explicit private server phase")
        return application

    def assert_application_contract(self, application):
        self.assertEqual(application["metadata"]["namespace"], "argocd")
        spec = application["spec"]
        self.assertEqual(spec["project"], "management")
        self.assertEqual(spec["destination"], {"namespace": "keycloak", "server": "https://kubernetes.default.svc"})
        self.assertEqual(spec["source"], {
            "repoURL": "https://github.com/KKamJi98/helm-charts.git",
            "targetRevision": "main", "path": "charts/keycloak-idp",
            "helm": {
                "releaseName": "keycloak", "valueFiles": ["kkamji_local_values.yaml", "production-values.yaml"],
                "parameters": [{"name": "productionPhase", "value": "application", "forceString": True}],
            },
        })
        self.assertIs(spec["source"]["helm"]["parameters"][0]["forceString"], True)
        self.assertTrue(spec["syncPolicy"]["automated"]["selfHeal"])
        self.assertIn("CreateNamespace=true", spec["syncPolicy"]["syncOptions"])
        self.assertIn("ServerSideApply=true", spec["syncPolicy"]["syncOptions"])
        self.assertEqual(spec["syncPolicy"], yaml.safe_load(VALUES.read_text())["syncPolicy"])
        self.assertEqual(application["metadata"]["finalizers"], ["resources-finalizer.argocd.argoproj.io"])

    def test_server_application_uses_exact_release_and_profile(self):
        self.assert_application_contract(self.application())

    def test_server_application_contract_refuses_sync_policy_weakening(self):
        original = yaml.safe_load(VALUES.read_text())
        for policy in ("selfHeal", "CreateNamespace=true", "ServerSideApply=true"):
            with self.subTest(policy=policy):
                invalid = copy.deepcopy(original)
                if policy == "selfHeal":
                    invalid["syncPolicy"]["automated"]["selfHeal"] = False
                else:
                    invalid["syncPolicy"]["syncOptions"].remove(policy)
                with tempfile.TemporaryDirectory() as temporary:
                    fixture = Path(temporary) / "management-values.yaml"
                    fixture.write_text(yaml.safe_dump(invalid, sort_keys=False))
                    application = management(fixture)["Application", "keycloak-idp"]
                    with mock.patch(__name__ + ".VALUES", fixture):
                        with self.assertRaises(AssertionError):
                            self.assert_application_contract(application)

    def test_existing_management_applications_are_unchanged(self):
        original = yaml.safe_load(VALUES.read_text())
        original["applications"]["keycloak-idp"]["source"]["helm"].pop("parameters", None)
        with tempfile.TemporaryDirectory() as temporary:
            before_values = Path(temporary) / "management-values.yaml"
            before_values.write_text(yaml.safe_dump(original, sort_keys=False))
            before, after = management(before_values), management()
        self.assertEqual(len(before), 20)
        self.assertEqual(set(after), set(before))
        self.assertEqual(after["Application", "keycloak-idp"]["spec"]["source"]["helm"].pop("parameters", None),
                         [{"name": "productionPhase", "value": "application", "forceString": True}])
        self.assertEqual(after, before)

    def test_application_values_add_only_private_server_to_unchanged_database(self):
        application = self.application()
        rendered = objects(application_command(application))
        database_application = copy.deepcopy(application)
        database_application["spec"]["source"]["helm"].pop("parameters", None)
        database = objects(application_command(database_application))
        self.assertEqual(yaml.safe_load((preparation.APP / "production-values.yaml").read_text())["productionPhase"], "database")
        self.assertEqual(len(database), 16)
        self.assertEqual(len(rendered), 17)
        self.assertEqual(set(rendered) - set(database), {("Keycloak", "keycloak")})
        self.assertEqual({key: rendered[key] for key in database}, database)
        self.assertIn(("Cluster", "keycloak-db"), rendered)
        self.assertIn(("ScheduledBackup", "keycloak-db-backup"), rendered)
        self.assertIn(("ExternalSecret", "keycloak-db-client-trust"), rendered)
        forbidden = {"HTTPRoute", "Ingress", "KeycloakRealmImport", "KeycloakOIDCClient", "KeycloakSAMLClient",
                     "Deployment", "StatefulSet", "Secret", "Job", "CronJob", "Application", "Namespace"}
        self.assertFalse(forbidden & {kind for kind, _ in rendered})
        for document in rendered.values():
            self.assertEqual(document["metadata"]["namespace"], "keycloak")
        cluster = rendered["Cluster", "keycloak-db"]
        self.assertEqual(cluster["metadata"]["annotations"]["argocd.argoproj.io/sync-options"], "Prune=false,Delete=false")
        self.assertNotIn("cnpg.io/reconcilePodSpec", cluster["metadata"].get("annotations", {}))
        self.assertNotIn("tolerations", cluster["spec"]["affinity"])
        preparation_result = preparation.KeycloakPreparationTests.command(preparation.APP)
        self.assertEqual(preparation_result.returncode, 0, preparation_result.stderr)
        default = {preparation.identity(obj): obj for obj in preparation.documents(preparation_result.stdout)}
        self.assertEqual(len(default), 8)
        server = rendered["Keycloak", "keycloak"]
        expected_spec = copy.deepcopy(default["Keycloak", "keycloak"]["spec"])
        expected_spec["instances"] = 1
        expected_spec["resources"] = {"requests": {"cpu": "50m", "memory": "768Mi"}, "limits": {"cpu": "1500m", "memory": "1536Mi"}}
        self.assertEqual(server["spec"], expected_spec)
        self.assertEqual(default["Keycloak", "keycloak"]["spec"]["instances"], 2)
        self.assertEqual(cluster["spec"]["instances"], 1)
        self.assertEqual(cluster["spec"]["resources"], {"requests": {"cpu": "25m", "memory": "256Mi"}, "limits": {"cpu": "1", "memory": "512Mi"}})
        self.assertEqual(server["apiVersion"], "k8s.keycloak.org/v2beta1")
        self.assertEqual(server["metadata"]["annotations"], {"argocd.argoproj.io/sync-wave": "1"})
        spec = server["spec"]
        self.assertEqual(spec["image"], preparation.SERVER_IMAGE)
        self.assertIs(spec["startOptimized"], False)
        self.assertEqual(spec["instances"], 1)
        self.assertEqual(spec["resources"]["requests"], {"cpu": "50m", "memory": "768Mi"})
        self.assertEqual(spec["additionalOptions"], [{"name": "db-tls-mode", "value": "verify-server"}])
        self.assertEqual(spec["db"]["host"], "keycloak-db-rw.keycloak.svc.cluster.local")
        self.assertEqual(spec["truststores"], {"database": {"secret": {"name": "keycloak-db-client-trust", "optional": False}}})
        self.assertEqual(spec["http"], {"httpEnabled": True, "httpPort": 8080})
        self.assertEqual(spec["ingress"], {"enabled": False})

    def test_server_application_contract_rejects_parameter_and_identity_drift(self):
        application = self.application()
        parameter = {"name": "productionPhase", "value": "application", "forceString": True}
        cases = [
            (("spec", "source", "helm", "parameters"), []),
            (("spec", "source", "helm", "parameters"), [parameter, {"name": "extra", "value": "true", "forceString": True}]),
            (("spec", "source", "helm", "parameters"), [{**parameter, "name": "productionPhaze"}]),
            (("spec", "source", "helm", "parameters"), [{**parameter, "value": "database"}]),
            (("spec", "source", "helm", "parameters"), [{**parameter, "forceString": False}]),
            (("spec", "source", "helm", "releaseName"), "other"),
            (("spec", "destination", "namespace"), "default"),
            (("spec", "source", "helm", "valueFiles"), ["production-values.yaml", "kkamji_local_values.yaml"]),
            (("spec", "source", "helm", "valueFiles"), ["kkamji_local_values.yaml"]),
            (("spec", "source", "path"), "charts/keycloak"),
            (("spec", "source", "targetRevision"), "other"),
        ]
        for path, value in cases:
            with self.subTest(path=path, value=value):
                invalid = copy.deepcopy(application)
                target = invalid
                for field in path[:-1]:
                    target = target[field]
                target[path[-1]] = value
                with self.assertRaises(AssertionError):
                    self.assert_application_contract(invalid)

    def test_server_application_refuses_identity_realm_and_public_activation(self):
        application = self.application()
        for arguments, override, message in [
            ({"namespace": "default"}, [], "exact namespace/release identity required"),
            ({"release": "other"}, [], "exact namespace/release identity required"),
            ({}, ["--set", "keycloak.ingress.enabled=true"], "immutable supported-field profile mismatch"),
            ({}, ["--set", "realm.enabled=true"], "immutable supported-field profile mismatch"),
            ({}, ["--set", "httpRoute.enabled=true"], "immutable supported-field profile mismatch"),
            ({}, ["--set", "client.enabled=true"], "immutable supported-field profile mismatch"),
        ]:
            for skip_schema in (False, True):
                with self.subTest(arguments=arguments, override=override, skip_schema=skip_schema):
                    command = application_command(application, **arguments) + override
                    if skip_schema:
                        command.append("--skip-schema-validation")
                    result = subprocess.run(command, capture_output=True, text=True)
                    self.assertNotEqual(result.returncode, 0)
                    if skip_schema or arguments:
                        self.assertIn(message, result.stderr)


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
        idp = objects(application_command(management()["Application", "keycloak-idp"]))
        self.assertEqual(len(idp), 17)
        self.assertFalse(set(operator) & set(idp))
        forbidden = {"Keycloak", "KeycloakRealmImport", "KeycloakOIDCClient", "KeycloakSAMLClient",
                     "HTTPRoute", "Ingress", "Secret", "Job", "CronJob", "Application"}
        self.assertFalse(forbidden & {kind for kind, _ in operator})
        self.assertEqual(forbidden & {kind for kind, _ in idp}, {"Keycloak"})
        self.assertEqual({name for kind, name in idp if kind == "Keycloak"}, {"keycloak"})
        self.assertEqual({name for kind, name in operator.keys() | idp.keys() if kind == "Deployment"},
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
