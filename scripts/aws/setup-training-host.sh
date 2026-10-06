#!/usr/bin/env bash
# Run from a fresh checkout on an Ubuntu 24.04 NVIDIA GPU instance.
set -euo pipefail

download_references=false
install_codex=false
install_ollama=false
for argument in "$@"; do
  case "$argument" in
    --download-references) download_references=true ;;
    --install-codex) install_codex=true ;;
    --install-ollama) install_ollama=true ;;
    --help)
      echo 'Usage: bash scripts/aws/setup-training-host.sh [--download-references] [--install-codex] [--install-ollama]'
      exit 0 ;;
    *) echo "Unknown option: $argument" >&2; exit 2 ;;
  esac
done

if [[ $EUID -eq 0 ]]; then
  echo 'Run as your normal SSH user with sudo access, rather than as root.' >&2
  exit 1
fi
source /etc/os-release
if [[ "$ID" != ubuntu || "$VERSION_ID" != 24.04 ]]; then
  echo 'This setup script targets Ubuntu 24.04; adapt package installation for your OS.' >&2
  exit 1
fi

repo_directory="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_directory"
sudo apt-get update
sudo apt-get install -y git curl ca-certificates python3 python3-venv python3-pip poppler-utils tmux

python3 -m venv .venv-tools
.venv-tools/bin/python -m pip install --upgrade pip
.venv-tools/bin/python -m pip install -r training/requirements.txt
PYTHONPATH=training .venv-tools/bin/python -m unittest discover -s training/tests -v
PYTHONPATH=training .venv-tools/bin/python -m unittest discover -s training/training_pipeline -p 'test_*.py' -v

if $install_codex; then
  curl -fsSL https://chatgpt.com/codex/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
  codex --version
  echo 'Next, run: export PATH="$HOME/.local/bin:$PATH"; codex login --device-auth'
fi

if $install_ollama; then
  if ! command -v nvidia-smi >/dev/null || ! nvidia-smi; then
    echo 'Configure the NVIDIA driver before installing GPU inference tools.' >&2
    exit 1
  fi
  curl -fsSL https://ollama.com/install.sh | sh
  sudo systemctl enable --now ollama
  echo 'Next, run: ollama pull qwen3-coder:30b'
fi

if $download_references; then
  PYTHONPATH=training .venv-tools/bin/python -m training_pipeline.bootstrap
fi

echo 'Host setup finished. Read AWSrun.md before preparing the IBM dataset and starting training.'
