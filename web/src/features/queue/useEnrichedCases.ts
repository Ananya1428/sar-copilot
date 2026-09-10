import { useQueries } from "@tanstack/react-query";

import { api, ApiError } from "@/api/client";
import type { CaseSummary, EvidencePack } from "@/api/types";

export interface EnrichedCase extends CaseSummary {
  subjectName: string | null;
  typologies: { code: string; label: string }[];
  hasEvidence: boolean;
}

/**
 * GET /cases only returns id/ref/status/score/band/deadline (see
 * api/app/api/v1/cases.py list_cases) — no subject name or typology
 * labels. Those live in each case's EvidencePack, so the queue enriches
 * its rows with a parallel per-case evidence fetch rather than fabricate
 * columns the backend doesn't provide. A case with no pack built yet
 * (404) just renders with those columns empty, not an error.
 */
export function useEnrichedCases(cases: CaseSummary[] | undefined) {
  const queries = useQueries({
    queries: (cases ?? []).map((c) => ({
      queryKey: ["evidence", c.id],
      queryFn: () => api.get<EvidencePack>(`/cases/${c.id}/evidence`),
      enabled: Boolean(cases),
      retry: false,
      staleTime: 60_000,
    })),
  });

  if (!cases) return { data: undefined, isLoading: true };

  const enriched: EnrichedCase[] = cases.map((c, i) => {
    const q = queries[i];
    const pack = q.data as EvidencePack | undefined;
    const failed = q.error instanceof ApiError && q.error.status === 404;
    return {
      ...c,
      subjectName: pack?.subjects[0]?.legal_name ?? null,
      typologies: pack?.typologies.map((t) => ({ code: t.code, label: t.label })) ?? [],
      hasEvidence: Boolean(pack) && !failed,
    };
  });

  const isLoading = queries.some((q) => q.isLoading);
  return { data: enriched, isLoading };
}
