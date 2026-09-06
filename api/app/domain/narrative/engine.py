"""Narrative engine orchestration (blueprint §13.5): section-scoped
generation, each section seeing ONLY its own `required_evidence` slice of
the pack, assembled deterministically, with a retry-then-fallback control
flow.

Verification is Part 5's job — `self.verifier`, if given, is called after
the structural check below and can reject a draft for reasons this part
doesn't yet know how to check (hallucination, entailment, completeness).
Until Part 5 exists, `verifier=None` means only the structural check
gates release: valid JSON, not `INSUFFICIENT_EVIDENCE`, at least one
sentence, and every sentence citing at least one evidence key. That's
deliberately weaker than real verification — it catches a broken response,
not a fabricated one — which is exactly the boundary the Part 4 brief
draws ("this part just needs to PRODUCE a narrative ... it does not yet
need to reject/retry on its own [for hallucination]").
"""

import json
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.domain.evidence.schema import EvidencePack
from app.domain.narrative.deterministic import render_all_sections, render_section
from app.domain.narrative.llm_client import OllamaClient
from app.domain.narrative.prompt_registry import PromptRegistry
from app.domain.narrative.sections import NARRATIVE_SECTIONS
from app.models.case import Case
from app.models.evidence import EvidencePack as EvidencePackRow
from app.models.narrative import Narrative as NarrativeRow
from app.models.narrative import NarrativeSentence as NarrativeSentenceRow

MAX_ATTEMPTS = 3
DEFAULT_TEMPERATURE = 0.1
DEFAULT_MAX_TOKENS = 600
FREEFORM_MAX_TOKENS = 2000


@dataclass
class GenerationResult:
    narrative_text: str
    sentences: list[dict]
    mode: str  # TEMPLATE | HYBRID | FREEFORM | TEMPLATE_FALLBACK
    model_id: str | None
    prompt_version: str | None
    seed: int
    attempts: int
    notes: list[str] = field(default_factory=list)


def _serialize_evidence_value(value):
    if isinstance(value, list):
        return [item.model_dump(mode="json") if hasattr(item, "model_dump") else item for item in value]
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


class NarrativeEngine:
    def __init__(self, llm: OllamaClient | None = None, prompts: PromptRegistry | None = None, verifier=None, max_attempts: int = MAX_ATTEMPTS):
        self.llm = llm or OllamaClient()
        self.prompts = prompts or PromptRegistry(settings.prompt_version)
        self.verifier = verifier
        self.max_attempts = max_attempts

    def generate(self, pack: EvidencePack, mode: str = "HYBRID", seed: int = 42) -> GenerationResult:
        mode = mode.upper()
        if mode == "TEMPLATE":
            return self._deterministic(pack, seed, attempts=0)
        if mode == "FREEFORM":
            return self._generate_freeform(pack, seed)
        if mode != "HYBRID":
            raise ValueError(f"unknown generation mode: {mode!r}")

        last_notes: list[str] = []
        for attempt in range(1, self.max_attempts + 1):
            attempt_seed = seed + attempt - 1
            sentences, notes = self._generate_sections(pack, attempt_seed)
            structural_ok, structural_notes = self._structural_check(sentences)
            notes = notes + structural_notes
            last_notes = notes

            if not structural_ok:
                continue

            if self.verifier is not None:
                report = self.verifier.verify(sentences, pack)
                if not getattr(report, "passed", False):
                    last_notes.append(f"verification failed: {report}")
                    continue

            return GenerationResult(
                narrative_text=self._assemble(sentences),
                sentences=sentences,
                mode="HYBRID",
                model_id=self.llm.model_id,
                prompt_version=self.prompts.version,
                seed=attempt_seed,
                attempts=attempt,
                notes=notes,
            )

        result = self._deterministic(pack, seed, attempts=self.max_attempts)
        result.mode = "TEMPLATE_FALLBACK"
        result.notes.append(
            f"HYBRID generation failed after {self.max_attempts} attempt(s): {'; '.join(last_notes) or 'no diagnostic notes'}"
        )
        return result

    def _deterministic(self, pack: EvidencePack, seed: int, attempts: int) -> GenerationResult:
        sentences = render_all_sections(pack)
        return GenerationResult(
            narrative_text=self._assemble(sentences),
            sentences=sentences,
            mode="TEMPLATE",
            model_id=None,
            prompt_version=None,
            seed=seed,
            attempts=attempts,
        )

    def _generate_sections(self, pack: EvidencePack, seed: int) -> tuple[list[dict], list[str]]:
        out: list[dict] = []
        notes: list[str] = []

        for section in NARRATIVE_SECTIONS:
            if section["static"]:
                sentences = render_section(section["id"], pack)
                for s in sentences:
                    s["section"] = section["id"]
                out.extend(sentences)
                continue

            prompt = self.prompts.render(
                section_id=section["id"],
                evidence_json=self._scope_evidence(pack, section),
                allowed_entities=sorted(pack.allowed_entities()),
                allowed_numbers=sorted(pack.allowed_numbers()),
                allowed_dates=sorted(pack.allowed_dates()),
            )
            result = self.llm.complete(
                system=self.prompts.system(),
                user=prompt,
                temperature=DEFAULT_TEMPERATURE,
                seed=seed,
                response_format="json",
                max_tokens=DEFAULT_MAX_TOKENS,
            )
            if not result.ok:
                notes.append(f"section {section['id']}: LLM call failed: {result.error}")
                continue

            parsed, parse_notes = self._parse_section_response(result.text, section)
            notes.extend(f"section {section['id']}: {n}" for n in parse_notes)
            for s in parsed:
                s["section"] = section["id"]
            out.extend(parsed)

        return out, notes

    def _scope_evidence(self, pack: EvidencePack, section: dict) -> str:
        """Each section gets ONLY the evidence it needs (blueprint
        §13.5) — narrower context means fewer opportunities to drift, and
        when one section fails, only that section needs regenerating."""
        subset = {key: _serialize_evidence_value(getattr(pack, key)) for key in section["required_evidence"]}
        return json.dumps(subset, default=str, indent=2)

    def _parse_section_response(self, raw_text: str, section: dict) -> tuple[list[dict], list[str]]:
        text = raw_text.strip()
        if text == "INSUFFICIENT_EVIDENCE":
            return [], ["model reported INSUFFICIENT_EVIDENCE"]

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            return [], [f"invalid JSON: {exc}"]

        sentences = data.get("sentences") if isinstance(data, dict) else None
        if not isinstance(sentences, list) or not sentences:
            return [], ["response contained no sentences"]

        cleaned = []
        for s in sentences:
            if isinstance(s, dict) and s.get("text"):
                cleaned.append({"text": s["text"], "evidence_keys": s.get("evidence_keys") or []})
        if not cleaned:
            return [], ["all sentences malformed or empty"]

        max_sentences = section.get("max_sentences")
        if max_sentences:
            cleaned = cleaned[:max_sentences]
        return cleaned, []

    def _structural_check(self, sentences: list[dict]) -> tuple[bool, list[str]]:
        """Everything Part 4 can check without a real verifier: the
        response parsed, wasn't empty, and every sentence cited SOME
        evidence key. Catches a broken response, not a fabricated one —
        Part 5 supplies the real hallucination checks via `self.verifier`."""
        if not sentences:
            return False, ["no sentences produced by any section"]
        unsupported = [s["text"] for s in sentences if not s.get("evidence_keys")]
        if unsupported:
            return False, [f"{len(unsupported)} sentence(s) cited no evidence_keys"]
        return True, []

    def _assemble(self, sentences: list[dict]) -> str:
        return "\n\n".join(s["text"] for s in sentences)

    def _generate_freeform(self, pack: EvidencePack, seed: int) -> GenerationResult:
        """Whole-pack, single-call generation. Never used in production
        (blueprint §13.2) — kept only as Part 7's benchmark baseline for
        *why* constrained, section-scoped generation matters."""
        evidence_json = json.dumps(pack.model_dump(mode="json"), default=str, indent=2)
        prompt = (
            "Draft the complete SAR narrative (introduction, who, what/when, where, "
            "how, why, conclusion) from the evidence below, in the same JSON output "
            "schema and under the same constraints as usual.\n\nEVIDENCE:\n" + evidence_json
        )
        result = self.llm.complete(
            system=self.prompts.system(),
            user=prompt,
            temperature=DEFAULT_TEMPERATURE,
            seed=seed,
            response_format="json",
            max_tokens=FREEFORM_MAX_TOKENS,
        )

        notes: list[str] = []
        sentences: list[dict] = []
        if not result.ok:
            notes.append(f"LLM call failed: {result.error}")
        else:
            sentences, parse_notes = self._parse_section_response(result.text, {"max_sentences": None})
            for s in sentences:
                s["section"] = "freeform"
            notes.extend(parse_notes)

        return GenerationResult(
            narrative_text=self._assemble(sentences),
            sentences=sentences,
            mode="FREEFORM",
            model_id=self.llm.model_id,
            prompt_version=self.prompts.version,
            seed=seed,
            attempts=1,
            notes=notes,
        )
