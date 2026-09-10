import { CHECK_NAMES, type VerificationSummary } from "@/api/types";
import { StatusIcon } from "@/components/ui/StatusIcon";
import { formatScore, titleCase } from "@/lib/format";

/**
 * Always visible, per-check pass/fail/score (blueprint §18 Screen 2) —
 * the real VerificationReport shape from Part 5's pipeline
 * (numeric/entity/temporal/prohibited/entailment/completeness), not a
 * mocked summary. Status is icon + text, never colour alone.
 */
export function VerificationCard({ verification }: { verification: VerificationSummary | null }) {
  if (!verification) {
    return (
      <section aria-label="Verification" className="border-b border-rule p-4">
        <h2 className="font-ui text-2xs font-semibold uppercase tracking-wide text-ink-faint">Verification</h2>
        <p className="mt-2 font-ui text-xs text-ink-faint">No verification report for this narrative version.</p>
      </section>
    );
  }

  return (
    <section aria-label="Verification" className="flex flex-col gap-3 border-b border-rule p-4">
      <div className="flex items-center justify-between">
        <h2 className="font-ui text-2xs font-semibold uppercase tracking-wide text-ink-faint">Verification</h2>
        <StatusIcon status={verification.passed ? "verified" : "critical"} label={verification.passed ? "Passed" : "Failed"} />
      </div>

      <div className="flex items-baseline gap-2">
        <span className="font-data text-lg text-ink">{formatScore(verification.overall_score)}</span>
        <span className="font-ui text-2xs text-ink-faint">overall score</span>
      </div>

      <ul className="flex flex-col gap-1.5">
        {CHECK_NAMES.map((name) => {
          const check = verification.checks[name];
          if (!check) return null;
          const status = check.passed ? "verified" : check.severity === "CRITICAL" ? "critical" : "caution";
          return (
            <li key={name} className="flex items-center justify-between gap-2 border-t border-rule pt-1.5 first:border-t-0 first:pt-0">
              <span className="font-ui text-xs text-ink">{titleCase(name)}</span>
              <div className="flex items-center gap-2">
                <span className="font-data text-2xs text-ink-muted">{formatScore(check.score)}</span>
                <StatusIcon status={status} />
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
