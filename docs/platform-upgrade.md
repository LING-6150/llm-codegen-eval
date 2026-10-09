# Model lifecycle platform upgrade

The upgrade lives in **llm-codegen-eval**. Existing Java agent benchmarks remain available.
Direct model-serving experiments reuse its HTML structural evaluator and result/report formats.
This keeps model quality, inference performance and infrastructure evidence connected.

| Increment | Implementation | Evidence still needed |
|---|---|---|
| vLLM + Kubernetes | 0.5B code model, streaming client, concurrency benchmark, paired reports | NVIDIA Pod Ready and real latency/throughput runs |
| Terraform + Azure | AKS/ACR, CPU/GPU pools, device plugin, jobs, report storage | Subscription plan/apply and completed cloud job |
| GraphQL | Authenticated queries for serving and legacy results | Live query of completed GPU run |
| Fine-tuning | Prompt split/leakage guard, LoRA/QLoRA SFT, provenance, paired held-out eval | Real curated corpus, GPU training, adapter eval |

Follow in order:

1. [vLLM/K8s recording guide](serving-demo.md)
2. [Azure/Terraform recording guide](azure-demo.md)
3. [GraphQL recording guide](graphql-demo.md)
4. [Fine-tuning recording guide](finetuning-demo.md)

## Evidence for applications

Before real GPU/cloud runs, describe the work as implemented integration and infrastructure
configuration. Do not claim deployed Azure services, reduced p95 latency, higher throughput or
fine-tuning quality gains from unit tests or toy training samples.

After running, retain: model revision and GPU SKU; commit/image version; workload hashes and generation
settings; A/B raw reports and errors; cloud deployment evidence; training dataset checksums, adapter
and validation loss; base-versus-adapter held-out structural scores. Keep the existing RESULTS.md
claims separate from these new experiments until the new evidence is available.

A useful interview narrative is a measured loop: deploy a model, benchmark serving and quality,
fine-tune against a separate corpus, then evaluate the adapter on unchanged held-out cases.
Report negative or neutral results just as clearly as improvements.
