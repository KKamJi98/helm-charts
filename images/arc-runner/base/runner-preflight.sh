#!/usr/bin/env bash
# Trusted image-owned checks; never source a repository-owned preflight before checkout.
set -euo pipefail
fail() { printf 'ARC runtime contract failed: %s\n' "$1" >&2; exit 1; }
mode=${1:-runtime}
case "$mode" in security|toolchain|primitive|runtime) ;; *) fail 'unknown mode' ;; esac
security() {
  [ "$(id -u)" = 1001 ] || fail 'uid 1001 required'
  [ ! -e /var/run/secrets/kubernetes.io/serviceaccount/token ] || fail 'Kubernetes API token must not be mounted'
  [ ! -S /var/run/docker.sock ] || fail 'host/default Docker socket must not be mounted'
  local caps=0 seccomp=0 nnp=0 key value rest
  while read -r key value rest; do
    case "$key" in
      CapEff:) [ "$value" = 0000000000000000 ] || fail 'capabilities must be dropped'; caps=1 ;;
      Seccomp:) [ "$value" = 2 ] || fail 'seccomp filtering required'; seccomp=1 ;;
      NoNewPrivs:) [ "$value" = 1 ] || fail 'no-new-privileges required'; nnp=1 ;;
    esac
  done < /proc/self/status
  [ "$caps$seccomp$nnp" = 111 ] || fail 'missing kernel security evidence'
  printf 'PASS security: uid1001 CapEff0 Seccomp2 NoNewPrivs1; no host socket/API token\n'
}
toolchain() {
  for tool in bash git python3 jq gh helm java javac node npm gradle docker rootlesskit dockerd-rootless.sh unshare; do
    command -v "$tool" >/dev/null || fail "missing $tool"
  done
  python3 - <<'PY'
import json, subprocess, sys
from pathlib import Path
assert sys.version_info >= (3, 12), 'Python3.12+ required'
lock = json.loads(Path('/opt/arc/tools-lock.json').read_text())
versions = {x['file']: x['version'] for x in lock['artifacts']}
def output(*args):
    try:
        return subprocess.check_output(args, stderr=subprocess.STDOUT, text=True).strip()
    except subprocess.CalledProcessError as exc:
        print(exc.output, file=sys.stderr)
        raise
assert output('node', '--version') == 'v' + versions['node.tar.xz']
assert output('javac', '-version').startswith('javac 25')
assert output('helm', 'version', '--short').startswith('v' + versions['helm.tar.gz'])
assert ('Gradle ' + versions['gradle.zip']) in output('gradle', '--no-daemon', '--version')
assert ('gh version ' + versions['gh.tar.gz']) in output('gh', '--version')
assert versions['docker.tgz'] in output('docker', '--version')
assert versions['docker-buildx'] in output('docker', 'buildx', 'version')
assert output('/opt/google/chrome/chrome', '--version').endswith(versions['chrome.zip'])
print('PASS toolchain versions: Python3.12+, Java25, Node26.7.0, Gradle9.8.1, Helm4.2.1, gh, Docker, Buildx, Chrome')
PY
}
primitive() {
  unshare --user --map-root-user /bin/true || fail 'unprivileged user namespace unavailable; do not relax security profiles'
  printf 'PASS unprivileged user namespace primitive (not subordinate-UID/rootless-Docker qualification)\n'
}
runtime() {
  security
  local memory cpu period
  read -r memory < /sys/fs/cgroup/memory.max
  case "$memory" in ''|*[!0-9]*) fail 'finite cgroup-v2 memory limit required' ;; esac
  [ "$memory" -ge 8589934592 ] || fail 'full-CI candidate requires reviewed 8Gi memory envelope'
  read -r cpu period < /sys/fs/cgroup/cpu.max
  case "$cpu" in ''|*[!0-9]*) fail 'finite CPU quota required' ;; esac
  if [ "$cpu" -le 0 ] || [ "$period" -le 0 ]; then fail 'invalid CPU quota'; fi
  toolchain
  [ "${DOCKER_HOST:-}" = unix:///run/user/1001/docker.sock ] || fail 'only in-Pod rootless Docker endpoint permitted'
  python3 - <<'PY'
import os, stat
p = '/run/user/1001/docker.sock'
s = os.lstat(p)
assert stat.S_ISSOCK(s.st_mode) and s.st_uid == os.getuid(), 'rootless socket ownership/type mismatch'
PY
  docker info --format '{{json .SecurityOptions}}' | python3 -c 'import json,sys; s=json.load(sys.stdin); assert "name=rootless" in s and not any("unconfined" in x for x in s)'
  docker info --format '{{json .DriverStatus}}' | python3 -c 'import json,sys; s=dict(json.load(sys.stdin)); assert s.get("driver-type") == "io.containerd.snapshotter.v1", "containerd image store required for builtin Buildx gha cache support"'
  [ "$(docker info --format '{{.Driver}}')" = native ] || fail 'reviewed copy snapshotter required'
  docker version --format '{{.Server.Version}}' >/dev/null
  printf 'PASS ARC runtime preflight; full tests and image contracts still required\n'
}
case "$mode" in security) security ;; toolchain) toolchain ;; primitive) security; primitive ;; runtime) runtime ;; esac
