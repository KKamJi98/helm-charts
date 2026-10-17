#!/bin/sh
set -eu
file=arc-docker-runtime-v2.json
expected=8814d29dfc13801408c724c09b762ace96681787e8b1c0384324af6a2374c725
actual=$(sha256sum "/profiles/$file")
test "${actual%% *}" = "$expected"
if test -e "/host-seccomp/$file"; then
  test ! -L "/host-seccomp/$file"
  actual=$(sha256sum "/host-seccomp/$file")
  test "${actual%% *}" = "$expected"
else
  umask 022
  cp "/profiles/$file" "/host-seccomp/$file.new"
  chmod 0644 "/host-seccomp/$file.new"
  mv "/host-seccomp/$file.new" "/host-seccomp/$file"
fi
