/**
 * Types mirror the live backend response shapes exactly (verified against
 * the running API in Part 6b, not guessed from the blueprint's illustrative
 * schema) — see api/app/api/v1/{cases,narratives,audit,metrics}.py and
 * api/app/domain/evidence/schema.py.
 */

/** api/app/api/v1/auth.py TokenResponse */
export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

/** api/app/api/v1/onboarding.py _customer_dict */
export interface CustomerRecord {
  id: string;
  customer_ref: string;
  legal_name: string;
  entity_type: "individual" | "business";
  onboarded_at: string;
  risk_rating: "LOW" | "MEDIUM" | "HIGH";
  occupation: string | null;
  country: string;
}

/** api/app/api/v1/onboarding.py _account_dict */
export interface AccountRecord {
  id: string;
  customer_id: string;
  account_ref: string;
  account_type: "checking" | "savings" | "business";
  currency: string;
  opened_at: string;
  expected_monthly_volume: number;
  status: string;
}

/** api/app/api/v1/onboarding.py _transaction_dict */
export interface TransactionRecord {
  id: string;
  account_id: string;
  txn_ref: string;
  executed_at: string;
  amount: number;
  currency: string;
  direction: "credit" | "debit";
  channel: "cash" | "wire" | "ach" | "card" | "check";
  counterparty_ref: string | null;
  counterparty_country: string | null;
  is_cash: boolean;
}

/** api/app/domain/detection/orchestrator.py run_detection() return value */
export interface DetectionSummary {
  accounts_evaluated: number;
  alerts_created: number;
  band_counts: Record<string, number>;
  ml_ensemble_fitted?: boolean;
}

/** api/app/domain/evidence/case_assembly.py assemble_cases() return value */
export interface AssembleSummary {
  accounts_considered: number;
  cases_created: number;
  cases_reused: number;
  alerts_linked: number;
}

export type RiskBand = "LOW" | "MEDIUM" | "HIGH";

export interface CaseSummary {
  id: string;
  case_ref: string;
  status: string;
  risk_score: number | null;
  risk_band: RiskBand | null;
  deadline_at: string | null;
}

/** api/app/domain/evidence/schema.py EvidenceItem */
export interface EvidenceItem {
  key: string;
  type: "entity" | "amount" | "date" | "count" | "location" | "channel" | "typology" | "text";
  raw_value: Record<string, unknown>;
  confidence: number;
  source_field: string;
  source_table: string;
  display_value: string;
  source_row_id: string;
}

export interface EvidenceSubject {
  role: string;
  country: string;
  legal_name: string;
  occupation: string;
  entity_type: string;
  risk_rating: string;
  account_refs: string[];
  customer_ref: string;
  relationship_start: string;
  expected_monthly_volume: string;
  observed_monthly_volume: string;
}

export interface EvidenceTypology {
  code: string;
  label: string;
  weight: number;
  description: string;
  quantitative_basis: Record<string, unknown>;
  supporting_txn_refs: string[];
}

export interface EvidenceTransaction {
  amount: string;
  channel: string;
  is_cash: boolean;
  txn_ref: string;
  currency: string;
  direction: "credit" | "debit";
  flagged_by: string[];
  executed_at: string;
  counterparty_ref: string | null;
  counterparty_country: string | null;
}

export interface EvidenceAggregates {
  txn_count: number;
  period_end: string;
  total_debit: string;
  period_start: string;
  total_credit: string;
  cash_txn_count: number;
  max_single_amount: string;
  velocity_peak_24h: number | null;
  distinct_countries: number;
  deviation_from_expected: number | null;
  distinct_counterparties: number;
}

export interface EvidencePack {
  items: EvidenceItem[];
  pack_id: string;
  built_at: string;
  case_ref: string;
  subjects: EvidenceSubject[];
  aggregates: EvidenceAggregates;
  prior_sars: unknown[];
  typologies: EvidenceTypology[];
  ml_findings: Record<string, unknown>;
  content_hash: string;
  transactions: EvidenceTransaction[];
  graph_findings: Record<string, unknown>;
  builder_version: string;
}

export type GenerationMode = "TEMPLATE" | "HYBRID" | "FREEFORM" | "TEMPLATE_FALLBACK";

export interface NarrativeSentence {
  ordinal: number;
  text: string;
  section: string | null;
  evidence_keys: string[];
  grounding_score?: number | null;
}

export type CheckSeverity = "CRITICAL" | "HIGH";

export interface CheckViolation {
  message: string;
  sentence_index: number | null;
  section: string | null;
  token: string | null;
  position: number | null;
}

export interface CheckResult {
  severity: CheckSeverity;
  passed: boolean;
  score: number;
  violations: CheckViolation[];
}

export const CHECK_NAMES = ["numeric", "entity", "temporal", "prohibited", "entailment", "completeness"] as const;
export type CheckName = (typeof CHECK_NAMES)[number];

export interface VerificationSummary {
  passed: boolean;
  overall_score: number;
  checks: Record<CheckName, CheckResult>;
}

export interface Narrative {
  id: string;
  case_ref?: string;
  pack_id: string;
  version: number;
  generation_mode: GenerationMode;
  model_id: string | null;
  prompt_version: string | null;
  seed: number | null;
  verified?: boolean;
  body: string;
  sentences: NarrativeSentence[];
  notes?: string[];
  verification: VerificationSummary | null;
}

export interface AuditRecord {
  id: string;
  case_id: string;
  actor_id: string | null;
  action: string;
  before_state: Record<string, unknown> | null;
  after_state: Record<string, unknown> | null;
  metadata: Record<string, unknown>;
  prev_hash: string;
  record_hash: string;
  occurred_at: string;
}

export interface AuditTrail {
  case_id: string;
  case_ref: string;
  records: AuditRecord[];
}

export interface ChainVerifyResult {
  valid: boolean;
  broken_at: string | null;
  reason: string | null;
}

export interface NarrativeDiff {
  case_id: string;
  this_version: {
    id: string;
    version: number;
    body: string;
    sentences: NarrativeSentence[];
    verification: { passed: boolean; overall_score: number } | null;
  };
  other_version: {
    id: string;
    version: number;
    body: string;
    sentences: NarrativeSentence[];
    verification: { passed: boolean; overall_score: number } | null;
  };
  diff: string[];
}

export interface QualityMetrics {
  narrative_count: number;
  verification_report_count: number;
  pass_rate_by_mode: Record<string, number | null>;
  mean_overall_score_by_mode: Record<string, number | null>;
  unverified_narratives_by_mode: Record<string, number>;
  failure_count_by_check: Record<CheckName, number>;
  generation_latency: { available: boolean; note: string };
  human_edit_rate: {
    value: number | null;
    narratives_with_version_gt_1: number;
    total_narratives: number;
    note: string;
  };
}
