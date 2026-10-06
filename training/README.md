# Training tools and reference-library setup

The repository contains the preparation code, tests, pinned document-processing
dependencies, and reference manifests needed to set up the AWS training workspace.
See [AWSrun.md](../AWSrun.md) for the remaining IBM ingestion and Qwen training work.

## Fresh Ubuntu 24.04 AWS checkout

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Dexmond-Technologies/agent-sql-alpha/main/scripts/aws/install.sh)
```

Use a normal SSH user with passwordless sudo on Ubuntu 24.04 x86_64 and at least
140 GiB free disk space. The script clones the repo, installs developer/document
tools, Codex, Ollama, Qwen inference and training weights, and CUDA training
libraries. It installs a missing NVIDIA driver and resumes after a required reboot.
Complete the displayed Codex device login in your browser; Codex opens when setup
finishes. Saved stages and tmux keep long downloads recoverable. Full details are
in [the AWS installer guide](../scripts/aws/README.md).

For a small document-only environment in an existing checkout, use
`bash scripts/aws/setup-training-host.sh --tools-only`. Training jobs are not
started automatically: the IBM dataset and resumable trainer remain planned work.

## Reference storage

The local reference library is approximately 3.4 GB and includes publisher PDFs,
HTML snapshots, nested upstream repositories, archives, and derived datasets.
Those downloaded bytes are not republished in this public application repository.
The source catalog, six collection manifests, indexes, and recorded general Git
revisions are committed under [reference-snapshots](reference-snapshots/CATALOG.md).
Publisher/repository notices and review status remain recorded in the manifests.

The bootstrap copies missing metadata into `training/TRAINING/`, creates pinned
general SQL and IBM OSS checkouts, and runs the existing publisher downloaders.
It never resets existing repositories or overwrites resumed manifests. Community
and engineering Git snapshots also use the recorded commits. Web pages can change
at their source; the downloaders retain new hashes and outcomes rather than claim
the original bytes are always available. Microsoft reference pages are fetched
from their recorded public source locations and are not revision-pinned.

Unavailable links are recorded in `training/TRAINING/bootstrap-unavailable.json`.
The standalone reference bootstrap exits with code 3 if sources are unavailable.
The full installer records that partial outcome and continues installing tools.
The original snapshot already records unavailable IBM links;
rerunning downloads may not recover retired publisher resources. Review each
collection's manifest and the integrity report before selecting training data.

Downloads are reference data only. No downloaded examples, installers, agent
instructions, or package/build scripts are executed by the bootstrap. References
are not automatically eligible for model training.

## Run preparation tools separately

```bash
python3 -m venv .venv-tools
.venv-tools/bin/python -m pip install -r training/requirements.txt
PYTHONPATH=training .venv-tools/bin/python -m training_pipeline.bootstrap
PYTHONPATH=training .venv-tools/bin/python -m training_pipeline.prepare
PYTHONPATH=training .venv-tools/bin/python -m training_pipeline.search 'window functions'
```

Preparation currently covers the configured general SQL sources. Integrating IBM
documents, resolving extraction review flags, generating instruction examples,
and adding resumable Qwen training remain the next steps in `AWSrun.md`. Ollama
provides inference and baseline testing; it does not perform fine-tuning.

## Verification

```bash
PYTHONPATH=training python3 -m unittest discover -s training/tests -v
PYTHONPATH=training python3 -m unittest discover -s training/training_pipeline -p 'test_*.py' -v
python3 training/training_pipeline/verify_ibm_collections.py
```

The last command requires restored collections and Poppler's `pdfinfo`. Integrity
checks are separate from extraction fidelity and model-quality evaluation.
