"""Thin client over Ollama's HTTP API (blueprint §13.5's call shape:
`complete(system, user, temperature, seed, response_format, max_tokens)`).

The engine treats every call through here as untrustworthy input (blueprint
§9.2 P2 — "generation is untrusted"), so this client's only job is to
never let a flaky Ollama call surface as an unhandled exception: timeouts,
connection failures, and non-2xx responses all come back as a
`CompletionResult(ok=False, ...)` the engine can act on (retry / fall back
to TEMPLATE), never as a crash of the whole generation request.
"""

from dataclasses import dataclass

import httpx

from app.config import settings

DEFAULT_TIMEOUT_SECONDS = 120.0


@dataclass
class CompletionResult:
    ok: bool
    text: str | None = None
    error: str | None = None


class OllamaClient:
    def __init__(self, base_url: str | None = None, model: str | None = None, timeout: float = DEFAULT_TIMEOUT_SECONDS):
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.model_id = model or settings.llm_model
        self.timeout = timeout

    def complete(
        self,
        system: str,
        user: str,
        temperature: float = 0.1,
        seed: int = 42,
        response_format: str | None = "json",
        max_tokens: int = 600,
    ) -> CompletionResult:
        payload = {
            "model": self.model_id,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": {
                "temperature": temperature,
                "seed": seed,
                "num_predict": max_tokens,
            },
        }
        if response_format == "json":
            payload["format"] = "json"

        try:
            resp = httpx.post(f"{self.base_url}/api/chat", json=payload, timeout=self.timeout)
        except httpx.TimeoutException as exc:
            return CompletionResult(ok=False, error=f"ollama request timed out after {self.timeout}s: {exc}")
        except httpx.ConnectError as exc:
            return CompletionResult(ok=False, error=f"could not connect to ollama at {self.base_url}: {exc}")
        except httpx.HTTPError as exc:
            return CompletionResult(ok=False, error=f"ollama request failed: {exc}")

        if resp.status_code != 200:
            return CompletionResult(ok=False, error=f"ollama returned HTTP {resp.status_code}: {resp.text[:500]}")

        try:
            data = resp.json()
            text = data["message"]["content"]
        except (ValueError, KeyError) as exc:
            return CompletionResult(ok=False, error=f"unexpected ollama response shape: {exc}")

        return CompletionResult(ok=True, text=text)
