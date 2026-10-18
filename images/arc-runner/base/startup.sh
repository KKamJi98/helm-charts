#!/usr/bin/env bash
# No registration unless ARC explicitly supplies --runner. Probe is the safe default.
set -euo pipefail
mode=${1:---probe}
case "$mode" in
  --toolchain-probe) exec /opt/arc/bin/runner-preflight.sh toolchain ;;
  --probe|--runner) ;;
  *) printf 'unsupported startup mode\n' >&2; exit 64 ;;
esac
/opt/arc/bin/runner-preflight.sh security
/opt/arc/bin/runner-preflight.sh primitive
[ "${DOCKER_HOST:-}" = unix:///run/user/1001/docker.sock ] || exit 1
mkdir -p "$XDG_RUNTIME_DIR" /home/runner/.local/share/docker
chmod 0700 "$XDG_RUNTIME_DIR"
daemon_pid=''
runner_pid=''
cleanup() {
  code=$?
  trap - EXIT TERM INT
  [ -z "$runner_pid" ] || kill -TERM "$runner_pid" 2>/dev/null || true
  [ -z "$daemon_pid" ] || kill -TERM "$daemon_pid" 2>/dev/null || true
  [ -z "$runner_pid" ] || wait "$runner_pid" 2>/dev/null || true
  [ -z "$daemon_pid" ] || wait "$daemon_pid" 2>/dev/null || true
  exit "$code"
}
trap cleanup EXIT
trap 'exit 143' TERM
trap 'exit 130' INT
# Native/copy snapshotter avoids an unreviewed /dev/fuse or overlay exception.
# Containerd image store is necessary for built-in Buildx + existing gha cache-from.
# No rootlesskit port-driver=none: Docker publish/loopback contract must remain real.
dockerd-rootless.sh --config-file=/opt/arc/docker-daemon.json \
  > "$XDG_RUNTIME_DIR/rootless-docker.log" 2>&1 &
daemon_pid=$!
ready=false
for _ in $(seq 1 45); do
  kill -0 "$daemon_pid" 2>/dev/null || break
  if docker info >/dev/null 2>&1; then ready=true; break; fi
  sleep 1
done
if [ "$ready" != true ]; then
  printf 'rootless Docker startup failed under the required security boundary\n' >&2
  # This log contains startup diagnostics only, no runner configuration/token.
  while IFS= read -r line; do printf '%s\n' "$line" >&2; done < "$XDG_RUNTIME_DIR/rootless-docker.log"
  exit 1
fi
/opt/arc/bin/runner-preflight.sh runtime
if [ "$mode" = --probe ]; then
  printf 'rootless startup probe passed; runner was not registered or started\n'
  exit 0
fi
/home/runner/run.sh &
runner_pid=$!
# Fail the runner if its sole Docker backend dies; do not leave a half-qualified agent.
while kill -0 "$runner_pid" 2>/dev/null; do
  kill -0 "$daemon_pid" 2>/dev/null || { printf 'rootless Docker exited during job\n' >&2; exit 1; }
  sleep 1
done
wait "$runner_pid"
