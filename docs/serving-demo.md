# Part 1: vLLM on Kubernetes and inference evaluation

Status: implementation with offline HTTP protocol tests. No GPU performance claim until actual runs are saved.
The existing Java workflow remains available. Direct inference deliberately starts with HTML cases;
these are the same existing evaluators and raw EvalResult format, but a different generation path.
Do not compare direct one-call inference to Java's agent workflow as a pure engine speedup.

## Deploy (NVIDIA Linux GPU cluster)

A Mac/minikube without NVIDIA GPU passthrough cannot run this GPU manifest.
Check `kubectl get nodes` and GPU capacity; install the NVIDIA device plugin if your cluster lacks it.
The model is public. First startup downloads weights, and emptyDir cache is lost on restart.

```bash
kubectl apply -k deploy/k8s
kubectl -n llm-eval rollout status deployment/vllm --timeout=1200s
kubectl -n llm-eval port-forward service/vllm 8000:8000
```

In another terminal:

```bash
uv sync --frozen --dev
curl http://127.0.0.1:8000/v1/models
uv run python -m llm_codegen_eval.serving.benchmark \
  --label vllm-c1 --concurrency 1 --environment 'GPU=<actual>; vLLM=0.10.2; warm cache; exclusive traffic'
uv run python -m llm_codegen_eval.serving.benchmark \
  --label vllm-c4 --concurrency 4 --environment 'GPU=<same>; vLLM=0.10.2; warm cache; exclusive traffic'
uv run python -m llm_codegen_eval.serving.compare \
  reports/serving/<first-run-id>/benchmark.json reports/serving/<second-run-id>/benchmark.json
```

Each command prints its unique report directory. Results contain request-level latency, TTFT,
usage tokens, errors, length truncation counts, configuration and workload hash.
Generation wall time excludes warmups and structural/browser evaluation; all failed attempts stay
in wall time. Throughput means successful requests/second and successful output tokens/second.
Token throughput is unknown when usage is unavailable. Latency percentiles cover successful requests,
so always show errors beside them. TTFT is time to first nonempty content chunk, including network and server queueing.
Client semaphore wait is excluded from per-request latency. The batch wall time includes all requests.
This is a closed-loop concurrency benchmark, not an open-loop arrival-rate capacity test.

For another compatible engine use `--base-url` with the same model, workload, and hardware.
Run both orders (A/B then B/A), repeat at least three times and record GPU/runtime/cache policy.
For model quality comparisons change `--model` and disclose that different output lengths affect throughput.

## Record a 2-minute demo

1. Show the GPU Pod Ready and model name from `/v1/models`.
2. Run concurrency 1 and 4 with identical generation settings and benchmark prompts.
3. Show the comparison plus request-level errors and structural scores.
4. Explain that structural pass rate is HTML contract compliance, not full functional correctness.
5. Save real run artifacts before adding measured speedup numbers to a resume.

References: [vLLM Kubernetes](https://docs.vllm.ai/en/v0.10.2/deployment/k8s.html),
[vLLM compatible server](https://docs.vllm.ai/en/v0.10.2/serving/openai_compatible_server.html).
