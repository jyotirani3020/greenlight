FROM python:3.12-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# uv/uvx runs mcp-clickhouse in its own isolated env at runtime (its
# `mcp`/`fastmcp` deps conflict with the version google-adk's McpToolset needs)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# Python dependencies (mcp pinned to the version google-adk's McpToolset needs;
# mcp-clickhouse itself is NOT installed here, it's run via uvx below)
RUN pip install --no-cache-dir \
    google-adk \
    plotly \
    kaleido \
    uvicorn \
    fastapi \
    pydantic \
    "mcp==1.30.0"

# Copy application
COPY . /app

# Cloud Run listens on this port
EXPOSE 8080

# Start ADK's HTTP server with the dev chat UI (unauthenticated — fine for a
# short public demo window only, per adk web's own security warning)
CMD ["adk", "web", ".", "--host", "0.0.0.0", "--port", "8080"]