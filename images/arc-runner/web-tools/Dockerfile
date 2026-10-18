# syntax=docker/dockerfile:1
# Runner/SDK image for the full and light ARC pools: base runner tools plus an
# offline npm cache for kkamji-platform apps/web and the font set of the
# hosted Ubuntu 26.04 runner. Inputs are produced by ../build.sh.
ARG BASE
FROM ${BASE}
COPY --chown=1001:1001 npm-cache/ /opt/arc/npm-cache/
COPY --chown=0:0 fonts/ /usr/share/fonts/
