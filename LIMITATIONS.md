# Limitations, Risks, and Ethics

Per blueprint §26 — organized as Technical limitations and Ethical
considerations. Written from what this build actually produced and
observed across Parts 1-7, not the blueprint's illustrative text.
Concrete evidence for every technical claim below is in `EVALUATION.md`
and the `eval/results/` JSON files that back it.

---

## Technical limitations

### Synthetic data is cleaner than real laundering

Every case in this build, seeded or freshly generated, comes from
`api/app/domain/ingestion/synthetic.py` — deliberately injected typology
patterns on top of Faker-generated background activity. Real financial
crime doesn't announce itself with a single clean typology signature; it
is adversarial, adapts to detection, and is mixed in with far more
ambiguous legitimate activity than this generator produces. The
detection evaluation's 100% typology recall (`EVALUATION.md`) should be
read as "the detection layer correctly recognizes the exact patterns it
was told to look for," not "this system catches real laundering at a
100% rate" — those are very different claims, and only the first one is
what was actually tested.

### The entailment check's false-positive pattern is real and measured, not hypothetical

The general-domain NLI entailment model (`MoritzLaurer/DeBERTa-v3-base-
mnli-fever-anli`, not fine-tuned on financial-crime text) genuinely
false-positives on the terse, telegraphic sentence style this system's
deterministic templates and prompts produce. Two independent, real data
points:

- The hand-built adversarial fixture's clean, 100%-correct baseline
  narrative (`eval/adversarial_cases.py`'s `base_sentences()`) scores
  **0.39 overall on the entailment check alone** — 4 of 6 sentences
  flagged "not entailed" (label=neutral) despite every fact being
  accurate and grounded.
- A real narrative generated against live seeded data (CASE-0003,
  TEMPLATE mode, verification otherwise fully passing at 0.969 overall)
  scored **0.686 on entailment** — below that check's own internal pass
  threshold.

This is mitigated architecturally (entailment carries only 0.10 of the
aggregate weight and HIGH, not CRITICAL, severity — see `pipeline.py`'s
`WEIGHTS`), so it does not by itself block a correct narrative from
passing overall verification. But it means the entailment sub-score, on
its own, is the least reliable of the six checks and should never be
read by an analyst as an independent confidence signal without that
context — a low entailment score is common on correct output, not
necessarily a red flag.

### TEMPLATE mode is not automatically verification-clean

This is the single most important finding in this evaluation
(`EVALUATION.md`). The deterministic template renderer
(`domain/narrative/deterministic.py`) computes some derived, human-
readable values from raw evidence — e.g. a circular-flow cycle's
retention percentage is rendered as `raw_fraction * 100` — but the
`EvidencePack`'s own `allowed_numbers()` set (blueprint §14.1) is built
only from literal `EvidenceItem` display values, which store the raw
fraction (`"0.797"`), never the rendered percentage (`"79.7"`). The
numeric check correctly can't find `"79.7"` in the allowed set, and
flags TEMPLATE's own, entirely accurate output as an ungrounded number.
The same gap affects a fixed system threshold (the 48-hour rapid-
movement window) rendered into prose: it's a detection-rule parameter,
not an evidence-backed fact, and was never meant to be in
`allowed_numbers()` at all.

The practical effect, observed directly: on the real cases evaluated,
TEMPLATE mode — the mode explicitly designed as the safe, always-
available fallback (blueprint §22: "never cut... the deterministic
fallback") — fails its own numeric check whenever the underlying case
involves a percentage-bearing typology like circular flow or rapid
movement. This does not mean TEMPLATE mode fabricates anything; it means
the verification pipeline's grounding vocabulary (raw evidence values
only) and the template renderer's presentation choices (percentage
conversion for readability) have drifted apart. "The safe mode" and "the
mode that reliably passes its own safety check" turned out, on real
testing, not to be automatically the same claim — which is exactly the
kind of gap this evaluation exercise exists to surface, not paper over.
This is a real, current gap in this build, left unfixed per Part 7's
scope (documentation and evaluation only, no application code changes).

### Regex-based entity/numeric extraction has real, specific edge cases

Two concrete bugs found and fixed during Part 5's live-data testing,
worth naming because the *class* of bug (not just the specific instance)
is a standing limitation of any regex-based grounding approach:

- **Comma-truncation**: Faker-generated occupations ("Geologist,
  engineering") truncate at the comma under the entity regex's word-
  sequence pattern, which would otherwise reject a correctly-grounded
  longer value as if only the truncated prefix mattered. Fixed via a
  full-string-match check at the same text position
  (`entity.py`'s `_matches_full_item_at`), but the underlying pattern —
  any regex-captured span that's a strict prefix of a real grounded
  value — is a standing risk for any future data source with different
  punctuation conventions.
- **Reference-code / hyphen adjacency**: an early version of the numeric
  check's reference-code exclusion only excluded the single character
  immediately after a hyphen, so a match starting one digit later in the
  same run (e.g. `"471"` inside `"CUS-4471"`) still slipped through as a
  spurious "ungrounded number." Fixed by excluding the reference code's
  full matched span, not just its first character.

More generally: lowercase entities are missed entirely (the entity check
only looks for capitalized sequences), and sentence-initial capitalized
words are deliberately exempted to avoid false-positiving on ordinary
sentence structure — which means a proper noun that happens to start a
sentence AND is only one word long is invisible to this check. Both are
documented, accepted trade-offs, not oversights, but real detection gaps
nonetheless.

### A single-digit account-number substitution is an undesigned-for blind spot

`numeric.py`'s reference-code exclusion and `entity.py`'s negative
lookahead both exist specifically so a legitimate account reference like
`"ACC-88213"` is never flagged as an ungrounded number or entity. That
same exclusion means a fabricated `"ACC-88214"` — a single digit off — is
structurally invisible to checks 1 and 2 by construction, confirmed
empirically in the ten-case adversarial suite (`EVALUATION.md`). The
real local entailment model did flag this case in testing, but given the
same model's measured tendency to over-flag almost everything on this
sentence style (see above), that catch should be read as a plausible
side-effect of general over-sensitivity, not a reliable, designed
detection mechanism for this specific attack class. This is a genuine,
currently unaddressed gap.

### FREEFORM mode fails silently, not gracefully

`engine.py`'s `_generate_freeform` makes exactly one LLM call with no
retry loop (unlike HYBRID's up-to-3-attempt retry-then-fallback). A
single malformed response — the model not returning parseable JSON, or
returning zero sentences — produces an empty narrative body with no
verification report at all. Observed directly during evaluation: the
same case, same seed, produced a fully-parseable FREEFORM narrative on
one run and a completely empty one on another (LLM output is not
strictly deterministic even at temperature 0.1 with a fixed seed — see
`EVALUATION.md`'s reproducibility section). This is treated as a
deliberate non-issue for this build (FREEFORM is never used in
production; it exists only as Part 7's benchmark baseline for *why*
constrained, section-scoped generation matters — blueprint §13.2) but
would need real retry/failure handling before FREEFORM could be anything
but a benchmark.

### No real-world validation

No compliance professional with access to actual filed SARs has reviewed
this system's output against real cases — and cannot, given SAR
confidentiality requirements. Every evaluation number in this repository
is against synthetic data and hand-built adversarial fixtures. This is a
hard ceiling on what any number in `EVALUATION.md` can claim.

### Single-jurisdiction scope

Built to US FinCEN SAR narrative conventions only (the five-section
structure: introduction, subject identification, activity description,
basis for suspicion, actions taken). Other jurisdictions' regimes (e.g.
FIU-IND STR, goAML) are not implemented — not even as stubs — despite
being named as extension targets in the blueprint's roadmap.

### Model size trade-off

An 8B-parameter model (`llama3.1:8b-instruct-q4_K_M`) was chosen
specifically for local, single-GPU deployability (confidentiality is a
hard architectural requirement — see below), at a measurable fluency
cost against a larger hosted model. The verification pipeline exists
precisely because this trade-off is real, not because it's been
eliminated.

---

## Ethical considerations

### Bias

Several detection features (Part 2) — counterparty geography, cash
intensity, transaction velocity relative to a declared profile — are
also legitimate, unremarkable characteristics of specific populations:
remittance corridors to particular countries, cash-based small
businesses, and recent migrants with thin credit/onboarding histories.
Over-flagging on these features causes real, asymmetric harm (frozen
accounts, de-banking, financial exclusion) concentrated on exactly the
populations least able to absorb it. This build implements no fairness
audit and no formal fairness constraint in composite scoring — that gap
is named here explicitly, not silently left out. The 500-account
detection evaluation in `EVALUATION.md` reports an aggregate false-
positive rate only; it does not, and currently cannot, break that rate
down by any protected or proxy characteristic, because no such
segmentation was built.

### Deskilling

If an analyst's daily practice becomes editing machine drafts rather
than composing narratives from evidence, the underlying skill of
reasoning from raw transaction data to a written suspicion narrative can
atrophy over time. This build's partial mitigation is structural: the
hover-to-trace interaction (blueprint §16.7) surfaces *why* each claim is
made — which evidence it draws on — rather than presenting a narrative as
a finished black box to be proofread. That keeps an analyst in the loop
of *reasoning*, not just spell-checking, but it does not eliminate the
underlying risk, only soften it.

### Automation bias — named as the most serious risk in this product

A confident, fluently-written, well-formatted draft is more likely to be
rubber-stamped than a blank page or a rough note would be — regardless of
whether the draft is actually correct. This is true independent of how
good the verification pipeline is, because the failure mode is *human*,
not technical: an analyst under deadline pressure, shown a narrative that
reads well and carries a green "PASSED" badge, has every incentive to
trust it. This build's mitigations are: always-visible verification
scores (never hidden behind a click), per-sentence grounding exposed
through the trace interaction rather than only in a separate report, low-
entailment sentences visually flagged rather than silently averaged away,
and an audit record for every narrative-affecting action. None of these
*prevent* automation bias — they reduce the friction of catching it,
which is the most this kind of system honestly can claim to do. This is,
per the blueprint's own framing (and this build agrees), the single most
serious risk in the whole product — more serious than any individual
regex gap or model limitation above.

### Confidentiality — verified true in this build, not just claimed

Local-only inference is a hard architectural requirement, not an
optimization: both models (Llama 3.1 8B via Ollama, the DeBERTa
entailment model) run inside this build's own Docker network, with no
code path anywhere in `api/app/domain/narrative/llm_client.py` or
`verification/semantic.py` that calls an external hosted API. This was
directly confirmed during Part 6c's Docker integration work — the
frontend's every API call was traced through nginx to the local `api`
service, never leaving the `sarnet` bridge network. Any future hosted-API
path in the narrative-generation or verification data path would violate
this build's own stated architecture and must not ship.

### Surveillance

AML systems are financial surveillance infrastructure by construction —
this one included. The SAR regime's real-world effectiveness is
genuinely and openly contested in the policy literature (conviction
rates relative to reporting volume are frequently cited as low), and
that debate is acknowledged here rather than papered over with a
"protecting the financial system" framing that treats the surveillance
trade-off as costless. Nothing in this build's design changes that
underlying trade-off; it only affects how a report gets written once an
institution has already decided to file one.

---

## Prominent statement

This is a demonstrator built on **synthetic data only**. It does not
file to FinCEN or any regulator, has not been validated against real
SAR filings or reviewed by a compliance professional with access to real
cases, and must never be used with real customer data.
