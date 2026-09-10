import type { ReactNode } from "react";

type ChipTone = "neutral" | "verified" | "caution" | "critical" | "trace";

const TONE_CLASSES: Record<ChipTone, string> = {
  neutral: "bg-canvas text-ink-muted border-rule",
  verified: "bg-verified-bg text-verified border-transparent",
  caution: "bg-caution-bg text-caution border-transparent",
  critical: "bg-critical-bg text-critical border-transparent",
  trace: "bg-trace-bg text-trace border-transparent",
};

export function Chip({ tone = "neutral", children }: { tone?: ChipTone; children: ReactNode }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-sm border px-2 py-0.5 text-2xs font-ui font-medium leading-none ${TONE_CLASSES[tone]}`}
    >
      {children}
    </span>
  );
}
