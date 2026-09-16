FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    ECHOMEMORY_DB=/app/data/echomemory.sqlite3 \
    ECHOMEMORY_MODELS_DIR=/app/models \
    ECHOMEMORY_SARVAM_API_KEY=/app/data/sarvam_api_key \
    ECHOMEMORY_SARVAM_SETTINGS=/app/data/sarvam_settings.json

# llama-cpp-python may use its native build path when a matching wheel is not
# available. Keep the build toolchain in the image for reproducible installs.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential cmake libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt requirements-local-ai.txt ./
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt

COPY app ./app

RUN useradd --create-home --uid 10001 echomemory \
    && mkdir -p /app/data /app/models \
    && chown -R echomemory:echomemory /app

USER echomemory

EXPOSE 8000
VOLUME ["/app/data", "/app/models"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/status', timeout=3)"

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
