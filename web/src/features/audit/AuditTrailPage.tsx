import { useEffect } from "react";
import { Link, useParams } from "react-router-dom";
import type { UseMutationResult } from "@tanstack/react-query";

import { useAuditTrail, useVerifyChain } from "@/api/hooks";
import type { AuditRecord, ChainVerifyResult } from "@/api/types";
import { StatusIcon } from "@/components/ui/StatusIcon";

/** Takes the verify-chain mutation as a prop rather than owning its own —
 * the ledger below needs to read the SAME live result (to highlight
 * whichever record broke_at names), so there must be exactly one
 * mutation instance shared between this header and the record list, not
 * two independent ones that could disagree. */
function ChainIntegrityHeader({
  caseId,
  verify,
}: {
  caseId: string;
  verify: UseMutationResult<ChainVerifyResult, unknown, string, unknown>;
}) {
  // A "persistent chain-integrity header" (blueprint §18 Screen 5) should
  // have a real answer on load, not just after the analyst clicks a
  // button — so check once on mount. The button below always re-triggers
  // a fresh network call (a mutation, never a cached read), so "Re-verify
  // chain" is never showing a stale result.
  useEffect(() => {
    verify.mutate(caseId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId]);

  const result = verify.data;
  const checking = verify.isPending;

  return (
    <div
      className={`flex items-center justify-between border-b px-6 py-4 ${
        result && !result.valid ? "border-critical bg-critical-bg" : "border-rule bg-panel"
      }`}
    >
      <div>
        <p className="font-ui text-2xs font-semibold uppercase tracking-wide text-ink-faint">Chain integrity</p>
        {checking ? (
          <p className="mt-1 font-ui text-sm text-ink-muted">Verifying hash chain…</p>
        ) : result ? (
          <div className="mt-1 flex items-center gap-2">
            <StatusIcon status={result.valid ? "verified" : "critical"} label={result.valid ? "Chain intact" : "Chain broken"} />
          </div>
        ) : (
          <p className="mt-1 font-ui text-sm text-ink-faint">Not yet verified.</p>
        )}
        {result && !result.valid && (
          <p className="mt-2 max-w-2xl font-data text-xs text-critical">
            broken at record {result.broken_at} — {result.reason}
          </p>
        )}
      </div>
      <button
        onClick={() => verify.mutate(caseId)}
        disabled={checking}
        className="shrink-0 rounded-sm border border-ink bg-ink px-3 py-1.5 font-ui text-xs font-medium text-paper disabled:opacity-50"
      >
        {checking ? "Verifying…" : "Re-verify chain"}
      </button>
    </div>
  );
}

function RecordRow({ record, isBroken }: { record: AuditRecord; isBroken: boolean }) {
  return (
    <li
      id={`record-${record.id}`}
      className={`border-b border-rule px-6 py-3 ${isBroken ? "bg-critical-bg" : ""}`}
    >
      <details>
        <summary className="flex cursor-pointer select-none flex-wrap items-center gap-3">
          <span className="font-data text-xs text-ink-muted">{new Date(record.occurred_at).toLocaleString()}</span>
          <span className="rounded-sm border border-rule bg-panel px-2 py-0.5 font-ui text-2xs font-medium uppercase tracking-wide text-ink">
            {record.action}
          </span>
          <span className="font-ui text-2xs text-ink-faint">{record.actor_id ? record.actor_id : "system"}</span>
          {isBroken && <StatusIcon status="critical" label="Tampered — hash mismatch" />}
          <span className="ml-auto font-data text-2xs text-ink-faint">{record.record_hash.slice(0, 16)}…</span>
        </summary>
        <div className="mt-3 grid grid-cols-1 gap-3 pl-1 md:grid-cols-3">
          <div>
            <p className="font-ui text-2xs font-semibold uppercase tracking-wide text-ink-faint">Before</p>
            <pre className="mt-1 overflow-x-auto rounded-sm bg-canvas p-2 font-data text-2xs text-ink-muted">
              {record.before_state ? JSON.stringify(record.before_state, null, 2) : "—"}
            </pre>
          </div>
          <div>
            <p className="font-ui text-2xs font-semibold uppercase tracking-wide text-ink-faint">After</p>
            <pre className="mt-1 overflow-x-auto rounded-sm bg-canvas p-2 font-data text-2xs text-ink-muted">
              {record.after_state ? JSON.stringify(record.after_state, null, 2) : "—"}
            </pre>
          </div>
          <div>
            <p className="font-ui text-2xs font-semibold uppercase tracking-wide text-ink-faint">Metadata</p>
            <pre className="mt-1 overflow-x-auto rounded-sm bg-canvas p-2 font-data text-2xs text-ink-muted">
              {Object.keys(record.metadata).length > 0 ? JSON.stringify(record.metadata, null, 2) : "—"}
            </pre>
          </div>
        </div>
        <div className="mt-2 flex flex-wrap gap-4 pl-1 font-data text-2xs text-ink-faint">
          <span>prev_hash: {record.prev_hash.slice(0, 16)}…</span>
          <span>record_hash: {record.record_hash.slice(0, 16)}…</span>
        </div>
      </details>
    </li>
  );
}

export function AuditTrailPage() {
  const { caseId } = useParams<{ caseId: string }>();
  const { data: trail, isLoading } = useAuditTrail(caseId);
  const verify = useVerifyChain();

  if (!caseId) return null;

  return (
    <div className="min-h-full bg-canvas">
      <header className="flex items-center gap-3 border-b border-rule bg-panel px-6 py-3">
        <Link to={`/cases/${caseId}`} className="font-ui text-xs text-ink-muted hover:text-ink">
          ← Case Workspace
        </Link>
        <h1 className="font-ui text-sm font-semibold text-ink">Audit trail</h1>
        {trail && <span className="font-data text-xs text-ink-faint">{trail.case_ref}</span>}
      </header>

      <ChainIntegrityHeader caseId={caseId} verify={verify} />

      {isLoading ? (
        <p className="px-6 py-6 font-ui text-sm text-ink-muted">Loading ledger…</p>
      ) : !trail || trail.records.length === 0 ? (
        <p className="px-6 py-6 font-ui text-sm text-ink-muted">No audit records for this case yet.</p>
      ) : (
        <ul>
          {trail.records.map((record) => (
            <RecordRow key={record.id} record={record} isBroken={verify.data?.broken_at === record.id} />
          ))}
        </ul>
      )}
    </div>
  );
}
