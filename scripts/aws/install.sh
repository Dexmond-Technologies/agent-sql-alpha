#!/usr/bin/env bash
# Standalone entry point: downloadable before Git or the repository is installed.
set -euo pipefail

if [[ ${1:-} == --help || ${1:-} == --plan ]]; then
  cat <<'EOF'
agentSQL AWS installer (Ubuntu 24.04 x86_64, NVIDIA GPU)
Run without flags to install everything, authenticate Codex, and open it when done.
Downloads the repo, developer tools, CUDA PyTorch/LoRA tools, Ollama Qwen,
Hugging Face Qwen weights, and reference documents. Progress survives disconnects.
If an NVIDIA driver reboot is needed, setup resumes automatically after reboot.
Options: --non-interactive (skip browser login and opening Codex), --help, --plan
Optional environment: AGENTSQL_INSTALL_DIR (default: ~/agent-sql-alpha)
Re-run the same command to reconnect or continue an interrupted run.
EOF
  exit 0
fi
non_interactive=false
if [[ ${1:-} == --non-interactive && $# == 1 ]]; then
  non_interactive=true
elif [[ $# != 0 ]]; then
  echo 'Unknown arguments. Use --help.' >&2
  exit 2
fi
if [[ $EUID -eq 0 ]]; then
  echo 'Connect as the normal Ubuntu SSH user and run this script with sudo access.' >&2
  exit 1
fi
source /etc/os-release
if [[ "$ID" != ubuntu || "$VERSION_ID" != 24.04 || $(uname -m) != x86_64 ]]; then
  echo 'This installer supports Ubuntu 24.04 x86_64 NVIDIA GPU instances.' >&2
  exit 1
fi
if ! $non_interactive && [[ ! -t 0 || ! -t 1 ]]; then
  echo 'Launch from an interactive SSH terminal, or use --non-interactive.' >&2
  exit 1
fi
if ! sudo -n -k true; then
  echo 'The AWS worker requires passwordless sudo (the default Ubuntu EC2 configuration).' >&2
  exit 1
fi
sudo apt-get update
sudo apt-get install -y git curl ca-certificates tmux
repo_directory="${AGENTSQL_INSTALL_DIR:-$HOME/agent-sql-alpha}"
if [[ "$repo_directory" != /* || "$repo_directory" =~ [[:space:]%] ]]; then
  echo 'AGENTSQL_INSTALL_DIR must be an absolute path without spaces or percent signs.' >&2
  exit 1
fi
if [[ ! -e "$repo_directory" ]]; then
  git clone --branch main https://github.com/Dexmond-Technologies/agent-sql-alpha.git "$repo_directory"
elif [[ ! -d "$repo_directory/.git" ]] || [[ $(git -C "$repo_directory" remote get-url origin) != https://github.com/Dexmond-Technologies/agent-sql-alpha.git ]]; then
  echo 'The installation directory contains another project; existing files were preserved.' >&2
  exit 1
fi
cd "$repo_directory"
if ! tmux has-session -t agentsql-install 2>/dev/null && \
   [[ -z $(git status --porcelain) && $(git branch --show-current) == main ]]; then
  git fetch origin main
  git merge --ff-only origin/main
fi
if [[ ! -f scripts/aws/setup-training-host.sh ]]; then
  echo 'This checkout does not contain the AWS worker. Update it before continuing.' >&2
  exit 1
fi
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$repo_directory/.aws-setup/node/bin:$PATH"
if ! command -v codex >/dev/null; then
  curl -fsSL https://chatgpt.com/codex/install.sh | CODEX_NON_INTERACTIVE=1 sh
fi
codex --version
if ! $non_interactive && ! codex login status >/dev/null 2>&1; then
  echo 'Complete Codex login using the displayed link and code in your browser.'
  codex login --device-auth
fi
session=agentsql-install
if ! tmux has-session -t "$session" 2>/dev/null; then
  printf -v worker_command 'exec bash %q --worker' "$repo_directory/scripts/aws/setup-training-host.sh"
  tmux new-session -d -s "$session" -c "$repo_directory" "$worker_command"
fi
if $non_interactive; then
  echo "Setup runs in tmux session $session. Log: $repo_directory/.aws-setup/install.log"
  exit 0
fi
tmux attach-session -t "$session" || true
status=$(cat .aws-setup/status 2>/dev/null || true)
case "$status" in
  complete|complete-with-reference-gaps)
    export PATH="$repo_directory/.venv-training/bin:$PATH"
    export VIRTUAL_ENV="$repo_directory/.venv-training"
    exec codex 'Read AWSrun.md and .aws-setup/summary.txt. Inspect the installed tools and reference download gaps, then help complete the IBM dataset and resumable Qwen training workflow.' ;;
  rebooting)
    echo 'The NVIDIA driver needs a reboot. Setup will resume automatically after restart.'
    echo 'Reconnect over SSH and run this same command to view progress and open Codex.' ;;
  *)
    echo "Setup is $status. Progress remains saved in $repo_directory/.aws-setup/."
    echo 'Re-run this same command to reconnect or retry.'
    [[ "$status" != failed ]] ;;
esac
