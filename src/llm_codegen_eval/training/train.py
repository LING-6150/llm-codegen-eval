"""LoRA / optional 4-bit QLoRA SFT; GPU execution is explicit."""
import argparse
import importlib.metadata
import json
from pathlib import Path
from datetime import datetime, timezone
from ..clients.openai_client import SYSTEM_PROMPT
from .data import verify


def conversational(row):
    return {"prompt": [{"role": "system", "content": SYSTEM_PROMPT},
                       {"role": "user", "content": row["prompt"]}],
            "completion": [{"role": "assistant", "content": row["completion"]}]}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--model", default="Qwen/Qwen2.5-Coder-0.5B-Instruct")
    p.add_argument("--revision", required=True, help="Pin the Hugging Face model commit SHA")
    p.add_argument("--qlora", action="store_true")
    p.add_argument("--max-steps", type=int, default=100)
    p.add_argument("--max-length", type=int, default=1024)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--dry-run", action="store_true", help="Check prepared data without loading GPU libraries or training")
    args = p.parse_args()
    manifest = verify(args.data)
    if args.max_steps < 1 or args.max_length < 32:
        p.error("max-steps must be positive and max-length at least 32")
    import re
    if not re.fullmatch(r"[a-f0-9]{40}", args.revision):
        p.error("revision must be a full 40-character Hugging Face commit SHA")
    if args.dry_run:
        print(json.dumps({"status": "data_validated_only", "trained": False, "dataset": manifest}, indent=2))
        return
    import torch
    from datasets import Dataset
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, set_seed
    from peft import LoraConfig
    from trl import SFTConfig, SFTTrainer
    if not torch.cuda.is_available():
        raise RuntimeError("Training requires an NVIDIA CUDA GPU; dry-run only validates data")
    if args.output.exists():
        raise ValueError("Use a new output directory for each experiment")
    set_seed(args.seed)
    dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    tokenizer = AutoTokenizer.from_pretrained(args.model, revision=args.revision, trust_remote_code=False)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                               bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=dtype) if args.qlora else None
    model = AutoModelForCausalLM.from_pretrained(args.model, revision=args.revision,
        torch_dtype=dtype, quantization_config=quant, device_map={"": torch.cuda.current_device()}, trust_remote_code=False)
    model.config.use_cache = False
    def load(split):
        rows = [conversational(json.loads(line)) for line in
                (args.data/f"{split}.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        for row in rows:
            tokens = tokenizer.apply_chat_template(row["prompt"] + row["completion"], tokenize=True)
            if len(tokens) > args.max_length:
                raise ValueError("Training example exceeds max-length; curate data or increase max-length")
        return Dataset.from_list(rows)
    config = SFTConfig(output_dir=str(args.output), max_steps=args.max_steps, max_length=args.max_length,
        per_device_train_batch_size=1, per_device_eval_batch_size=1, gradient_accumulation_steps=4,
        learning_rate=2e-4, seed=args.seed, data_seed=args.seed, completion_only_loss=True,
        bf16=dtype == torch.bfloat16, fp16=dtype == torch.float16,
        gradient_checkpointing=True, gradient_checkpointing_kwargs={"use_reentrant": False},
        eval_strategy="steps", eval_steps=max(1, args.max_steps//4),
        save_strategy="steps", save_steps=max(1, args.max_steps//4), save_total_limit=2,
        logging_steps=1, report_to="none")
    trainer = SFTTrainer(model=model, processing_class=tokenizer, args=config,
        train_dataset=load("train"), eval_dataset=load("validation"),
        peft_config=LoraConfig(r=8, lora_alpha=16, lora_dropout=.05,
                              target_modules=["q_proj", "k_proj", "v_proj", "o_proj"], task_type="CAUSAL_LM"))
    trained = trainer.train()
    validation = trainer.evaluate()
    adapter = args.output/"adapter"
    trainer.save_model(str(adapter))
    tokenizer.save_pretrained(str(adapter))
    run = {"created_at": datetime.now(timezone.utc).isoformat(), "model": args.model,
        "revision": args.revision, "qlora": args.qlora, "seed": args.seed,
        "max_steps": args.max_steps, "max_length": args.max_length,
        "dataset": manifest, "train_metrics": trained.metrics, "validation_metrics": validation,
        "gpu": torch.cuda.get_device_name(), "packages": {name: importlib.metadata.version(name)
            for name in ["torch", "transformers", "trl", "peft", "datasets", "accelerate"]}}
    (args.output/"training-run.json").write_text(json.dumps(run, indent=2), encoding="utf-8")
    print(f"Adapter: {adapter}. Evaluate held-out cases before claiming quality improvement.")

if __name__ == "__main__":
    main()
