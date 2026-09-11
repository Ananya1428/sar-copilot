import { Link, useParams, useSearchParams } from "react-router-dom";

import { useEvidencePackById, useNarrative } from "@/api/hooks";
import { CHECK_NAMES, type CheckName, type CheckViolation, type EvidenceItem, type NarrativeSentence } from "@/api/types";
import { StatusIcon, type Status } from "@/components/ui/StatusIcon";
import { AuthBadge } from "@/features/auth/AuthBadge";
import { formatScore, titleCase } from "@/lib/format";
import { groundedItems } from "@/lib/grounding";

/** blueprint §16-19 forensic-ledger style offending-span highlight —
 * "…deposits totalling ▸147,300.00◂ USD were…". Falls back to flagging
 * the whole sentence (italic, no span) for checks like entailment that
 * don't have a specific token/position, only a sentence-level verdict. */
function HighlightedSentence({ sentence, violation }: { sentence: NarrativeSentence; violation: CheckViolation }) {
  const { position, token } = violation;
  if (position === null || token === null) {
    return <p className="font-narrative text-base italic leading-[1.7] text-ink">{sentence.text}</p>;
  }
  const before = sentence.text.slice(0, position);
  const span = sentence.text.slice(position, position + token.length) || token;
  const after = sentence.text.slice(position + token.length);
  return (
    <p className="font-narrative text-base leading-[1.7] text-ink">
      {before}
      <mark className="rounded-sm bg-critical-bg px-0.5 text-critical">{span}</mark>
      {after}
    </p>
  );
}

function ViolationCard({
  violation,
  sentence,
  evidenceItems,
}: {
  violation: CheckViolation;
  sentence: NarrativeSentence | undefined;
  evidenceItems: EvidenceItem[] | undefined;
}) {
  const nearby = sentence && evidenceItems ? groundedItems(sentence.text, evidenceItems) : [];

  return (
    <li className="border border-rule bg-panel p-4">
      <div className="flex items-start justify-between gap-3">
        <p className="font-ui text-sm text-ink">{violation.message}</p>
        {violation.section && (
          <span className="shrink-0 rounded-sm border border-rule px-1.5 py-0.5 font-ui text-2xs uppercase text-ink-faint">
            {violation.section}
          </span>
        )}
      </div>

      <div className="mt-3 rounded-sm bg-paper p-3">
        {sentence ? (
          <HighlightedSentence sentence={sentence} violation={violation} />
        ) : (
          <p className="font-ui text-xs text-ink-faint">Sentence text unavailable.</p>
        )}
      </div>

      {nearby.length > 0 && (
        <div className="mt-3">
          <p className="font-ui text-2xs font-medium uppercase tracking-wide text-ink-faint">
            Nearest evidence values for comparison
          </p>
          <ul className="mt-1.5 flex flex-wrap gap-1.5">
            {nearby.map((item) => (
              <li key={item.key} className="rounded-sm border border-rule bg-canvas px-2 py-1 font-data text-2xs text-ink">
                {item.display_value}
                <span className="ml-1.5 text-ink-faint">{item.type}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </li>
  );
}

export function VerificationDetailPage() {
  const { caseId, narrativeId } = useParams<{ caseId: string; narrativeId: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const activeCheck = (searchParams.get("check") as CheckName | null) ?? "numeric";

  const { data: narrative, isLoading } = useNarrative(narrativeId);
  const { data: pack } = useEvidencePackById(narrative?.pack_id);

  const verification = narrative?.verification ?? null;
  const check = verification?.checks[activeCheck];

  return (
    <div className="min-h-full bg-canvas">
      <header className="flex items-center gap-3 border-b border-rule bg-panel px-6 py-3">
        <Link to={`/cases/${caseId}`} className="font-ui text-xs text-ink-muted hover:text-ink">
          ← Case Workspace
        </Link>
        <h1 className="font-ui text-sm font-semibold text-ink">Verification detail</h1>
        {narrative && <span className="font-data text-xs text-ink-faint">narrative v{narrative.version}</span>}
        <div className="ml-auto">
          <AuthBadge />
        </div>
      </header>

      {isLoading ? (
        <p className="px-6 py-6 font-ui text-sm text-ink-muted">Loading…</p>
      ) : !verification ? (
        <p className="px-6 py-6 font-ui text-sm text-ink-muted">No verification report for this narrative.</p>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-2 border-b border-rule bg-panel px-6 py-3">
            {CHECK_NAMES.map((name) => {
              const c = verification.checks[name];
              if (!c) return null;
              const status: Status = c.passed ? "verified" : c.severity === "CRITICAL" ? "critical" : "caution";
              return (
                <button
                  key={name}
                  onClick={() => setSearchParams({ check: name })}
                  aria-pressed={activeCheck === name}
                  className={`flex items-center gap-2 rounded-sm border px-2.5 py-1.5 font-ui text-xs ${
                    activeCheck === name ? "border-trace bg-trace-bg text-trace" : "border-rule bg-paper text-ink-muted hover:bg-canvas"
                  }`}
                >
                  {titleCase(name)}
                  <span className="font-data text-2xs">{c.violations.length}</span>
                  <StatusIcon status={status} label="" />
                </button>
              );
            })}
          </div>

          <main className="mx-auto max-w-narrative px-6 py-6">
            {check ? (
              <>
                <div className="mb-4 flex items-center justify-between">
                  <h2 className="font-ui text-sm font-semibold text-ink">{titleCase(activeCheck)}</h2>
                  <div className="flex items-center gap-3">
                    <span className="font-data text-sm text-ink-muted">{formatScore(check.score)}</span>
                    <StatusIcon status={check.passed ? "verified" : check.severity === "CRITICAL" ? "critical" : "caution"} />
                  </div>
                </div>

                {check.violations.length === 0 ? (
                  <p className="font-ui text-sm text-ink-muted">No violations for this check.</p>
                ) : (
                  <ul className="flex flex-col gap-4">
                    {check.violations.map((violation, i) => {
                      const sentence =
                        violation.sentence_index !== null
                          ? narrative?.sentences.find((s) => s.ordinal === violation.sentence_index! + 1)
                          : undefined;
                      return <ViolationCard key={i} violation={violation} sentence={sentence} evidenceItems={pack?.items} />;
                    })}
                  </ul>
                )}

                <div className="mt-6 border-t border-rule pt-4">
                  <p className="font-ui text-xs text-ink-faint">
                    Remediation: this build only supports regenerating the whole narrative (no per-section regeneration
                    endpoint exists yet) — return to the workspace to regenerate, or fall back to TEMPLATE mode.
                  </p>
                  <Link
                    to={`/cases/${caseId}`}
                    className="mt-2 inline-block rounded-sm border border-rule bg-panel px-3 py-1.5 font-ui text-xs font-medium text-ink hover:bg-canvas"
                  >
                    Back to workspace
                  </Link>
                </div>
              </>
            ) : (
              <p className="font-ui text-sm text-ink-muted">No data for this check.</p>
            )}
          </main>
        </>
      )}
    </div>
  );
}
