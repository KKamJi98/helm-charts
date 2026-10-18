---
title: ARC runner images build, publish and recovery
updated: 2026-10-18T15:53:12+09:00
type: runbook
status: current
---

# ARC runner images

The full and light ARC pools run two custom images. They used to exist only
in the node containerd store of `k8s-w2` and in the build host's local Docker,
pinned with `imagePullPolicy: Never`, so a runner on another node failed with
`ErrImageNeverPull` and losing `k8s-w2` lost the images. The images are now
in private GHCR and the charts pull them by digest with `IfNotPresent`. This
page is the recipe, the publish procedure and the pull path.

| Role | Containers | Chart reference | Former local name |
| --- | --- | --- | --- |
| runner/SDK tools | `seed-sdk`, `runner`, `verified-static-tools` | `ghcr.io/kkamji98/arc-runner-web-tools@sha256:0d5fe73d622effec94798a9859382f9779ab5d026bbdcdbfb2930bd5ca48b7d5` | `arc-platform-web-tools-20261017:font-parity` |
| trusted rootless Docker | `dind` | `ghcr.io/kkamji98/arc-runner-dind@sha256:0a8a8a31aac32784698f59ce1d45a242eeb2dcb9221894d39d14fce00ccff72d` | `arc-platform-nosuidmount-setfcap-20261017:diagnostic` |

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
- The npm cache holds 238 entries, all from `https://registry.npmjs.org`. No
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
  digest. The build host's Docker uses the containerd image store, so the
  manifest is pushed unchanged and the registry digest equals the former
  local digest (verified for both images on 2026-10-18).

## Cluster pull

- Pull credential: one classic PAT with only `read:packages`, in SSM
  `/kkamji/personal/kkamji-platform/ghcr/pull-token` (SecureString JSON with
  `username` and `token`). The same parameter already backs
  `kkamji-platform/ghcr-pull-secret`, so ARC needs no new credential or IAM
  change. The owner enters it; agents never read or print the value.
- `arc-full` (`ci-full`) and `arc-foundation` (`ci-pr`) render an
  ExternalSecret `ghcr-pull-secret` of type `kubernetes.io/dockerconfigjson`
  from `parameter-store` when `imagePullSecret.enabled` is true. The runner
  Pod templates reference it with `imagePullSecrets`. The job service
  accounts cannot read Secrets, and no Secret is mounted into runner Pods.
- Rotation: create a new classic PAT, replace the parameter value, then
  force a refresh of every ExternalSecret that reads it
  (`kubectl annotate externalsecret ghcr-pull-secret -n <ns> force-sync=$(date +%s) --overwrite`
  for `kkamji-platform`, `ci-full` and `ci-pr`). Deleting the PAT breaks new
  pulls in all three namespaces; running Pods keep working.
- Verification: a real pull and start on a node without the image in its
  cache, followed by one full CI run per repository. Each image is about
  7 GB unpacked, so check node disk headroom before a cold pull.

## Rollback

- The local images stay on `k8s-w2` and in the build host's Docker until the
  registry path is verified. Reverting the chart commit restores the
  `Never`/local digest pins and removes the ARC pull Secrets.
- Node image cleanup starts only after the cold pull verification. Images used
  by running or scheduled ARC jobs and CronJobs are kept.
