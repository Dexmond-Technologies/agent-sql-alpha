# One-command AWS installation

Connect to the AWS machine over SSH, then run:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Dexmond-Technologies/agent-sql-alpha/main/scripts/aws/install.sh)
```

The entry point works before Git or the repository is installed. It targets Ubuntu
24.04 x86_64 NVIDIA GPU instances, using the normal Ubuntu SSH user with
passwordless sudo. Curl and Bash must be available to fetch the entry point.
Provide at least 140 GiB free space on the installation filesystem; additional
space is needed for long training runs and checkpoints. Outbound access to
Ubuntu packages, GitHub, OpenAI, Ollama, Node/Rust, PyPI/PyTorch and Hugging Face
is required for installation.

## What happens automatically

1. Install Git and the persistent terminal tools, then clone the application into
   `~/agent-sql-alpha`. A clean existing `main` checkout is updated by fast-forward;
   local modifications and unrelated directories are preserved.
2. Install Codex and start device-code login if required. Open the displayed link
   and enter the code in your browser; account sign-in is the interactive step.
3. Start the remaining installation in a tmux session that survives SSH disconnects.
4. Install document tools, compilers, Linux desktop build libraries, Node 24,
   Rust when absent, and the app's npm dependencies. Build the frontend.
5. Check GPU access. Install a missing NVIDIA compute driver using Ubuntu's driver
   tooling. If it needs a reboot, register automatic setup resumption and schedule
   a reboot. Working drivers are retained. Reconnect after restart and run the
   same installer command to attach to progress.
6. Create `.venv-training`, install CUDA 12.8 PyTorch 2.10.0 and pinned
   Transformers/PEFT/TRL/Accelerate/bitsandbytes/Datasets dependencies. Check imports,
   CUDA matrix operations, and 4-bit kernels on the actual GPU.
7. Install Ollama, bind it to localhost, and download `qwen3-coder:30b`.
8. Download `Qwen/Qwen3-Coder-30B-A3B-Instruct` training weights into
   `models/qwen3-coder-30b`. Save the resolved model revision before transfer so
   interrupted downloads continue at the same revision.
9. Restore the reference library from its publisher sources and recorded Git
   commits, verify downloads, and run the preparation/downloader tests.
10. Save a summary and open Codex in the repository with the training environment
    on its command path, ready to assist with the next steps in `AWSrun.md`.

These stages install the workspace and tooling. They do not run the desktop UI on
a headless server or begin model fine-tuning. IBM extraction, training examples,
and a resumable training job still need implementing and validating. Ollama is for
baseline inference; the Hugging Face checkpoint and GPU trainer are for training.

## Recovery and outcomes

The installer stores progress, logs, package versions, model revisions, and a
summary under `.aws-setup/`. The training environment and downloaded artifacts
are ignored by Git. Successful stages are skipped when rerunning the same command;
failed stages are retried. Only one worker can hold the installation lock.

Unavailable document URLs produce a `complete-with-reference-gaps` outcome rather
than block installation of the remaining software. Details are in
`training/TRAINING/bootstrap-unavailable.json`. Hardware, dependency, download
infrastructure, or integrity failures produce a failed outcome with the stage
recorded in `install.log`; they are not reported as successful installations.
The original snapshot contains retired URLs, so reference review is expected.

For a noninteractive provisioning run, append `--non-interactive`. It starts the
background worker without account login or opening Codex. Use the regular command
later to sign in and attach. Use `--plan` to print the scope without installing.
Set `AGENTSQL_INSTALL_DIR` before launching to use a different absolute directory;
paths cannot contain whitespace or percent signs because of systemd resume paths.

Codex installation/authentication follows [the official CLI guide](https://learn.chatgpt.com/docs/codex/cli)
and [headless device login](https://learn.chatgpt.com/docs/auth). The GPU driver
uses [Ubuntu's compute-driver workflow](https://ubuntu.com/server/docs/how-to/graphics/install-nvidia-drivers/).
PyTorch uses [the official CUDA 12.8 wheel instructions](https://pytorch.org/get-started/previous-versions/).

## Validation limits

Installer recovery tests use fake system commands to exercise resumed stages,
failed downloads, partial references, insufficient storage, driver reboot/resume,
and prevention of reboot loops without modifying the test host. Package and
model-source checks establish availability, not GPU training performance. The
full installation must still be exercised on the receiving AWS GPU instance.
