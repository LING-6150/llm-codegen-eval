"""Compare matching serving workloads; keep errors visible."""
import argparse
import json
from pathlib import Path

def compare(a, b):
    if a["workload_hash"] != b["workload_hash"]:
        raise ValueError("Workloads differ: use identical cases, repeats and generation parameters")
    keys = ("structural_pass_rate", "errors", "latency_p50_ms", "latency_p95_ms",
            "ttft_p95_ms", "requests_per_second", "output_tokens_per_second")
    lines = ["# Serving comparison", "", f"A: {a['label']} / {a['model']} / concurrency {a['concurrency']}",
             f"B: {b['label']} / {b['model']} / concurrency {b['concurrency']}", "",
             f"A environment: {a['environment']}", f"B environment: {b['environment']}", "",
             "| Metric | A | B |", "|---|---:|---:|"]
    for key in keys:
        lines.append(f"| {key} | {a['summary'][key]} | {b['summary'][key]} |")
    lines += ["", "Client-observed timings. Warmups and evaluators excluded from generation wall time.",
              "Failed requests remain in wall time and error counts. Token throughput is null when usage is missing.",
              "Concurrency changes include queueing at the inference server. Report hardware/cache policy and repeat runs.",
              "Different models measure a quality/latency tradeoff, not a pure serving-engine speedup."]
    return "\n".join(lines) + "\n"

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("a", type=Path); p.add_argument("b", type=Path)
    args = p.parse_args()
    print(compare(json.loads(args.a.read_text()), json.loads(args.b.read_text())))

if __name__ == "__main__":
    main()
