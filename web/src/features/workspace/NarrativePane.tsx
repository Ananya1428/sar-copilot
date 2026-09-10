import { useEffect, useMemo } from "react";

import type { EvidenceItem, Narrative } from "@/api/types";
import { groundedItems } from "@/lib/grounding";
import { useTraceStore } from "@/stores/traceStore";

import { sectionLabel } from "./sections";
import { SentenceButton } from "./SentenceButton";

const TXN_KEY_RE = /^transaction\.(TXN-[^.]+)\./;
const TYPOLOGY_KEY_RE = /^typology\.([A-Z_]+)\./;

function sourceRefsFor(items: EvidenceItem[]): string[] {
  const refs = new Set<string>();
  for (const item of items) {
    const txnMatch = TXN_KEY_RE.exec(item.key);
    if (txnMatch) refs.add(txnMatch[1]);
    const typologyMatch = TYPOLOGY_KEY_RE.exec(item.key);
    if (typologyMatch) refs.add(typologyMatch[1]);
  }
  return [...refs];
}

export function NarrativePane({ narrative, evidenceItems }: { narrative: Narrative; evidenceItems: EvidenceItem[] }) {
  const hoveredId = useTraceStore((s) => s.hoveredSentenceId);
  const pinnedId = useTraceStore((s) => s.pinnedSentenceId);
  const setActiveEvidence = useTraceStore((s) => s.setActiveEvidence);

  const activeOrdinal = pinnedId ?? hoveredId;

  // Single source of truth for "what does the active sentence ground to" —
  // derived here from evidence pack items + sentence TEXT (not the LLM's
  // own evidence_keys array, per Part 5's caution about trusting a model's
  // self-reported citations), and pushed into the shared store so the
  // evidence panel and case rail can never disagree with what's
  // highlighted in the narrative itself.
  useEffect(() => {
    if (activeOrdinal === null) {
      setActiveEvidence([], []);
      return;
    }
    const sentence = narrative.sentences.find((s) => s.ordinal === activeOrdinal);
    if (!sentence) {
      setActiveEvidence([], []);
      return;
    }
    const grounded = groundedItems(sentence.text, evidenceItems);
    setActiveEvidence(
      grounded.map((g) => g.key),
      sourceRefsFor(grounded),
    );
  }, [activeOrdinal, narrative.sentences, evidenceItems, setActiveEvidence]);

  const evidenceSummaryByOrdinal = useMemo(() => {
    const map = new Map<number, string>();
    for (const sentence of narrative.sentences) {
      const grounded = groundedItems(sentence.text, evidenceItems);
      map.set(
        sentence.ordinal,
        grounded.length > 0
          ? `Grounded in: ${grounded.map((g) => g.display_value).join(", ")}`
          : "No matching evidence items found for this sentence.",
      );
    }
    return map;
  }, [narrative.sentences, evidenceItems]);

  const groups = useMemo(() => {
    const out: { section: string | null; sentences: typeof narrative.sentences }[] = [];
    for (const sentence of narrative.sentences) {
      const last = out[out.length - 1];
      if (last && last.section === sentence.section) {
        last.sentences.push(sentence);
      } else {
        out.push({ section: sentence.section, sentences: [sentence] });
      }
    }
    return out;
  }, [narrative.sentences]);

  return (
    <div className="mx-auto flex max-w-narrative flex-col gap-6 px-8 py-8">
      {groups.map((group, i) => (
        <section key={i} aria-label={sectionLabel(group.section)}>
          <h2 className="mb-2 font-ui text-2xs font-semibold uppercase tracking-wide text-ink-faint">
            {sectionLabel(group.section)}
          </h2>
          <div className="flex flex-col gap-1">
            {group.sentences.map((sentence) => (
              <SentenceButton
                key={sentence.ordinal}
                sentence={sentence}
                evidenceSummary={evidenceSummaryByOrdinal.get(sentence.ordinal) ?? ""}
              />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
