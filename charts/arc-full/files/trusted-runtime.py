import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

SOCKET_ROOT = Path("/run/arc-api")
RUN_ROOT = Path("/run/arc-runtime")


def status():
    return dict(
        line.split(":", 1)
        for line in Path("/proc/self/status").read_text().splitlines()
        if ":" in line
    )


def main():
    ready = SOCKET_ROOT / "ready"
    if "--check-ready" in sys.argv:
        if not ready.exists():
            return 1
        try:
            result = subprocess.run(
                [
                    "docker",
                    "--host=unix:///run/arc-api/docker.sock",
                    "info",
                    "--format",
                    "{{json .SecurityOptions}}",
                ],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            return (
                0
                if result.returncode == 0
                and "name=rootless" in json.loads(result.stdout)
                else 1
            )
        except (OSError, subprocess.TimeoutExpired, ValueError):
            return 1
    assert os.getuid() == os.getgid() == 1001
    before = status()
    assert before["NoNewPrivs"].strip() == "0"
    assert int(before["CapBnd"].strip(), 16) == (1 << 6) | (1 << 7) | (1 << 31)
    expected = "runner:0:1001\nrunner:1002:64534\n"
    assert Path("/etc/subuid").read_text() == expected
    assert Path("/etc/subgid").read_text() == expected
    rows = [
        list(map(int, r.split()))
        for r in Path("/proc/self/uid_map").read_text().splitlines()
    ]
    assert (
        len(rows) == 1 and rows[0][0] == 0 and rows[0][1] != 0 and rows[0][2] == 65536
    )
    tun = Path("/dev/net/tun").stat()
    assert (os.major(tun.st_rdev), os.minor(tun.st_rdev)) == (10, 200)
    for path in [
        SOCKET_ROOT,
        RUN_ROOT / "runtime",
        Path("/privatehome/home"),
        Path("/var/lib/arc-docker/data"),
    ]:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
    ready.unlink(missing_ok=True)
    (RUN_ROOT / "daemon.pid").unlink(missing_ok=True)
    env = os.environ.copy()
    env.update(
        HOME="/privatehome/home",
        XDG_RUNTIME_DIR=str(RUN_ROOT / "runtime"),
        DOCKER_HOST="unix:///run/arc-api/docker.sock",
        DOCKER_CONFIG="/privatehome/home/.docker",
        DOCKERD_ROOTLESS_ROOTLESSKIT_DETACH_NETNS="0",
    )
    stopped = False

    def stop(signum, frame):
        nonlocal stopped
        stopped = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    binary = shutil.which("dockerd-rootless.sh")
    assert binary
    child = subprocess.Popen(
        [
            binary,
            "--host=unix:///run/arc-api/docker.sock",
            "--data-root=/var/lib/arc-docker/data",
            "--exec-root=/run/arc-runtime/exec",
            "--pidfile=/run/arc-runtime/daemon.pid",
        ],
        env=env,
        start_new_session=True,
    )
    try:
        while not stopped:
            if child.poll() is not None:
                raise RuntimeError("per-job daemon exited")
            if not ready.exists():
                result = subprocess.run(
                    ["docker", "info", "--format", "{{json .SecurityOptions}}"],
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
                if result.returncode == 0:
                    assert "name=rootless" in json.loads(result.stdout)
                    ready.write_text("ready\n")
                    print(
                        json.dumps(
                            {
                                "phase": "TRUSTED_ROLE_READY",
                                "rootless": True,
                                "whole_lifetime_bounding_capabilities": [
                                    "SETUID",
                                    "SETGID",
                                    "SETFCAP",
                                ],
                                "post_init_all_thread_privdrop": False,
                            }
                        ),
                        flush=True,
                    )
            time.sleep(0.5)
        return 0
    finally:
        ready.unlink(missing_ok=True)
        if child.poll() is None:
            os.killpg(child.pid, signal.SIGTERM)
            try:
                child.wait(timeout=25)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
