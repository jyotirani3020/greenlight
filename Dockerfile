FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir google-adk plotly kaleido uvicorn fastapi pydantic mcp

COPY . /app

EXPOSE 8080

# 🌟 FIXED FOR PRODUCTION CONTAINERS: 
# Execute using 'web' to initialize the asynchronous SSE network stream bindings on Cloud Run
CMD ["adk", "web", "--host", "0.0.0.0", "--port", "8080"]
