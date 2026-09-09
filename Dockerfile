FROM python:3.12-slim

WORKDIR /app

# Install standard Linux package tracking assets needed for graphic building tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Pre-install your exact execution frameworks
RUN pip install --no-cache-dir google-adk plotly kaleido uvicorn fastapi pydantic mcp

COPY . /app

EXPOSE 8080

# Expose using the standard ADK run wrapper target hooks
CMD ["adk", "run", "greenlight_agent", "--host", "0.0.0.0", "--port", "8080"]
