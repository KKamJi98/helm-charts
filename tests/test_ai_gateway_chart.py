"""Offline contracts for official-image-only gateway deployment."""

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "charts/ai-gateway"
HELM = os.environ.get("HELM", "helm")


def render(*extra):
    return subprocess.run(
        [
            HELM,
            "template",
            "ai-gateway",
            str(CHART),
            "-n",
            "ai-system",
            "--skip-tests",
            "--kube-version",
            "1.36.1",
            "-f",
            str(CHART / "kkamji_local_values.yaml"),
            *extra,
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def test_internal_official_image_contract():
    result = render()
    assert result.returncode == 0, result.stderr
    docs = [d for d in yaml.safe_load_all(result.stdout) if d]
    assert not {d["kind"] for d in docs} & {
        "Secret",
        "HTTPRoute",
        "Ingress",
        "Role",
        "ClusterRole",
        "Job",
        "StatefulSet",
    }
    assert len({(d["kind"], d["metadata"]["name"]) for d in docs}) == len(docs)
    deployments = [d for d in docs if d["kind"] == "Deployment"]
    assert len(deployments) == 1
    deployment = deployments[0]
    assert deployment["spec"]["replicas"] == 1
    assert deployment["spec"]["strategy"]["type"] == "Recreate"
    pod = deployment["spec"]["template"]["spec"]
    sa = next(d for d in docs if d["kind"] == "ServiceAccount")
    assert sa["automountServiceAccountToken"] is False
    assert pod["serviceAccountName"] == sa["metadata"]["name"] == "ai-gateway"
    assert pod["securityContext"]["runAsNonRoot"] is True
    assert pod["securityContext"]["fsGroupChangePolicy"] == "OnRootMismatch"
    assert pod["securityContext"]["seccompProfile"]["type"] == "RuntimeDefault"
    assert (
        deployment["spec"]["template"]["metadata"]["labels"]["ai.kkamji.net/component"]
        == "proxy"
    )
    expected = json.loads((CHART / "vendor-provenance.json").read_text())["runtime"][
        "image"
    ]
    for container in pod["containers"] + pod["initContainers"]:
        assert container["image"] == expected
        security = container["securityContext"]
        assert security["readOnlyRootFilesystem"] is True
        assert security["allowPrivilegeEscalation"] is False
        assert "ALL" in security["capabilities"]["drop"]
    env = {e["name"]: e for e in pod["containers"][0]["env"]}
    assert env["PROXY_MASTER_KEY"]["valueFrom"]["secretKeyRef"] == {
        "name": "ai-gateway-keys",
        "key": "PROXY_MASTER_KEY",
    }
    assert env["TMPDIR"]["value"] == "/tmp/litellm"
    assert env["CHATGPT_TOKEN_DIR"]["value"] == "/data/chatgpt/tokens"
    assert all(
        d["spec"].get("type", "ClusterIP") == "ClusterIP"
        for d in docs
        if d["kind"] == "Service"
    )
    assert len([d for d in docs if d["kind"] == "NetworkPolicy"]) == 4
    for policy in (
        d
        for d in docs
        if d["kind"] == "NetworkPolicy"
        and d["metadata"]["name"] != "ai-gateway-default-deny"
    ):
        assert (
            policy["spec"]["podSelector"]["matchLabels"]["ai.kkamji.net/component"]
            == "proxy"
        )
    assert len([d for d in docs if d["kind"] == "PersistentVolumeClaim"]) == 1


@pytest.mark.parametrize(
    "override",
    [
        "proxy.replicaCount=2",
        "proxy.numWorkers=2",
        "proxy.strategy.type=RollingUpdate",
        "proxy.autoscaling.enabled=true",
        "proxy.keda.enabled=true",
        "proxy.db.deployStandalone=true",
        "proxy.db.useExisting=true",
        "proxy.redis.enabled=true",
        "proxy.ingress.enabled=true",
        "proxy.service.type=LoadBalancer",
        "proxy.securityContext.readOnlyRootFilesystem=false",
        "proxy.podSecurityContext.fsGroupChangePolicy=Always",
        "proxy.image.tag=latest",
        "proxy.proxy_config.general_settings.allow_client_side_credentials=true",
        "proxy.proxy_config.router_settings.fallbacks[0]=openai/test",
        "proxy.proxy_config.model_list[0].litellm_params.model=openai/test",
    ],
)
def test_unsafe_override_rejected(override):
    result = render("--set", override)
    assert result.returncode != 0
    assert "Error:" in result.stderr


def test_seed_and_application_do_not_activate_unsafe_defaults():
    app = yaml.safe_load((ROOT / "examples/ai-gateway/application.yaml").read_text())
    assert "automated" not in app["spec"]["syncPolicy"]
    assert app["spec"]["source"]["targetRevision"] == "main"
    assert app["spec"]["destination"]["namespace"] == "ai-system"
    seed = yaml.safe_load((ROOT / "examples/ai-gateway/auth-seed-pod.yaml").read_text())
    assert seed["spec"]["automountServiceAccountToken"] is False
    assert seed["spec"]["securityContext"]["fsGroupChangePolicy"] == "OnRootMismatch"
    script = seed["spec"]["containers"][0]["args"][0]
    assert "'refresh_token'" in script and "json.loads(payload)" in script
    assert "0o700" in script and "0o600" in script
    assert "Existing refresh authority must not be overwritten" in script


def test_upstream_vendor_bytes_are_pinned():
    pin = json.loads((CHART / "vendor-provenance.json").read_text())["chart"]
    archive = CHART / "charts" / f"litellm-helm-{pin['version']}.tgz"
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == pin["archive_sha256"]
