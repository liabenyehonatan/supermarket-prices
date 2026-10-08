FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

# Headless Chromium for the scrapers that need a real browser (shared path so the
# non-root user below can use it).
RUN pip install playwright && playwright install --with-deps chromium \
    && chmod -R a+rX /ms-playwright

# Run as an unprivileged user. dumps/ is created and owned up front so a named
# volume mounted there inherits that ownership.
RUN useradd --create-home --uid 10001 app \
    && mkdir -p /app/dumps \
    && chown app:app /app /app/dumps

COPY --chown=app:app . .
USER app

EXPOSE 8000

# Overridden per service in docker-compose.yml (api, worker, migrate).
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
