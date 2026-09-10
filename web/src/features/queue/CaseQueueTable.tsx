import { Link } from "react-router-dom";

import { Chip } from "@/components/ui/Chip";
import { daysUntil, formatDate, formatScore } from "@/lib/format";
import type { RiskBand } from "@/api/types";

import type { EnrichedCase } from "./useEnrichedCases";

const BAND_TONE: Record<RiskBand, "critical" | "caution" | "neutral"> = {
  HIGH: "critical",
  MEDIUM: "caution",
  LOW: "neutral",
};

function DeadlineCell({ deadlineAt }: { deadlineAt: string | null }) {
  const days = daysUntil(deadlineAt);
  if (days === null) {
    return <span className="font-data text-xs text-ink-faint">—</span>;
  }
  const tone = days <= 5 ? "critical" : days <= 10 ? "caution" : null;
  const colorClass = tone === "critical" ? "text-critical" : tone === "caution" ? "text-caution" : "text-ink-muted";
  return (
    <span className={`font-data text-xs ${colorClass}`}>
      {formatDate(deadlineAt)}
      <span className="ml-1.5 text-2xs">
        ({days < 0 ? `${Math.abs(days)}d overdue` : `${days}d`})
      </span>
    </span>
  );
}

function TypologyChips({ typologies }: { typologies: EnrichedCase["typologies"] }) {
  if (typologies.length === 0) {
    return <span className="text-2xs text-ink-faint">—</span>;
  }
  const shown = typologies.slice(0, 3);
  const overflow = typologies.length - shown.length;
  return (
    <div className="flex flex-wrap items-center gap-1">
      {shown.map((t) => (
        <Chip key={t.code} tone="neutral">
          {t.label}
        </Chip>
      ))}
      {overflow > 0 && <Chip tone="neutral">+{overflow}</Chip>}
    </div>
  );
}

export function CaseQueueTable({ cases }: { cases: EnrichedCase[] }) {
  if (cases.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-1 py-24 text-center">
        <p className="font-ui text-sm text-ink-muted">No cases match these filters.</p>
        <p className="font-ui text-xs text-ink-faint">Adjust status, risk band, or the search text and try again.</p>
      </div>
    );
  }

  return (
    <table className="w-full border-collapse text-left">
      <thead>
        <tr className="border-b border-rule">
          {["Case", "Subject", "Risk", "Typologies", "Deadline", "Status", "Assignee"].map((h) => (
            <th key={h} className="px-3 py-2 font-ui text-2xs font-medium uppercase tracking-wide text-ink-faint">
              {h}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {cases.map((c) => (
          <tr key={c.id} className="border-b border-rule hover:bg-panel">
            <td className="px-3 py-2.5">
              <Link
                to={`/cases/${c.id}`}
                className="font-data text-xs font-medium text-trace underline-offset-2 hover:underline"
              >
                {c.case_ref}
              </Link>
            </td>
            <td className="max-w-[180px] truncate px-3 py-2.5 font-ui text-sm text-ink" title={c.subjectName ?? undefined}>
              {c.subjectName ?? <span className="text-ink-faint">no evidence yet</span>}
            </td>
            <td className="px-3 py-2.5">
              <div className="flex items-center gap-2">
                <Chip tone={c.risk_band ? BAND_TONE[c.risk_band] : "neutral"}>{c.risk_band ?? "—"}</Chip>
                <span className="font-data text-xs text-ink-muted">{formatScore(c.risk_score)}</span>
              </div>
            </td>
            <td className="px-3 py-2.5">
              <TypologyChips typologies={c.typologies} />
            </td>
            <td className="px-3 py-2.5">
              <DeadlineCell deadlineAt={c.deadline_at} />
            </td>
            <td className="px-3 py-2.5">
              <span className="font-ui text-xs text-ink-muted">{c.status}</span>
            </td>
            <td className="px-3 py-2.5">
              <span className="font-ui text-xs text-ink-faint">Unassigned</span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
