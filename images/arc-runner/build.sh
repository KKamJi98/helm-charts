#!/usr/bin/env bash
# Build and publish the ARC runner images (see docs/arc-runner-images.md).
#
#   build.sh fetch                  download base tools and font packages, verify sha256
#   build.sh npm-cache              rebuild the offline npm cache (needs fetch and gh access to kkamji-platform)
#   build.sh build [TAG]            build base, web-tools and dind locally (default TAG: today, UTC)
#   build.sh publish LOCAL NAME TAG push a local image as ghcr.io/kkamji98/NAME:TAG, print its digest
#
# Publishing needs `docker login ghcr.io` with a token that has write:packages.
# Nothing here reads cluster credentials or runs CI code on the host.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
registry="ghcr.io/kkamji98"
work="$here/.work"

need() {
  command -v "$1" >/dev/null || { printf 'missing command: %s\n' "$1" >&2; exit 2; }
}

verify() { # file sha256
  printf '%s  %s\n' "$2" "$1" | sha256sum --check --quiet - || {
    printf 'sha256 mismatch: %s\n' "$1" >&2
    exit 1
  }
}

download() { # url dest sha256
  if [[ ! -f "$2" ]]; then
    curl -fsSL --retry 3 -o "$2.part" "$1"
    mv "$2.part" "$2"
  fi
  verify "$2" "$3"
}

fetch() {
  need curl; need python3; need dpkg-deb
  mkdir -p "$here/base/vendor" "$work/debs"
  python3 - "$here/base/tools-lock.json" <<'PY' | while read -r file url sha; do
import json, sys
for item in json.load(open(sys.argv[1]))["artifacts"]:
    print(item["file"], item["url"], item["sha256"])
PY
    download "$url" "$here/base/vendor/$file" "$sha"
    printf '%s  %s\n' "$sha" "$file"
  done > "$work/SHA256SUMS"
  mv "$work/SHA256SUMS" "$here/base/vendor/SHA256SUMS"

  rm -rf "$here/web-tools/fonts" "$work/fonts"
  mkdir -p "$work/fonts"
  python3 - "$here/inputs.lock.json" <<'PY' | while read -r url sha; do
import json, sys
fonts = json.load(open(sys.argv[1]))["fonts"]
for item in fonts["packages"]:
    print(fonts["mirror"] + "/" + item["path"], item["sha256"])
PY
    deb="$work/debs/${url##*/}"
    download "$url" "$deb" "$sha"
    dpkg-deb -x "$deb" "$work/fonts"
  done
  mv "$work/fonts/usr/share/fonts" "$here/web-tools/fonts"
  count="$(find "$here/web-tools/fonts" -type f | wc -l)"
  expected="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["fonts"]["font_file_count"])' "$here/inputs.lock.json")"
  [[ "$count" == "$expected" ]] || { printf 'font files: %s, expected %s\n' "$count" "$expected" >&2; exit 1; }
  printf 'fetch ok: %s base tools, %s font files\n' "$(wc -l < "$here/base/vendor/SHA256SUMS")" "$count"
}

npm_cache() {
  need gh; need docker; need python3
  read -r repo commit dir lock_sha < <(python3 - "$here/inputs.lock.json" <<'PY'
import json, sys
n = json.load(open(sys.argv[1]))["npm_cache"]
print(n["repository"], n["commit"], n["directory"], n["package_lock_sha256"])
PY
)
  local src="$work/npm-src" base_ref="${BASE_IMAGE:-arc-runner-base:npm-cache}"
  [[ -n "${BASE_IMAGE:-}" ]] || docker build -q -t "$base_ref" "$here/base" >/dev/null
  rm -rf "$src" "$work/npm-out" "$here/web-tools/npm-cache"
  mkdir -p "$src" "$work/npm-out"
  for name in package.json package-lock.json; do
    gh api "repos/$repo/contents/$dir/$name?ref=$commit" \
      -H 'Accept: application/vnd.github.raw' > "$src/$name"
  done
  verify "$src/package-lock.json" "$lock_sha"
  # Registry-only install: no lifecycle scripts, no npm credentials, no host HOME.
  # The image keeps the cacache store itself (content-v2, index-v5) at
  # /opt/arc/npm-cache, so only <cache>/_cacache is kept.
  docker run --rm --network bridge --user "$(id -u):$(id -g)" \
    -v "$src:/src:ro" -v "$work/npm-out:/cache" \
    --entrypoint /usr/bin/env "$base_ref" -i PATH=/opt/arc/node/bin:/usr/bin:/bin HOME=/tmp \
    bash -euo pipefail -c 'cp /src/package.json /src/package-lock.json /tmp/ && cd /tmp &&
      : > /tmp/npmrc-user && : > /tmp/npmrc-global &&
      npm ci --ignore-scripts --no-audit --no-fund --cache /cache \
        --userconfig /tmp/npmrc-user --globalconfig /tmp/npmrc-global \
        --registry https://registry.npmjs.org/'
  mv "$work/npm-out/_cacache" "$here/web-tools/npm-cache"
  local hosts
  hosts="$(cat "$here"/web-tools/npm-cache/index-v5/*/*/* | grep -oE 'https?://[^/"]+' | sort -u)"
  [[ "$hosts" == "https://registry.npmjs.org" ]] || { printf 'unexpected cache hosts: %s\n' "$hosts" >&2; exit 1; }
  printf 'npm cache ok: %s entries from %s\n' "$(find "$here/web-tools/npm-cache/index-v5" -type f | wc -l)" "$hosts"
}

build() {
  need docker
  local tag="${1:-$(date -u +%Y%m%d)}"
  [[ -f "$here/base/vendor/SHA256SUMS" && -d "$here/web-tools/fonts" ]] || { printf 'run fetch first\n' >&2; exit 2; }
  [[ -d "$here/web-tools/npm-cache/index-v5" ]] || { printf 'run npm-cache first\n' >&2; exit 2; }
  docker build -t "arc-runner-base:$tag" "$here/base"
  docker build --build-arg "BASE=arc-runner-base:$tag" -t "arc-runner-web-tools:$tag" "$here/web-tools"
  docker build --build-arg "BASE=arc-runner-base:$tag" -t "arc-runner-dind:$tag" "$here/dind"
  printf 'built arc-runner-{base,web-tools,dind}:%s\n' "$tag"
}

publish() {
  need docker
  [[ $# == 3 ]] || { printf 'usage: build.sh publish LOCAL NAME TAG\n' >&2; exit 2; }
  [[ "$2" =~ ^arc-runner-[a-z-]+$ && "$3" =~ ^[A-Za-z0-9._-]+$ ]] || { printf 'invalid NAME or TAG\n' >&2; exit 2; }
  local target="$registry/$2:$3"
  docker image inspect "$1" >/dev/null
  docker tag "$1" "$target"
  docker push "$target" >/dev/null
  docker image inspect --format '{{range .RepoDigests}}{{println .}}{{end}}' "$target" | grep -F "$registry/$2@"
}

case "${1:-}" in
  fetch) fetch ;;
  npm-cache) npm_cache ;;
  build) shift; build "$@" ;;
  publish) shift; publish "$@" ;;
  *) sed -n '2,10p' "${BASH_SOURCE[0]}" >&2; exit 2 ;;
esac
