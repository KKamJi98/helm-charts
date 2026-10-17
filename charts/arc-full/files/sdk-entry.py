import json
import os
from pathlib import Path


def disk_required_bytes(total):
    gib = 1024**3
    imagefs_margin = (total * 15 + 99) // 100 + gib
    return 16 * gib + max(5 * gib, imagefs_margin)


def main():
    assert os.getuid() == os.getgid() == 1001
    status = dict(
        line.split(":", 1)
        for line in Path("/proc/self/status").read_text().splitlines()
        if ":" in line
    )
    assert status["NoNewPrivs"].strip() == "1"
    assert all(int(status[k].strip(), 16) == 0 for k in ["CapEff", "CapPrm", "CapBnd"])
    assert not Path("/var/run/secrets/kubernetes.io/serviceaccount/token").exists()
    assert os.statvfs("/").f_flag & os.ST_RDONLY
    available = (
        int(
            next(
                line.split()[1]
                for line in Path("/proc/meminfo").read_text().splitlines()
                if line.startswith("MemAvailable:")
            )
        )
        * 1024
    )
    fs = os.statvfs("/home/runner/_work")
    free = fs.f_bavail * fs.f_frsize
    assert available >= 6 * 1024**3, (
        "node memory reserve below shared5Gi plus1Gi; no repository workload started"
    )
    required_disk = disk_required_bytes(fs.f_blocks * fs.f_frsize)
    assert free >= required_disk, (
        "node disk reserve below16Gi plus max5Gi/imagefs15percent+1Gi; "
        "no repository workload started"
    )
    print(
        json.dumps(
            {
                "phase": "SDK_SECURITY_AND_NODE_RESERVE_PASS",
                "UID": 1001,
                "NNP": 1,
                "capabilities": 0,
                "shared_Pod_budget_GiB": 5,
                "node_memory_available_bytes": available,
                "node_disk_available_bytes": free,
                "node_disk_required_bytes": required_disk,
                "job_ephemeral_budget_GiB": 16,
                "imagefs_pressure_guard_percent": 15,
            }
        ),
        flush=True,
    )
    os.execv("/home/runner/run.sh", ["/home/runner/run.sh"])


if __name__ == "__main__":
    main()
