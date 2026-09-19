# syntax=docker/dockerfile:1.26@sha256:ecfaec9ed6d810b56388c508f4121597bfbba70d41a6dfeee4d8cad5f295fc32
# postgen — Chainguard python, uv-managed venv, nonroot, no shell in the runtime.
# Renovate keeps builder (:latest-dev) and runtime (:latest) in lockstep so the
# venv's interpreter always matches the runtime Python.

FROM cgr.dev/chainguard/python:latest-dev@sha256:dc0368ac6a4792f563e7f523d207f6c5ed17e3d7ed16e7424ac01d47772b096b AS builder

USER root

COPY --from=ghcr.io/astral-sh/uv:0.12@sha256:10787c682e4184e4f290de1171fd4703dc63de99221f10fe1c99002ce7fa9acc /uv /uvx /usr/local/bin/

WORKDIR /app

ENV UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never

# Dependencies first (cached layer), then the project itself.
COPY pyproject.toml uv.lock README.md ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project --no-editable

COPY src ./src

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

# /data is the named volume (profile, corpus, SQLite, voice profile). It must exist
# in the image owned by nonroot or the mount inherits root; the runtime has no mkdir.
RUN mkdir -p /data && chown -R nonroot:nonroot /app /data

FROM cgr.dev/chainguard/python:latest@sha256:011e73b4e30e0fe9407a42b82a920b4fa13ebc0bf029a48b714f950df254ca20

WORKDIR /app

COPY --from=builder --chown=nonroot:nonroot /app/.venv /app/.venv
COPY --from=builder --chown=nonroot:nonroot /data /data

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    POSTGEN_DATA_DIR=/data \
    POSTGEN_HOST=0.0.0.0

VOLUME ["/data"]
EXPOSE 8790

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import os,urllib.request; p=os.environ.get('POSTGEN_PORT','8790'); urllib.request.urlopen(f'http://127.0.0.1:{p}/healthz', timeout=4)"]

# Clear the upstream ENTRYPOINT (/usr/bin/python) so PATH-resolved "python" is the venv's.
ENTRYPOINT []
CMD ["python", "-m", "postgen"]
