"""Streaming OpenAI-compatible inference client (vLLM and other servers)."""
import json
import re
from time import perf_counter
import httpx

SYSTEM_PROMPT = "Return only a complete HTML document, without explanations or Markdown fences."

class OpenAIClient:
    def __init__(self, http: httpx.AsyncClient, base_url: str, model: str,
                 api_key: str = "", max_tokens: int = 1024, temperature: float = 0.0,
                 seed: int = 42):
        self.http, self.base_url, self.model = http, base_url.rstrip("/"), model
        self.api_key, self.max_tokens, self.temperature, self.seed = api_key, max_tokens, temperature, seed

    async def generate(self, prompt: str, agent=False, extra_params=None) -> dict:
        start = perf_counter()
        first = None
        parts, usage, finished, reason = [], None, False, None
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        payload = {"model": self.model, "messages": [
            {"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
            "max_tokens": self.max_tokens, "temperature": self.temperature, "seed": self.seed,
            "stream": True, "stream_options": {"include_usage": True}}
        async with self.http.stream("POST", f"{self.base_url}/chat/completions",
                                    headers=headers, json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    finished = True
                    break
                event = json.loads(data)
                if event.get("error"):
                    raise RuntimeError("Inference server returned an error event")
                if event.get("usage"):
                    usage = event["usage"]
                for choice in event.get("choices", []):
                    content = choice.get("delta", {}).get("content")
                    if content:
                        first = first if first is not None else (perf_counter() - start) * 1000
                        parts.append(content)
                    if choice.get("finish_reason"):
                        reason = choice["finish_reason"]
        if not finished or reason is None:
            raise RuntimeError("Incomplete inference stream")
        code = "".join(parts).strip()
        if not code:
            raise RuntimeError("Empty inference response")
        # Remove only an enclosing fence; retain HTML text and internal whitespace.
        fence = re.fullmatch(r"```(?:html)?\s*\n(.*)\n```", code, re.S | re.I)
        if fence:
            code = fence.group(1)
        return {"code": code, "duration_ms": (perf_counter() - start) * 1000,
                "ttft_ms": first, "usage": usage, "finish_reason": reason}
