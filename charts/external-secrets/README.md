# external-secrets-bundle

External Secrets Operator(ESO) + `ClusterSecretStore`(AWS SSM ParameterStore) wrapper chart.
SSM ParameterStore에 저장한 값을 클러스터 Secret으로 동기화한다.

## 구성 요소

- ESO operator (subchart `external-secrets`)
- `ClusterSecretStore` `parameter-store` (provider: AWS ParameterStore) - `templates/cluster-secret-store.yaml`

각 애플리케이션의 ExternalSecret은 해당 소비자 chart에서 관리한다
(예: external-dns -> `charts/external-dns`, argocd -> `charts/argocd`).

## 부트스트랩 (수동, 클러스터 재구축 시 1회)

`awssm-secret`은 `ClusterSecretStore`가 SSM에 인증하는 마스터 키다. 자기 자신을 SSM에서
가져올 수 없으므로(닭-달걀) 자동화가 불가능하며, ESO 배포 전에 수동으로 만들어야 한다.
(self-managed 클러스터라 IRSA/Pod Identity를 쓸 수 없다.)

```bash
kubectl create namespace external-secrets
kubectl create secret generic awssm-secret -n external-secrets \
  --from-literal=access-key='<id>' \
  --from-literal=secret-access-key='<key>'
```

`awssm-secret`의 IAM user에는 사용하는 SSM 파라미터 경로에 대한 `ssm:GetParameter`와,
SecureString 복호화용 `kms:Decrypt` 권한이 있어야 한다.

## 배포 순서

external-secrets는 sync-wave -2로 가장 먼저 배포되어 `ClusterSecretStore`를 준비한다.
이후 각 소비자 chart의 ExternalSecret이 SSM에서 값을 받아 Secret을 생성한다.

1. `awssm-secret` 수동 생성 (위 부트스트랩)
2. external-secrets 배포 -> ESO + ClusterSecretStore
3. 소비자 chart 배포 -> ExternalSecret이 Secret 생성

## 검증

```bash
kubectl get clustersecretstore parameter-store
kubectl get externalsecret -A
```
