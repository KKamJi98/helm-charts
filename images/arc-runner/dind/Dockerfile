# syntax=docker/dockerfile:1
# Trusted rootless Docker sidecar image. newuidmap/newgidmap carry file
# capabilities instead of setuid, iproute2 is added for rootlesskit networking,
# and mount/umount lose their setuid bit. Built on the same base as web-tools.
ARG BASE
FROM ${BASE}
USER 0:0
COPY apply_filecaps.py /apply_filecaps.py
RUN /usr/bin/python3 /apply_filecaps.py && rm /apply_filecaps.py
ENV PATH=/opt/arc/node/bin:/opt/arc/java/bin:/opt/arc/gradle-9.8.1/bin:/opt/arc/gh/bin:/opt/arc/helm:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin
RUN apt-get update && apt-get install -y --no-install-recommends iproute2 \
    && dpkg-query -W iproute2 iptables \
    && rm -rf /var/lib/apt/lists/*
RUN chmod 0755 /usr/bin/mount /usr/bin/umount
USER 1001:1001
