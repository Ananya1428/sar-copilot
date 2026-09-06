import json

import pytest

from app.domain.narrative.prompt_registry import PromptIntegrityError, PromptRegistry


def test_loads_the_real_activated_version():
    registry = PromptRegistry("v1.0.0")
    assert "ABSOLUTE CONSTRAINTS" in registry.system()
    rendered = registry.render(
        "who",
        evidence_json="{}",
        allowed_entities=[],
        allowed_numbers=[],
        allowed_dates=[],
    )
    assert "SECTION: Subject identification" in rendered


def test_unknown_version_raises():
    with pytest.raises(PromptIntegrityError):
        PromptRegistry("v99.0.0")


def test_tampered_prompt_file_is_detected(tmp_path, monkeypatch):
    """Simulates the exact scenario this feature exists to catch: a prompt
    file edited after its version was activated, without updating
    registry.json."""
    import app.domain.narrative.prompt_registry as pr_module

    version_dir = tmp_path / "v9.9.9"
    version_dir.mkdir()
    (version_dir / "system.txt").write_text("original content")
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(
        json.dumps({"v9.9.9": {"files": {"system.txt": "0" * 64}}})  # deliberately wrong hash
    )

    monkeypatch.setattr(pr_module, "_PROMPTS_ROOT", tmp_path)
    monkeypatch.setattr(pr_module, "_REGISTRY_PATH", registry_path)

    with pytest.raises(PromptIntegrityError, match="changed since it was activated"):
        pr_module.PromptRegistry("v9.9.9")
