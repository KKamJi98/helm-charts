import json
import os
from pathlib import Path


def disk_required_bytes(total, job_budget_gib=11):
    # Platform 7Gi Docker data plus SDK 4Gi; BQL 30Gi plus 4Gi (values.yaml).
    if job_budget_gib not in (11, 34):
        raise ValueError("job disk budget must match a qualified pool:11Gi or34Gi")
    gib = 1024**3
    imagefs_margin = (total * 15 + 99) // 100 + gib
    return job_budget_gib * gib + max(5 * gib, imagefs_margin)


def memory_required_bytes(pod_mib=5120):
    # The node must still hold this Pod's whole budget plus 1Gi when it starts.
    if pod_mib not in (3584, 5120, 7168):
        raise ValueError("Pod memory budget must match a qualified slot:3584, 5120 or 7168MiB")
    return (pod_mib + 1024) * 1024**2


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
    pod_mib = int(os.environ.get("ARC_POD_MEMORY_MIB", "5120"))
    assert available >= memory_required_bytes(pod_mib), (
        f"node memory reserve below{pod_mib}MiB Pod budget plus1Gi; no repository workload started"
    )
    job_budget_gib = int(os.environ.get("ARC_JOB_EPHEMERAL_GIB", "16"))
    required_disk = disk_required_bytes(fs.f_blocks * fs.f_frsize, job_budget_gib)
    assert free >= required_disk, (
        f"node disk reserve below{job_budget_gib}Gi plus max5Gi/imagefs15percent+1Gi; "
        "no repository workload started"
    )
    print(
        json.dumps(
            {
                "phase": "SDK_SECURITY_AND_NODE_RESERVE_PASS",
                "UID": 1001,
                "NNP": 1,
                "capabilities": 0,
                "Pod_memory_budget_MiB": pod_mib,
                "node_memory_available_bytes": available,
                "node_disk_available_bytes": free,
                "node_disk_required_bytes": required_disk,
                "job_ephemeral_budget_GiB": job_budget_gib,
                "imagefs_pressure_guard_percent": 15,
            }
        ),
        flush=True,
    )
    os.execv("/home/runner/run.sh", ["/home/runner/run.sh"])


if __name__ == "__main__":
    main()
