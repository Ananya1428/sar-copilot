# Model Card — SAR Copilot

SR 11-7-style model documentation, per blueprint §24.1. Covers both
models this system actually calls: the narrative-drafting LLM and the
semantic entailment checker. Written from what Parts 4-7 actually built
and observed — not the blueprint's illustrative text.

---

## 1. Models used

### 1.1 Narrative drafting: Llama 3.1 8B Instruct

- **Model**: `llama3.1:8b-instruct-q4_K_M` (Meta, quantized to Q4_K_M),
  served locally via [Ollama](https://ollama.com). Configured in
  `api/app/config.py` (`llm_model`), overridable via the `LLM_MODEL`
  env var.
- **Why this size**: local deployability on a single consumer GPU (this
  build was developed and evaluated on an RTX 4060) at a real fluency
  cost against a hosted frontier model — named explicitly as a limitation
  (§26 / LIMITATIONS.md), not hidden.
- **Not fine-tuned.** Used entirely as-is, off the shelf, prompted only
  (see §13.4's versioned prompt system, `api/app/domain/narrative/
  prompts/<version>/`). No training data of any kind — there is no
  training step in this build.
- **Inputs**: a scoped slice of one case's `EvidencePack` per narrative
  section (`engine.py`'s `_scope_evidence` — each section sees only the
  evidence fields it needs, not the whole pack), plus the section's
  system/user prompt from the active prompt version.
- **Outputs**: JSON-structured sentence lists per section
  (`{"sentences": [{"text": ..., "evidence_keys": [...]}]}`), assembled
  into a full narrative body. Never returned to a caller unverified — see
  §3.
- **Decoding parameters**: `temperature=0.1`, a fixed integer `seed`
  (persisted per generation), `max_tokens=600` per section (2000 for the
  FREEFORM benchmark mode). Not sampled at a higher temperature anywhere
  in this build.
- **Reproducibility**: `Narrative` rows persist `model_id`, `prompt_
  version`, and `seed` (blueprint §15.3's reproducibility tuple) —
  `temperature` itself is NOT persisted as a column (a fixed constant in
  `engine.py`, not yet a stored field), which is a real gap against the
  full tuple the blueprint describes; noted in LIMITATIONS.md.

### 1.2 Semantic entailment: DeBERTa-v3-base MNLI-FEVER-ANLI

- **Model**: `MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli`, a general-
  domain NLI (Natural Language Inference) model, loaded locally via
  `transformers` (`api/app/domain/verification/semantic.py`), pre-
  downloaded at Docker build time (`api/Dockerfile`) so a container with
  no outbound network access still has a working model.
- **Not fine-tuned** on financial-crime or SAR-domain text. This is the
  single most important caveat in this card — see §4.
- **Inputs**: a constructed "premise" (the grounded evidence facts a
  narrative sentence cites) and "hypothesis" (the sentence's own text).
- **Outputs**: an entailment/neutral/contradiction label and probability
  per sentence, aggregated into Check 5's score.
- **Degrades gracefully**: if the model fails to load (no GPU, no
  network, disk issue), `semantic.py` reports the check as unavailable
  with a neutral score rather than crashing the pipeline — visible via
  `details.unavailable` in the persisted `VerificationReport`.

---

## 2. Intended use

Drafting the narrative *text* of a Suspicious Activity Report from an
already-detected case's evidence, for a human compliance analyst to
review, edit, and approve before any filing decision. It is **not**:

- an auto-filing system — there is no code path in this build that
  submits a narrative anywhere without a human step in between, and no
  actual filing integration exists at all;
- a detection system on its own — narrative generation happens strictly
  *after* Part 2's separate rule/ML/graph detection layer has already
  flagged a case; the LLM never decides what's suspicious, only how to
  describe evidence a human-configured detection layer already flagged;
- validated for, or intended for, real customer data or production
  regulatory use. See the prominent statement in README.md and
  LIMITATIONS.md.

## 3. The verification pipeline (why an 8B, unfine-tuned model is usable at all)

Every narrative — regardless of mode — passes through six independent
checks (`api/app/domain/verification/`) before it's considered usable:
numeric grounding, entity grounding, temporal grounding, prohibited
content, semantic entailment, and section completeness. A single
CRITICAL-severity failure (numeric/entity/temporal/prohibited) blocks
release regardless of the weighted score; HYBRID mode retries up to 3
times against real verification failures, then falls back to a fully
deterministic template rather than ever shipping an unverified draft.
This is the design answer to using an unfine-tuned local model: the
system does not trust the model's fluency, it trusts the verification
gate.

## 4. Known limitations (from what this build actually found)

These are measured, reproduced findings from Parts 4-7's own testing —
not hypothetical caveats. Full detail and evidence in LIMITATIONS.md;
summarized here because they bear directly on how much to trust this
model's output.

1. **The entailment check has a real, measured false-positive pattern on
   terse/template-style sentences.** Even a 100%-correct, fully-grounded
   narrative can score low on entailment: the hand-built adversarial
   fixture's clean baseline scored 0.39 overall on the entailment check
   (4 of 6 sentences flagged "not entailed" despite being entirely
   accurate), and a real narrative generated against live seeded data
   (CASE-0003, TEMPLATE mode, otherwise fully passing) scored 0.686 —
   both below that check's own internal pass threshold. This is a
   precision problem in the premise-construction heuristic (how a
   sentence's cited evidence is turned into an NLI "premise"), not a
   defect in the underlying model's general NLI accuracy. It's mitigated
   by weighting (entailment is 0.10 of the aggregate score, HIGH not
   CRITICAL severity) so it doesn't block release on its own, but it
   means the per-check entailment score should be read with real
   skepticism, not treated as equally reliable to the four deterministic
   checks.
2. **evidence_keys mismatch is expected, not a bug.** The LLM's own
   self-reported `evidence_keys` per sentence are never trusted as the
   grounding mechanism (every check scans the sentence's rendered TEXT
   instead) — a sentence with a correct evidence_key on a fabricated
   number still fails numeric grounding, and a sentence with a wrong
   evidence_key on a correct number still passes. This is by design
   (documented in numeric.py/entity.py's own module docstrings), but
   worth naming here because it means `evidence_keys` in a persisted
   `NarrativeSentence` row is UI/provenance decoration, not a safety
   mechanism, and should never be read as one.
3. **Regex-based entity extraction has real, fixed edge cases** — comma-
   truncation (Faker-generated occupations like "Geologist, engineering"
   truncate at the comma; a `_matches_full_item_at` prefix-match was
   added to fix false rejections of correctly-grounded values) and
   reference-code/hyphen adjacency (an early version of the numeric
   check's reference-code exclusion only skipped the character right
   after a hyphen, still flagging the remainder of the same digit run —
   the fix excludes the full matched span). Both fixed during Part 5; see
   the modules' own docstrings for detail.
4. **A single-digit account-number substitution is a known, undesigned-
   for blind spot in checks 1-4.** `numeric.py`'s reference-code
   exclusion and `entity.py`'s negative lookahead both exist specifically
   to avoid false-positiving on legitimate reference codes like
   "ACC-88213" — and that same exclusion means a fabricated
   "ACC-88214" is invisible to both checks by construction. See
   EVALUATION.md's adversarial confusion matrix for what the real
   entailment model does and doesn't catch here.
5. **FREEFORM mode has no retry logic** (`engine.py`'s
   `_generate_freeform` makes exactly one LLM call) — a single malformed
   response yields an empty narrative with no verification report at
   all, silently. This is intentional (FREEFORM is never used in
   production, only shipped as Part 7's benchmark baseline for why
   constrained generation matters — blueprint §13.2), but it means
   FREEFORM's own failure mode is qualitatively different from HYBRID's
   (structural failure vs. verification failure), which EVALUATION.md
   reports as a separate "generation failure rate," not folded into
   hallucination rate.
6. **TEMPLATE mode is not automatically verification-clean.** The
   deterministic template renderer computes some derived display values
   (e.g. a circular-flow retention percentage, rendered as `fraction *
   100`) that are correctly derived from real evidence but were never
   independently flattened into the EvidencePack's own `allowed_numbers()`
   set — so the numeric check can flag TEMPLATE's own output as
   "ungrounded" even though nothing was fabricated. See EVALUATION.md and
   LIMITATIONS.md for the concrete case and numbers. This is arguably the
   single most important finding in this evaluation: "the safe fallback
   mode" and "the mode that reliably passes its own safety check" are not
   automatically the same thing, and this build's own evaluation caught
   the gap between them.

## 5. Validation performed

See `EVALUATION.md` for the full record: TEMPLATE/HYBRID/FREEFORM
comparison on real cases (hallucination rate, per-check violation rates,
entailment/completeness scores, typology coverage, material fact recall,
latency, retry/fallback rate, reproducibility), the full ten-case
adversarial confusion matrix, and a 500-account detection evaluation.
Every number there is from a real run against this build, dated and
reproducible via the `eval/` scripts that produced it — never a
projected or blueprint-illustrative figure.

## 6. Version / reproducibility info

- **Prompt version**: `v1.0.0` (`api/app/domain/narrative/prompts/
  v1.0.0/`), integrity-checked at load via `PromptRegistry` (SHA-256 of
  every prompt file, recorded in `registry.json` at activation time —
  editing an activated prompt file in place raises `PromptIntegrityError`
  rather than silently drifting).
- **Model pinning**: `llama3.1:8b-instruct-q4_K_M` is the default; the
  exact tag is what Ollama actually pulled (verify with
  `docker compose exec ollama ollama list`). The entailment model is
  pinned by its exact HuggingFace repo id, no version range.
- **Verification pipeline version**: unversioned as of this build (six
  checks, weights in `pipeline.py`'s `WEIGHTS` dict, pass threshold
  0.85) — a future change to check logic or weights should get its own
  version marker if this model card is to stay trustworthy over time;
  noted as a gap, not implemented here (no new features in Part 7).
