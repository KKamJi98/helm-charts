# Alerting Quality Improvements (2026-06-12)

> Historical Slack-era record. Its routing, inhibition, and template quality goals are now implemented through Discord configuration in `charts/kube-prometheus-stack`; do not use Slack receiver instructions from this document.

Slack 알림의 노이즈(15분 도배)와 식별 불가 문제(TargetDown 에 pod 미표기)를 해소한
변경 기록과, 신규 알람 룰 추가 시 적용할 품질 기준.

## 변경 사항 (charts/kube-prometheus-stack/kkamji_local_values.yaml)

### 1. 라우팅 타이밍
- `group_wait` 10s -> 30s, `group_interval` 1m -> 5m
- `repeat_interval`: critical `1h`, warning `12h` (route 별 차등; 기존 15m 전역)

### 2. Inhibition
- pod 단위 원인 알람(KubePodCrashLooping / KubePodNotReady / ScrapeTargetDown)이
  있으면 같은 namespace 의 집계형 TargetDown 억제
- KubeNodeNotReady 발화 시 같은 node 라벨의 warning 억제
- 같은 alertname/namespace 의 critical 발화 시 warning 채널 중복 발송 억제

### 3. Per-target 가시성
- `kubernetes-pods` scrape job 에 `namespace`/`pod` 라벨 매핑 추가
  (기존에는 up 시계열에 라벨이 없어 "in  namespace" 처럼 빈 칸으로 출력)
- 커스텀 룰 `ScrapeTargetDown` (`up == 0`, for 5m, keep_firing_for 5m) 추가.
  집계형 TargetDown 은 inhibition 으로 억제하되 안전망으로 유지.

### 4. Slack 템플릿 v2 (Alertmanager >= 0.27 함수 사용)
- KST 시간 표기 (`tz "Asia/Seoul"`) + firing 경과 시간 (`since`/`humanizeDuration`)
- resolved 메시지에 Duration 표기
- 액션 링크: Runbook / Query(Prometheus) / Logs(Grafana Explore + Loki, pod 알람 한정) / Silence
- 전제: `alertmanagerSpec.externalUrl`, `prometheusSpec.externalUrl`,
  Loki datasource `uid: loki` 고정

## 알람 품질 기준 (신규 룰 추가 시 체크)

1. **행동 가능(actionable)**: 알람을 받고 할 행동이 없으면 룰을 만들지 않는다 (대시보드로 충분).
2. **식별 가능**: 메시지만 보고 대상(pod/node/job)을 특정할 수 있어야 한다.
   라벨이 없으면 scrape relabel 부터 고친다.
3. **severity 근거**: critical = 즉시 행동(1h 리마인드), warning = 확인 필요(12h),
   info = Slack 미발송. 근거 없는 critical 금지.
4. **중복 신호 금지**: 원인 알람이 있으면 파생 알람은 inhibit_rules 로 누른다.
5. **flapping 방어**: 재발화 가능성이 있는 룰은 `keep_firing_for` 를 설정한다.

## 잔여 작업: Watchdog deadman switch (미적용)

Watchdog 은 현재 null 드롭 -> 모니터링 스택 전체 장애를 감지할 외부 장치가 없다.

적용 절차:
1. healthchecks.io 에서 check 생성 (period 5m / grace 10m), ping URL 확보
2. ping URL 을 SSM `/kkamji/monitoring/alertmanager/healthchecks-ping-url` 에 SecureString 으로 저장
3. ESO ExternalSecret 으로 monitoring ns 의 Secret 으로 sync, alertmanagerSpec.secrets 에 추가
4. receiver 추가 후 Watchdog 라우트를 null 에서 교체:
   ```yaml
   - receiver: "healthchecks-deadman"
     matchers:
       - alertname = "Watchdog"
     repeat_interval: 5m
   # receivers:
   - name: "healthchecks-deadman"
     webhook_configs:
       - url_file: /etc/alertmanager/secrets/alertmanager-healthchecks/ping-url
         send_resolved: false
   ```
