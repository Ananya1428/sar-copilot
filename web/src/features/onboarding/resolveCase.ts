import { api, ApiError } from "@/api/client";
import type { AuditTrail, CaseSummary } from "@/api/types";

/**
 * There is no "find the case for this account" endpoint (Part 8b never
 * built one — case_assembly.py groups by account internally but doesn't
 * expose that mapping). The audit ledger already records it though: every
 * CASE_OPENED record's metadata carries the exact `account_id` that case
 * was opened for (case_assembly.py's `ledger.append(..., metadata={
 * "account_id": ..., "alert_ids": [...]})`). Reusing that as the source of
 * truth mirrors how useLatestNarrativeId.ts already treats the audit
 * ledger as queryable data rather than inventing a new backend lookup.
 *
 * Bounded scan: `casesCreatedThisRun` (from the real POST /cases/assemble
 * response) tells us exactly how many NEW cases this run opened. Every
 * case's `deadline_at` is `opened_at + a fixed 30 days`
 * (case_assembly.py's DEFAULT_CASE_DEADLINE_DAYS), so sorting the full
 * case list by `deadline_at` descending reproduces creation order —
 * the newest `casesCreatedThisRun` cases in that order are exactly the
 * ones this run just opened, nothing more. Only those get an audit-trail
 * fetch, not the whole table.
 *
 * Requires the caller to hold a role that can read GET /audit/case/{id}
 * (reviewer/officer/admin per blueprint §11.3) — in practice this is
 * always true here, since only an admin can trigger detection/assembly
 * in the first place (Part 8a RBAC), and admin already has audit-read
 * access too.
 */
export async function resolveNewCaseForAccount(accountId: string, casesCreatedThisRun: number): Promise<string | null> {
  if (casesCreatedThisRun <= 0) return null;

  const cases = await api.get<CaseSummary[]>("/cases/");
  const candidates = [...cases]
    .sort((a, b) => new Date(b.deadline_at ?? 0).getTime() - new Date(a.deadline_at ?? 0).getTime())
    .slice(0, casesCreatedThisRun);

  for (const candidate of candidates) {
    try {
      const trail = await api.get<AuditTrail>(`/audit/case/${candidate.id}`);
      const opened = trail.records.find((r) => r.action === "CASE_OPENED");
      const metadata = opened?.metadata as { account_id?: string } | undefined;
      if (metadata?.account_id === accountId) {
        return candidate.id;
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        // Caller's role can't read audit trails — stop trying entirely
        // rather than fail candidate-by-candidate.
        throw err;
      }
      // Any other per-candidate failure (e.g. a 404 race) — skip it.
    }
  }
  return null;
}
