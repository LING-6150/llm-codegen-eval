"""Run inside the built eval image with only its runtime dependencies."""

import argparse
import asyncio
import json
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx

from llm_codegen_eval.api.app import create_app


class InferenceFixture(BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        if self.path == "/unavailable/chat/completions":
            self.send_error(503)
            return
        html = "<h1>Hello</h1>" if self.path == "/good/chat/completions" else "<p>Hello</p>"
        event = {"choices": [{"delta": {"content": html}, "finish_reason": "stop"}]}
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        self.wfile.write(f"data: {json.dumps(event)}\n\ndata: [DONE]\n\n".encode())


async def check_api(root, expected):
    token = "offline-image-smoke-token"
    app = create_app(root, token)
    query = {"query": "{ runs { label requests errors structuralPassRate releaseVerdict } }"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.post("/graphql", json=query)).status_code == 401
        response = await client.post("/graphql", json=query, headers={"Authorization": f"Bearer {token}"})
        response.raise_for_status()
        rows = response.json()["data"]["runs"]
        assert {r["label"]: (r["requests"], r["errors"], r["structuralPassRate"], r["releaseVerdict"])
                for r in rows} == expected


def run(root, revision):
    cases = root / "cases.json"
    cases.write_text(json.dumps([{"case_id": "heading", "prompt": "One heading", "code_type": "html",
                                 "required_checks": [{"type": "tag_exists", "selector": "h1",
                                                      "description": "Page heading"}]}]))
    scenarios = [
        ("good", "good", 0, "passed", 0, 1, 1),
        ("quality", "bad", 0, "quality_failure", 3, 1, 1),
        ("inference", "unavailable", 0, "invalid", 1, 1, 0),
        ("warmup", "unavailable", 1, "invalid", 1, 0, 0),
    ]
    with ThreadingHTTPServer(("127.0.0.1", 0), InferenceFixture) as server:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            for label, endpoint, warmup, verdict, exit_code, completed, judged in scenarios:
                args = [sys.executable, "-m", "llm_codegen_eval.serving.benchmark", "--release-gate",
                        "--base-url", f"http://127.0.0.1:{server.server_port}/{endpoint}",
                        "--cases", str(cases), "--repeats", "1", "--warmup", str(warmup),
                        "--environment", "offline image fixture", "--label", label,
                        "--output-dir", str(root / "serving")]
                proc = subprocess.run(args, cwd=root, capture_output=True, text=True, timeout=30)
                assert proc.returncode == exit_code, (label, proc.stdout, proc.stderr)
                directory = Path(proc.stdout.splitlines()[0])
                assert (directory / "report.md").is_file()
                metadata = json.loads((directory / "benchmark.json").read_text())
                assert metadata["git_commit"] == revision
                assert metadata["summary"]["release_gate"] == {
                    "verdict": verdict, "expected": 1, "completed": completed, "judged": judged,
                    "failed": int(verdict == "quality_failure"), "enforced": True, "execution_smoke": False,
                }
        finally:
            server.shutdown()
    asyncio.run(check_api(root, {"good": (1, 0, 1.0, "passed"), "quality": (1, 0, 0.0, "quality_failure"),
                                 "inference": (1, 1, 0.0, "invalid"), "warmup": (0, 0, None, "invalid")}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-revision", required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as directory:
        run(Path(directory), args.expected_revision)
