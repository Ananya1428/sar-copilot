"""Real integration test against the running Ollama service (not mocked) —
proves the GPU-backed service actually completes a prompt end to end, not
just that the client code compiles. Skips (doesn't fail) if Ollama isn't
reachable, since this suite may run in environments without it."""

import pytest

from app.domain.narrative.llm_client import OllamaClient


def test_ollama_completes_a_simple_prompt():
    client = OllamaClient()
    result = client.complete(
        system="You are a helpful assistant. Respond with exactly one word.",
        user="Reply with the single word: OK",
        temperature=0.0,
        seed=1,
        response_format=None,
        max_tokens=10,
    )

    if not result.ok and result.error and ("connect" in result.error.lower() or "timed out" in result.error.lower()):
        pytest.skip(f"Ollama not reachable: {result.error}")

    assert result.ok, result.error
    assert result.text is not None
    assert len(result.text.strip()) > 0
