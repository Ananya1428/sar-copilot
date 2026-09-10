# Five-minute demo script

The actual walkthrough for this build (blueprint §24.2), using real seeded
data and the real screens — not a hypothetical. Start from a clean
`docker compose up -d` (see README's Quick start) and open
`http://localhost:8080`.

Beats 4, 5, and 7 below (the trace, the guardrail, the audit chain) are
the product — if you're short on time, show only those three.

---

## 1. The problem (Case Queue)

Open `http://localhost:8080/`. This is the Case Queue: a dense table, not
cards — case ref, subject, risk band + numeric score, typology chips,
deadline (colour-coded by urgency), status. Point out **CASE-0005**
(Michael Brooks, HIGH band, 0.934) — a multi-typology case (circular flow
+ deviation from declared profile) — as the kind of case an analyst would
actually pick up first, sorted to the top by deadline.

## 2. Detection (case rail)

Click into **CASE-0003** (Ashley Dyer, HIGH, 0.894 — four typologies:
circular flow, cross-border exposure, deviation from profile, rapid
movement). In the left rail, expand **Typologies** — each has a weight
bar. Expand **Timeline** to show the real transaction list each alert
fired against. Expand **ML findings** and **Money-flow graph** to be
honest about what's live (ML findings render when present; the money-flow
graph is explicitly labeled "not yet visualized" rather than faked).

## 3. Generation (section-by-section)

Click **Regenerate** with **HYBRID** selected. While it runs (real GPU
inference through Ollama, on the order of a minute — see EVALUATION.md
for the real measured latency), point out the section-by-section skeleton
loading state, not a spinner: it's honestly communicating "working
through sections in order," matching how `engine.py` actually generates
one section at a time.

## 4. The trace (hover a sentence) — THE signature interaction

Once the narrative renders, hover over any sentence in the centre pane.
Every other sentence dims to 35% opacity; the hovered one gets a highlight;
the right-hand Evidence panel populates with exactly the evidence items
that sentence's *text* grounds to (scanned client-side against the
evidence pack, not trusted from the LLM's own citations). Click to pin
the trace, then hover a sentence naming a typology (e.g. "Circular flow /
round-tripping...") and show the left rail's matching **Typologies** row
light up too — the same trace state driving all three panes at once.

## 5. The guardrail (two kinds of catch)

**A fabricated amount, caught by regex:** in the Verification panel on
the right, click a failed check (if the current draft has one — TEMPLATE
mode's own known numeric-check limitation, see LIMITATIONS.md, means this
is not hard to find) to open **Verification Detail**: the offending
number is highlighted in place in the sentence — `▸88888888.88◂` style —
with nearby real evidence values shown for comparison.

**A relationship fabrication, caught only by entailment:** this is the
headline adversarial result (EVALUATION.md's confusion matrix) —
`eval/adversarial_cases.py`'s `relationship_fabrication` case: every
individual fact in the sentence is real and grounded (a real name, a real
amount, a real date), but the *relationship* between them never happened.
Checks 1-4 all pass it; only entailment catches it. Run it live:

```bash
docker compose exec api python eval/adversarial_cases.py --stub
```

## 6. Degradation (template fallback)

Point out `generation_mode: TEMPLATE_FALLBACK` on any narrative that
shows it (or trigger one: HYBRID mode exhausting all retries falls back
to the deterministic template rather than ever shipping an unverified
draft) — the system's answer to "what happens when the LLM keeps
failing" is "it stops trying and hands back something grounded by
construction," not silence and not a bad guess.

## 7. Audit (re-verify the chain) — live corruption demo

Click **Audit trail** from the case workspace header. The chain-integrity
header shows **CHAIN INTACT** on load (a real `POST /audit/verify-chain`
call, not cached). Now corrupt a record for real, live, in front of the
audience:

```bash
docker compose exec postgres psql -U sar -d sarcopilot -c \
  "SELECT id, action FROM audit_records WHERE case_id='<case-uuid>' ORDER BY occurred_at LIMIT 3;"

docker compose exec postgres psql -U sar -d sarcopilot -c \
  "UPDATE audit_records SET after_state = '{\"tampered\": true}'::jsonb WHERE id = '<record-id>';"
```

Click **Re-verify chain** in the browser. It reports **CHAIN BROKEN**
with the exact record id and a hash-mismatch reason, and highlights that
row inline in the ledger — live, not a canned screenshot (this exact
sequence is documented working end-to-end in the Part 6c build notes).
Restore it and re-verify to show recovery:

```bash
docker compose exec postgres psql -U sar -d sarcopilot -c \
  "UPDATE audit_records SET after_state = '<original-json>'::jsonb WHERE id = '<record-id>';"
```

## 8. Reproducibility (byte-identical regen)

```bash
docker compose exec api python eval/compare_modes.py 1
```

Points at the reproducibility section of the output: TEMPLATE mode is
byte-identical across repeated calls with the same pack + seed by
construction (no LLM call at all); HYBRID's reproducibility is tested
empirically against the real Ollama call, not assumed — see
EVALUATION.md for what was actually found.

## 9. Results (the honest trade-off table)

Open `EVALUATION.md`. This is the actual comparison across TEMPLATE /
HYBRID / FREEFORM on real cases — including wherever HYBRID underperforms
TEMPLATE or FREEFORM. The real finding worth saying out loud: TEMPLATE
mode's own numeric check fails on some cases due to a percentage-
formatting gap between the deterministic renderer and the evidence
schema (documented in LIMITATIONS.md) — an honest example of what this
kind of evaluation is *for*: finding the gap between "the safe mode" and
"the mode that reliably passes its own safety check," which are not
automatically the same thing.
