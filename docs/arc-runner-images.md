---
title: ARC runner images build, publish and recovery
updated: 2026-10-18T15:29:16+09:00
type: runbook
status: current
---

# ARC runner images

The full and light ARC pools run two custom images. Until they are published,
both exist only in the node containerd store of `k8s-w2` and in the build
host's local Docker, and the chart pins them with `imagePullPolicy: Never`.
A runner scheduled on another node fails with `ErrImageNeverPull`, and losing
`k8s-w2` loses the images. This page is the recipe and the procedure that
remove that dependency.

| Role | Containers | Current local reference |
| --- | --- | --- |
| runner/SDK tools | `seed-sdk`, `runner`, `verified-static-tools` | `arc-platform-web-tools-20261017@sha256:0d5fe73d622effec94798a9859382f9779ab5d026bbdcdbfb2930bd5ca48b7d5` (tag `font-parity`) |
| trusted rootless Docker | `dind` | `arc-platform-nosuidmount-setfcap-20261017@sha256:0a8a8a31aac32784698f59ce1d45a242eeb2dcb9221894d39d14fce00ccff72d` (tag `diagnostic`) |

## Recipe (`images/arc-runner/`)

The local images were built as a chain of tags. The recipe keeps the same
steps in three Dockerfiles:

- `base/`: official `actions-runner` pinned by digest, Ubuntu runtime packages,
  and nine vendored tools from `base/tools-lock.json` (Node, Corretto, Gradle,
  gh, Helm, Docker static, rootless extras, buildx, Chrome for Testing), each
  verified by sha256. The four helper files are byte-identical to the files in
  the current images.
- `web-tools/`: base plus the offline npm cache for `kkamji-platform`
  `apps/web` and the 277 font files of the hosted Ubuntu 26.04 runner
  (`fonts-dejavu-core`, `fonts-noto-core`, `fonts-noto-cjk`,
  `fonts-noto-color-emoji`, data files only).
- `dind/`: base plus file capabilities on `newuidmap`
  (`cap_setuid,cap_setfcap=ep`) and `newgidmap` (`cap_setgid=ep`) instead of
  setuid, `iproute2`, and `mount`/`umount` without the setuid bit. The two
  historical filecaps layers collapse into the final values.

`inputs.lock.json` pins the font packages, the npm cache source commit and the
lock file hash. Downloaded inputs are ignored by Git.

```bash
cd images/arc-runner
./build.sh fetch            # base tools + font packages, sha256 verified
./build.sh npm-cache        # registry-only npm ci --ignore-scripts, no credentials
./build.sh build 20261018   # arc-runner-{base,web-tools,dind}:20261018
```

A rebuild is functionally equivalent, not byte-identical: Ubuntu packages
installed by `apt-get` and npm cache index timestamps move. The 2026-10-18 test
rebuild reproduced the font files and vendored tool archives byte for byte,
the same 238 npm cache entries with identical content, and the same tool
versions, file capabilities, file modes, user and `PATH` as the current images. A rebuilt image
therefore needs the same qualification as any image change (native Docker,
SDK and one full CI run per repository) before the chart uses it. The exact
current bytes are preserved by publishing the current local images as they are.

## Content check

Checked on 2026-10-18 before publishing, without printing any matched text:

- `gitleaks dir --redact` over `/opt/arc`, `/home/runner`, `/root`, `/etc`,
  `/tmp`, `/var/tmp` and `/usr/local/bin` of both images: 12 `generic-api-key`
  matches each, all in files byte-identical to the official base image
  (`k8s` hook bundles, Node headers, launchpadlib cache) or inside sha256-verified
  upstream archives (Node headers, Corretto `java.security`). No match in the
  layers this recipe adds. Image `Env` and `Labels` hold no credentials.
- The npm cache holds 476 entries, all from `https://registry.npmjs.org`. No
  private source is included.

## Publishing (GHCR, private)

- Packages: `ghcr.io/kkamji98/arc-runner-web-tools`, `ghcr.io/kkamji98/arc-runner-dind`.
  A new package is private by default. Container registry storage and
  bandwidth are currently free.
- GHCR accepts only a personal access token (classic). Publishing uses the
  owner's token with `write:packages` (`gh auth refresh -h github.com -s write:packages`,
  then `gh auth token | docker login ghcr.io -u KKamJi98 --password-stdin`).
- Publish the current images first, unchanged:

```bash
./build.sh publish arc-platform-web-tools-20261017:font-parity arc-runner-web-tools 20261017
./build.sh publish arc-platform-nosuidmount-setfcap-20261017:diagnostic arc-runner-dind 20261017
```

  The printed `ghcr.io/kkamji98/<name>@sha256:...` is the registry manifest
  digest. It differs from the local containerd digest because the registry
  stores compressed layers; the image content is the same.

## Cluster pull (planned, separate change)

- Pull credential: a classic PAT with only `read:packages`, entered by the
  owner into SSM `/kkamji/arc/ghcr-pull` (SecureString). Agents never read or
  print the value.
- ESO renders a `kubernetes.io/dockerconfigjson` Secret in `ci-full` and
  `ci-pr` from the existing `parameter-store`; the runner Pod templates
  reference it with `imagePullSecrets`.
- The chart then pins the registry digests and switches `Never` to
  `IfNotPresent`. Verification is a real pull and start on a node without the
  image in its cache (`k8s-w1`), followed by one full CI run per repository.

## Rollback

- The local images stay on `k8s-w2` and in the build host's Docker until the
  registry path is verified. Reverting the chart commit restores the
  `Never`/local digest pins.
- Node image cleanup starts only after the cold pull verification. Images used
  by running or scheduled ARC jobs and CronJobs are kept.
