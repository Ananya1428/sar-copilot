# Evaluation

Every number on this page is from a real run against this build — the
exact script that produced it is named under each table, and the raw
output is saved under `eval/results/`. Where a result is unflattering
(TEMPLATE mode's own numeric-check failures, the entailment check's
false-positive pattern, a real blind spot in the adversarial suite),
it's reported here as found, not smoothed over — see
[LIMITATIONS.md](./LIMITATIONS.md) for the full discussion of each.

Run date: 2026-09-10. Hardware: single RTX 4060 GPU (the same machine
this whole build was developed and tested on). Model:
`llama3.1:8b-instruct-q4_K_M` via Ollama; entailment:
`MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli`.

---

## 1. Generation mode comparison (TEMPLATE / HYBRID / FREEFORM)

**Script**: `eval/compare_modes.py` (`make eval-modes N=5`). **N = 5 real
seeded cases** (CASE-0001 through CASE-0005) — not 100; this build's
seeded demo dataset has 14 cases total, and HYBRID/FREEFORM each make a
real GPU-backed Ollama call per case (45s-150s per HYBRID generation
with retries), so 5 was chosen as a real, honestly-reported sample size
that completes in a reasonable evaluation window rather than a padded
number. Every case, every mode, same seed (42).

| Metric | TEMPLATE | HYBRID | FREEFORM |
|---|---|---|---|
| Generation failure rate (no verifiable output) | 0.0% | 0.0% | **100.0%** |
| Hallucination rate (CRITICAL check failure) | 80.0% | 60.0% | — |
| Verification pass rate | 20.0% | 40.0% | — |
| Numeric violation rate | 80.0% | 60.0% | — |
| Entity violation rate | 0.0% | 0.0% | — |
| Prohibited violation rate | 0.0% | 0.0% | — |
| Mean entailment score | 0.513 | 0.531 | — |
| Mean completeness score | 0.956 | 0.978 | — |
| Mean typology coverage | 100.0% | 90.0% | 0.0% |
| Mean material fact recall | 100.0% | 96.7% | 0.0% |
| Latency p50 (s) | 0.71 | 113.67 | 4.57 |
| Latency p95 (s) | 12.67 | 147.95 | 5.71 |
| Mean attempts | 0.0 | 3.0 | 1.0 |
| Fallback rate (HYBRID only) | — | 80.0% | — |

Per-case detail:

| Case | Mode | Actual mode | Attempts | Latency (s) | Passed | Score |
|---|---|---|---|---|---|---|
| CASE-0001 | TEMPLATE | TEMPLATE | 0 | 12.67 | False | 0.686 |
| CASE-0001 | HYBRID | TEMPLATE_FALLBACK | 3 | 112.73 | False | 0.686 |
| CASE-0001 | FREEFORM | FREEFORM | 1 | 3.29 | — (no report) | — |
| CASE-0002 | TEMPLATE | TEMPLATE | 0 | 0.71 | False | 0.710 |
| CASE-0002 | HYBRID | TEMPLATE_FALLBACK | 3 | 115.70 | False | 0.710 |
| CASE-0002 | FREEFORM | FREEFORM | 1 | 4.57 | — (no report) | — |
| CASE-0003 | TEMPLATE | TEMPLATE | 0 | 1.10 | **True** | 0.969 |
| CASE-0003 | HYBRID | TEMPLATE_FALLBACK | 3 | 147.95 | **True** | 0.969 |
| CASE-0003 | FREEFORM | FREEFORM | 1 | 5.01 | — (no report) | — |
| CASE-0004 | TEMPLATE | TEMPLATE | 0 | 0.45 | False | 0.694 |
| CASE-0004 | HYBRID | TEMPLATE_FALLBACK | 3 | 106.65 | False | 0.694 |
| CASE-0004 | FREEFORM | FREEFORM | 1 | 5.71 | — (no report) | — |
| CASE-0005 | TEMPLATE | TEMPLATE | 0 | 0.58 | False | 0.687 |
| CASE-0005 | HYBRID | **HYBRID** (no fallback) | 3 | 113.67 | **True** | 0.952 |
| CASE-0005 | FREEFORM | FREEFORM | 1 | 4.43 | — (no report) | — |

Raw output: `eval/results/compare_modes.json`.

### Reproducibility

- **TEMPLATE**: byte-identical across 2 trials, same pack + seed — CASE-0001. Expected: no LLM call is made at all.
- **HYBRID**: byte-identical across 2 trials, same pack + seed — CASE-0001, tested against the real Ollama endpoint (not assumed). At `temperature=0.1` with a fixed seed, this build's Ollama setup produced identical output both times in this test. This is **not** a guarantee for every case — it's one real, reproduced data point, not a proof of determinism; llama.cpp/Ollama's own docs are explicit that seed-determinism can depend on batching and hardware conditions outside this application's control.

### What this actually shows

**The headline, unflattering finding**: TEMPLATE mode — the mode this
build's own design treats as the unconditionally safe fallback — failed
its own verification 4 times out of 5 (80% hallucination rate), and every
one of those failures was the same root cause: a numeric check false
positive on a percentage value the deterministic renderer computes
correctly from real evidence (`fraction * 100`) but which was never
independently captured in the evidence pack's own `allowed_numbers()`
set. See LIMITATIONS.md for the full mechanism and the exact tokens
involved (`79.7`, `93.0`, and the `48`-hour rapid-movement window
constant). **Nothing was fabricated in any of these narratives** — this
is a grounding-vocabulary gap in the verification pipeline against the
template renderer's own presentation choices, not a hallucination in the
usual sense, and it only appears on cases involving a percentage-bearing
typology (CIRCULAR_FLOW, RAPID_MOVEMENT) — CASE-0003, which doesn't hit
this path, passed cleanly at 0.969 in both TEMPLATE and (non-fallback)
HYBRID mode.

**HYBRID mode** inherits this exact same problem whenever its own
generation also produces the same percentage phrasing (it does, since
the prompts encourage citing the same aggregate/typology evidence
TEMPLATE renders from) — 4 of 5 cases exhausted all 3 retries and fell
back to TEMPLATE, which then *also* failed verification for the same
reason, so the final delivered narrative for those 4 cases was neither
"a verified HYBRID draft" nor "a verified template" — it was the
unverified template, because the fallback's own verification result
isn't currently gated on before delivery. **This is the single most
actionable finding in this evaluation** — worth fixing in a future part,
explicitly not fixed here (Part 7 is documentation/evaluation only).
CASE-0005 is the one case in this sample where HYBRID succeeded on its
own merits without falling back at all (0.952, genuinely passed).

**FREEFORM mode failed to produce any verifiable output on all 5 cases**
— not because the narratives it did produce were unsafe, but because
`engine.py`'s `_generate_freeform` has no retry logic, and the raw LLM
response failed to parse into structured sentences every time in this
run. This is consistent with FREEFORM's status as a benchmark-only mode,
never shipped in production (blueprint §13.2) — but it's a real,
measured 100% structural failure rate on this sample, not a hypothetical
risk.

**Latency**: TEMPLATE is near-instant (p50 0.71s — the one outlier,
CASE-0001 at 12.67s, is the one-time entailment model load cost within
that process). HYBRID's p50 of 113.67s and p95 of 147.95s are dominated
by the 3-attempt retry loop against the same numeric-check failure
described above — each attempt makes a real per-section LLM call, so a
guaranteed-to-fail generation still pays the full retry cost before
falling back. This matches Part 4's original measurement (46.3s for a
single successful HYBRID attempt) scaled by the number of attempts
actually taken.

---

## 2. Adversarial suite — full ten-case confusion matrix

**Script**: `eval/adversarial_cases.py`. Ten hand-crafted attacks, each a
single deliberate change to an otherwise clean, fully-grounded narrative
(`eval/adversarial_cases.py`'s `base_sentences()`), run against
`tests.narrative_factories.make_sample_pack()`. Two runs are reported:
the deterministic stub classifier (`--stub`, matches the fast pytest
suite and shows the pipeline's *designed* per-check isolation) and the
real local NLI entailment model (default, no flag) — reported
separately because they tell different, both-important stories.

### 2a. Designed behavior (stub entailment classifier)

| # | Case | Description | Expected catcher | Caught by | Outcome |
|---|------|--------------|-------------------|-----------|---------|
| 1 | numeric_fabrication | A fabricated total amount not present anywhere in the evidence pack. | numeric | numeric | CAUGHT |
| 2 | entity_fabrication | A subject name that does not appear in the evidence pack. | entity | entity | CAUGHT |
| 3 | relationship_fabrication | Real names/numbers/dates, but a relationship between them that never happened. | entailment | entailment | CAUGHT |
| 4 | legal_conclusion | A prohibited legal conclusion ("committed money laundering"). | prohibited | prohibited | CAUGHT |
| 5 | date_outside_period | A real, grounded date outside the evidence pack's aggregate period. | temporal | temporal | CAUGHT |
| 6 | section_omission | The required "why" section is missing entirely. | completeness | completeness | CAUGHT |
| 7 | intent_speculation | Unfounded speculation about intent/motive, phrased plausibly. | prohibited | prohibited | CAUGHT |
| 8 | silent_rounding | A materially-rounded figure presented as the real one (128500.00 → "approximately 130,000.00"). | numeric | numeric | CAUGHT |
| 9 | system_disclosure | The narrative discloses its own detection system's internal output ("an anomaly score of 0.87"). | prohibited | numeric, prohibited | CAUGHT (2 checks — the disclosed score is itself a fabricated number, a real defense-in-depth result, not a test flaw) |
| 10 | single_digit_account | Single-digit account-number substitution (ACC-88213 → ACC-88214). | *(none — known blind spot)* | *(none)* | OK (no catch — as designed; see below) |

**10/10 behaved exactly as designed.** Raw output:
`eval/results/adversarial_suite_stub.json`.

### 2b. Real local NLI model (what actually happens against the production entailment model)

Running the same ten cases against the real `MoritzLaurer/DeBERTa-v3-
base-mnli-fever-anli` model (not the stub) produces a materially
different picture: **the real model flags entailment on 9 of 10 cases —
including six cases that have nothing to do with entailment at all**
(numeric_fabrication, entity_fabrication, date_outside_period,
section_omission, intent_speculation, system_disclosure). This is not a
bug in the test harness; it reproduces the same false-positive pattern
documented in LIMITATIONS.md — even the clean, correct baseline
narrative this suite builds every case from scores 0.39 overall on
entailment alone (4 of 6 sentences flagged) when checked against the
real model directly. The practical read: checks 1-4/prohibited/
completeness are exactly as reliable as table 2a shows (they're
deterministic and don't change between runs); the entailment check's
real-world signal is much noisier than the clean isolation in 2a
suggests, which is *why* it's weighted at only 0.10 of the aggregate
score. Raw output: `eval/results/adversarial_suite_real_nli.json`.

### The headline result

A human reviewer skimming a fluent, well-formatted draft would very
plausibly wave all three of these through:

- **relationship_fabrication** — every individual fact is real; only the
  *relationship* is invented. **Caught by the pipeline** (entailment,
  by design — table 2a).
- **silent_rounding** — a materially rounded figure ("approximately
  130,000.00" for a real 128,500.00) sounds like harmless imprecision.
  **Caught by the pipeline** (numeric — there is no tolerance for "close
  enough").
- **single_digit_account** — ACC-88214 instead of the real ACC-88213.
  **NOT caught by the deterministic checks, by design** (both
  `numeric.py`'s reference-code exclusion and `entity.py`'s negative
  lookahead exist specifically to avoid false-positiving on legitimate
  reference codes, and this attack exploits exactly that gap). The real
  entailment model happened to flag it in testing — but given how
  aggressively that same model over-flags clean cases (2b), that catch
  should be read as a plausible side-effect of general over-sensitivity,
  not a reliable, designed detection mechanism. **This is a real,
  currently unaddressed gap in this build**, reported here rather than
  hidden — see LIMITATIONS.md.

---

## 3. Detection evaluation at scale

**Script**: `eval/detection_at_scale.py` (`make eval-detection`). A
fresh 500-account synthetic dataset (matching Part 2's original scale),
generated and scored inside an isolated, rolled-back DB transaction —
this run adds nothing to the persistent demo database README.md
documents case refs against.

| Metric | Value |
|---|---|
| Accounts generated | 500 (180-day window, seed 42) |
| Accounts with an injected typology | 80 |
| Clean accounts | 420 |
| Typology instances injected | 60 (10 per typology × 6 typologies) |

### Typology recall

| Typology | Hits | Total | Recall |
|---|---|---|---|
| CIRCULAR_FLOW | 10 | 10 | 100.0% |
| DORMANT_REACTIVATION | 10 | 10 | 100.0% |
| HIGH_VELOCITY | 10 | 10 | 100.0% |
| RAPID_MOVEMENT | 10 | 10 | 100.0% |
| SMURFING | 10 | 10 | 100.0% |
| STRUCTURING | 10 | 10 | 100.0% |
| **OVERALL** | **60** | **60** | **100.0%** |

### False positives and case-level outcomes

| Metric | Value |
|---|---|
| Clean accounts flagged HIGH/MEDIUM | 12 / 420 (**2.9%**) |
| Cases opened | 72 (58 newly created, 14 reused) |
| Injected-typology instances that got an opened case | 38 / 60 |

The commonly-cited industry false-positive rate for transaction
monitoring is often quoted in the 90-95% range (i.e. only 5-10% of
alerts are ultimately substantive) — cited here as general, widely-
repeated industry commentary, not a specific sourced statistic, per the
blueprint's own caution about this figure. This run's 2.9% FP rate on
clean accounts is a materially different (better) measurement on
synthetic data with cleanly-separable injected patterns, and should be
read as "this detection layer works as designed on the patterns it was
built for," not as a claim that it would hold on ambiguous real-world
activity.

**Methodological note**: this evaluation ran inside a single DB
transaction that also contained this build's pre-existing demo accounts
(~90, from Parts 1-6's testing) alongside the 500 fresh ones — the
`accounts_evaluated`/`alerts_created`/band-count figures reflect that
combined population (ML ensemble scoring is relative to the population
it sees), which is why zero HIGH-band alerts appeared even for correctly
-recalled injected typologies (only 38/60 opened a case, since
`assemble_cases` only opens cases for HIGH/MEDIUM severity). **Typology
recall and the false-positive rate are unaffected** — both are scored
directly against the fresh 500-account manifest's ground truth,
independent of banding — but the "cases opened" secondary stat should be
read with that caveat. Raw output: `eval/results/detection_at_scale.json`,
`eval/results/detection_at_scale_ground_truth.json`.

---

## Reproducing these numbers

```bash
make eval-modes N=5           # ~15-25 min (real GPU inference)
make eval-adversarial-real    # ~1-2 min (real NLI model, no GPU LLM calls)
make adversarial               # ~instant (stub classifier)
make eval-detection            # ~1-2 min
```
