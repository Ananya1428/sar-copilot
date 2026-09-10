import { create } from "zustand";

/**
 * The connective tissue for the signature hover-to-trace interaction
 * (blueprint §16.7 / §19) — one state object all three workspace panes
 * subscribe to. Hover sets `hoveredSentenceId`; click "pins" the trace by
 * setting `pinnedSentenceId`, which then wins over hover until dismissed.
 */

export interface TraceState {
  hoveredSentenceId: number | null;
  pinnedSentenceId: number | null;
  /** evidence item keys the active (pinned, else hovered) sentence grounds to */
  activeEvidenceKeys: string[];
  /** typology codes / txn refs referenced by the active sentence's evidence, for rail highlighting */
  highlightedSourceRefs: string[];

  setHovered: (sentenceId: number | null) => void;
  setPinned: (sentenceId: number | null) => void;
  setActiveEvidence: (evidenceKeys: string[], sourceRefs: string[]) => void;
  clear: () => void;
}

export const useTraceStore = create<TraceState>((set) => ({
  hoveredSentenceId: null,
  pinnedSentenceId: null,
  activeEvidenceKeys: [],
  highlightedSourceRefs: [],

  setHovered: (sentenceId) => set({ hoveredSentenceId: sentenceId }),
  setPinned: (sentenceId) => set({ pinnedSentenceId: sentenceId }),
  setActiveEvidence: (evidenceKeys, sourceRefs) =>
    set({ activeEvidenceKeys: evidenceKeys, highlightedSourceRefs: sourceRefs }),
  clear: () => set({ hoveredSentenceId: null, pinnedSentenceId: null, activeEvidenceKeys: [], highlightedSourceRefs: [] }),
}));
