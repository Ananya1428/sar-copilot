import type { EvidenceItem } from "@/api/types";

/**
 * Client-side "does this sentence's text actually ground to this evidence
 * item" scan — the same category of check as the backend's numeric/entity
 * verification (domain/verification/numeric.py, entity.py): scan the
 * sentence's rendered TEXT for the item's display_value, rather than
 * trusting the LLM's own self-reported `evidence_keys` array as the sole
 * source (Part 5's caution about a model citing a key it didn't actually
 * use, or omitting one it did).
 *
 * Deliberately a light heuristic, not a port of the full backend pipeline:
 * case-insensitive substring match after stripping currency symbols and
 * thousands separators, skipping values too short to be meaningful
 * (single characters, empty strings).
 */

const TXN_GROUP_RE = /^transaction\.(TXN-[^.]+)\./;
const TXN_REF_KEY_RE = /^transaction\.(TXN-[^.]+)\.txn_ref$/;
const TYPOLOGY_GROUP_RE = /^typology\.([A-Z_]+)\./;
// Sentences almost always use the human label ("Circular flow /
// round-tripping"), not the raw code ("CIRCULAR_FLOW") — anchor on
// either, so the code-only case doesn't drop every legitimately-grounded
// quantitative_basis value (hop counts, retention percentages, ...) just
// because the sentence never spells out the code itself.
const TYPOLOGY_ANCHOR_KEY_RE = /^typology\.([A-Z_]+)\.(code|label)$/;

function normalize(value: string): string {
  return value.toLowerCase().replace(/[$,]/g, "").trim();
}

export function groundedItems(sentenceText: string, items: EvidenceItem[]): EvidenceItem[] {
  const normalizedText = normalize(sentenceText);

  // Many fields repeat the same value across unrelated records — every ACH
  // transaction's `channel` item has display_value "ach", so a naive scan
  // would match every ACH transaction's items against ANY sentence that
  // mentions "ach", not just the one about that specific transaction.
  // Anchor on each record group's own identifying value (a txn_ref, a
  // typology code) first, and only count a shared-field match if the
  // sentence actually names that specific record.
  const referencedTxnRefs = new Set<string>();
  const referencedTypologyCodes = new Set<string>();
  for (const item of items) {
    const txnRefMatch = TXN_REF_KEY_RE.exec(item.key);
    if (txnRefMatch && normalizedText.includes(normalize(item.display_value))) {
      referencedTxnRefs.add(txnRefMatch[1]);
    }
    const typologyAnchorMatch = TYPOLOGY_ANCHOR_KEY_RE.exec(item.key);
    if (typologyAnchorMatch && normalizedText.includes(normalize(item.display_value))) {
      referencedTypologyCodes.add(typologyAnchorMatch[1]);
    }
  }

  const matches: EvidenceItem[] = [];
  const seen = new Set<string>();

  for (const item of items) {
    if (seen.has(item.key)) continue;
    const normalizedVal = normalize(item.display_value ?? "");
    if (normalizedVal.length < 2) continue;
    if (!normalizedText.includes(normalizedVal)) continue;

    const txnGroup = TXN_GROUP_RE.exec(item.key);
    if (txnGroup && !referencedTxnRefs.has(txnGroup[1])) continue;
    const typologyGroup = TYPOLOGY_GROUP_RE.exec(item.key);
    if (typologyGroup && !referencedTypologyCodes.has(typologyGroup[1])) continue;

    matches.push(item);
    seen.add(item.key);
  }

  return matches;
}
