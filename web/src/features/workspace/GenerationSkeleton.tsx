import { useEffect, useState } from "react";

import { NARRATIVE_SECTIONS } from "./sections";

/**
 * Section-by-section skeleton loading during generation (blueprint §18
 * Screen 2) — matches the backend's real section-scoped generation
 * (engine.py generates one section at a time), rather than a single
 * 45-second spinner for HYBRID mode on this machine's GPU-backed Ollama.
 *
 * The backend doesn't stream per-section progress today (a single POST
 * resolves once the whole narrative is done), so this can't show *real*
 * per-section completion — instead it honestly communicates "working
 * through sections in order" by cycling which section row is the active
 * one, and swaps to the real content in one shot the moment the response
 * lands. Nothing here is presented as an actually-completed section.
 */
export function GenerationSkeleton() {
  const [activeIndex, setActiveIndex] = useState(0);

  useEffect(() => {
    const id = setInterval(() => {
      setActiveIndex((i) => (i + 1) % NARRATIVE_SECTIONS.length);
    }, 2200);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="flex flex-col gap-6" aria-live="polite" aria-busy="true">
      <p className="font-ui text-xs text-ink-muted">Generating narrative — this can take up to a minute in HYBRID mode…</p>
      {NARRATIVE_SECTIONS.map((section, i) => (
        <div key={section.id} className="flex flex-col gap-2">
          <span
            className={`font-ui text-2xs font-medium uppercase tracking-wide ${
              i === activeIndex ? "text-trace" : "text-ink-faint"
            }`}
          >
            {section.label}
            {i === activeIndex && <span className="ml-1.5">·  drafting…</span>}
          </span>
          <SkeletonLines active={i === activeIndex} />
        </div>
      ))}
    </div>
  );
}

function SkeletonLines({ active }: { active: boolean }) {
  const widths = ["92%", "78%", "85%"];
  return (
    <div className="flex flex-col gap-2">
      {/* Instant style swap, not an animated transition — the trace
          interaction is the product's only piece of motion. */}
      {widths.map((w, i) => (
        <div key={i} className={`h-[18px] rounded-sm bg-rule ${active ? "opacity-60" : "opacity-30"}`} style={{ width: w }} />
      ))}
    </div>
  );
}
