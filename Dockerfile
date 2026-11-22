# Trakt MCP server - Streamable HTTP transport (legacy HTTP+SSE kept on /sse)
# Endpoints on :8080: /mcp (Streamable HTTP), /sse (deprecated), /healthz

FROM python:3.12-slim

ARG VERSION=dev
ARG REPO_URL=https://github.com/wwiens/trakt_mcpserver
LABEL org.opencontainers.image.version=${VERSION}
LABEL org.opencontainers.image.source=${REPO_URL}
LABEL org.opencontainers.image.title="trakt-mcp"
LABEL org.opencontainers.image.description="MCP server for Trakt.tv"
LABEL org.opencontainers.image.licenses="MIT"

# Create a non-root user and group
RUN groupadd -g 1000 appuser && \
    useradd -u 1000 -g appuser -m appuser

WORKDIR /app

# Layer 1 - deps from pyproject.toml only (cache key is pyproject.toml)
COPY pyproject.toml ./
RUN python -c "import tomllib; \
print('\n'.join(tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']))" \
      > /tmp/requirements.txt \
    && pip install --no-cache-dir -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

# Layer 2 - source + project metadata install (deps already satisfied)
COPY . .
RUN pip install --no-cache-dir --no-deps .

# Create data directory for auth token persistence
RUN mkdir -p /data && chown -R appuser:appuser /data /app

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

ENTRYPOINT ["python", "server.py"]
