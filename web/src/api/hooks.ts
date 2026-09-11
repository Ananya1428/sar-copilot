import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./client";
import type {
  AccountRecord,
  AssembleSummary,
  AuditTrail,
  CaseSummary,
  ChainVerifyResult,
  CustomerRecord,
  DetectionSummary,
  EvidencePack,
  Narrative,
  NarrativeDiff,
  QualityMetrics,
  TokenResponse,
  TransactionRecord,
} from "./types";

export function useLogin() {
  return useMutation({
    mutationFn: (creds: { email: string; password: string }) => api.post<TokenResponse>("/auth/login", creds),
  });
}

export function useCases() {
  return useQuery({
    queryKey: ["cases"],
    queryFn: () => api.get<CaseSummary[]>("/cases/"),
  });
}

// --- Part 8b onboarding endpoints (api/app/api/v1/onboarding.py) ---

export interface CustomerCreateInput {
  legal_name: string;
  entity_type: "individual" | "business";
  onboarded_at: string;
  risk_rating: "LOW" | "MEDIUM" | "HIGH";
  occupation?: string | null;
  country: string;
}

export function useCreateCustomer() {
  return useMutation({
    mutationFn: (input: CustomerCreateInput) => api.post<CustomerRecord>("/customers/", input),
  });
}

export interface AccountCreateInput {
  account_type: "checking" | "savings" | "business";
  currency: string;
  opened_at: string;
  expected_monthly_volume: string;
}

export function useCreateAccount(customerId: string | undefined) {
  return useMutation({
    mutationFn: (input: AccountCreateInput) => api.post<AccountRecord>(`/customers/${customerId}/accounts`, input),
  });
}

export interface TransactionCreateInput {
  amount: string;
  currency: string;
  direction: "credit" | "debit";
  channel: "cash" | "wire" | "ach" | "card" | "check";
  executed_at: string;
  counterparty_ref?: string | null;
  counterparty_country?: string | null;
  is_cash: boolean;
}

export function useCreateTransaction(accountId: string | undefined) {
  return useMutation({
    mutationFn: (input: TransactionCreateInput) =>
      api.post<TransactionRecord>(`/accounts/${accountId}/transactions`, input),
  });
}

export function useRunDetection() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<DetectionSummary>("/detection/run"),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["cases"] }),
  });
}

export function useAssembleCases() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<AssembleSummary>("/cases/assemble"),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["cases"] }),
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
