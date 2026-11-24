"""Offline tests for scoped public Keycloak HTTPRoute (/realms/kkamji and /resources only)."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
HELM = os.environ.get("HELM_BIN", "helm")
CHART = ROOT / "charts/keycloak-public-access"
MGMT_VALUES = ROOT / "charts/argo-applications/management_local_values.yaml"


def render(
    release="keycloak-public-access",
    namespace="keycloak",
    values_file=None,
    extra_args=(),
):
    cmd = [
        HELM,
        "template",
        release,
        str(CHART),
        "-n",
        namespace,
        "--kube-version",
        "1.36.1",
    ]
    if values_file is not None:
        cmd.extend(["-f", str(values_file)])
    cmd.extend(extra_args)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60)


class PublicRouteContractTests(unittest.TestCase):
    def test_defaults_fail_closed_with_zero_objects(self):
        result = render()
        self.assertEqual(result.returncode, 0, result.stderr)
        docs = [d for d in yaml.safe_load_all(result.stdout) if d]
        self.assertEqual(docs, [])

    def test_local_values_render_only_scoped_public_http_route(self):
        result = render(values_file=CHART / "kkamji_local_values.yaml")
        self.assertEqual(result.returncode, 0, result.stderr)
        docs = [d for d in yaml.safe_load_all(result.stdout) if d]
        self.assertEqual(len(docs), 1)
        route = docs[0]
        self.assertEqual(route["apiVersion"], "gateway.networking.k8s.io/v1")
        self.assertEqual(route["kind"], "HTTPRoute")
        self.assertEqual(
            route["metadata"], {"name": "keycloak-public", "namespace": "keycloak"}
        )
        self.assertEqual(
            route["spec"],
            {
                "hostnames": ["sso.kkamji.net"],
                "parentRefs": [
                    {
                        "group": "gateway.networking.k8s.io",
                        "kind": "Gateway",
                        "name": "kkamji",
                        "namespace": "envoy-gateway-system",
                        "sectionName": "https",
                    }
                ],
                "rules": [
                    {
                        "matches": [
                            {"path": {"type": "PathPrefix", "value": "/realms/kkamji"}},
                            {"path": {"type": "PathPrefix", "value": "/resources"}},
                        ],
                        "backendRefs": [
                            {
                                "group": "",
                                "kind": "Service",
                                "name": "keycloak-service",
                                "port": 8080,
                                "weight": 1,
                            }
                        ],
                    }
                ],
            },
        )
        paths = [
            m["path"]["value"] for r in route["spec"]["rules"] for m in r["matches"]
        ]
        self.assertEqual(paths, ["/realms/kkamji", "/resources"])
        for forbidden in ("/", "/admin", "/realms/master", "/health", "/metrics"):
            self.assertNotIn(forbidden, paths)

    def test_refuses_invalid_flags_extra_fields_and_wrong_identity(self):
        unsafe = [
            {"keycloakPublicRoute": {"enabled": "true"}},
            {"keycloakPublicRoute": {"enabled": 1}},
            {"keycloakPublicRoute": {"enabled": True, "hostname": "*.kkamji.net"}},
            {"keycloakPublicRoute": {"enabled": True}, "extra": True},
        ]
        for payload in unsafe:
            for skip_schema in (False, True):
                with self.subTest(payload=payload, skip_schema=skip_schema):
                    with tempfile.TemporaryDirectory() as tmp:
                        vf = Path(tmp) / "bad.yaml"
                        vf.write_text(yaml.safe_dump(payload))
                        extra = ("--skip-schema-validation",) if skip_schema else ()
                        res = render(values_file=vf, extra_args=extra)
                        self.assertNotEqual(res.returncode, 0)
        for release, ns in [
            ("other", "keycloak"),
            ("keycloak-public-access", "default"),
        ]:
            with self.subTest(release=release, ns=ns):
                res = render(
                    release=release,
                    namespace=ns,
                    values_file=CHART / "kkamji_local_values.yaml",
                )
                self.assertNotEqual(res.returncode, 0)
                self.assertIn("exact namespace/release identity required", res.stderr)

    def test_management_root_wires_keycloak_public_access_and_lints(self):
        values = yaml.safe_load(MGMT_VALUES.read_text())
        app = values["applications"].get("keycloak-public-access")
        self.assertEqual(
            app,
            {
                "enabled": True,
                "name": "keycloak-public-access",
                "project": "management",
                "destination": {"namespace": "keycloak"},
                "source": {
                    "repoURL": "https://github.com/KKamJi98/helm-charts.git",
                    "targetRevision": "main",
                    "path": "charts/keycloak-public-access",
                    "helm": {
                        "releaseName": "keycloak-public-access",
                        "valueFiles": ["kkamji_local_values.yaml"],
                    },
                },
            },
        )
        lint = subprocess.run(
            [
                HELM,
                "lint",
                "--strict",
                str(CHART),
                "-f",
                str(CHART / "kkamji_local_values.yaml"),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(lint.returncode, 0, lint.stdout + lint.stderr)


if __name__ == "__main__":
    unittest.main()
