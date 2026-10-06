#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${1:-} == --help || ${1:-} == --plan ]]; then
  cat <<'EOF'
Usage: bash scripts/aws/setup-training-host.sh [--tools-only | --worker]
Default: full installation, Codex login, Qwen and reference downloads.
--tools-only: document tools and tests without GPU/model downloads.
--worker: all stages inside the installer's persistent tmux session.
Legacy --install-codex, --install-ollama and --download-references select full setup.
EOF
  exit 0
fi
repo_directory="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
mode=all
for argument in "$@"; do
  case "$argument" in
    --worker) mode=worker ;;
    --tools-only) mode=tools ;;
    --install-codex|--install-ollama|--download-references) : ;;
    *) echo "Unknown option: $argument" >&2; exit 2 ;;
  esac
done
if [[ "$mode" == all ]]; then
  export AGENTSQL_INSTALL_DIR="$repo_directory"
  exec bash "$repo_directory/scripts/aws/install.sh"
fi
if [[ $EUID -eq 0 ]]; then
  echo 'Run as your normal Ubuntu SSH user with sudo access.' >&2
  exit 1
fi
source /etc/os-release
if [[ "$ID" != ubuntu || "$VERSION_ID" != 24.04 || $(uname -m) != x86_64 ]]; then
  echo 'This installer supports Ubuntu 24.04 x86_64.' >&2
  exit 1
fi
cd "$repo_directory"
mkdir -p .aws-setup
chmod 700 .aws-setup
state_directory="$repo_directory/.aws-setup"
exec 9>"$state_directory/worker.lock"
if ! flock -n 9; then
  echo 'Another setup worker is already running.' >&2
  exit 1
fi
exec > >(tee -a "$state_directory/install.log") 2>&1
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$state_directory/node/bin:$PATH"
trap 'printf "failed\n" > "$state_directory/status"; echo "Setup failed in ${current_step:-startup}; re-run the installer to continue."' ERR
printf 'running\n' > "$state_directory/status"

run_step() {
  local name="$1"
  shift
  current_step="$name"
  if [[ -f "$state_directory/$name.done" ]]; then
    echo "Already installed: $name"
    return
  fi
  echo "Installing: $name"
  "$@"
  touch "$state_directory/$name.done"
}

base_tools() {
  sudo -n apt-get update
  sudo -n env DEBIAN_FRONTEND=noninteractive apt-get install -y \
    git curl ca-certificates python3 python3-venv python3-pip poppler-utils tmux \
    pciutils xz-utils build-essential cmake pkg-config libssl-dev \
    libgtk-3-dev libwebkit2gtk-4.1-dev libayatana-appindicator3-dev librsvg2-dev patchelf
  python3 -m venv .venv-tools
  .venv-tools/bin/python -m pip install --upgrade pip
  .venv-tools/bin/python -m pip install -r training/requirements.txt
}

check_storage() {
  local available_kib
  available_kib=$(df -Pk "$repo_directory" | awk 'END {print $4}')
  if (( available_kib < 140 * 1024 * 1024 )); then
    echo 'At least 140 GiB free space is required for both model formats, libraries, and training tools.' >&2
    return 1
  fi
}

gpu_driver() {
  if command -v nvidia-smi >/dev/null && nvidia-smi; then
    return
  fi
  if ! lspci -nn | grep -qi nvidia; then
    echo 'No NVIDIA GPU found. Use an NVIDIA GPU EC2 instance.' >&2
    return 1
  fi
  if [[ -f "$state_directory/driver-reboot-requested" ]]; then
    echo 'The NVIDIA driver still fails after restart; check the kernel/driver or use an NVIDIA Deep Learning AMI.' >&2
    return 1
  fi
  sudo -n env DEBIAN_FRONTEND=noninteractive apt-get install -y ubuntu-drivers-common
  sudo -n ubuntu-drivers install --gpgpu
  sudo -n modprobe nvidia || true
  if command -v nvidia-smi >/dev/null && nvidia-smi; then
    return
  fi
  local login_user
  login_user=$(id -un)
  if [[ "$repo_directory" =~ [[:space:]%] || "$HOME" =~ [[:space:]%] ]]; then
    echo 'Automatic resume requires paths without spaces or percent signs.' >&2
    return 1
  fi
  sudo -n tee /etc/systemd/system/agentsql-install-resume.service >/dev/null <<EOF
[Unit]
Description=Resume agentSQL AWS installation after NVIDIA driver reboot
Wants=network-online.target
After=network-online.target
[Service]
Type=oneshot
User=$login_user
WorkingDirectory=$repo_directory
Environment=PATH=/usr/local/bin:/usr/bin:/bin
ExecStart=/usr/bin/tmux new-session -d -s agentsql-install -c $repo_directory /bin/bash $repo_directory/scripts/aws/setup-training-host.sh --worker
RemainAfterExit=yes
[Install]
WantedBy=multi-user.target
EOF
  sudo -n systemctl daemon-reload
  sudo -n systemctl enable agentsql-install-resume.service
  touch "$state_directory/driver-reboot-requested"
  printf 'rebooting\n' > "$state_directory/status"
  echo 'NVIDIA driver installed. Rebooting in one minute; setup resumes automatically after restart.'
  sudo -n shutdown -r +1 'Continue agentSQL GPU setup after NVIDIA driver installation'
  exit 0
}

developer_tools() {
  local temporary archive
  temporary=$(mktemp -d)
  curl -fsSL https://nodejs.org/dist/latest-v24.x/SHASUMS256.txt -o "$temporary/SHASUMS256.txt"
  archive=$(awk '$2 ~ /^node-v24\.[0-9]+\.[0-9]+-linux-x64\.tar\.xz$/ {print $2}' "$temporary/SHASUMS256.txt")
  [[ -n "$archive" && "$archive" != *$'\n'* ]]
  curl -fL --retry 3 "https://nodejs.org/dist/latest-v24.x/$archive" -o "$temporary/$archive"
  (cd "$temporary"; awk -v target="$archive" '$2 == target' SHASUMS256.txt | sha256sum -c -)
  mkdir -p "$state_directory/node"
  tar -xJf "$temporary/$archive" --strip-components=1 -C "$state_directory/node"
  rm -rf -- "$temporary"
  if ! command -v cargo >/dev/null; then
    curl -fsSL https://sh.rustup.rs | sh -s -- -y --profile minimal
  fi
  npm ci
  npm run build
  node --version
  cargo --version
}

training_environment() {
  python3 -m venv .venv-training
  .venv-training/bin/python -m pip install --upgrade pip
  .venv-training/bin/python -m pip install torch==2.10.0 --index-url https://download.pytorch.org/whl/cu128
  .venv-training/bin/python -m pip install -r training/requirements-training.txt
  .venv-training/bin/python -m pip check
  .venv-training/bin/python scripts/aws/prepare-runtime.py verify
  .venv-training/bin/python -m pip freeze > "$state_directory/training-environment.lock"
}

ollama_model() {
  if ! command -v ollama >/dev/null; then
    curl -fsSL https://ollama.com/install.sh | sh
  fi
  sudo -n mkdir -p /etc/systemd/system/ollama.service.d
  printf '[Service]\nEnvironment="OLLAMA_HOST=127.0.0.1:11434"\n' | \
    sudo -n tee /etc/systemd/system/ollama.service.d/agentsql.conf >/dev/null
  sudo -n systemctl daemon-reload
  sudo -n systemctl enable --now ollama
  sudo -n systemctl restart ollama
  local ready=false
  for attempt in {1..30}; do
    if curl -fsS http://127.0.0.1:11434/api/tags >/dev/null; then
      ready=true
      break
    fi
    sleep 2
  done
  $ready
  ollama pull qwen3-coder:30b
  ollama show qwen3-coder:30b --modelfile > "$state_directory/ollama-model.txt"
}

reference_documents() {
  local result=0
  PYTHONPATH=training .venv-tools/bin/python -m training_pipeline.bootstrap || result=$?
  if [[ "$result" == 3 ]]; then
    touch "$state_directory/reference-gaps"
    echo 'Some publisher links are unavailable. Setup continues; Codex can inspect the recorded gaps.'
  elif [[ "$result" != 0 ]]; then
    return "$result"
  else
    rm -f "$state_directory/reference-gaps"
  fi
}

verify_tools() {
  PYTHONPATH=training .venv-tools/bin/python -m unittest discover -s training/tests -v
  PYTHONPATH=training .venv-tools/bin/python -m unittest discover -s training/training_pipeline -p 'test_*.py' -v
  if [[ "$mode" == worker ]]; then
    .venv-training/bin/python scripts/aws/prepare-runtime.py verify
    codex --version
    ollama list
  fi
}

run_step base-tools base_tools
if [[ "$mode" == tools ]]; then
  verify_tools
  printf 'tools-only\n' > "$state_directory/status"
  exit 0
fi
run_step storage-check check_storage
run_step gpu-driver gpu_driver
run_step developer-tools developer_tools
run_step training-environment training_environment
run_step ollama-model ollama_model
run_step huggingface-model .venv-training/bin/python scripts/aws/prepare-runtime.py download
run_step reference-documents reference_documents
verify_tools
cat > "$state_directory/summary.txt" <<EOF
agentSQL AWS installation completed.
Repository: $repo_directory
Codex and Ollama installed; Ollama listens on localhost.
Inference model: qwen3-coder:30b
Training weights: $repo_directory/models/qwen3-coder-30b
Training environment: $repo_directory/.venv-training
Reference report: $repo_directory/training/TRAINING/bootstrap-unavailable.json
Training package versions: $state_directory/training-environment.lock
Model revisions: $state_directory/huggingface-model.json and ollama-model.txt
IBM dataset preparation and a resumable training job remain in AWSrun.md.
Stop Ollama before GPU training if it has loaded a model.
EOF
if [[ -f "$state_directory/reference-gaps" ]]; then
  printf 'complete-with-reference-gaps\n' > "$state_directory/status"
else
  printf 'complete\n' > "$state_directory/status"
fi
if [[ -f /etc/systemd/system/agentsql-install-resume.service ]]; then
  sudo -n systemctl disable agentsql-install-resume.service
fi
cat "$state_directory/summary.txt"
