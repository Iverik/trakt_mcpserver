# Trakt MCP server - Streamable HTTP transport (legacy HTTP+SSE kept on /sse)
# Endpoints on :8080: /mcp (Streamable HTTP), /sse (deprecated), /healthz

# Stage 1: resolve and install locked dependencies with uv.
FROM python:3.15-slim AS build

COPY --from=ghcr.io/astral-sh/uv:0.13.9 /uv /uvx /bin/

WORKDIR /app
ENV UV_NO_DEV=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv

# Layer 1: dependencies only. Source-only changes do not invalidate it, and a
# stale uv.lock fails the build instead of silently re-resolving.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-editable

# Layer 2: the project itself.
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-editable

# Stage 2: runtime with the virtualenv only (no uv, no build tooling).
FROM python:3.15-slim

ARG VERSION=dev
ARG REPO_URL=https://github.com/wwiens/trakt_mcpserver
LABEL org.opencontainers.image.version=${VERSION}
LABEL org.opencontainers.image.source=${REPO_URL}
LABEL org.opencontainers.image.title="trakt-mcp"
LABEL org.opencontainers.image.description="MCP server for Trakt.tv"
LABEL org.opencontainers.image.licenses="MIT"

# Non-root user, and a data directory it owns for the auth token
RUN groupadd -g 1000 appuser \
    && useradd -u 1000 -g appuser -m appuser \
    && mkdir -p /data \
    && chown appuser:appuser /data

COPY --from=build /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

# Environment variables (pass at runtime via -e or --env-file)
ENV TRAKT_CLIENT_ID=""
# Optional: Trakt deprecated client_secret for user sign-in
ENV TRAKT_CLIENT_SECRET=""
ENV TRAKT_AUTH_TOKEN_PATH=/data/auth_token.json
# Serve Streamable HTTP on every interface. Stateless: no session survives a
# restart, so clients never need to re-initialise after one.
ENV TRAKT_MCP_TRANSPORT=http
ENV TRAKT_MCP_HOST=0.0.0.0
ENV TRAKT_MCP_PORT=8080
ENV TRAKT_MCP_STATELESS=true
# Browser Origins to accept and Host headers to accept (see README). Unset: any
# request carrying an Origin header is rejected and the Host is not checked.
# ENV TRAKT_MCP_ALLOWED_ORIGINS=https://claude.ai
# ENV TRAKT_MCP_ALLOWED_HOSTS=trakt:8080

EXPOSE 8080

# Declare volume for auth token persistence across container restarts
VOLUME /data

USER appuser

# /healthz needs no MCP session and does not call Trakt
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request as u; u.urlopen('http://127.0.0.1:8080/healthz', timeout=4)"]

ENTRYPOINT ["trakt-mcp"]
