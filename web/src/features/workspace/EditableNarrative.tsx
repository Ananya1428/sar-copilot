import { useState } from "react";

import type { Narrative } from "@/api/types";
import { sectionLabel } from "./sections";

export function EditableNarrative({
  narrative,
  onSave,
  onCancel,
  isSaving,
}: {
  narrative: Narrative;
  onSave: (sentences: { text: string; section: string | null; evidence_keys: string[] }[]) => void;
  onCancel: () => void;
  isSaving: boolean;
}) {
  const [texts, setTexts] = useState(() => narrative.sentences.map((s) => s.text));

  function updateText(index: number, value: string) {
    setTexts((prev) => prev.map((t, i) => (i === index ? value : t)));
  }

  function handleSave() {
    onSave(
      narrative.sentences.map((s, i) => ({
        text: texts[i],
        section: s.section,
        evidence_keys: s.evidence_keys,
      })),
    );
  }

  return (
    <div className="mx-auto flex max-w-narrative flex-col gap-6 px-8 py-8">
      <p className="font-ui text-xs text-ink-muted">
        Editing creates a new version and re-runs verification against the same evidence pack.
      </p>
      {narrative.sentences.map((sentence, i) => (
        <div key={sentence.ordinal}>
          <h2 className="mb-2 font-ui text-2xs font-semibold uppercase tracking-wide text-ink-faint">
            {sectionLabel(sentence.section)}
          </h2>
          <textarea
            value={texts[i]}
            onChange={(e) => updateText(i, e.target.value)}
            rows={2}
            className="w-full resize-y rounded-sm border border-rule bg-paper px-3 py-2 font-narrative text-base leading-[1.7] text-ink focus-visible:border-trace"
          />
        </div>
      ))}
      <div className="flex gap-2">
        <button
          onClick={handleSave}
          disabled={isSaving}
          className="rounded-sm border border-trace bg-trace-bg px-3 py-1.5 font-ui text-xs font-medium text-trace disabled:opacity-50"
        >
          {isSaving ? "Saving…" : "Save as new version"}
        </button>
        <button
          onClick={onCancel}
          disabled={isSaving}
          className="rounded-sm border border-rule bg-paper px-3 py-1.5 font-ui text-xs font-medium text-ink-muted hover:bg-canvas"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
