# kcd-2025 Demo 저장용 Nginx Helm Chart

이 저장소는 Cloud Native Korea Community Day 2025(KCD 2025) 데모를 위한
Nginx Helm 차트입니다. ConfigMap 기반 HTML 템플릿과 환경변수를 사용해
`[kcd-west]` 또는 `[kcd-east]` 형식의 배너 문구를 렌더링합니다.

## 주요 특징

- 이미지: `nginx:stable-alpine3.21-perl`
- 출력: 중앙 정렬, 깔끔한 단일 페이지
- 자원: Deployment, Service, ConfigMap
- 보안: `readOnlyRootFilesystem: true` 유지, 필요한 경로만 쓰기 가능
- 안정화: `/etc/nginx/conf.d`를 `emptyDir`로 마운트하고 initContainer로
  `default.conf`를 주입하여 엔트리포인트 수정 경고를 방지

## 사전 요구 사항

- Kubernetes 1.30+
- Helm 3.16+

## 설치/업그레이드

- 릴리스 이름: `kcd-2025-mookup`

서쪽(west) 값으로 설치:

```bash
helm upgrade --install kcd-2025-mookup . \
  -n kcd --create-namespace \
  -f kcd_west_values.yaml \
  --set fullnameOverride=kcd-2025-mookup
```

동쪽(east) 값으로 설치:

```bash
helm upgrade --install kcd-2025-mookup . \
  -n kcd --create-namespace \
  -f kcd_east_values.yaml \
  --set fullnameOverride=kcd-2025-mookup
```

배포 후 서비스 확인:

```bash
kubectl -n kcd get deploy,po,svc -l app.kubernetes.io/name=kcd-2025-nginx
```

포트포워딩(네임스페이스 표기):

```bash
kubectl -n kcd port-forward svc/kcd-2025-mookup 8080:80
```

## 값 파일 예시

두 파일 모두 저장소 루트에 포함되어 있습니다.

- `kcd_west_values.yaml`:

```yaml
prefix: kcd
region: west
```

- `kcd_east_values.yaml`:

```yaml
prefix: kcd
region: east
```

기본 `values.yaml`의 핵심 값:

```yaml
prefix: kcd
region: west
```

## 설계 메모(보안/안정성)

- 루트 파일시스템은 읽기 전용으로 유지합니다.
- 다음 경로는 `emptyDir`로 쓰기 가능하게 마운트합니다:
  - `/etc/nginx/conf.d`(nginx confd)
  - `/var/cache/nginx`(캐시)
  - `/var/run`(런타임 소켓)
  - `/tmp`(임시 파일)
- initContainer가 ConfigMap의 `default.conf`를 confd 디렉터리에 복사합니다.
  - 엔트리포인트의 IPv6 보정 스크립트가 실패하지 않고 동작합니다.
- HTML은 `/etc/nginx/templates`에 템플릿으로 제공되며, 컨테이너 시작 시
  envsubst가 `/usr/share/nginx/html`로 렌더링합니다.

## 동작 방식 요약

- 템플릿 경로: `/etc/nginx/templates`
- 출력 경로: `/usr/share/nginx/html`
- 템플릿 확장자: `.template`
- 환경변수: `PREFIX`, `REGION`(values로 주입)
- 리스닝 포트: 컨테이너 8080, Service는 80 → 8080(TargetPort) 전달
- Nginx confd 구성:
  - `nginx-confd-configmap.yaml`의 `default.conf`를 initContainer가
    `/etc/nginx/conf.d`로 복사합니다.
  - ConfigMap 볼륨은 내부적으로 심볼릭 링크를 사용하므로, 복사 시 링크를
    해제해 실제 파일로 만들기 위해 `cp -rLv`를 사용합니다.

## 볼륨/마운트 구성

- `/etc/nginx/templates`: ConfigMap(`*-html`) 직접 마운트(읽기 전용)
- `/usr/share/nginx/html`: `emptyDir` — envsubst 결과물이 기록됨
- `/etc/nginx/conf.d`: `emptyDir` — initContainer가 `default.conf`를 채움
- `/var/cache/nginx`, `/var/run`, `/tmp`: `emptyDir`

## 문제 해결(nginx 기동 실패)

증상 로그 예시:

```text
open() "/etc/nginx/conf.d/default.conf" failed (2: No such file or directory)
```

점검 순서:

1) initContainer가 conf 복사를 수행했는지 확인

```bash
kubectl -n kcd logs <pod> -c init-nginx-confd
```

2) confd 경로에 파일 존재 여부 확인(기동 중인 경우)

```bash
kubectl -n kcd exec -it <pod> -c nginx -- ls -al /etc/nginx/conf.d
```

3) 차트 템플릿 확인 포인트

- `Deployment` init 스크립트가 `cp -rLv /confd-src/* /confd/` 인지 확인
- `/etc/nginx/conf.d`가 `emptyDir`로 마운트되어 있는지 확인
- `nginx-confd-configmap.yaml`에 `default.conf`가 존재하는지 확인

4) ConfigMap 변경 자동 반영(선택)

- Pod 템플릿에 체크섬 주입을 통해 conf 변경 시 자동 롤아웃을 유도할 수
  있습니다.

예시(주석):

```yaml
metadata:
  annotations:
    checksum/confd: {{ include (print $.Template.BasePath "/nginx-confd-configmap.yaml") . | sha256sum }}
```

## 제거

```bash
helm uninstall kcd-2025-declarative -n kcd
```

## 참고

- 자세한 작업 흐름과 운영 메모는 `kcd_2025/AGENTS.md`를 참고하세요.
