import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { useCases } from "@/api/hooks";
import type { RiskBand } from "@/api/types";
import { AuthBadge } from "@/features/auth/AuthBadge";

import { CaseQueueTable } from "./CaseQueueTable";
import { useEnrichedCases } from "./useEnrichedCases";

const STATUS_OPTIONS = ["ALL", "OPEN", "CLOSED"] as const;
const BAND_OPTIONS: ("ALL" | RiskBand)[] = ["ALL", "HIGH", "MEDIUM", "LOW"];

export function CaseQueuePage() {
  const { data: cases, isLoading: casesLoading, error } = useCases();
  const { data: enriched, isLoading: enrichLoading } = useEnrichedCases(cases);

  const [status, setStatus] = useState<(typeof STATUS_OPTIONS)[number]>("ALL");
  const [band, setBand] = useState<(typeof BAND_OPTIONS)[number]>("ALL");
  const [search, setSearch] = useState("");

  const filtered = useMemo(() => {
    if (!enriched) return [];
    return enriched
      .filter((c) => status === "ALL" || c.status === status)
      .filter((c) => band === "ALL" || c.risk_band === band)
      .filter((c) => {
        if (!search.trim()) return true;
        const q = search.trim().toLowerCase();
        return c.case_ref.toLowerCase().includes(q) || (c.subjectName ?? "").toLowerCase().includes(q);
      })
      .sort((a, b) => {
        if (!a.deadline_at) return 1;
        if (!b.deadline_at) return -1;
        return new Date(a.deadline_at).getTime() - new Date(b.deadline_at).getTime();
      });
  }, [enriched, status, band, search]);

  return (
    <div className="min-h-full bg-canvas">
      <header className="flex items-start justify-between border-b border-rule bg-panel px-6 py-4">
        <div>
          <h1 className="font-ui text-lg font-semibold text-ink">Case Queue</h1>
          <p className="mt-0.5 font-ui text-xs text-ink-muted">SAR Copilot — active investigations</p>
        </div>
        <div className="flex items-center gap-3">
          <Link
            to="/data-entry"
            className="rounded-sm border border-rule bg-paper px-3 py-1.5 font-ui text-xs font-medium text-ink hover:bg-canvas"
          >
            + Add data
          </Link>
          <Link
            to="/metrics"
            className="rounded-sm border border-rule bg-paper px-3 py-1.5 font-ui text-xs font-medium text-ink hover:bg-canvas"
          >
            Quality Metrics
          </Link>
          <AuthBadge />
        </div>
      </header>

      <div className="flex flex-wrap items-center gap-3 border-b border-rule bg-panel px-6 py-3">
        <input
          type="search"
          placeholder="Search case ref or subject…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-64 rounded-sm border border-rule bg-paper px-2.5 py-1.5 font-ui text-sm text-ink placeholder:text-ink-faint focus-visible:border-trace"
        />
        <FilterGroup label="Status" value={status} options={STATUS_OPTIONS} onChange={setStatus} />
        <FilterGroup label="Risk band" value={band} options={BAND_OPTIONS} onChange={setBand} />
        <span className="ml-auto font-ui text-xs text-ink-faint">
          {filtered.length} of {enriched?.length ?? 0} cases
        </span>
      </div>

      <main className="px-6 py-4">
        {error ? (
          <p className="font-ui text-sm text-critical">Could not reach the backend: {String(error)}</p>
        ) : casesLoading || enrichLoading ? (
          <p className="font-ui text-sm text-ink-muted">Loading cases…</p>
        ) : (
          <div className="overflow-x-auto rounded-md border border-rule bg-panel">
            <CaseQueueTable cases={filtered} />
          </div>
        )}
      </main>
    </div>
  );
}

function FilterGroup<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: readonly T[];
  onChange: (v: T) => void;
}) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="font-ui text-2xs uppercase tracking-wide text-ink-faint">{label}</span>
      <div className="flex overflow-hidden rounded-sm border border-rule">
        {options.map((opt) => (
          <button
            key={opt}
            onClick={() => onChange(opt)}
            aria-pressed={value === opt}
            className={`px-2 py-1 font-ui text-xs ${
              value === opt ? "bg-ink text-paper" : "bg-paper text-ink-muted hover:bg-canvas"
            }`}
          >
            {opt}
          </button>
        ))}
      </div>
    </div>
  );
}
