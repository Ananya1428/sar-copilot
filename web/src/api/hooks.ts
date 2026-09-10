import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./client";
import type {
  AuditTrail,
  CaseSummary,
  ChainVerifyResult,
  EvidencePack,
  Narrative,
  NarrativeDiff,
  QualityMetrics,
} from "./types";

export function useCases() {
  return useQuery({
    queryKey: ["cases"],
    queryFn: () => api.get<CaseSummary[]>("/cases/"),
  });
}

export function useEvidencePack(caseId: string | undefined) {
  return useQuery({
    queryKey: ["evidence", caseId],
    queryFn: () => api.get<EvidencePack>(`/cases/${caseId}/evidence`),
    enabled: Boolean(caseId),
    retry: false, // a 404 here just means "no pack built yet" — don't retry into it
  });
}

/**
 * A specific pack by id, not "latest for a case" — a narrative generated
 * against an older pack (evidence packs are immutable/versioned; a case
 * can have several) needs its own exact pack, e.g. for the Verification
 * Detail screen's "nearest evidence values" comparison.
 */
export function useEvidencePackById(packId: string | undefined) {
  return useQuery({
    queryKey: ["evidence-pack", packId],
    queryFn: () => api.get<EvidencePack>(`/evidence/${packId}`),
    enabled: Boolean(packId),
  });
}

export function useRebuildEvidence() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (caseId: string) => api.post<EvidencePack>(`/cases/${caseId}/evidence/rebuild`),
    onSuccess: (_data, caseId) => {
      queryClient.invalidateQueries({ queryKey: ["evidence", caseId] });
    },
  });
}

export function useNarrative(narrativeId: string | undefined) {
  return useQuery({
    queryKey: ["narrative", narrativeId],
    queryFn: () => api.get<Narrative>(`/narratives/${narrativeId}`),
    enabled: Boolean(narrativeId),
  });
}

export function useGenerateNarrative(caseId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (params: { mode: "TEMPLATE" | "HYBRID" | "FREEFORM"; seed?: number }) =>
      api.post<Narrative>(`/cases/${caseId}/narrative?mode=${params.mode}&seed=${params.seed ?? 42}`),
    onSuccess: (narrative) => {
      queryClient.setQueryData(["narrative", narrative.id], narrative);
      if (caseId) {
        queryClient.invalidateQueries({ queryKey: ["evidence", caseId] });
      }
    },
  });
}

export function useEditNarrative(narrativeId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (sentences: { text: string; section: string | null; evidence_keys: string[] }[]) =>
      api.patch<Narrative>(`/narratives/${narrativeId}`, { sentences }),
    onSuccess: (narrative) => {
      queryClient.setQueryData(["narrative", narrative.id], narrative);
    },
  });
}

export function useNarrativeDiff(narrativeId: string | undefined, otherVersion: number | undefined) {
  return useQuery({
    queryKey: ["narrative-diff", narrativeId, otherVersion],
    queryFn: () => api.get<NarrativeDiff>(`/narratives/${narrativeId}/diff/${otherVersion}`),
    enabled: Boolean(narrativeId) && otherVersion !== undefined,
  });
}

export function useAuditTrail(caseId: string | undefined) {
  return useQuery({
    queryKey: ["audit", caseId],
    queryFn: () => api.get<AuditTrail>(`/audit/case/${caseId}`),
    enabled: Boolean(caseId),
  });
}

export function useVerifyChain() {
  return useMutation({
    mutationFn: (caseId: string) => api.post<ChainVerifyResult>("/audit/verify-chain", { case_id: caseId }),
  });
}

export function useQualityMetrics() {
  return useQuery({
    queryKey: ["metrics", "quality"],
    queryFn: () => api.get<QualityMetrics>("/metrics/quality"),
  });
}
