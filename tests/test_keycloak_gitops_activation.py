"""Offline management-root activation boundary; no credentials or cluster access."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml

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
        application = self.application()
        source = application["spec"]["source"]
        chart = ROOT / source["path"]
        command = [HELM, "template", source["helm"]["releaseName"], str(chart), "-n", "keycloak",
                   "--kube-version", "1.36.1", "--skip-tests"]
        for value_file in source["helm"]["valueFiles"]:
            command.extend(["-f", str(chart / value_file)])
        rendered = objects(command)
        self.assertEqual(len(rendered), 16)
        self.assertIn(("Cluster", "keycloak-db"), rendered)
        self.assertIn(("ScheduledBackup", "keycloak-db-backup"), rendered)
        self.assertIn(("ExternalSecret", "keycloak-db-client-trust"), rendered)
        self.assertFalse(any(kind in {"Keycloak", "KeycloakRealmImport", "HTTPRoute", "Deployment"} for kind, _ in rendered))
        for document in rendered.values():
            self.assertEqual(document["metadata"]["namespace"], "keycloak")
        self.assertEqual(rendered["Cluster", "keycloak-db"]["metadata"]["annotations"]["argocd.argoproj.io/sync-options"], "Prune=false,Delete=false")


if __name__ == "__main__":
    unittest.main()
