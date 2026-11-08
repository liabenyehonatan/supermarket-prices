# The MCP service: its own image (its dependencies cannot share an environment with the API's pinned ones).
# Build context is this folder:  docker build -t supermarket-mcp ./mcp_service
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

# The code is the package `mcp_service` (imports are mcp_service.x), so it goes in a folder of that name.
COPY . /app/mcp_service

RUN useradd --create-home --uid 10001 app
USER app

EXPOSE 8001
CMD ["uvicorn", "mcp_service.server:app", "--host", "0.0.0.0", "--port", "8001", "--proxy-headers", "--forwarded-allow-ips=*"]
