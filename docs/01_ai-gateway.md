---
title: Official LiteLLM gateway operations
updated: 2026-10-25T21:01:25+09:00
type: runbook
status: current
---

# 공식 LiteLLM gateway

## 운영 범위

이 구성은 공식 LiteLLM 이미지와 공식 chart source를 사용합니다. 자체 API 서버, Mem0 내부 provider 교체, dependency override나 파생 runtime 이미지는 포함하지 않습니다. 기존 중지된 LiteLLM PoC도 수정하지 않습니다.

- Application/chart: `ai-gateway` / `charts/ai-gateway`.
- namespace: `ai-system`, context: `kkamji-lab`, project: `automation`.
- image: `litellm/litellm:v1.106.4@sha256:c169fb3adc514fcf210377c203f3de406d54f10bfdacf13948a4a839db9af7de`.
- chart: upstream `litellm-helm` 1.1.3, alias `proxy`. [provenance](../charts/ai-gateway/vendor-provenance.json)를 따릅니다. source archive는 원본 runtime 파일과 동일하며 Chart.yaml만 Helm metadata 재직렬화를 거쳤습니다. PostgreSQL/Redis 의존성은 bundled 상태지만 비활성입니다.
- model alias: `primary`. 실제 provider/model은 [local values](../charts/ai-gateway/kkamji_local_values.yaml)에 명시합니다. 자동 model/provider fallback과 자동 retry는 없습니다.
- 데이터베이스, 별도 UI backend, 기존 Hermes 설정 변경, 실 대화 ingestion은 범위 밖입니다. [Mem0 도입 상태](02_memory-api-status.md)를 별도로 따릅니다.

## 주소

| 역할 | 주소 | 현재 노출 정책 |
|---|---|---|
| LLM API의 기준 hostname | `https://ai.kkamji.net/v1` | 역할 기반 예약. HTTPRoute/DNS를 자동 생성하지 않음 |
| 후속 memory API | `https://memory.kkamji.net` | Mem0 도입 보류. 서비스나 route 없음 |
| 클러스터 내부 API | `http://ai-gateway.ai-system.svc.cluster.local:4000/v1` | 같은 namespace의 승인된 client label만 허용 |
| 로컬 검증 | `http://127.0.0.1:14000/v1` | loopback port-forward와 새 master key 필요 |

서로 다른 hostname을 써서 SDK path rewriting을 피합니다. `/litellm`이나 `/mem0` 하위 경로로 합치지 않습니다. 외부 노출은 별도 승인한 인증/권한 경계를 검증한 후 추가합니다. 이 chart에는 Ingress/HTTPRoute가 없으며 공개 gateway를 기존처럼 활용한다고 가정하지 않습니다.

## 보안 상태와 제한

이 이미지를 취약점 무검출 이미지로 표시하지 않습니다. 같은 digest의 검사 결과는 Critical 0, High 1, Medium 8, Low 2입니다. 원본 이미지 그대로 운영하므로 해당 dependency를 자체 강제 교체하지 않습니다.

- High `CVE-2026-112940` / `GHSA-v4x8-3wr5-3wq8`는 `filelock==3.32.7`의 ReadWriteLock 조건입니다. LiteLLM Python source에서 해당 class 참조는 발견되지 않았습니다. 일반 FileLock과 구분합니다. 이는 package가 patched라는 뜻이 아닙니다.
- 같은 Pod에서 untrusted code/다중 사용자를 실행하지 않습니다. 1 replica, 1 worker, Recreate, 읽기 전용 root, 비특권 UID 10001, capability 전부 제거, RuntimeDefault seccomp를 사용합니다. hostPath/hostNetwork/SA token/RBAC가 없습니다.
- TMPDIR는 init container가 만든 UID-10001/mode-0700 전용 경로입니다. OAuth도 UID-10001/mode-0700 디렉터리와 mode-0600 파일을 요구합니다. 다른 사용자와 writable lock 경로를 공유하지 않습니다.
- Medium 중 `/opt/liteadmin`의 PyJWT/OpenTelemetry는 별도 interpreter에 있습니다. 실제 proxy interpreter는 PyJWT 2.15.0, OpenTelemetry API 1.45.1이며 그 경로를 sys.path에 포함하지 않는 것을 확인했습니다.
- 나머지 Python/ALSA 조건은 임의 로컬 파일, POP3나 audio 기능과 관련됩니다. 이 구성은 해당 기능을 설정하지 않습니다. raw finding을 삭제하거나 영구 ignore하지 않습니다.
- 이 제한적 내부 검증 구성을 인터넷용 multi-tenant 서비스의 보안 승인으로 확장하지 않습니다. untrusted 실행, audio/file ingestion, 별도 admin backend나 외부 노출을 추가하면 다시 평가합니다.
- 공식 release의 rotated cosign key로 이 digest의 signature와 transparency-log bundle을 검증했습니다. [release](https://github.com/BerriAI/litellm/releases/tag/v1.106.4)와 [사고 보고](https://docs.litellm.ai/blog/security-incident-oct-21-2026)를 확인합니다. 임의 latest tag나 compromised 1.107.0을 사용하지 않습니다.

기본 NetworkPolicy는 namespace 내 labeled client -> port 4000, CoreDNS, RFC1918/loopback/link-local을 제외한 IPv4 HTTPS egress를 허용합니다. HTTPS egress는 hostname allowlist가 아닙니다. CNI enforcement를 별도로 검증합니다. bearer master key 보유자는 gateway 전체 권한을 갖습니다. 불특정 사용자와 공유하지 않습니다.

DNS/provider egress는 proxy component label에만 적용합니다. seed Pod는 default-deny에만 해당하므로 외부 egress를 허용하지 않습니다. 실제 CNI 동작 확인과 label/RBAC 경계는 별도입니다.

## 상태와 비밀

- chart는 `ai-gateway-keys`의 `PROXY_MASTER_KEY`만 참조하며 값을 생성하거나 Git에 저장하지 않습니다. 새 전용 키를 사용합니다.
- 이 호스트에는 AWS `personal` profile이 없어 다른 계정으로 우회하지 않습니다. 이번 구축은 승인된 신규 Kubernetes Secret을 사용합니다. SSM/ESO 이전은 AWS 신원/권한을 확인한 별도 작업입니다.
- OAuth는 기존 Hermes/Codex 파일을 읽거나 복사하지 않고 새 전용 디렉터리에서 진행합니다. 패스키/MFA는 사용자가 직접 승인합니다. OAuth timeout이나 timestamp-only 파일을 로그인 성공으로 취급하지 않습니다.
- 운영 중 refresh authority는 `ai-gateway-auth` 1Gi PVC의 `tokens/auth.json`입니다. 단일 writer만 허용합니다. directory 0700/file 0600과 access/refresh token 필드를 seed 단계에서 검증합니다. 값은 출력하지 않습니다.
- seed/proxy 모두 `fsGroupChangePolicy: OnRootMismatch`를 사용합니다. volume root의 GID/권한이 이미 맞으면 재귀 변경을 건너뛰어 private 파일의 권한을 보존합니다. init gate는 소유자/권한을 매번 검증합니다. seed는 기존 `auth.json`이 있으면 중단하며, 재로그인이라는 이유로 현재 refresh authority를 덮어쓰지 않습니다.
- 공식 proxy는 로그인 파일이 없어도 readiness 200을 반환하면서 등록 모델은 0개일 수 있습니다. 실제 no-network 검사에서 이를 확인했습니다. init gate와 로그인 후 `primary` 모델 등록/합성 호출을 모두 확인하기 전에는 서비스가 작동한다고 표시하지 않습니다.
- `local-path`는 node-local/Delete/WaitForFirstConsumer이고 PVC 용량이 filesystem quota라는 보장은 없습니다. 노드 유실 대비 제한된 암호화 백업/재로그인 절차가 필요합니다. `helm.sh/resource-policy: keep`만 믿고 Argo prune/namespace/PVC 삭제를 하지 않습니다.

## 검증과 반영 순서

```bash
helm lint charts/ai-gateway -n ai-system -f charts/ai-gateway/kkamji_local_values.yaml
helm template ai-gateway charts/ai-gateway -n ai-system --skip-tests \
  --kube-version 1.36.1 -f charts/ai-gateway/kkamji_local_values.yaml > "$PRIVATE_DIR/rendered.yaml"
uv run --no-project --python 3.12 --with pytest --with pyyaml pytest -q tests/test_ai_gateway_chart.py
python3 docs/_meta/docs_lint.py --root . --base origin/main
```

Helm은 Argo renderer와 같은 4.2.1을 사용합니다. vendored archive로 lint/render하고 검증만을 위해 dependency를 갱신하지 않습니다. lock 재생성은 scratch에 chart를 풀고, 분리된 HELM_REPOSITORY_CONFIG/CACHE와 `--skip-refresh`를 사용합니다. 사용자 전역 repo cache를 갱신하지 않습니다.

1. source/범위/Secret scan/최종 commit CI를 검증하고 승인된 main 반영을 확인합니다. 기존 automation root에는 이 app을 추가하지 않습니다.
2. context와 namespace 충돌, CPU/RAM/node disk, CRD/admission을 재확인합니다. 새 namespace/Secret/Application만 대상으로 diff/dry-run하고 영향과 rollback을 보고합니다.
3. 새 전용 master key를 private mode-0600 파일에서 생성/주입합니다. `--from-literal`이나 raw Secret dump로 값을 콘솔에 노출하지 않습니다. 기존 monitoring/registry/provider credential을 재사용하지 않습니다.
4. [manual Application](../examples/ai-gateway/application.yaml)을 등록하고 정확한 main revision을 수동 sync합니다. 자동 sync는 설정하지 않습니다. 인증 파일이 없으면 init gate에서 멈추는 것이 정상입니다. 이를 서비스 준비 완료로 표시하지 않습니다.
5. 새 OAuth 로그인을 완료한 후 proxy를 0으로 정지하고 old Pod 삭제를 기다립니다. 새 artifact만 임시 seed Secret으로 주입합니다. [seed Pod](../examples/ai-gateway/auth-seed-pod.yaml)를 실행하고 성공/삭제를 확인한 뒤 임시 Secret을 삭제합니다. source의 replicas=1을 수동 sync로 복원합니다.
6. readiness와 실제 image ID를 확인합니다. readiness는 실제 model call이 아닙니다. 루프백으로 port-forward하고 잘못된/없는 bearer 거절, 합성 inference, 없는 model 거절을 검사합니다. 모델/계정/쿼터/권한 실패가 있으면 보고하고 fallback으로 우회하지 않습니다.
7. 승인된 proxy 재시작 후 같은 PVC와 private auth를 유지하고 합성 inference를 재검증합니다. 실제 사용자 대화나 Hermes session을 가져오지 않습니다. rollout/모델 호출을 실제 확인하지 않으면 미완료로 보고합니다.

```bash
kubectl config current-context
kubectl port-forward service/ai-gateway --context kkamji-lab -n ai-system \
  --address=127.0.0.1 14000:4000
```

Rollback은 reviewed Git revision과 manual sync로 수행합니다. 실패했다고 auth PVC/namespace를 지우거나 기존 token을 덮어쓰지 않습니다. 먼저 caller를 멈추고 마지막 정상 image/config와 refresh authority를 확인합니다.
