import { useAuditTrail } from "@/api/hooks";

/**
 * There is no "list narratives for a case" endpoint (Parts 1-6a never
 * built one) — but the audit ledger already records every
 * NARRATIVE_GENERATED / NARRATIVE_EDITED event with the resulting
 * narrative's id in `after_state.id` (api/app/domain/narrative/engine.py
 * persist_narrative, api/app/api/v1/narratives.py edit_narrative). Reusing
 * that as the source of truth for "which narrative is current" avoids
 * fabricating a lookup the backend doesn't expose, and doubles as a live
 * demonstration that Part 6a's ledger is real, queryable data.
 */
export function useLatestNarrativeId(caseId: string | undefined) {
  const { data: trail, isLoading } = useAuditTrail(caseId);

  if (!trail) return { narrativeId: undefined, isLoading };

  const latest = [...trail.records]
    .reverse()
    .find((r) => r.action === "NARRATIVE_GENERATED" || r.action === "NARRATIVE_EDITED");

  const afterState = latest?.after_state as { id?: string } | null;
  return { narrativeId: afterState?.id, isLoading };
}
