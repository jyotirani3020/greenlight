FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir google-adk plotly kaleido uvicorn fastapi pydantic mcp mcp-clickhouse

COPY . /app

EXPOSE 8080

# 🌟 THE CORRECT ADK 2.8.0 RUNTIME COMMAND:
# Since your root __init__.py imports root_agent, we serve the parent context path directory explicitly!
CMD ["adk", "run", ".", "--host", "0.0.0.0", "--port", "8080"]
