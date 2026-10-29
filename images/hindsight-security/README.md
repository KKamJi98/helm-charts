---
title: Hindsight 1.1.0 Python security image
updated: 2026-10-29T20:13:22+09:00
type: runbook
status: candidate
---

# Hindsight 1.1.0 최소 보안 파생 이미지

공식 AIO 1.1.0을 유지하고 다음 Python 배포판만 변경합니다. 공식 새 release가 아닌 자체 보안 파생 이미지입니다. Dockerfile의 upstream OCI label은 원본에서 상속한 값이며 공식 배포를 뜻하지 않습니다. 아래 전용 public key 서명과 digest로 게시물을 별도 검증합니다.

| 배포판 | 원본 | 후보 |
|---|---|---|
| authlib | 1.6.12 | 1.9.1 |
| dnspython | 2.8.0 | 2.9.0 |
| joserfc | 없음 | 1.6.8 |

Authlib 1.9.1이 요구하는 joserfc의 최소 버전을 추가합니다. cryptography 50.0.0은 이미 두 라이브러리의 `>=45.0.1` 조건을 충족하므로 변경하지 않습니다. fastmcp 3.2.0, pg0-embedded 0.15.2, onnxruntime 1.31.0, Python 3.11.17 및 Hindsight source/schema/model/provider 설정은 유지합니다.

## 고정 입력과 빌드

- 원본 AIO와 빌드 도구 uv 0.13.6은 Dockerfile에서 정확한 GHCR digest로 고정합니다.
- requirements.txt의 SHA256은 각 버전의 PyPI wheel metadata와 대조했습니다. uv는 `--require-hashes --no-deps --only-binary :all:`로 이 세 wheel만 설치합니다. pip로 설치하지 않습니다.
- 설치 뒤 동일한 `/app/api/.venv/bin/python` 환경에 `uv pip check`를 실행합니다. dependency 해석이나 다른 배포판의 묵시적 갱신을 허용하지 않습니다.
- uv binary와 requirements는 BuildKit 읽기 전용 mount이고 `--no-cache`를 사용합니다. 설치 도구, 내려받은 wheel, requirements 파일을 최종 이미지로 COPY하지 않습니다. 빌드 context도 Dockerfile과 requirements.txt로 제한합니다.
- 공개 registry/PyPI 다운로드만 수행합니다. 모델, credential, PVC, auth home은 빌드 입력이 아닙니다.
- 재현 가능한 입력 pin을 제공하지만 timestamp를 포함한 OCI 출력의 bit-for-bit 재현성까지 주장하지 않습니다.

저장소 루트에서 실행합니다. 로컬 amd64만 검증했으며 push나 배포는 수행하지 않습니다.

```sh
docker build --platform linux/amd64 --progress plain \
  -t hindsight-security:1.1.0-20261029 images/hindsight-security

HINDSIGHT_TEST_IMAGE=hindsight-security:1.1.0-20261029 \
HINDSIGHT_TEST_EVIDENCE="$TMPDIR/hindsight-remediation" \
  python3 -m unittest discover -s tests -p test_hindsight_image.py -v
```

`HINDSIGHT_TEST_IMAGE`가 없으면 recipe 검사만 실행하고 Docker 검사는 skip합니다. skip을 이미지 인수 성공으로 해석하지 않습니다. Docker 검사는 local image에 `--pull never`를 사용하므로 원본 digest도 먼저 존재해야 합니다.

## 검증 범위

- host 검사 4개와 컨테이너 내부 검사 6개를 통과했습니다.
- 원본과 후보의 설치 목록을 비교하여 정확히 위 세 항목만 바뀐 것을 확인했습니다. `uv pip check`는 211 packages에 대해 호환성 오류 없이 종료했습니다.
- `/app`의 `.venv`와 `__pycache__`를 제외한 2,597개 파일/링크 fingerprint, 전체 OCI Config, 원본 layer prefix를 비교했습니다. startup script, API/provider, migration, CP source는 같습니다. uid 1000, default command `/app/start-all.sh`를 유지합니다.
- 공식 advisory의 빈 JWS signatures, 빈 HMAC key(HS256/384/512), leading-byte PEM을 HMAC key로 오인하는 공격을 차단했습니다. 실제 무작위 key로 만든 정상 서명과 RS256 검증은 통과하고 잘못된 key는 거부합니다.
- 동일한 advisory 검사 4개를 수정 전 이미지에 먼저 실행했습니다. 정상 서명 control은 통과했고 취약 동작 13개 subcase가 예상대로 실패했습니다. 후보에서는 모두 통과했습니다.
- Hindsight API factory, ChatGPT provider/auth module, FastMCP, pg0, ONNX Runtime, transformers/tokenizers와 DNS module import를 확인했습니다. CPUExecutionProvider가 존재합니다.
- 네트워크가 없는 새 컨테이너에서 tmpfs home의 합성 pg0 DB 생성, SQL write/read, 정상 stop/start와 데이터 보존을 확인했습니다. real PVC나 host home을 mount하지 않았습니다. root filesystem은 read-only, capabilities는 모두 제거하고 no-new-privileges를 설정했습니다.
- 이 smoke는 실제 API startup/readiness, OAuth 갱신, E5 inference, retain/recall 또는 기존 PVC 인수가 아닙니다. app factory import와 pg0 실행을 full application 인수로 확대하지 않습니다.

## 취약점 재검사

같은 Grype 0.121.0 및 DB `v6.1.10`, built `2026-10-29T06:23:34Z`를 사용했습니다. DB/app 자동 갱신은 끄고 ignore rule을 추가하지 않았습니다.

```sh
TASK="$TMPDIR/hindsight-remediation"
GRYPE_DB_CACHE_DIR="$TASK/grype-db" \
GRYPE_DB_AUTO_UPDATE=false GRYPE_CHECK_FOR_APP_UPDATE=false \
  "$TASK/grype" docker:hindsight-security:1.1.0-20261029 -o json \
  > "$TASK/api-candidate-grype.json" 2> "$TASK/api-candidate-grype.log"
python3 images/hindsight-security/compare_scans.py \
  "$TASK/api-current-grype.json" "$TASK/api-candidate-grype.json" \
  > "$TASK/api-candidate-grype-summary.json"
```

비교기는 scanner/DB 일치, 원본의 네 advisory 존재, 후보에서의 제거, OS High finding 불변과 새 finding ID 부재를 검사합니다. 개별 package/version/CVE/fix state를 summary에 보존합니다.

| severity matches | 원본 | 후보 |
|---|---|---|
| Critical | 1 | 0 |
| High | 62 | 59 |
| Medium | 74 | 70 |
| Low | 19 | 18 |
| Negligible | 63 | 63 |

제거된 대상:

- [GHSA-6v38-4h7w-rj9h](https://github.com/advisories/GHSA-6v38-4h7w-rj9h): 빈 JWS signatures 검증 우회.
- [GHSA-8m4g-j4wp-wgcg](https://github.com/advisories/GHSA-8m4g-j4wp-wgcg): 빈 HMAC key 수용.
- [GHSA-7vr2-2fgp-9w7p](https://github.com/advisories/GHSA-7vr2-2fgp-9w7p): prefixed PEM/HMAC algorithm confusion.
- [GHSA-45c3-73f7-pv4m](https://github.com/advisories/GHSA-45c3-73f7-pv4m): DNS name decompression CPU DoS.

새 finding ID는 없습니다. **OS High 59건은 그대로이며 58 wont-fix, 1 not-fixed입니다. OS High를 해결한 이미지가 아닙니다.** Medium 이하 Python/OS findings도 남습니다. 이미지 scan은 pg0의 압축 binary bundle 또는 기존 PVC의 추출 cache까지 안전함을 입증하지 않습니다.

## 로컬 산출물과 남은 gate

- tag: `hindsight-security:1.1.0-20261029`
- `docker image inspect .Id`: `sha256:99f91e62f5e870d91a2e03bb3fce695541dff694dac6dcdb692319f462060074`
- linux/amd64 OCI manifest: `sha256:338a6bbe4989a6d1ce27fcac7e609ab9bb2c2239df82e13ca4701dcaf971495c`
- image config digest, Grype imageID: `sha256:9518c78ab46ba172ad0445239669ccda59f36cf6e4e737542a72d6d1408a6bdc`

위 첫 ID는 이 Docker image store가 반환한 index ID이고 config digest와 다릅니다. registry 게시 digest나 서명으로 대신 사용하지 않습니다.

상세 로그는 `/home/kkamji/.hermes/cache/scratch/hindsight-remediation/`에 있습니다. scratch는 자동 정리 대상이므로 장기 증적이 필요하면 부모 작업에서 승인된 보존 위치로 옮깁니다.

- `image-build.log`: 해시 고정 설치와 uv dependency 검사.
- `image-red.log`: 원본 advisory 회귀 실패.
- `image-tests.log`, `image-smoke-green.log`: 최종 성공 결과.
- `image-verification.json`: 실제 이미지 inspect, package/source inventory와 현재 recipe 파일 SHA256.
- `api-candidate-grype.json`, `api-candidate-grype.log`, `api-candidate-grype-summary.json`: 전체 scan과 비교.
- `image-smoke.log`: 최초 smoke의 잘못 지정한 module 이름과 key 없는 server-entrypoint import 실패 기록. 최종 smoke는 실제 존재하는 API factory/provider module을 검사합니다.

## 게시와 서명 검증

게시물은 `ghcr.io/kkamji98/hindsight-security:1.1.0-20261029@sha256:99f91e62f5e870d91a2e03bb3fce695541dff694dac6dcdb692319f462060074`입니다. registry readback과 익명 manifest 조회로 검사한 local index와 동일함을 확인했습니다. 공개 패키지에는 원본 공개 이미지와 hash 고정 wheel만 포함하며 개인 데이터나 credential을 넣지 않았습니다. 부동 tag나 패키지 UI의 Latest 표시는 배포 기준이 아닙니다.

Cosign 3.1.4의 전용 로컬 key로 서명했습니다. [signing.pub](signing.pub)는 공개 검증키이며 [signing-config.json](signing-config.json)은 외부 transparency/OIDC/TSA 서비스를 지정하지 않습니다. 이는 pinned-key 검증이지 upstream 공식 identity나 transparency-log 포함 증명이 아닙니다. 개인키와 비밀번호는 WSL의 전용 비추적 디렉터리에 각각 0600으로 보관하며 CI, Git, 이미지로 복사하지 않습니다.

```sh
cosign verify --key images/hindsight-security/signing.pub \
  --insecure-ignore-tlog \
  ghcr.io/kkamji98/hindsight-security@sha256:99f91e62f5e870d91a2e03bb3fce695541dff694dac6dcdb692319f462060074
```

이 옵션은 애초 업로드하지 않은 transparency log 검사만 제외합니다. TLS, 서명과 image digest 검사는 유지합니다. 공개 key를 임의 교체하거나 서명 확인 실패를 우회하지 않습니다. 본문 signature와 registry digest를 재조회해 성공을 확인했지만 서명이 OS High를 없애지는 않습니다.

운영 rollout은 별도 인수 단계입니다. 실제 auth/model/PVC 검증 전 배포 완료로 표시하지 않습니다. 현재 credential을 복사해서 병렬 OAuth canary를 시작하지 않습니다. 새 image를 쓰는 model Job은 공개 checksum 재검증만 하며, API StatefulSet은 이전 writer 종료 뒤 하나만 시작합니다. [운영 정본](../../docs/03_hindsight.md)을 따릅니다.
