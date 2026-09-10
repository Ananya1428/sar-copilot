import type { NarrativeSentence } from "@/api/types";
import { useTraceStore } from "@/stores/traceStore";

/**
 * The signature interaction (blueprint §16.7): hover a sentence -> every
 * other sentence dims to opacity 0.35, the hovered sentence gets a
 * --trace-bg highlight. Click pins the trace (persists until dismissed or
 * another sentence is clicked) — pinning wins over hover entirely, so
 * moving the mouse over other sentences while pinned does not change
 * which one drives the evidence panel. This is the one piece of motion in
 * the whole product.
 *
 * A real `<button>` (not a styled `<div>`) with `aria-describedby`
 * pointing at a hidden per-sentence evidence description, per the
 * blueprint's accessibility floor — keyboard focus drives the same trace
 * hover does, so the interaction works without a mouse.
 *
 * Deliberately does NOT compute grounded evidence itself — that's derived
 * centrally in NarrativePane from whichever sentence is active
 * (pinned ?? hovered), so the evidence panel can never fall out of sync
 * with what's visually highlighted.
 */
export function SentenceButton({
  sentence,
  evidenceSummary,
}: {
  sentence: NarrativeSentence;
  evidenceSummary: string;
}) {
  const hoveredId = useTraceStore((s) => s.hoveredSentenceId);
  const pinnedId = useTraceStore((s) => s.pinnedSentenceId);
  const setHovered = useTraceStore((s) => s.setHovered);
  const setPinned = useTraceStore((s) => s.setPinned);

  const active = pinnedId ?? hoveredId;
  const isActive = active === sentence.ordinal;
  const anyActive = active !== null;
  const evidenceDescId = `evidence-desc-${sentence.ordinal}`;

  function handleEnter() {
    if (pinnedId === null) setHovered(sentence.ordinal);
  }
  function handleLeave() {
    if (pinnedId === null) setHovered(null);
  }
  function handleFocus() {
    if (pinnedId === null) setHovered(sentence.ordinal);
  }
  function handleBlur() {
    if (pinnedId === null) setHovered(null);
  }
  function handleClick() {
    setPinned(pinnedId === sentence.ordinal ? null : sentence.ordinal);
  }

  return (
    <button
      type="button"
      id={`sentence-${sentence.ordinal}`}
      aria-describedby={evidenceDescId}
      aria-pressed={pinnedId === sentence.ordinal}
      onMouseEnter={handleEnter}
      onMouseLeave={handleLeave}
      onFocus={handleFocus}
      onBlur={handleBlur}
      onClick={handleClick}
      className={`block w-full rounded-sm px-3 py-1.5 text-left font-narrative text-base leading-[1.7] text-ink transition-opacity duration-trace ${
        isActive ? "bg-trace-bg opacity-100" : anyActive ? "opacity-35" : "opacity-100"
      }`}
    >
      {sentence.text}
      <span id={evidenceDescId} className="sr-only">
        {evidenceSummary}
      </span>
    </button>
  );
}
