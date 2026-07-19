# ArgoCD Notifications 점검 & 개선

> Historical Slack-era record. Discord replaced the live Argo CD notification route on 2026-07-19. Current configuration and validation are in `charts/argocd/kkamji_local_values.yaml` and the Discord migration runbook.

**Date**: 2026-06-08
**Status**: values 적용 완료, 배포(push/sync) 대기
**Scope**: `charts/argocd/kkamji_local_values.yaml` 의 `notifications` 섹션 (-> `argocd-notifications-cm`)

## Context

"ArgoCD 알림이 Slack 으로 안 온다" 신고로 진단. 결과 파이프라인(controller / ESO 토큰 / trigger / template)은 정상이었고, 안 온 원인은 두 가지였다.

1. **dedup**: `on-deployed` 는 commit(revision) 당 1회만 전송. 새 배포가 없으면 안 오는 게 정상 동작.
2. **봇 이탈**: 2026-06-07 채널을 `monitor-argocd` -> `00_monitor-argocd` 로 rename 하고 public -> private 전환하면서 ArgoCD Slack 봇이 채널에서 빠졌다. 재초대 후 정상화.

추가로 설정 약점이 확인됐다: `when` 조건의 nil 가드 부재(에러 로그), trigger 정의/구독 불일치.

## 채널 규약 (중요)

- **`00_monitor-argocd`**: ArgoCD notifications 전용. ArgoCD 알림은 전부 이 채널로만 보낸다.
- **`00_monitor-critical` / `00_monitor-warning`**: AlertManager(Prometheus) 전용. **ArgoCD 가 사용하지 않는다.**

## 변경 (적용 완료)

| # | 항목 | 변경 |
|---|---|---|
| P1 | `when` nil 가드 | `on-deployed`/`on-sync-failed`/`on-sync-running` 의 when 에 `app.status.operationState != nil and ...` 추가. operationState 없는 앱(alloy/tempo/loki/kiali)의 `cannot fetch phase from <nil>` 에러 제거 |
| P2 | 장애 멘션 | `on-sync-failed`/`on-health-degraded` 메시지에 `<!here>` 추가 |
| - | 라우팅 | 단일 채널 `00_monitor-argocd` 유지 (severity 분리는 AlertManager 채널과 겹쳐 폐기) |

검증: `helm template argocd charts/argocd -f kkamji_local_values.yaml` 로 `argocd-notifications-cm` 렌더 확인 (변경 반영, YAML OK).

## 알림 라우팅 (적용 후)

| trigger | 조건 | 채널 | 멘션 |
|---|---|---|---|
| `on-deployed` | synced + healthy (commit 당 1회) | `00_monitor-argocd` | - |
| `on-sync-failed` | operationState Error/Failed | `00_monitor-argocd` | `@here` |
| `on-health-degraded` | health Degraded | `00_monitor-argocd` | `@here` |
| `on-sync-status-unknown` | sync Unknown | `00_monitor-argocd` | - |
| `on-sync-running` | (정의됨, 미구독 - 노이즈) | - | - |
| `on-sync-succeeded` | (template 만 존재, trigger/구독 없음) | - | - |

## 운영 노트

### dedup (알림이 "안 올 때" 1순위 확인)

- `on-deployed` 는 `oncePer: app.status.operationState.syncResult.revision` -> **revision 이 바뀔 때만 1회** 전송.
- 같은 revision 은 app annotation `notified.notifications.argoproj.io` 에 기록되어 재전송 스킵. controller 로그엔 `already sent` 로 찍힌다 (정상).
- `on-sync-failed`/`on-health-degraded`/`on-sync-status-unknown` 은 해당 상태가 실제 발생해야 전송. 전 앱이 Synced/Healthy 면 안 오는 게 정상.

### 비공개 채널 + 봇 멤버십

- `00_monitor-argocd` 가 private 이면 ArgoCD Slack 봇이 **채널 멤버여야** 전송된다.
- **채널 rename 또는 public -> private 전환 시 봇이 이탈**할 수 있다 -> 재초대 필요. (2026-06-07 실제 발생)
- **적용**: recipient 를 **채널 ID** (`C0B8D959UQP` = `00_monitor-argocd`)로 지정해 rename 영향을 제거했다. (단, 봇은 여전히 해당 채널 멤버여야 한다)

### 검증 / 강제 테스트

controller 로그:
```
kubectl -n argocd logs deploy/argocd-notifications-controller --tail=100 --context kkamji-lab
```
- `already sent` = dedup 스킵(정상). `failed to send` = 전송 실패(토큰/채널/봇 점검).

강제 재전송(실제 도달 확인 - dedup 우회):
```
kubectl -n argocd annotate app <app> notified.notifications.argoproj.io- --context kkamji-lab
```
다음 reconcile 에 `on-deployed` 재평가 -> Slack 도달 확인.

### 토큰

`argocd-notifications-secret` 의 `slack-token` 은 ExternalSecrets(ESO)로 동기화된다. 토큰 교체는 시크릿 스토어(SSM)에서 수행한다.

## 잔여 / TODO

- [x] recipient 채널 ID 전환 완료 (`00_monitor-argocd` = `C0B8D959UQP`)
- [ ] `on-sync-succeeded` template 미사용 정리 또는 trigger 추가 결정 (현재는 `on-deployed` 와 중복이라 미사용)
- [ ] `on-sync-running` 구독 여부 결정 (현재 노이즈 회피로 미구독)
- [ ] 단일 `00_monitor-argocd` 채널에서 `@here` 멘션이 과하면 제거 검토
