"""Compare offline Grype JSON reports without suppressing any findings."""

import collections
import json
import sys
from pathlib import Path

TARGETS = {
    "GHSA-6v38-4h7w-rj9h",
    "GHSA-8m4g-j4wp-wgcg",
    "GHSA-7vr2-2fgp-9w7p",
    "GHSA-45c3-73f7-pv4m",
}


def findings(report):
    return {m["vulnerability"]["id"] for m in report["matches"]}


def os_high(report):
    return sorted(
        (
            m["artifact"]["name"],
            m["artifact"]["version"],
            m["vulnerability"]["id"],
            m["vulnerability"]["fix"]["state"],
        )
        for m in report["matches"]
        if m["artifact"]["type"] == "deb" and m["vulnerability"]["severity"] == "High"
    )


def main():
    before, after = (json.loads(Path(p).read_text()) for p in sys.argv[1:3])
    assert before["descriptor"]["version"] == after["descriptor"]["version"], (
        "scanner mismatch"
    )
    assert before["descriptor"]["db"] == after["descriptor"]["db"], "database mismatch"
    assert TARGETS <= findings(before), "baseline must contain all four advisories"
    assert not TARGETS & findings(after), "target advisory remains"
    assert not findings(after) - findings(before), (
        "new finding IDs require investigation"
    )
    assert os_high(before) == os_high(after), "unexpected OS High delta: investigate"
    summary = {
        "scanner": after["descriptor"]["version"],
        "database": after["descriptor"]["db"],
        "baseline_config_id": before["source"]["target"]["imageID"],
        "candidate_config_id": after["source"]["target"]["imageID"],
        "candidate_repo_digests": after["source"]["target"]["repoDigests"],
        "target_advisories_removed": sorted(TARGETS),
        "baseline_severity_matches": dict(
            collections.Counter(
                m["vulnerability"]["severity"] for m in before["matches"]
            )
        ),
        "candidate_severity_matches": dict(
            collections.Counter(
                m["vulnerability"]["severity"] for m in after["matches"]
            )
        ),
        "unchanged_os_high_matches": len(os_high(after)),
        "unchanged_os_high_fix_states": dict(
            collections.Counter(row[3] for row in os_high(after))
        ),
        "remaining_os_high": os_high(after),
        "new_findings": sorted(findings(after) - findings(before)),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
