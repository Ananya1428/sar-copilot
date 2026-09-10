import { Link, useParams } from "react-router-dom";

import { useAuditTrail, useNarrativeDiff } from "@/api/hooks";
import type { AuditRecord } from "@/api/types";
import { StatusIcon } from "@/components/ui/StatusIcon";
import { formatScore } from "@/lib/format";

/** Finds the audit record documenting how a specific narrative version
 * came to exist — NARRATIVE_GENERATED or NARRATIVE_EDITED — for its
 * actor/timestamp/provenance label. The diff endpoint itself doesn't
 * carry actor/timestamp (blueprint §18 asks for it "if available"); the
 * audit ledger is where it actually lives. */
function findProvenance(records: AuditRecord[] | undefined, narrativeId: string) {
  return records?.find((r) => {
    const after = r.after_state as { id?: string } | null;
    return after?.id === narrativeId && (r.action === "NARRATIVE_GENERATED" || r.action === "NARRATIVE_EDITED");
  });
}

function VersionColumn({
  label,
  body,
  score,
  passed,
  provenance,
}: {
  label: string;
  body: string;
  score: number | undefined;
  passed: boolean | undefined;
  provenance: AuditRecord | undefined;
}) {
  return (
    <div className="flex min-w-0 flex-1 flex-col border border-rule bg-panel">
      <div className="flex items-center justify-between border-b border-rule px-3 py-2">
        <div>
          <p className="font-ui text-xs font-semibold text-ink">{label}</p>
          <p className="font-ui text-2xs text-ink-faint">
            {provenance
              ? `${provenance.action === "NARRATIVE_EDITED" ? "edited" : "generated"} · ${new Date(provenance.occurred_at).toLocaleString()}`
              : "provenance unavailable"}
          </p>
        </div>
        {score !== undefined && (
          <div className="flex items-center gap-2">
            <span className="font-data text-xs text-ink-muted">{formatScore(score)}</span>
            {passed !== undefined && <StatusIcon status={passed ? "verified" : "critical"} label={passed ? "Passed" : "Failed"} />}
          </div>
        )}
      </div>
      <div className="max-h-[420px] overflow-y-auto bg-paper p-4">
        <p className="whitespace-pre-line font-narrative text-base leading-[1.7] text-ink">{body}</p>
      </div>
    </div>
  );
}

/** Renders difflib's unified-diff lines as-is (blueprint §11.2 — the
 * backend already computed this, don't recompute it client-side).
 * Added/removed lines are distinguished by a left border and a leading
 * +/- character, not colour — colour stays reserved for verification
 * state (blueprint §16.6). */
function DiffLines({ lines }: { lines: string[] }) {
  if (lines.length === 0) {
    return <p className="font-ui text-xs text-ink-faint">No textual differences between these versions.</p>;
  }
  return (
    <pre className="overflow-x-auto rounded-sm border border-rule bg-panel p-3 font-data text-xs leading-6">
      {lines.map((line, i) => {
        const isAdded = line.startsWith("+") && !line.startsWith("+++");
        const isRemoved = line.startsWith("-") && !line.startsWith("---");
        const isHeader = line.startsWith("@@") || line.startsWith("---") || line.startsWith("+++");
        return (
          <div
            key={i}
            className={`border-l-2 px-2 ${
              isAdded || isRemoved ? "border-ink font-medium text-ink" : isHeader ? "border-transparent text-ink-faint" : "border-transparent text-ink-muted"
            }`}
          >
            {line || " "}
          </div>
        );
      })}
    </pre>
  );
}

export function VersionDiffPage() {
  const { caseId, narrativeId, otherVersion } = useParams<{ caseId: string; narrativeId: string; otherVersion: string }>();
  const { data: diff, isLoading } = useNarrativeDiff(narrativeId, otherVersion ? Number(otherVersion) : undefined);
  const { data: trail } = useAuditTrail(caseId);

  return (
    <div className="min-h-full bg-canvas">
      <header className="flex items-center gap-3 border-b border-rule bg-panel px-6 py-3">
        <Link to={`/cases/${caseId}`} className="font-ui text-xs text-ink-muted hover:text-ink">
          ← Case Workspace
        </Link>
        <h1 className="font-ui text-sm font-semibold text-ink">Version diff</h1>
      </header>

      <main className="px-6 py-6">
        {isLoading ? (
          <p className="font-ui text-sm text-ink-muted">Loading…</p>
        ) : !diff ? (
          <p className="font-ui text-sm text-ink-muted">Could not load a diff for these versions.</p>
        ) : (
          <div className="flex flex-col gap-6">
            <div className="flex gap-4">
              <VersionColumn
                label={`Version ${diff.other_version.version}`}
                body={diff.other_version.body}
                score={diff.other_version.verification?.overall_score}
                passed={diff.other_version.verification?.passed}
                provenance={findProvenance(trail?.records, diff.other_version.id)}
              />
              <VersionColumn
                label={`Version ${diff.this_version.version}`}
                body={diff.this_version.body}
                score={diff.this_version.verification?.overall_score}
                passed={diff.this_version.verification?.passed}
                provenance={findProvenance(trail?.records, diff.this_version.id)}
              />
            </div>

            <div>
              <h2 className="mb-2 font-ui text-2xs font-semibold uppercase tracking-wide text-ink-faint">
                Line diff (v{diff.other_version.version} → v{diff.this_version.version})
              </h2>
              <DiffLines lines={diff.diff} />
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
