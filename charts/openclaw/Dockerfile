FROM node:24-bookworm-slim

ARG OPENCLAW_VERSION=2026.4.2

RUN npm config set fetch-retries 5 \
    && npm config set fetch-retry-factor 2 \
    && npm config set fetch-retry-mintimeout 10000 \
    && npm config set fetch-retry-maxtimeout 120000 \
    && npm install -g "openclaw@${OPENCLAW_VERSION}" \
    && npm cache clean --force \
    && install -d -m 0755 -o 1000 -g 1000 \
      /home/node/.openclaw \
      /home/node/.openclaw/workspace

USER 1000:1000
WORKDIR /home/node

ENV HOME="/home/node"

EXPOSE 18789

CMD ["openclaw", "gateway", "--port", "18789"]
