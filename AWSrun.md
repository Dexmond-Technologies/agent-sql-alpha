# SQL Alpha on AWS: Qwen training next steps

## Purpose

Run SQL Alpha's document preparation and Qwen training workflow on a rented AWS GPU machine. This is a training experiment using IBM documentation, not a production application deployment.

The immediate priorities are IBM document ingestion, clean training datasets, and a resumable training script. Complete CPU-based preparation and validation before starting the paid GPU training run.

## Set up a fresh AWS checkout

On Ubuntu 24.04, connect as your normal SSH user with sudo access, verify the GPU with `nvidia-smi`, and run:

```bash
git clone https://github.com/Dexmond-Technologies/agent-sql-alpha.git
cd agent-sql-alpha
bash scripts/aws/setup-training-host.sh --install-codex --install-ollama --download-references
export PATH="$HOME/.local/bin:$PATH"
codex login --device-auth
ollama pull qwen3-coder:30b
codex
```

The setup script installs document-processing tools and optionally Codex/Ollama, runs tests, and restores reference documents from their publisher locations and recorded Git revisions. The public repository includes training code and source metadata; the approximately 3.4 GB downloaded library is retrieved separately by the script. Existing local collections remain intact. Retired URLs and changed web snapshots require review; see [training setup](training/README.md) for recovery details. If the download step reports unavailable sources, resolve or explicitly scope those gaps before training.

Model training is not started by this setup. A separate GPU trainer and Hugging Face training checkpoint are still required. Use Ollama for baseline inference, and stop it before training to release GPU memory. Node/Rust desktop build dependencies are not required for this console-based document workflow.

## Current state

- IBM document downloaders and collection manifests exist under `training/`.
- `training/training_pipeline/sources.json` lists general SQL sources but does not include the downloaded IBM collections. The current preparation run therefore does not export those IBM documents into the training dataset.
- `training/training_pipeline/prepare.py` exports raw text chunks and a search index. It does not create instruction/response examples or train a model.
- Chunks currently use a 3,000-character limit rather than the target Qwen tokenizer.
- PDF extraction adds a review flag, and flagged documents are excluded from eligible training exports. An explicit review-resolution workflow is needed before reviewed PDFs can become eligible.
- `deployment/qwen/compose.yaml` runs vLLM inference with an FP8 checkpoint. It is not a training environment.
- All seven existing preparation tests passed during the review. They do not establish IBM extraction quality, training compatibility, or model improvement.

## Ordered next steps

### 1. Connect the IBM collections to preparation

- Extend the source configuration and preparation code to consume IBM collection manifests, including `training/TRAINING/ibm-i-as400/` and the relevant companion collections.
- Preserve original URLs, titles, content hashes, source notices, platform, and release metadata.
- Select sources approved for the intended training use; collection download status alone is not a training-eligibility decision.
- Report documents included, excluded, failed, or awaiting review, with reasons. Fail the IBM training export if it contains no eligible IBM content.

### 2. Clean and validate document extraction

- Add HTML content extraction that removes scripts, navigation, and page boilerplate.
- Remove repeated PDF headers, footers, and page numbers while preserving meaningful text.
- Preserve SQL, RPG, COBOL, and CL examples, indentation, tables, and section headings.
- Identify image-only pages and extraction failures; use OCR where necessary and review its output.
- Add a recorded review process for resolving extraction flags without disabling the quality checks globally.
- Manually inspect representative manuals and extracted examples before exporting the full dataset.

### 3. Preserve platform and release distinctions

- Keep IBM i and z/OS material explicitly separate.
- Label Db2 for i, RPG, ILE COBOL, Enterprise COBOL for z/OS, and CL accurately.
- Preserve publication releases and relevant prerequisites, including TR/PTF information when available.
- Do not infer publication release solely from the download directory or catalog release; shared manuals can appear under multiple catalogs.
- Remove repeated content across editions and keep related editions together when splitting data.

### 4. Define the training objective and dataset format

- Decide whether the experiment uses continued language-model training on document text, supervised fine-tuning on instruction examples, or separate stages for both.
- For assistant behavior, create reviewed question/answer, explanation, troubleshooting, and schema/SQL examples grounded in the source documents.
- Retain source and release references for each example so answers can be checked.
- Include examples where the correct response asks for missing release/schema information or acknowledges unsupported information.
- Validate generated examples before training; do not treat synthetic answers as verified facts.

TRL supports language-modeling and conversational datasets: [SFT Trainer documentation](https://huggingface.co/docs/trl/main/en/sft_trainer).

### 5. Prepare data with the selected Qwen tokenizer

- Pin the exact model and tokenizer revisions.
- Replace character-based training chunking with token-aware preparation.
- Preserve complete examples and meaningful section boundaries where possible.
- Apply the model's chat template to instruction data and verify special tokens, end-of-sequence handling, and the intended loss mask.
- Record token counts, sequence-length distribution, truncation, and packing behavior.

### 6. Add a reproducible, resumable training job

- Create a dedicated training entry point and a pinned training environment; keep inference serving configuration separate.
- Record the model revision, dataset hashes, seed, optimizer, learning rate, sequence length, batch size, gradient accumulation, and adapter settings.
- Evaluate LoRA/QLoRA first to reduce training memory requirements. Verify support for the exact Qwen architecture and chosen libraries.
- Choose a supported training checkpoint and quantization method; do not assume the existing FP8 inference setup can be reused for training.
- Save adapter/model artifacts and resumable checkpoints, including optimizer, scheduler, and random-state information.
- Test interruption and resume before launching a long run.

Reference: [Hugging Face PEFT quantization guidance](https://huggingface.co/docs/peft/main/developer_guides/quantization).

### 7. Establish an IBM evaluation baseline

- Build a held-out evaluation set before training. Keep document families, near duplicates, and related editions in the same split to reduce leakage.
- Evaluate release-specific answers, SQL correctness, code examples, and handling of unsupported questions.
- Validate SQL/code against the appropriate engine or compiler where available; distinguish reviewed answers from execution-verified answers.
- Compare the original model and trained model on the same examples and retain general SQL/coding checks to detect regressions.
- Record improvements and regressions. Validation loss alone does not establish practical usefulness.

### 8. Run the AWS experiment efficiently

- Complete document extraction, review, dataset validation, and tokenization before starting the GPU training run.
- Run a short training benchmark to measure peak GPU memory and throughput before selecting capacity for the full run. Inference sizing is not a training capacity guarantee.
- Store datasets, checkpoints, and run metadata on persistent storage. Back up artifacts to S3 or another durable destination and verify recovery.
- Monitor GPU memory, utilization, training/validation loss, throughput, and disk capacity.
- Keep administration and notebook interfaces restricted, and keep credentials out of datasets and logs.
- Use interruption-prone capacity only after checkpoint/resume works reliably.
- Stop the GPU instance when the job is finished and account for storage that continues to incur charges.

## Completion criteria for the first AWS run

- [ ] IBM documents are included in the prepared dataset, with eligibility and extraction decisions recorded.
- [ ] Platform/release metadata is preserved, and related documents do not cross dataset splits.
- [ ] The dataset format, tokenizer, model revision, and training configuration are pinned.
- [ ] A short training job completes on the selected AWS hardware.
- [ ] Interrupted training resumes successfully from a saved checkpoint.
- [ ] Baseline and trained-model evaluation results are saved and compared.
- [ ] Training artifacts and run metadata are retained outside the rented instance.
- [ ] GPU compute is stopped when no longer needed.
