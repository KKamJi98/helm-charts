# syntax=docker/dockerfile:1
FROM ghcr.io/actions/actions-runner@sha256:4ffadc0002b2581327e06101fc8c06cd189232baf79fe561fac9caeb76f5e807
USER root
SHELL ["/bin/bash", "-euo", "pipefail", "-c"]
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install --no-install-recommends -y \
    ca-certificates curl git jq python3 unzip xz-utils uidmap slirp4netns iptables libatomic1 shellcheck \
    libasound2t64 libatk-bridge2.0-0 libatk1.0-0 libcups2 libdbus-1-3 libdrm2 \
    libgbm1 libgtk-3-0 libnspr4 libnss3 libx11-6 libxcb1 libxcomposite1 libxdamage1 \
    libxext6 libxfixes3 libxkbcommon0 libxrandr2 fonts-liberation \
    && rm -rf /var/lib/apt/lists/*
# No runtime network installers, host socket or sudo-based daemon startup.
COPY vendor/ /opt/arc/vendor/
RUN cd /opt/arc/vendor && sha256sum --check SHA256SUMS \
    && mkdir -p /opt/arc/node /opt/arc/java /opt/arc/gh /opt/arc/helm /opt/google /opt/arc/bin \
        /usr/local/lib/docker/cli-plugins \
    && tar -xJf node.tar.xz --strip-components=1 -C /opt/arc/node \
    && tar -xzf java.tar.gz --strip-components=1 -C /opt/arc/java \
    && tar -xzf gh.tar.gz --strip-components=1 -C /opt/arc/gh \
    && tar -xzf helm.tar.gz --strip-components=1 -C /opt/arc/helm \
    && unzip -q gradle.zip -d /opt/arc \
    && tar -xzf docker.tgz --strip-components=1 -C /usr/local/bin \
    && tar -xzf docker-rootless-extras.tgz --strip-components=1 -C /usr/local/bin \
    && install -m 0755 docker-buildx /usr/local/lib/docker/cli-plugins/docker-buildx \
    && unzip -q chrome.zip -d /opt/google && mv /opt/google/chrome-linux64 /opt/google/chrome \
    && chmod 0755 /opt/google/chrome/chrome \
    && rm -rf /opt/arc/vendor \
    && printf 'runner:100000:65536\n' > /etc/subuid \
    && printf 'runner:100000:65536\n' > /etc/subgid \
    && mkdir -p /run/user/1001 /home/runner/.local/share/docker /home/runner/_work /home/runner/.gradle \
    && chown -R 1001:1001 /run/user/1001 /home/runner/.local /home/runner/_work /home/runner/.gradle \
    && chmod 0700 /run/user/1001
COPY --chmod=0755 runner-preflight.sh startup.sh /opt/arc/bin/
COPY tools-lock.json /opt/arc/tools-lock.json
COPY docker-daemon.json /opt/arc/docker-daemon.json
ENV JAVA_HOME=/opt/arc/java \
    GRADLE_HOME=/opt/arc/gradle-9.8.1 \
    PATH=/opt/arc/node/bin:/opt/arc/java/bin:/opt/arc/gradle-9.8.1/bin:/opt/arc/gh/bin:/opt/arc/helm:/usr/local/bin:/usr/bin:/bin \
    DOCKER_HOST=unix:///run/user/1001/docker.sock \
    XDG_RUNTIME_DIR=/run/user/1001 \
    DISABLE_RUNNER_UPDATE=true \
    GRADLE_OPTS="-Dorg.gradle.workers.max=1 -Dorg.gradle.jvmargs=-Xmx1g" \
    PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
USER 1001:1001
WORKDIR /home/runner
ENTRYPOINT ["/opt/arc/bin/startup.sh"]
CMD ["--probe"]
