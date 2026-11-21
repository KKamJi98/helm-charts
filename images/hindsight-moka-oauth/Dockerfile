FROM ghcr.io/astral-sh/uv@sha256:a12ede1e6dc90d3b3e600d0901731e71f0ab0f4d72683ea097b76c19c43cc8df AS uv
FROM docker.io/library/python@sha256:48d884813cf44e927cf64c5529dd630dd3b18338c6dc727991eef9b71e934a20 AS build
COPY --from=uv /uv /usr/local/bin/uv
COPY requirements.lock /tmp/requirements.lock
ENV UV_CONCURRENT_DOWNLOADS=4 UV_CONCURRENT_INSTALLS=1
RUN uv venv --python /usr/local/bin/python3 /venv && uv pip sync --python /venv/bin/python --require-hashes --no-cache /tmp/requirements.lock
FROM docker.io/library/python@sha256:48d884813cf44e927cf64c5529dd630dd3b18338c6dc727991eef9b71e934a20
RUN apt-get update && apt-get install -y --only-upgrade --no-install-recommends zlib1g=1:1.3.dfsg+really1.3.1-1+deb13u1 && apt-get clean && rm -rf /var/lib/apt/lists/*
COPY --from=build /venv /venv
ENV PATH=/venv/bin:$PATH HOME=/tmp TMPDIR=/tmp PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER 10001:10001
