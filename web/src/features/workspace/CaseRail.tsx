import type { EvidencePack } from "@/api/types";
import { formatDate } from "@/lib/format";
import { useTraceStore } from "@/stores/traceStore";

function RailSection({ title, defaultOpen = true, children }: { title: string; defaultOpen?: boolean; children: React.ReactNode }) {
  return (
    <details open={defaultOpen} className="border-b border-rule">
      <summary className="cursor-pointer select-none px-4 py-3 font-ui text-2xs font-semibold uppercase tracking-wide text-ink-faint hover:text-ink-muted">
        {title}
      </summary>
      <div className="px-4 pb-4">{children}</div>
    </details>
  );
}

export function CaseRail({ pack }: { pack: EvidencePack | undefined }) {
  const highlightedRefs = useTraceStore((s) => s.highlightedSourceRefs);

  if (!pack) {
    return (
      <aside className="min-h-0 w-[260px] shrink-0 overflow-y-auto border-r border-rule bg-panel">
        <div className="p-4">
          <p className="font-ui text-xs text-ink-faint">No evidence pack built for this case yet.</p>
        </div>
      </aside>
    );
  }

  const subject = pack.subjects[0];

  return (
    <aside className="min-h-0 w-[260px] shrink-0 overflow-y-auto border-r border-rule bg-panel">
      <RailSection title="Subjects">
        {subject ? (
          <dl className="flex flex-col gap-1.5">
            <RailField label="Name" value={subject.legal_name} />
            <RailField label="Customer ref" value={subject.customer_ref} mono />
            <RailField label="Entity type" value={subject.entity_type} />
            <RailField label="Country" value={subject.country} />
            <RailField label="Risk rating" value={subject.risk_rating} />
            <RailField label="Occupation" value={subject.occupation} />
            <RailField label="Relationship since" value={formatDate(subject.relationship_start)} />
          </dl>
        ) : (
          <p className="font-ui text-xs text-ink-faint">No subject data.</p>
        )}
      </RailSection>

      <RailSection title="Typologies">
        {pack.typologies.length === 0 ? (
          <p className="font-ui text-xs text-ink-faint">No typologies recorded.</p>
        ) : (
          <ul className="flex flex-col gap-2.5">
            {pack.typologies.map((t) => {
              const isHighlighted = highlightedRefs.includes(t.code);
              return (
                <li
                  key={t.code}
                  className={`rounded-sm px-2 py-1.5 ${isHighlighted ? "bg-trace-bg" : ""}`}
                >
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="font-ui text-xs font-medium text-ink">{t.label}</span>
                    <span className="font-data text-2xs text-ink-faint">{t.weight.toFixed(2)}</span>
                  </div>
                  <div className="mt-1 h-1 w-full overflow-hidden rounded-sm bg-canvas">
                    <div className="h-full bg-ink-faint" style={{ width: `${Math.min(t.weight, 1) * 100}%` }} />
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </RailSection>

      <RailSection title="Timeline" defaultOpen={false}>
        {pack.transactions.length === 0 ? (
          <p className="font-ui text-xs text-ink-faint">No transactions in the evidence period.</p>
        ) : (
          <ul className="flex max-h-72 flex-col gap-1 overflow-y-auto">
            {pack.transactions.map((txn) => {
              const isHighlighted = highlightedRefs.includes(txn.txn_ref);
              return (
                <li
                  key={txn.txn_ref}
                  className={`rounded-sm px-1.5 py-1 font-data text-2xs ${isHighlighted ? "bg-trace-bg" : ""}`}
                >
                  <div className="flex justify-between text-ink">
                    <span>{formatDate(txn.executed_at)}</span>
                    <span>{txn.direction === "credit" ? "+" : "-"}{txn.amount}</span>
                  </div>
                  <div className="text-ink-faint">
                    {txn.txn_ref} · {txn.channel}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </RailSection>

      <RailSection title="ML findings" defaultOpen={false}>
        {Object.keys(pack.ml_findings).length === 0 ? (
          <p className="font-ui text-xs text-ink-faint">No ML ensemble findings for this case.</p>
        ) : (
          <pre className="whitespace-pre-wrap font-data text-2xs text-ink-muted">
            {JSON.stringify(pack.ml_findings, null, 2)}
          </pre>
        )}
      </RailSection>

      <RailSection title="Money-flow graph" defaultOpen={false}>
        <p className="font-ui text-xs text-ink-faint">Not yet visualized — planned for a future part.</p>
      </RailSection>
    </aside>
  );
}

function RailField({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-2">
      <dt className="font-ui text-2xs text-ink-faint">{label}</dt>
      <dd className={`text-right text-xs text-ink ${mono ? "font-data" : "font-ui"}`}>{value}</dd>
    </div>
  );
}
