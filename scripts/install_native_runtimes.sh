#!/usr/bin/env bash
set -euo pipefail

# Install the native executables required by the GGUF speech models.
# Everything is kept inside the checkout so EchoMemory can discover it without
# relying on a shell profile or a system-wide installation.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCAL_DIR="$ROOT_DIR/.local"
BIN_DIR="$LOCAL_DIR/bin"
NEMO_DIR="$LOCAL_DIR/nemo-speech"
LLAMA_DIR="$LOCAL_DIR/src/llama.cpp"
LLAMA_BUILD_DIR="$LLAMA_DIR/build-funasr"
FUNASR_DIR="$LOCAL_DIR/src/FunASR"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This installer is for macOS. Docker installs both runtimes in its image." >&2
  exit 1
fi

for command_name in curl git cmake ninja; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Missing '$command_name'. Install Xcode Command Line Tools and Homebrew packages:" >&2
    echo "  brew install cmake ninja git" >&2
    exit 1
  fi
done

mkdir -p "$BIN_DIR" "$LOCAL_DIR/src"

echo "Installing NVIDIA NeMo-Speech.cpp..."
curl -fsSL https://github.com/NVIDIA/NeMo-Speech.cpp/raw/main/scripts/install.sh \
  | sh -s -- --prefix "$NEMO_DIR" --backend auto --no-modify-path

if [[ ! -x "$NEMO_DIR/bin/nemo-speech" ]]; then
  echo "NeMo-Speech.cpp installed, but nemo-speech was not found at $NEMO_DIR/bin/nemo-speech." >&2
  exit 1
fi
ln -sf "$NEMO_DIR/bin/nemo-speech" "$BIN_DIR/nemo-speech"

if [[ ! -d "$LLAMA_DIR/.git" ]]; then
  echo "Downloading llama.cpp source for Fun-ASR-Nano..."
  git clone --depth 1 https://github.com/ggml-org/llama.cpp "$LLAMA_DIR"
fi

if [[ ! -d "$FUNASR_DIR/.git" ]]; then
  echo "Downloading FunASR's llama.cpp runtime examples..."
  git clone --depth 1 https://github.com/modelscope/FunASR "$FUNASR_DIR"
fi

# llama-funasr-cli is maintained by FunASR and is built as an example against
# the llama.cpp checkout; it is not a target in upstream llama.cpp by itself.
if [[ ! -f "$LLAMA_DIR/examples/funasr-cli/CMakeLists.txt" || ! -f "$LLAMA_DIR/examples/funasr-common/funasr_audio.h" ]]; then
  # Replace incomplete copies from older installer revisions. The expected
  # source is fun-asr-nano/funasr-cli itself, not its parent directory.
  rm -rf "$LLAMA_DIR/examples/funasr-cli" "$LLAMA_DIR/examples/funasr-common"
  cp -a "$FUNASR_DIR/runtime/llama.cpp/funasr-common" "$LLAMA_DIR/examples/"
  cp -a "$FUNASR_DIR/runtime/llama.cpp/fun-asr-nano/funasr-cli" "$LLAMA_DIR/examples/"
fi
if ! grep -q 'add_subdirectory(funasr-cli)' "$LLAMA_DIR/examples/CMakeLists.txt"; then
  printf '\nadd_subdirectory(funasr-cli)\n' >> "$LLAMA_DIR/examples/CMakeLists.txt"
fi

echo "Building llama-funasr-cli..."
metal_flag=OFF
if [[ "$(uname -m)" == "arm64" ]]; then
  metal_flag=ON
fi
cmake -S "$LLAMA_DIR" -B "$LLAMA_BUILD_DIR" \
  -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DGGML_NATIVE=OFF \
  -DGGML_METAL="$metal_flag"
cmake --build "$LLAMA_BUILD_DIR" --target llama-funasr-cli

if [[ ! -x "$LLAMA_BUILD_DIR/bin/llama-funasr-cli" ]]; then
  echo "llama-funasr-cli was not produced by the llama.cpp build." >&2
  exit 1
fi
ln -sf "$LLAMA_BUILD_DIR/bin/llama-funasr-cli" "$BIN_DIR/llama-funasr-cli"

echo
echo "Native speech runtimes are ready:"
"$BIN_DIR/nemo-speech" --version || true
echo "  $BIN_DIR/llama-funasr-cli"
echo
echo "EchoMemory will discover both binaries automatically."
