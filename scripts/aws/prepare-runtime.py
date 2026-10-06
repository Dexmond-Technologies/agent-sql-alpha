"""Verify CUDA training tools and download a pinned Qwen checkpoint."""

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODEL = "Qwen/Qwen3-Coder-30B-A3B-Instruct"


def download(root=ROOT):
    from huggingface_hub import HfApi, snapshot_download
    state = root / ".aws-setup"
    state.mkdir(parents=True, exist_ok=True)
    pin = state / "huggingface-model.json"
    if pin.exists():
        metadata = json.loads(pin.read_text())
        if metadata.get("model") != MODEL:
            raise ValueError("Existing checkpoint pin refers to another model; preserved.")
        revision = metadata["revision"]
    else:
        revision = HfApi().model_info(MODEL).sha
        pin.write_text(json.dumps({"model": MODEL, "revision": revision}, indent=2) + "\n")
    snapshot_download(repo_id=MODEL, revision=revision,
                      local_dir=root / "models/qwen3-coder-30b")
    print(f"Downloaded training checkpoint {MODEL} at {revision}")


def verify():
    import torch
    from transformers import AutoConfig, AutoTokenizer
    from peft import LoraConfig
    from trl import SFTTrainer
    import accelerate
    import bitsandbytes as bnb
    import datasets
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is unavailable in PyTorch. Check the installed NVIDIA driver.")
    device = torch.device("cuda:0")
    matrix = torch.ones((8, 8), device=device, dtype=torch.float16)
    assert (matrix @ matrix).sum().item() == 512
    layer = bnb.nn.Linear4bit(8, 8, bias=False, quant_type="nf4").to(device)
    layer(matrix)
    torch.cuda.synchronize()
    print(f"CUDA and 4-bit kernels verified on {torch.cuda.get_device_name(0)}; torch={torch.__version__}")
    print("Transformers, PEFT, TRL, Accelerate and Datasets imported successfully.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["download", "verify"])
    args = parser.parse_args()
    if args.action == "download":
        download()
    else:
        verify()
