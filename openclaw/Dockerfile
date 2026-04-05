FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

# System dependencies
RUN apt-get update && apt-get install -y \
    curl wget git build-essential ca-certificates gnupg \
    python3 python3-pip python3-venv \
    && rm -rf /var/lib/apt/lists/*

# Node.js 24
RUN curl -fsSL https://deb.nodesource.com/setup_24.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Go
ARG GO_VERSION=1.24.2
RUN curl -fsSL "https://go.dev/dl/go${GO_VERSION}.linux-amd64.tar.gz" | tar -C /usr/local -xz

# OpenClaw
RUN npm install -g openclaw@latest

# Non-root user
RUN useradd -m -u 1000 -s /bin/bash openclaw
USER openclaw
WORKDIR /home/openclaw

ENV GOPATH="/home/openclaw/go"
ENV PATH="${GOPATH}/bin:/usr/local/go/bin:${PATH}"

EXPOSE 18789

CMD ["openclaw", "gateway", "--port", "18789"]
