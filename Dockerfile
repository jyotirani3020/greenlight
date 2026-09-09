FROM python:3.12-slim

WORKDIR /app

# Install baseline tracking assets
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Install specific API delivery dependencies
RUN pip install --no-cache-dir google-adk plotly kaleido uvicorn fastapi pydantic mcp mcp-clickhouse

COPY . /app

EXPOSE 8080

# 🌟 DIRECT CLOUD RUN RUNTIME SPECIFICATION:
# Bypasses local 'adk web' dependency commands by serving via a standard Uvicorn worker process
CMD ["uvicorn", "greenlight_agent.agent:app", "--host", "0.0.0.0", "--port", "8080"]
