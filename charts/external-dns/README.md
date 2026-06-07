# external-dns-bundle

upstream external-dns chart의 umbrella wrapper. external-dns 배포와 함께
Route53 자격증명 Secret(`external-dns-aws`)을 ExternalSecret으로 관리한다.

## 구성

- upstream `external-dns` 1.21.1 (subchart, values는 `external-dns:` 키 밑)
- `templates/external-secret.yaml`: SSM ParameterStore(SecureString JSON)에서
  `external-dns-aws` Secret을 release 네임스페이스에 생성

## SSM 파라미터 (수동, 1회)

ExternalSecret이 읽는 SecureString 파라미터를 미리 만든다 (값은 JSON):

```bash
aws ssm put-parameter --name "/kkamji/external-dns/aws-credentials" --type SecureString \
  --value '{"AWS_ACCESS_KEY_ID":"<id>","AWS_SECRET_ACCESS_KEY":"<key>"}' --region ap-northeast-2
```

JSON 키 이름은 deployment env(`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`)와 일치해야
`dataFrom.extract`가 Secret 키로 그대로 매핑한다.

전제: `external-secrets` chart의 `ClusterSecretStore`(parameter-store)와 `awssm-secret`
부트스트랩이 선행되어야 한다 (sync-wave -2). 자세한 절차는 `charts/external-secrets/README.md`.

## 검증

```bash
helm dependency build charts/external-dns
helm lint charts/external-dns
helm template external-dns charts/external-dns -f charts/external-dns/kkamji_local_values.yaml
```
