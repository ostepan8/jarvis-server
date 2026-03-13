# ── Builder stage: compile C extensions, then discard the toolchain ──
FROM python:3.13-slim-bookworm AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Runtime stage: slim image with only what Jarvis needs ──
FROM python:3.13-slim-bookworm AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    portaudio19-dev libsndfile1 libsndfile1-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local

RUN groupadd -r jarvis && useradd -r -g jarvis -m -d /home/jarvis -s /bin/bash jarvis

WORKDIR /app
COPY --chown=jarvis:jarvis jarvis/ ./jarvis/
COPY --chown=jarvis:jarvis server/ ./server/
COPY --chown=jarvis:jarvis main.py .
COPY --chown=jarvis:jarvis skills/ ./skills/

RUN mkdir -p /app/data /home/jarvis/.jarvis \
    && chown -R jarvis:jarvis /app/data /home/jarvis/.jarvis

USER jarvis
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health/ || exit 1

STOPSIGNAL SIGTERM
ENV PYTHONUNBUFFERED=1
CMD ["python", "-m", "server.main"]
