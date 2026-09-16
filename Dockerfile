FROM python:3.14-slim AS native-runtimes

ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
      build-essential \
      ca-certificates \
      cmake \
      curl \
      git \
      libabsl-dev \
      libsentencepiece-dev \
      ninja-build \
      pkg-config \
    && rm -rf /var/lib/apt/lists/*

# NeMo-Speech.cpp publishes a native CLI for Linux. Pinning the backend to CPU
# keeps the default image portable; NVIDIA GPU users can use the upstream CUDA
# runtime image instead of rebuilding EchoMemory's application image.
RUN curl -fsSL https://github.com/NVIDIA/NeMo-Speech.cpp/raw/main/scripts/install.sh \
    | sh -s -- --prefix /opt/nemo-speech --backend cpu --no-modify-path

# Fun-ASR-Nano's GGUF path is an upstream llama.cpp target, not a Python wheel.
RUN git clone --depth 1 https://github.com/ggml-org/llama.cpp /opt/llama.cpp \
    && cmake -S /opt/llama.cpp -B /opt/llama.cpp/build-funasr \
      -G Ninja \
      -DCMAKE_BUILD_TYPE=Release \
      -DGGML_NATIVE=OFF \
    && cmake --build /opt/llama.cpp/build-funasr --target llama-funasr-cli \
    && mkdir -p /opt/llama-funasr \
    && cp -a /opt/llama.cpp/build-funasr/bin /opt/llama-funasr/

FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    ECHOMEMORY_DB=/app/data/echomemory.sqlite3 \
    ECHOMEMORY_MODELS_DIR=/app/models \
    ECHOMEMORY_SARVAM_API_KEY=/app/data/sarvam_api_key \
    ECHOMEMORY_SARVAM_SETTINGS=/app/data/sarvam_settings.json \
    PATH=/opt/nemo-speech/bin:/opt/llama-funasr/bin:$PATH

# llama-cpp-python may use its native build path when a matching wheel is not
# available. Keep the build toolchain in the image for reproducible installs.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential cmake libabsl20240722 libgomp1 libsentencepiece0 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=native-runtimes /opt/nemo-speech /opt/nemo-speech
COPY --from=native-runtimes /opt/llama-funasr /opt/llama-funasr

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
