import type { EvidenceItem } from "@/api/types";
import { useTraceStore } from "@/stores/traceStore";

export function EvidencePanel({ items }: { items: EvidenceItem[] }) {
  const activeKeys = useTraceStore((s) => s.activeEvidenceKeys);
  const pinnedId = useTraceStore((s) => s.pinnedSentenceId);
  const hoveredId = useTraceStore((s) => s.hoveredSentenceId);

  const byKey = new Map(items.map((i) => [i.key, i]));
  const activeItems = activeKeys.map((k) => byKey.get(k)).filter((i): i is EvidenceItem => Boolean(i));
  const isPinned = pinnedId !== null;
  const hasActive = pinnedId !== null || hoveredId !== null;

  return (
    <section aria-label="Evidence for selected sentence" className="flex flex-col gap-3 border-b border-rule p-4">
      <div className="flex items-center justify-between">
        <h2 className="font-ui text-2xs font-semibold uppercase tracking-wide text-ink-faint">Evidence</h2>
        {isPinned && <span className="font-ui text-2xs text-trace">pinned</span>}
      </div>

      {!hasActive ? (
        <p className="font-ui text-xs text-ink-faint">Hover or click a sentence to see the evidence it draws on.</p>
      ) : activeItems.length === 0 ? (
        <p className="font-ui text-xs text-caution">
          No evidence pack item text-matched this sentence — verify it manually.
        </p>
      ) : (
        <ul className="flex flex-col gap-2">
          {activeItems.map((item) => (
            <li key={item.key} className="rounded-sm border border-rule bg-canvas px-2.5 py-2">
              <div className="flex items-baseline justify-between gap-2">
                <span className="font-data text-xs font-medium text-ink">{item.display_value}</span>
                <span className="font-ui text-2xs uppercase text-ink-faint">{item.type}</span>
              </div>
              <div className="mt-1 font-ui text-2xs text-ink-faint">
                {item.source_table} · {item.key}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
