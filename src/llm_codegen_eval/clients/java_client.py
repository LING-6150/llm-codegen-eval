"""Client for calling the Java code generation service via SSE."""

import json
import time
import re
import httpx

JAVA_SERVICE_URL = "http://localhost:8123"
APP_ID = "415591816310689792"
USER_ACCOUNT = "gigiiscool"
USER_PASSWORD = "Ajisky543210"

class JavaServiceClient:

    def __init__(
        self,
        base_url: str = JAVA_SERVICE_URL,
        app_id: str = APP_ID
    ):
        self.base_url = base_url
        self.app_id = app_id
        self.cookies: dict = {}

    async def health(self) -> bool:
        """Return True when the Java service actuator health endpoint is UP."""
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                resp = await client.get(f"{self.base_url}/api/actuator/health")
            if resp.status_code != 200:
                return False
            data = resp.json()
            return data.get("status") == "UP"
        except Exception:
            return False

    async def login(self):
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/api/user/login",
                json={
                    "userAccount": USER_ACCOUNT,
                    "userPassword": USER_PASSWORD
                }
            )
            resp.raise_for_status()
            self.cookies = dict(resp.cookies)

    async def generate(
        self,
        prompt: str,
        agent: bool = True,
        extra_params: dict | None = None,
    ) -> dict:
        if not self.cookies:
            await self.login()

        code_tokens = []
        review_score = None
        review_passed = None
        workflow_error = None
        start_time = time.time()

        params = {
            "appId": self.app_id,
            "message": prompt,
            "agent": str(agent).lower()
        }
        if extra_params:
            params.update({
                key: str(value).lower() if isinstance(value, bool) else value
                for key, value in extra_params.items()
            })

        async with httpx.AsyncClient(cookies=self.cookies, timeout=300) as client:
            async with client.stream(
                "GET",
                f"{self.base_url}/api/app/chat/gen/code",
                params=params
            ) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue

                    raw = line[5:].strip()
                    if not raw:
                        continue

                    try:
                        event = json.loads(raw)
                        payload = json.loads(event.get("d", "{}"))
                    except json.JSONDecodeError:
                        continue

                    event_type = payload.get("type")

                    if event_type == "code_token":
                        code_tokens.append(payload.get("detail", ""))
                    elif event_type == "review_done":
                        detail = payload.get("detail", "")
                        score_match = re.search(r'score=(\d+)', detail)
                        passed_match = re.search(r'passed=(true|false)', detail)
                        if score_match:
                            review_score = int(score_match.group(1))
                        if passed_match:
                            review_passed = passed_match.group(1) == "true"
                    elif event_type == "workflow_error":
                        workflow_error = payload.get("detail", "Unknown error")

        duration_ms = int((time.time() - start_time) * 1000)

        return {
            "code": "".join(code_tokens),
            "review_score": review_score,
            "review_passed": review_passed,
            "duration_ms": duration_ms,
            "error": workflow_error
        }
