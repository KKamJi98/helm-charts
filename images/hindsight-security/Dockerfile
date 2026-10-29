FROM ghcr.io/astral-sh/uv:0.13.6@sha256:af22a52f5eafef3d78e551599d405c02df61919d18028f0cea8eda93bc9986d0 AS uv
FROM ghcr.io/vectorize-io/hindsight:1.1.0@sha256:50311d02b4d5d2b7c5242bd336edf8735df8374eaad496a92f49c83b37d2aa06

USER root
# Build-only mounts: no installer, wheel cache or requirements file in the final layer.
RUN --mount=from=uv,source=/uv,target=/uv,ro \
    --mount=type=bind,source=requirements.txt,target=/security-requirements.txt,ro \
    UV_PYTHON_DOWNLOADS=never /uv --no-config --no-cache pip install \
      --python /app/api/.venv/bin/python \
      --index-url https://pypi.org/simple \
      --only-binary :all: --require-hashes --no-deps \
      -r /security-requirements.txt \
    && /uv --no-config --no-cache pip check --python /app/api/.venv/bin/python
USER hindsight
