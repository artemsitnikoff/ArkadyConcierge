FROM python:3.11-slim

# Node.js + Claude CLI: `claude --print` is invoked as a subprocess by AIClient.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g @anthropic-ai/claude-code \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir .

COPY app ./app
COPY prompts ./prompts

# Create non-root user and give it ownership of the app + writable data dir.
# Claude CLI needs a home dir to store its config — point HOME at /home/app.
RUN useradd --create-home --shell /bin/bash --uid 1000 app \
    && mkdir -p /app/data \
    && chown -R app:app /app

USER app
ENV HOME=/home/app \
    PYTHONUNBUFFERED=1

EXPOSE 8003

# Container-level liveness probe — used by docker-compose + k8s readiness.
# `start-period` gives lifespan enough time to init Claude token + clients.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8003/api/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003"]
