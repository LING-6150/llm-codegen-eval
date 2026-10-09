# Part 4: LoRA / QLoRA and held-out evaluation

Status: dataset preparation, integrity checks and dry-run validated offline. GPU training and
trained-adapter evaluation require an NVIDIA GPU; no training or quality improvement is claimed yet.

## Data

Format: one JSON object per line with `prompt` and `completion` strings. Completions are full HTML.
`examples/sft-smoke.jsonl` contains eight hand-authored toy examples strictly for pipeline smoke tests.
It is not a useful training corpus or evidence of generalization. Replace with curated, reviewed
instruction/HTML pairs for a real experiment. Hold out the existing benchmark prompts throughout.
Preparation rejects normalized exact prompt overlaps with the benchmark and duplicate prompts, then
splits reproducibly into training and validation by prompt. Semantic paraphrases require review.
Dataset checksums let training reject files changed after preparation. Validation loss is distinct
from the final benchmark structural score.

```bash
uv sync --frozen --extra api --dev
uv run python -m llm_codegen_eval.training.data examples/sft-smoke.jsonl \
  --output training-data/smoke-v1
```

## Pin the base model

Obtain and record the Hugging Face repository commit SHA for the model revision you will use.
Use that same SHA for training and serving; do not compare a trained adapter to a moving base revision.
The trainer requires a full 40-character SHA. Substitute it below:

```bash
export MODEL_REVISION='<full-model-commit-sha>'
uv run python -m llm_codegen_eval.training.train \
  --data training-data/smoke-v1 --output outputs/html-lora-smoke \
  --revision "$MODEL_REVISION" --max-steps 5 --dry-run
```

Dry-run requires no GPU or training dependencies and explicitly reports `trained: false`.

## NVIDIA GPU training

On a Linux CUDA host with matching NVIDIA drivers:

```bash
uv sync --frozen --extra training
uv run --extra training python -m llm_codegen_eval.training.train \
  --data training-data/smoke-v1 --output outputs/html-lora-smoke \
  --revision "$MODEL_REVISION" --max-steps 5
```

Add `--qlora` for 4-bit NF4 with double quantization. On the small 0.5B model plain LoRA is a
reasonable first experiment. The script uses completion-only loss, seeded SFT, validation loss,
and rank-8 attention adapters. Overlong examples fail instead of silently truncating the target.
A real run should use a larger curated dataset and choose training steps using validation behavior.
Outputs include `adapter/` plus `training-run.json` with revision, package versions, GPU, data
checksums, training metrics and validation metrics. Adapter weights and datasets are ignored by Git.

## Serve base and adapter together

On the same Linux GPU host, after training has actually completed:

```bash
docker run --rm --gpus all --ipc=host -p 127.0.0.1:8000:8000 \
  -v "$PWD/outputs/html-lora-smoke/adapter:/models/html-lora:ro" \
  vllm/vllm-openai:v0.10.2 \
  --model Qwen/Qwen2.5-Coder-0.5B-Instruct --revision "$MODEL_REVISION" \
  --enable-lora --max-lora-rank 8 --lora-modules html-lora=/models/html-lora \
  --max-model-len 4096 --generation-config vllm --disable-log-requests
```

For AKS, upload adapter files to a private volume/object store, mount them read-only in the vLLM Pod,
and apply equivalent arguments through the Terraform-owned manifest. The default Azure manifest
serves the base model; it does not automatically upload or deploy trained weights.

From a workstation with the inference endpoint forwarded:

```bash
uv run python -m llm_codegen_eval.serving.benchmark \
  --model Qwen/Qwen2.5-Coder-0.5B-Instruct --label base --concurrency 1 \
  --environment "same GPU; revision=$MODEL_REVISION; LoRA enabled server; warm cache"
uv run python -m llm_codegen_eval.serving.benchmark \
  --model html-lora --label tuned --concurrency 1 \
  --environment "same GPU; revision=$MODEL_REVISION; adapter=html-lora-smoke; warm cache"
uv run python -m llm_codegen_eval.serving.compare \
  reports/serving/<base-run>/benchmark.json reports/serving/<tuned-run>/benchmark.json
```

Use the identical benchmark, limit, repeats, seed, max tokens and concurrency for both.
For stronger evidence use all HTML cases (`--limit 1000`) and at least three repeated experiments.
Keep errors, length-limited generations, sample size, and per-case results visible. An adapter
that lowers training loss can still reduce held-out quality. Structural score is not functional correctness.

## Record

Show data checks and held-out split, a real GPU training log, saved adapter and provenance,
then `/v1/models` containing both model IDs. Run the paired held-out evaluation and query the
result through GraphQL. Report the observed direction even if the adapter does not improve quality.

References: [TRL 0.22 SFT trainer](https://huggingface.co/docs/trl/v0.22.2/sft_trainer),
[vLLM LoRA serving](https://docs.vllm.ai/en/v0.10.2/features/lora.html).
