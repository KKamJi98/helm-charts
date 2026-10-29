"""Offline Hindsight chart contracts; all auth/model fixtures are synthetic.

Run: uv run --no-project --with pyyaml python -m unittest discover \
    -s tests -p test_hindsight_chart.py -v
No cluster, credential files, model downloads, or dependency rebuilds are used.
"""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "charts/hindsight"
HELM = os.environ.get("HELM", "helm")
REPO = "intfloat/multilingual-e5-small"
REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
API_IMAGE = (
    "ghcr.io/kkamji98/hindsight-security:1.1.0-20261029@sha256:"
    "99f91e62f5e870d91a2e03bb3fce695541dff694dac6dcdb692319f462060074"
)
CP_IMAGE = (
    "ghcr.io/vectorize-io/hindsight-control-plane:1.1.0@sha256:"
    "373f86848649a8dadc9b2d9ecf1d18b4c446162ca7b556fc4152e92ef433e983"
)
MODEL_HASHES = {
    "config.json": "69137736cab8b8903a07fe8afaafdda25aac55415a12a55d1bffa9f581abf959",
    "onnx/model.onnx": "ca456c06b3a9505ddfd9131408916dd79290368331e7d76bb621f1cba6bc8665",
    "sentencepiece.bpe.model": "cfc8146abe2a0488e9e2a0c56de7952f7c11ab059eca145a0a727afce0db2865",
    "special_tokens_map.json": "d05497f1da52c5e09554c0cd874037a083e1dc1b9cfd48034d1c717f1afc07a7",  # gitleaks:allow - public model SHA256
    "tokenizer.json": "0b44a9d7b51c3c62626640cda0e2c2f70fdacdc25bbbd68038369d14ebdf4c39",  # gitleaks:allow - public model SHA256
    "tokenizer_config.json": "a1d6bc8734a6f635dc158508bef000f8e2e5a759c7d92f984b2c86e5ff53425b",  # gitleaks:allow - public model SHA256
}


def render(*extra):
    return subprocess.run(
        [
            HELM,
            "template",
            "hindsight",
            str(CHART),
            "-n",
            "hindsight",
            "--skip-tests",
            "--kube-version",
            "1.36.1",
            "-f",
            str(CHART / "kkamji_local_values.yaml"),
            *extra,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


def objects(result):
    if result.returncode:
        raise AssertionError(result.stderr)
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


def load_script(name):
    """Load only chart-owned public source, without creating source pycache."""
    source = CHART / "files" / name
    module = types.ModuleType(name.removesuffix(".py"))
    module.__file__ = str(source)
    exec(compile(source.read_text(), str(source), "exec"), module.__dict__)  # noqa: S102 - fixed chart-owned test sources
    return module


class ChartTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs = objects(render())
        cls.index = {(d["kind"], d["metadata"]["name"]): d for d in cls.docs}
        cls.api = cls.index["StatefulSet", "hindsight-api"]
        cls.pod = cls.api["spec"]["template"]["spec"]
        cls.container = cls.pod["containers"][0]
        cls.env = {e["name"]: e.get("value") for e in cls.container["env"]}
        cls.job = next(d for d in cls.docs if d["kind"] == "Job")

    def test_bootstrap_configmaps_resolve_every_mounted_script_and_manifest(self):
        for owner in (self.api, self.job):
            pod = owner["spec"]["template"]["spec"]
            for volume in pod.get("volumes", []):
                if "configMap" not in volume:
                    continue
                reference = volume["configMap"]
                key = ("ConfigMap", reference["name"])
                self.assertTrue(
                    key in self.index, f"missing bootstrap ConfigMap: {key[1]}"
                )
                data = self.index[key]["data"]
                for item in reference.get("items", []):
                    self.assertIn(item["key"], data)
                for filename, payload in data.items():
                    if filename.endswith(".py"):
                        self.assertEqual(
                            payload, (CHART / "files" / filename).read_text()
                        )
                    elif filename.endswith(".json"):
                        self.assertEqual(json.loads(payload), MODEL_HASHES)

    def test_single_api_writer_and_only_official_control_plane_deployment(self):
        self.assertEqual(
            len(self.index), len(self.docs), "duplicate resource identities"
        )
        workloads = [
            d
            for d in self.docs
            if d["kind"] in ("Deployment", "StatefulSet", "DaemonSet")
        ]
        self.assertEqual(
            {(d["kind"], d["metadata"]["name"]) for d in workloads},
            {
                ("StatefulSet", "hindsight-api"),
                ("Deployment", "hindsight-control-plane"),
            },
        )
        self.assertEqual(self.api["spec"]["replicas"], 1)
        self.assertEqual(self.api["spec"]["podManagementPolicy"], "OrderedReady")
        self.assertIn(
            self.api["spec"]["updateStrategy"]["type"], ("RollingUpdate", "OnDelete")
        )
        self.assertEqual(self.container["command"], ["/app/start-all.sh"])
        self.assertEqual(self.env["HINDSIGHT_API_WORKERS"], "1")
        self.assertEqual(self.env["HINDSIGHT_API_WORKER_ENABLED"], "true")
        service = self.index["Service", "hindsight-api"]["spec"]
        self.assertEqual(
            service["selector"], self.api["spec"]["selector"]["matchLabels"]
        )
        self.assertTrue(any(p["port"] == 8888 for p in service["ports"]))
        for doc in self.docs:
            if doc["kind"] == "Service":
                self.assertEqual(doc["spec"].get("type", "ClusterIP"), "ClusterIP")
        self.assertFalse(
            {"Ingress", "HorizontalPodAutoscaler", "ScaledObject", "Secret"}
            & {d["kind"] for d in self.docs}
        )

    def test_approved_digest_pins_and_nonroot_no_serviceaccount_authority(self):
        accounts = {
            d["metadata"]["name"]: d for d in self.docs if d["kind"] == "ServiceAccount"
        }
        for doc in self.docs:
            if doc["kind"] not in ("StatefulSet", "Deployment", "Job"):
                continue
            pod = doc["spec"]["template"]["spec"]
            account = accounts.get(pod.get("serviceAccountName", "default"), {})
            self.assertIs(
                pod.get(
                    "automountServiceAccountToken",
                    account.get("automountServiceAccountToken"),
                ),
                False,
            )
            security = pod.get("securityContext", {})
            self.assertEqual(
                security.get("seccompProfile", {}).get("type"), "RuntimeDefault"
            )
            self.assertFalse(pod.get("hostNetwork", False))
            self.assertFalse(pod.get("hostPID", False))
            self.assertFalse(pod.get("hostIPC", False))
            for volume in pod.get("volumes", []):
                self.assertNotIn("hostPath", volume)
                self.assertFalse(
                    any(
                        "serviceAccountToken" in source
                        for source in volume.get("projected", {}).get("sources", [])
                    )
                )
            expected_image = (
                CP_IMAGE
                if doc["metadata"]["name"] == "hindsight-control-plane"
                else API_IMAGE
            )
            for container in pod.get("containers", []) + pod.get("initContainers", []):
                with self.subTest(
                    workload=doc["metadata"]["name"], container=container["name"]
                ):
                    self.assertEqual(container["image"], expected_image)
                    effective = {**security, **container.get("securityContext", {})}
                    self.assertIs(effective.get("runAsNonRoot"), True)
                    self.assertGreater(effective.get("runAsUser", 0), 0)
                    self.assertFalse(effective.get("privileged", False))
                    self.assertIs(effective.get("allowPrivilegeEscalation"), False)
                    self.assertIn(
                        "ALL", effective.get("capabilities", {}).get("drop", [])
                    )

    def test_auth_home_is_dedicated_and_seed_is_optional_init_only(self):
        volumes = {v["name"]: v for v in self.pod["volumes"]}
        mounts = {m["mountPath"]: m for m in self.container["volumeMounts"]}
        auth_volume = volumes[mounts["/auth"]["name"]]
        self.assertEqual(
            auth_volume["persistentVolumeClaim"]["claimName"], "hindsight-chatgpt"
        )
        self.assertNotEqual(
            mounts["/auth"]["name"], mounts["/home/hindsight/.pg0"]["name"]
        )
        seed_volume = next(v for v in volumes.values() if "secret" in v)
        self.assertIs(seed_volume["secret"]["optional"], True)
        self.assertEqual(seed_volume["secret"]["defaultMode"], 0o440)
        self.assertNotIn(
            seed_volume["name"], {m["name"] for m in self.container["volumeMounts"]}
        )
        seed = next(
            c
            for c in self.pod["initContainers"]
            if "seed_auth.py" in " ".join(c.get("command", []))
        )
        self.assertTrue(
            any(
                m["name"] == seed_volume["name"] and m.get("readOnly")
                for m in seed["volumeMounts"]
            )
        )
        self.assertEqual(self.env["HINDSIGHT_API_LLM_CHATGPT_HOME"], "/auth/chatgpt")
        self.assertEqual(self.env["HINDSIGHT_API_LLM_PROVIDER"], "chatgpt")
        self.assertFalse(any("FALLBACK" in key for key in self.env))
        values = yaml.safe_load((CHART / "kkamji_local_values.yaml").read_text())
        self.assertEqual(
            self.env["HINDSIGHT_API_LLM_MODEL"], values["runtime"]["model"]
        )
        self.assertEqual(
            self.env["HINDSIGHT_API_LLM_REASONING_EFFORT"],
            values["runtime"]["reasoningEffort"],
        )

    def test_native_api_and_mcp_auth_are_not_disabled(self):
        self.assertEqual(
            self.env["HINDSIGHT_API_TENANT_EXTENSION"],
            "hindsight_api.extensions.builtin.tenant:ApiKeyTenantExtension",
        )
        self.assertEqual(
            self.env.get("HINDSIGHT_API_TENANT_MCP_AUTH_DISABLED"), "false"
        )
        api_secret = self.index["ExternalSecret", "hindsight-api-auth"]["spec"]
        keys = {e["secretKey"]: e["remoteRef"]["property"] for e in api_secret["data"]}
        self.assertEqual(keys["HINDSIGHT_API_TENANT_API_KEY"], "api_key")
        self.assertTrue(
            any(
                e["secretRef"]["name"] == "hindsight-api-auth"
                and not e["secretRef"].get("optional", False)
                for e in self.container["envFrom"]
            )
        )

    def test_runtime_models_are_readonly_and_cpu_e5_config_is_complete(self):
        for container in self.pod["containers"] + self.pod["initContainers"]:
            mount = next(
                m for m in container["volumeMounts"] if m["mountPath"] == "/models"
            )
            self.assertIs(mount["readOnly"], True)
        volume = next(v for v in self.pod["volumes"] if v["name"] == "models")
        self.assertIs(volume["persistentVolumeClaim"]["readOnly"], True)
        self.assertNotIn("HINDSIGHT_API_EMBEDDINGS_ONNX_CONFIG", self.env)
        expected = {
            "MODEL_ID": REPO,
            "MODEL_PATH": "/models/e5-small/onnx/model.onnx",
            "TOKENIZER_NAME_OR_PATH": "/models/e5-small",
            "DEVICE": "cpu",
            "DIMENSIONS": "384",
            "MAX_TOKENS": "512",
            "POOLING": "mean",
            "NORMALIZE": "true",
            "QUERY_PREFIX": "query: ",
            "PASSAGE_PREFIX": "passage: ",
            "BATCH_SIZE": "8",
            "CPU_MEM_ARENA": "false",
        }
        for field, value in expected.items():
            self.assertEqual(
                self.env.get("HINDSIGHT_API_EMBEDDINGS_ONNX_" + field), value, field
            )
        self.assertEqual(self.env["HINDSIGHT_API_RERANKER_PROVIDER"], "rrf")
        for name in (
            "HF_HUB_OFFLINE",
            "TRANSFORMERS_OFFLINE",
            "HF_HUB_DISABLE_IMPLICIT_TOKEN",
        ):
            self.assertEqual(self.env[name], "1")

    def test_health_probes_do_not_restart_for_dependency_readiness(self):
        self.assertEqual(self.container["readinessProbe"]["httpGet"]["path"], "/health")
        for name in ("startupProbe", "livenessProbe"):
            self.assertEqual(self.container[name]["httpGet"]["path"], "/health/live")

    def test_retained_rwo_claims_and_wffc_first_consumer_share_wave(self):
        claims = [d for d in self.docs if d["kind"] == "PersistentVolumeClaim"]
        self.assertEqual(
            {c["metadata"]["name"] for c in claims},
            {"hindsight-data", "hindsight-chatgpt", "hindsight-models"},
        )
        for claim in claims:
            self.assertEqual(claim["spec"]["accessModes"], ["ReadWriteOnce"])
            self.assertEqual(claim["spec"]["storageClassName"], "local-path")
            options = claim["metadata"]["annotations"][
                "argocd.argoproj.io/sync-options"
            ].split(",")
            self.assertTrue({"Prune=false", "Delete=false"}.issubset(options))
        model_pvc = self.index["PersistentVolumeClaim", "hindsight-models"]
        wave = lambda obj: int(
            obj["metadata"]
            .get("annotations", {})
            .get("argocd.argoproj.io/sync-wave", 0)
        )
        self.assertEqual(
            wave(self.job), wave(model_pvc), "WFFC PVC cannot wait for an earlier wave"
        )
        self.assertLess(wave(self.job), wave(self.api))
        for volume in self.job["spec"]["template"]["spec"]["volumes"]:
            if "configMap" in volume:
                key = ("ConfigMap", volume["configMap"]["name"])
                self.assertTrue(
                    key in self.index, f"missing bootstrap ConfigMap: {key[1]}"
                )
                self.assertLessEqual(wave(self.index[key]), wave(self.job))

    def test_model_job_has_no_credentials_no_auto_retry_and_exact_revision(self):
        spec = self.job["spec"]
        self.assertEqual(spec["backoffLimit"], 0)
        self.assertEqual(spec["parallelism"], 1)
        self.assertEqual(spec["completions"], 1)
        self.assertNotIn("ttlSecondsAfterFinished", spec)
        self.assertNotIn(
            "argocd.argoproj.io/hook", self.job["metadata"].get("annotations", {})
        )
        pod = spec["template"]["spec"]
        self.assertEqual(pod["restartPolicy"], "Never")
        self.assertFalse(any("secret" in v for v in pod["volumes"]))
        for container in pod["containers"]:
            self.assertNotIn("envFrom", container)
            self.assertFalse(any("valueFrom" in e for e in container.get("env", [])))
        args = pod["containers"][0]["args"]
        self.assertEqual(args[args.index("--repo") + 1], REPO)
        self.assertEqual(args[args.index("--revision") + 1], REVISION)
        self.assertEqual(self.pod["nodeSelector"], pod["nodeSelector"])
        mount = next(
            m
            for m in pod["containers"][0]["volumeMounts"]
            if m["mountPath"] == "/models"
        )
        self.assertFalse(mount.get("readOnly", False))

    def test_model_job_name_is_stable_and_changes_with_pod_inputs(self):
        name = self.job["metadata"]["name"]
        job_name = lambda docs: next(
            d["metadata"]["name"] for d in docs if d["kind"] == "Job"
        )
        self.assertEqual(job_name(objects(render())), name)
        override = (
            "runtime.nodeSelector.kubernetes\\.io/hostname=synthetic-offline-node"
        )
        self.assertNotEqual(job_name(objects(render("--set-string", override))), name)

    def test_control_plane_requires_private_ui_and_native_api_secrets(self):
        cp = self.index["Deployment", "hindsight-control-plane"]
        self.assertEqual(cp["spec"]["replicas"], 1)
        pod = cp["spec"]["template"]["spec"]
        container = pod["containers"][0]
        self.assertEqual(container["image"], CP_IMAGE)
        self.assertTrue(
            any(
                e["secretRef"]["name"] == "hindsight-control-plane-auth"
                and not e["secretRef"].get("optional", False)
                for e in container["envFrom"]
            )
        )
        env = {e["name"]: e.get("value") for e in container["env"]}
        self.assertEqual(
            env["HINDSIGHT_CP_DATAPLANE_API_URL"], "http://hindsight-api:8888"
        )
        secret = self.index["ExternalSecret", "hindsight-control-plane-auth"]["spec"]
        keys = {e["secretKey"]: e["remoteRef"]["property"] for e in secret["data"]}
        self.assertEqual(
            keys,
            {
                "HINDSIGHT_CP_ACCESS_KEY": "ui_access_key",
                "HINDSIGHT_CP_DATAPLANE_API_KEY": "api_key",
            },
        )
        guard = next(
            c for c in pod["initContainers"] if c["name"] == "require-private-access"
        )
        refs = {e["name"]: e["valueFrom"]["secretKeyRef"] for e in guard["env"]}
        for name in keys:
            self.assertEqual(refs[name]["key"], name)
            self.assertEqual(refs[name]["name"], "hindsight-control-plane-auth")
            self.assertFalse(refs[name].get("optional", False))
            self.assertIn(name, " ".join(guard["command"]))

    def test_gateway_preserves_control_plane_api_paths_and_protects_both_routes(self):
        routes = [d for d in self.docs if d["kind"] == "HTTPRoute"]
        self.assertEqual(
            {r["metadata"]["name"] for r in routes}, {"hindsight-ui", "hindsight-api"}
        )
        paths = {}
        for route in routes:
            self.assertEqual(route["spec"]["hostnames"], ["hindsight.kkamji.net"])
            self.assertTrue(
                any(
                    ref["name"] == "kkamji"
                    and ref["namespace"] == "envoy-gateway-system"
                    and ref["sectionName"] == "https"
                    for ref in route["spec"]["parentRefs"]
                )
            )
            for rule in route["spec"]["rules"]:
                backend = rule["backendRefs"][0]
                self.assertIn(("Service", backend["name"]), self.index)
                for match in rule["matches"]:
                    self.assertEqual(match["path"]["type"], "PathPrefix")
                    paths[match["path"]["value"]] = backend["name"]
        self.assertEqual(paths["/"], "hindsight-control-plane")
        self.assertEqual(paths["/v1"], "hindsight-api")
        self.assertEqual(paths["/mcp"], "hindsight-api")
        self.assertFalse(
            any(
                path == "/api" or path.startswith("/api/")
                for path in paths
                if paths[path] == "hindsight-api"
            )
        )
        policies = {
            d["spec"]["targetRefs"][0]["name"]: d["spec"]
            for d in self.docs
            if d["kind"] == "SecurityPolicy"
        }
        self.assertEqual(set(policies), {"hindsight-ui", "hindsight-api"})
        ui = policies["hindsight-ui"]
        self.assertNotIn("basicAuth", ui)
        client_id = (
            "47443292322-rlsttvfbbvbp3lg5icerudodded0i7ev.apps.googleusercontent.com"
        )
        self.assertEqual(
            ui.get("oidc"),
            {
                "provider": {"issuer": "https://accounts.google.com"},
                "clientID": client_id,
                "clientSecret": {
                    "name": "hindsight-google-oidc",
                    "group": "",
                    "kind": "Secret",
                },
                "scopes": ["openid", "email"],
                "redirectURL": "https://hindsight.kkamji.net/oauth2/callback",
                "logoutPath": "/oauth2/logout",
                "cookieNames": {"idToken": "HindsightGoogleIdToken"},
                "cookieConfig": {"sameSite": "Lax"},
                "forwardAccessToken": False,
                "passThroughAuthHeader": False,
                "disableTokenEncryption": False,
                "refreshToken": True,
            },
        )
        self.assertEqual(
            ui.get("jwt"),
            {
                "optional": False,
                "providers": [
                    {
                        "name": "google-owner",
                        "issuer": "https://accounts.google.com",
                        "audiences": [client_id],
                        "remoteJWKS": {
                            "uri": "https://www.googleapis.com/oauth2/v3/certs",
                            "cacheDuration": "300s",
                        },
                        "extractFrom": {"cookies": ["HindsightGoogleIdToken"]},
                    }
                ],
            },
        )
        self.assertEqual(
            ui.get("authorization"),
            {
                "defaultAction": "Deny",
                "rules": [
                    {
                        "name": "exact-owner-email",
                        "action": "Allow",
                        "principal": {
                            "jwt": {
                                "provider": "google-owner",
                                "claims": [
                                    {
                                        "name": "email",
                                        "valueType": "String",
                                        "values": ["rlaxowl5460@gmail.com"],
                                    }
                                ],
                            }
                        },
                    }
                ],
            },
        )
        auth = policies["hindsight-api"]["apiKeyAuth"]
        self.assertEqual(
            auth,
            {
                "credentialRefs": [
                    {
                        "group": "",
                        "kind": "Secret",
                        "name": "hindsight-gateway-client-keys",
                    }
                ],
                "extractFrom": [{"headers": ["X-Hindsight-Client-Key"]}],
                "sanitize": True,
                "forwardClientIDHeader": "X-Hindsight-Client-ID",
            },
            "only the gateway key header is consumed; native Authorization is preserved",
        )
        self.assertEqual(set(policies["hindsight-api"]), {"targetRefs", "apiKeyAuth"})

    def test_edge_secrets_are_separate_from_unchanged_native_and_rollback_secrets(self):
        expected = {
            "hindsight-google-oidc": {"client-secret": "oidc_client_secret"},
            "hindsight-gateway-client-keys": {
                key: key
                for key in ("wsl_claude", "wsl_hermes", "mac_claude", "mac_hermes")
            },
        }
        for name, mapping in expected.items():
            with self.subTest(secret=name):
                self.assertIn(("ExternalSecret", name), set(self.index))
                spec = self.index["ExternalSecret", name]["spec"]
                self.assertNotIn("dataFrom", spec)
                self.assertEqual(
                    spec["target"],
                    {
                        "name": name,
                        "creationPolicy": "Orphan",
                        "deletionPolicy": "Retain",
                        "template": {"type": "Opaque"},
                    },
                )
                self.assertEqual(
                    spec["secretStoreRef"],
                    {
                        "name": "parameter-store",
                        "kind": "ClusterSecretStore",
                    },
                )
                self.assertEqual(
                    {e["secretKey"]: e["remoteRef"]["property"] for e in spec["data"]},
                    mapping,
                )
                self.assertEqual(
                    {e["remoteRef"]["key"] for e in spec["data"]},
                    {"/kkamji/automation/hindsight/edge-auth"},
                )
        legacy = {
            "hindsight-api-auth",
            "hindsight-control-plane-auth",
            "hindsight-gateway-ui-auth",
            "hindsight-gateway-api-auth",
        }
        secrets = {
            d["metadata"]["name"]: d["spec"]
            for d in self.docs
            if d["kind"] == "ExternalSecret"
        }
        self.assertEqual(set(secrets), legacy | set(expected))
        for name in legacy:
            self.assertEqual(
                {e["remoteRef"]["key"] for e in secrets[name]["data"]},
                {"/kkamji/automation/hindsight/access"},
            )
        self.assertEqual(
            secrets["hindsight-gateway-api-auth"]["target"]["template"]["data"],
            {"owner": "{{ .api_key }}"},
        )
        self.assertEqual(
            secrets["hindsight-gateway-ui-auth"]["data"],
            [
                {
                    "secretKey": ".htpasswd",
                    "remoteRef": {
                        "key": "/kkamji/automation/hindsight/access",
                        "property": "ui_htpasswd",
                    },
                }
            ],
        )

    def test_oidc_client_must_be_the_approved_public_id(self):
        for override in (
            "exposure.oidc.clientID=",
            "exposure.oidc.clientID=null",
            "exposure.oidc=null",
            "exposure.oidc.clientID=synthetic-wrong-client.apps.googleusercontent.com",
        ):
            with self.subTest(override=override):
                result = render("--set", override)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("approved Google OIDC clientID", result.stderr)

    def test_route_local_limits_and_response_headers_are_bounded(self):
        policies = {
            d["metadata"]["name"]: d["spec"]
            for d in self.docs
            if d["kind"] == "BackendTrafficPolicy"
        }
        self.assertEqual(set(policies), {"hindsight-ui-limits", "hindsight-api-limits"})
        for suffix, requests in (("ui", 300), ("api", 120)):
            self.assertEqual(
                policies[f"hindsight-{suffix}-limits"],
                {
                    "targetRefs": [
                        {
                            "group": "gateway.networking.k8s.io",
                            "kind": "HTTPRoute",
                            "name": f"hindsight-{suffix}",
                        }
                    ],
                    "requestBuffer": {"limit": "1Mi"},
                    "rateLimit": {
                        "type": "Local",
                        "local": {
                            "rules": [
                                {"limit": {"requests": requests, "unit": "Minute"}}
                            ]
                        },
                    },
                },
            )
        for doc in self.docs:
            if doc["kind"] != "HTTPRoute":
                continue
            for rule in doc["spec"]["rules"]:
                self.assertEqual(
                    rule.get("filters"),
                    [
                        {
                            "type": "ResponseHeaderModifier",
                            "responseHeaderModifier": {
                                "set": [
                                    {
                                        "name": "Strict-Transport-Security",
                                        "value": "max-age=86400",
                                    },
                                    {
                                        "name": "X-Content-Type-Options",
                                        "value": "nosniff",
                                    },
                                    {"name": "Referrer-Policy", "value": "no-referrer"},
                                ]
                            },
                        }
                    ],
                )
        self.assertFalse(
            {"Gateway", "EnvoyProxy", "ClientTrafficPolicy"}
            & {d["kind"] for d in self.docs}
        )

    def test_response_only_lua_preserves_authentication_and_streaming(self):
        policy = self.index[
            "EnvoyExtensionPolicy", "hindsight-response-security-headers"
        ]["spec"]
        self.assertEqual(
            policy["targetRefs"],
            [
                {
                    "group": "gateway.networking.k8s.io",
                    "kind": "HTTPRoute",
                    "name": f"hindsight-{suffix}",
                }
                for suffix in ("ui", "api")
            ],
        )
        self.assertEqual(
            policy["lua"],
            [
                {
                    "type": "Inline",
                    "inline": (
                        "function envoy_on_response(response_handle)\n"
                        "  local headers = response_handle:headers()\n"
                        '  headers:replace("strict-transport-security", "max-age=86400")\n'
                        '  headers:replace("x-content-type-options", "nosniff")\n'
                        '  headers:replace("referrer-policy", "no-referrer")\n'
                        "end\n"
                    ),
                }
            ],
        )
        for doc in self.docs:
            if doc["kind"] == "BackendTrafficPolicy":
                self.assertNotIn("responseOverride", doc["spec"])

    def test_exposure_off_removes_routes_and_gateway_auth_policies(self):
        docs = objects(render("--set", "exposure.enabled=false"))
        self.assertFalse(
            {
                "HTTPRoute",
                "Ingress",
                "SecurityPolicy",
                "BackendTrafficPolicy",
                "EnvoyExtensionPolicy",
            }
            & {d["kind"] for d in docs}
        )
        self.assertEqual(
            {d["metadata"]["name"] for d in docs if d["kind"] == "ExternalSecret"},
            {
                "hindsight-api-auth",
                "hindsight-control-plane-auth",
                "hindsight-gateway-ui-auth",
                "hindsight-gateway-api-auth",
            },
        )

    def test_unsafe_runtime_and_upstream_defaults_fail_closed(self):
        overrides = (
            "runtime.image=ghcr.io/vectorize-io/hindsight:latest",
            "runtime.image=ghcr.io/vectorize-io/hindsight:1.1.0@sha256:" + "d" * 64,
            "runtime.image=ghcr.io/kkamji98/hindsight-security:1.1.0-20261029@sha256:"
            + "d" * 64,
            "runtime.image=example.invalid/untrusted@sha256:" + "d" * 64,
            "model.repo=synthetic-other/model",
            "model.revision=main",
            "model.filesSha256=null",
            "model.filesSha256.tokenizer\\.json=not-a-digest",
            "runtime.model=",
            "runtime.reasoningEffort=",
            "server.api.enabled=true",
            "server.worker.enabled=true",
            "server.postgresql.enabled=true",
            "server.autoscaling.enabled=true",
            "server.ingress.enabled=true",
            "server.gatewayApi.enabled=true",
        )
        for override in overrides:
            with self.subTest(override=override):
                result = render("--set", override)
                self.assertNotEqual(
                    result.returncode, 0, "unsafe override unexpectedly rendered"
                )
                self.assertIn("Error:", result.stderr)

    def test_cilium_policies_when_present_do_not_allow_unrestricted_world(self):
        # Cilium details are owned by the chart author; do not snapshot endpoints.
        policies = [d for d in self.docs if d["kind"] == "CiliumNetworkPolicy"]
        if not policies:
            self.skipTest("optional Cilium policies are not rendered yet")
        for policy in policies:
            with self.subTest(policy=policy["metadata"]["name"]):
                for spec in policy.get("specs", [policy.get("spec", {})]):
                    # An empty selector is valid for namespace-wide default deny.
                    self.assertIn("endpointSelector", spec)
                    self.assertIsInstance(spec["endpointSelector"], dict)
                    for rule in spec.get("ingress", []):
                        self.assertFalse(
                            {"world", "all"} & set(rule.get("fromEntities", []))
                        )
                        cidrs = rule.get("fromCIDR", []) + [
                            c["cidr"] for c in rule.get("fromCIDRSet", [])
                        ]
                        self.assertFalse({"0.0.0.0/0", "::/0"} & set(cidrs))
                    for rule in spec.get("egress", []):
                        self.assertFalse(
                            {"world", "all"} & set(rule.get("toEntities", []))
                        )
                        cidrs = rule.get("toCIDR", []) + [
                            c["cidr"] for c in rule.get("toCIDRSet", [])
                        ]
                        self.assertFalse({"0.0.0.0/0", "::/0"} & set(cidrs))
                        self.assertFalse(
                            any(
                                fqdn.get("matchPattern") == "*"
                                for fqdn in rule.get("toFQDNs", [])
                            )
                        )

    def test_dns_rules_cover_multilevel_kubernetes_search_names(self):
        policies = [d for d in self.docs if d["kind"] == "CiliumNetworkPolicy"]
        self.assertEqual(
            {p["metadata"]["name"] for p in policies},
            {"hindsight-api", "hindsight-control-plane", "hindsight-model-init"},
        )
        for policy in policies:
            with self.subTest(policy=policy["metadata"]["name"]):
                patterns = [
                    rule.get("matchPattern")
                    for egress in policy["spec"]["egress"]
                    for port in egress.get("toPorts", [])
                    for rule in port.get("rules", {}).get("dns", [])
                ]
                self.assertIn("**.cluster.local", patterns)

    def test_authenticated_routes_allow_long_model_requests(self):
        routes = [d for d in self.docs if d["kind"] == "HTTPRoute"]
        self.assertEqual(
            {r["metadata"]["name"] for r in routes}, {"hindsight-ui", "hindsight-api"}
        )
        for route in routes:
            with self.subTest(route=route["metadata"]["name"]):
                for rule in route["spec"]["rules"]:
                    self.assertEqual(
                        rule.get("timeouts"),
                        {"request": "600s", "backendRequest": "600s"},
                    )

    def test_native_bank_transfer_is_enabled_with_native_auth(self):
        for capability in ("IMPORT", "EXPORT"):
            self.assertEqual(
                self.env[f"HINDSIGHT_API_ENABLE_DOCUMENT_{capability}_API"], "true"
            )
        self.assertEqual(
            self.env["HINDSIGHT_API_TENANT_EXTENSION"],
            "hindsight_api.extensions.builtin.tenant:ApiKeyTenantExtension",
        )
        self.assertEqual(self.env["HINDSIGHT_API_TENANT_MCP_AUTH_DISABLED"], "false")

    def test_public_model_cdn_is_allowed_only_for_model_bootstrap(self):
        host = "us.aws.cdn.hf.co"
        policies = [d for d in self.docs if d["kind"] == "CiliumNetworkPolicy"]
        for policy in policies:
            with self.subTest(policy=policy["metadata"]["name"]):
                dns_hosts = [
                    rule.get("matchName")
                    for egress in policy["spec"]["egress"]
                    for port in egress.get("toPorts", [])
                    for rule in port.get("rules", {}).get("dns", [])
                ]
                https_hosts = [
                    rule.get("matchName")
                    for egress in policy["spec"]["egress"]
                    for rule in egress.get("toFQDNs", [])
                    if any(
                        p.get("port") == "443"
                        for port in egress.get("toPorts", [])
                        for p in port.get("ports", [])
                    )
                ]
                expected = policy["metadata"]["name"] == "hindsight-model-init"
                self.assertEqual(host in dns_hosts, expected)
                self.assertEqual(host in https_hosts, expected)

    def test_vendored_upstream_archive_pin(self):
        archive = CHART / "charts/hindsight-1.1.0.tgz"
        self.assertEqual(
            hashlib.sha256(archive.read_bytes()).hexdigest(),
            "5199851d7c998c14517d43d70d15f5c87756388acc8128621fd3504c77c275bd",
        )
        dependency = yaml.safe_load((CHART / "Chart.yaml").read_text())["dependencies"][
            0
        ]
        self.assertEqual(dependency["repository"], "oci://ghcr.io/vectorize-io/charts")
        self.assertEqual(str(dependency["version"]), "1.1.0")
        locked = yaml.safe_load((CHART / "Chart.lock").read_text())["dependencies"][0]
        self.assertEqual(locked["repository"], dependency["repository"])
        self.assertEqual(str(locked["version"]), str(dependency["version"]))


class SyntheticFixtureTests(unittest.TestCase):
    """All paths and auth records are created here, never discovered on the host."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="hindsight-offline-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.seed = self.root / "synthetic-seed"
        self.home = self.root / "synthetic-runtime-home"
        self.record = {
            "client_id": "synthetic-test-client-not-a-real-id",
            "refresh_token": "SYNTHETIC-TEST-ONLY-NOT-A-REAL-REFRESH-TOKEN",
            "scopes": ["chatgpt.tokens.use.direct"],
            "ext_agent_host_id": "synthetic-test-host-not-a-real-host",
        }
        self.fixtures = {
            "onnx/model.onnx": b"SYNTHETIC OFFLINE FIXTURE, NOT MODEL WEIGHTS",
            "tokenizer.json": b'{"synthetic_offline_fixture": true}',
        }
        self.manifest = {
            name: hashlib.sha256(data).hexdigest()
            for name, data in self.fixtures.items()
        }
        self.model = self.root / "synthetic-model"

    def write_auth(self, directory, record=None):
        directory.mkdir(mode=0o700)
        directory.chmod(0o700)
        (directory / "credentials.json").write_text(
            json.dumps(self.record if record is None else record)
        )
        (directory / "host_id").write_text(self.record["ext_agent_host_id"] + "\n")
        for name in ("credentials.json", "host_id"):
            (directory / name).chmod(0o600)

    def auth_bytes(self, directory):
        return {
            name: (directory / name).read_bytes()
            for name in ("credentials.json", "host_id")
        }

    def populate_model(self):
        for name, data in self.fixtures.items():
            path = self.model / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)


class SeedAuthTests(SyntheticFixtureTests):
    def setUp(self):
        super().setUp()
        self.module = load_script("seed_auth.py")

    def test_first_seed_is_private_and_second_seed_cannot_overwrite_rotation(self):
        self.write_auth(self.seed)
        self.assertIs(self.module.ensure_auth(self.home, self.seed), True)
        self.assertEqual(self.auth_bytes(self.home), self.auth_bytes(self.seed))
        self.assertEqual(self.home.stat().st_mode & 0o777, 0o700)
        for name in self.module.FILES:
            self.assertEqual((self.home / name).stat().st_mode & 0o777, 0o600)
        rotated = {
            **self.record,
            "refresh_token": "SYNTHETIC-ROTATED-TEST-ONLY-NOT-A-TOKEN",
        }
        (self.home / "credentials.json").write_text(json.dumps(rotated))
        before = self.auth_bytes(self.home)
        # An optional, removed seed must not even be read for initialized homes.
        self.assertIs(
            self.module.ensure_auth(self.home, self.root / "missing-synthetic-seed"),
            False,
        )
        self.assertEqual(self.auth_bytes(self.home), before)
        self.assertIs(self.module.ensure_auth(self.home, self.seed), False)
        self.assertEqual(self.auth_bytes(self.home), before)

    def test_fresh_home_without_seed_fails_closed(self):
        with self.assertRaises(OSError):
            self.module.ensure_auth(self.home, self.seed)
        self.assertFalse(self.home.exists())

    def test_invalid_seed_content_never_initializes_runtime_home(self):
        self.write_auth(self.seed)
        bad_records = [
            {**self.record, "scopes": []},
            {**self.record, "scopes": "chatgpt.tokens.use.direct"},
            {**self.record, "ext_agent_host_id": "synthetic-other-host"},
            {**self.record, "refresh_token": ""},
            {**self.record, "client_id": None},
            [],
        ]
        for record in bad_records:
            with self.subTest(record=record):
                (self.seed / "credentials.json").write_text(json.dumps(record))
                with self.assertRaises(ValueError):
                    self.module.ensure_auth(self.home, self.seed)
                self.assertFalse(self.home.exists())
        (self.seed / "credentials.json").write_text(json.dumps(self.record))
        (self.seed / "host_id").write_text("\n")
        with self.assertRaises(ValueError):
            self.module.ensure_auth(self.home, self.seed)
        self.assertFalse(self.home.exists())

    def test_initialized_invalid_home_is_refused_not_repaired_from_seed(self):
        self.write_auth(self.seed)
        self.write_auth(self.home, {**self.record, "scopes": []})
        before = self.auth_bytes(self.home)
        with self.assertRaises(ValueError):
            self.module.ensure_auth(self.home, self.seed)
        self.assertEqual(self.auth_bytes(self.home), before)

    def test_bad_runtime_permissions_fail_closed_without_chmod(self):
        self.write_auth(self.seed)
        self.write_auth(self.home)
        for path, bad_mode, restored in (
            (self.home, 0o750, 0o700),
            (self.home / "credentials.json", 0o640, 0o600),
            (self.home / "host_id", 0o644, 0o600),
        ):
            with self.subTest(path=path.name):
                path.chmod(bad_mode)
                with self.assertRaises(ValueError):
                    self.module.ensure_auth(self.home, self.seed)
                self.assertEqual(path.stat().st_mode & 0o777, bad_mode)
                path.chmod(restored)

    def test_runtime_symlinks_and_wrong_owner_are_rejected(self):
        self.write_auth(self.seed)
        self.home.symlink_to(self.seed, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.module.ensure_auth(self.home, self.seed)
        self.home.unlink()
        self.write_auth(self.home)
        record_path = self.home / "credentials.json"
        record_path.unlink()
        record_path.symlink_to(self.seed / "credentials.json")
        with self.assertRaises(ValueError):
            self.module.ensure_auth(self.home, self.seed)
        record_path.unlink()
        record_path.write_bytes((self.seed / "credentials.json").read_bytes())
        record_path.chmod(0o600)
        runtime_uid = os.getuid()
        with (
            patch.object(self.module.os, "getuid", return_value=runtime_uid + 1),
            self.assertRaises(ValueError),
        ):
            self.module.ensure_auth(self.home, self.seed)

    def test_concurrently_initialized_home_is_never_replaced(self):
        self.write_auth(self.seed)
        real_rename = self.module.os.rename
        winner = {
            **self.record,
            "refresh_token": "SYNTHETIC-CONCURRENT-WINNER-NOT-A-TOKEN",
        }

        def race(source, destination):
            self.write_auth(self.home, winner)
            return real_rename(source, destination)

        with (
            patch.object(self.module.os, "rename", side_effect=race),
            self.assertRaises(OSError),
        ):
            self.module.ensure_auth(self.home, self.seed)
        self.assertEqual(
            json.loads((self.home / "credentials.json").read_text()), winner
        )
        self.assertFalse(list(self.root.glob(".hindsight-seed-*")))

    def test_seed_cli_checks_models_before_auth_and_never_prints_fixture_values(self):
        self.write_auth(self.seed)
        self.populate_model()
        script = self.root / "seed_auth.py"
        script.write_text((CHART / "files/seed_auth.py").read_text())
        (self.root / "model-files.json").write_text(json.dumps(self.manifest))
        env = {
            "AUTH_HOME": str(self.home),
            "SEED_DIR": str(self.seed),
            "MODEL_DIR": str(self.model),
            "PYTHONDONTWRITEBYTECODE": "1",
        }

        def run():
            return subprocess.run(
                [sys.executable, str(script)],
                env=env,
                cwd=self.root,
                capture_output=True,
                text=True,
                check=False,
                timeout=15,
            )

        result = run()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            {
                "bootstrap_ready": True,
                "seed_installed": True,
                "secret_values_disclosed": False,
            },
        )
        before = self.auth_bytes(self.home)
        result = run()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIs(json.loads(result.stdout)["seed_installed"], False)
        self.assertEqual(self.auth_bytes(self.home), before)
        (self.model / "tokenizer.json").write_bytes(b"synthetic corruption")
        result = run()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertEqual(
            result.stderr.strip(),
            "bootstrap_failed: auth or public-model validation refused",
        )
        self.assertNotIn(self.record["refresh_token"], result.stdout + result.stderr)
        self.assertEqual(self.auth_bytes(self.home), before)

    def test_runtime_model_check_rejects_corruption_empty_manifest_and_escape(self):
        self.populate_model()
        manifest = self.root / "synthetic-manifest.json"
        manifest.write_text(json.dumps(self.manifest))
        self.module.require_model(self.model, manifest)
        (self.model / "tokenizer.json").write_bytes(b"synthetic corruption")
        with self.assertRaises(ValueError):
            self.module.require_model(self.model, manifest)
        for bad in ({}, {"../outside": "d" * 64}, {"/absolute": "d" * 64}):
            with self.subTest(manifest=bad):
                manifest.write_text(json.dumps(bad))
                with self.assertRaises(ValueError):
                    self.module.require_model(self.model, manifest)
        outside = self.root / "outside-synthetic-file"
        outside.write_bytes(self.fixtures["tokenizer.json"])
        (self.model / "tokenizer.json").unlink()
        (self.model / "tokenizer.json").symlink_to(outside)
        manifest.write_text(json.dumps(self.manifest))
        with self.assertRaises(ValueError):
            self.module.require_model(self.model, manifest)


class PrepareModelTests(SyntheticFixtureTests):
    def setUp(self):
        super().setUp()
        self.module = load_script("prepare_model.py")
        # Any unplanned download is a failure; Hugging Face is never imported.
        guard = patch.object(
            self.module,
            "download_file",
            side_effect=AssertionError("unexpected network"),
        )
        self.download = guard.start()
        self.addCleanup(guard.stop)
        self.environment = patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def prepare(self, manifest=None):
        return self.module.prepare_model(
            REPO, REVISION, self.manifest if manifest is None else manifest, self.model
        )

    def synthetic_download(self, **kwargs):
        destination = Path(kwargs["local_dir"]) / kwargs["filename"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(self.fixtures[kwargs["filename"]])
        return str(destination)

    def test_download_verifies_pins_explicitly_disables_tokens_and_publishes_marker(
        self,
    ):
        self.download.side_effect = self.synthetic_download
        self.assertEqual(self.prepare(), "downloaded")
        self.assertEqual(self.download.call_count, len(self.fixtures))
        for call in self.download.call_args_list:
            self.assertEqual(call.kwargs["repo_id"], REPO)
            self.assertEqual(call.kwargs["revision"], REVISION)
            self.assertIs(call.kwargs["token"], False)
        self.assertEqual(os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"], "1")
        marker = json.loads((self.model / self.module.COMPLETE_FILE).read_text())
        self.assertEqual(
            marker, {"repo": REPO, "revision": REVISION, "filesSha256": self.manifest}
        )

    def test_verified_completed_model_is_reused_without_download(self):
        self.populate_model()
        self.assertEqual(self.prepare(), "downloaded")
        self.assertEqual(self.prepare(), "verified-existing")
        self.download.assert_not_called()

    def test_completed_model_corruption_or_manifest_change_never_triggers_refresh(self):
        self.populate_model()
        self.prepare()
        marker = self.model / self.module.COMPLETE_FILE
        before = marker.read_bytes()
        for manifest in ({**self.manifest, "tokenizer.json": "d" * 64}, self.manifest):
            with self.subTest(manifest=manifest):
                (self.model / "tokenizer.json").write_bytes(b"synthetic corruption")
                with self.assertRaises(ValueError):
                    self.prepare(manifest)
                self.assertEqual(marker.read_bytes(), before)
        self.download.assert_not_called()

    def test_corrupt_download_never_publishes_completion(self):
        self.download.side_effect = lambda **kwargs: self.synthetic_download(**kwargs)
        self.fixtures["onnx/model.onnx"] = b"synthetic corrupt download"
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertFalse((self.model / self.module.COMPLETE_FILE).exists())

    def test_wrong_repository_or_revision_is_rejected_before_writes(self):
        for repo, revision in (("synthetic-other/model", REVISION), (REPO, "main")):
            with self.subTest(repo=repo, revision=revision):
                with self.assertRaises(ValueError):
                    self.module.prepare_model(repo, revision, self.manifest, self.model)
                self.assertFalse(self.model.exists())
        self.download.assert_not_called()

    def test_invalid_manifest_paths_digests_and_empty_maps_are_rejected_before_writes(
        self,
    ):
        bad_manifests = [
            {},
            [],
            {"onnx/model.onnx": "d" * 64},
            {**self.manifest, "bad-digest": "not-a-sha256"},
        ]
        for path in (
            "../escape",
            "/absolute",
            "onnx/../escape",
            "onnx//model.onnx",
            ".cache/metadata",
            "remote.py",
            "windows\\path",
            "newline\npath",
        ):
            bad_manifests.append({**self.manifest, path: "d" * 64})
        for manifest in bad_manifests:
            with self.subTest(manifest=manifest):
                with self.assertRaises(ValueError):
                    self.prepare(manifest)
                self.assertFalse(self.model.exists())
        self.download.assert_not_called()

    def test_symlink_download_destination_cannot_escape_model_volume(self):
        self.model.mkdir()
        outside = self.root / "synthetic-outside-model"
        outside.mkdir()
        (self.model / "onnx").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertEqual(list(outside.iterdir()), [])
        self.download.assert_not_called()

    def test_concurrent_model_writer_is_refused_without_retry(self):
        import fcntl

        self.model.mkdir()
        with (self.model / ".hindsight-bootstrap.lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(ValueError):
                self.prepare()
        self.download.assert_not_called()

    def test_duplicate_manifest_paths_are_rejected(self):
        manifest = self.root / "synthetic-duplicate-manifest.json"
        manifest.write_text('{"tokenizer.json": "first", "tokenizer.json": "second"}')
        with self.assertRaises(ValueError):
            self.module.load_manifest(manifest)


class WorkflowTests(unittest.TestCase):
    def test_ci_is_path_scoped_readonly_and_runs_offline_unittest_with_uv(self):
        # BaseLoader preserves GitHub's YAML 1.2 `on` key as a string.
        workflow = yaml.load(
            (ROOT / ".github/workflows/hindsight-lint.yml").read_text(),
            Loader=yaml.BaseLoader,
        )
        self.assertEqual(workflow["permissions"], {"contents": "read"})
        expected = {
            "charts/hindsight/**",
            "tests/test_hindsight_chart.py",
            "tests/test_hindsight_image.py",
            "images/hindsight-security/**",
            ".github/workflows/hindsight-lint.yml",
        }
        for trigger in ("pull_request", "push"):
            self.assertEqual(set(workflow["on"][trigger]["paths"]), expected)
        self.assertEqual(workflow["on"]["push"]["branches"], ["main"])
        steps = workflow["jobs"]["validate"]["steps"]
        commands = "\n".join(s.get("run", "") for s in steps)
        self.assertIn("helm lint charts/hindsight", commands)
        self.assertIn("helm template hindsight charts/hindsight", commands)
        self.assertIn(
            "uv run --no-project --python 3.12 --with pyyaml python -m unittest discover",
            commands,
        )
        self.assertIn("-p test_hindsight_chart.py", commands)
        self.assertIn("-p test_hindsight_image.py", commands)
        self.assertNotIn("helm dependency", commands)
        self.assertNotIn("kubectl", commands)
        self.assertFalse(any("secrets." in str(step) for step in steps))


if __name__ == "__main__":
    unittest.main()
