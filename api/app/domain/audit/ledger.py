"""blueprint §15.1 hash-chained append-only audit ledger.

Every state change is a record cryptographically linked to its
predecessor: `record_hash = SHA256(canonical_json({case_id, actor_id,
action, before_state, after_state, metadata, occurred_at, prev_hash}))`.
Tampering with any historical record's stored fields changes what
`verify_chain()` recomputes for that record's hash, which no longer
matches the stored `record_hash` — and every record after it was chained
off the now-invalid value, so the break is detectable at the exact record
where the data was altered, not just "somewhere in the chain".

`occurred_at` doubles as the ordering key. Append-time monotonicity is
enforced explicitly (bumped by 1us past the previous record if the clock
doesn't strictly advance) rather than trusted to wall-clock resolution,
which on some platforms is coarser than a single ledger write.
"""

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit import AuditRecord

GENESIS_HASH = "0" * 64

# blueprint §15.2's full action list. Parts 1-5 have only built the
# workflow up through narrative generation/editing — SUBMITTED_FOR_REVIEW
# onward depend on a review workflow no part has implemented yet, but the
# names are reserved here now so a later part doesn't have to touch the
# ledger's validation again.
VALID_ACTIONS = frozenset(
    {
        "CASE_OPENED",
        "EVIDENCE_BUILT",
        "NARRATIVE_GENERATED",
        "VERIFICATION_FAILED",
        "NARRATIVE_EDITED",
        "SUBMITTED_FOR_REVIEW",
        "REVIEW_APPROVED",
        "REVIEW_REJECTED",
        "SIGNED_OFF",
        "EXPORTED",
    }
)


def _json_default(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    raise TypeError(f"not JSON serializable: {value!r}")


def _canonical_json(payload: dict) -> str:
    """Deterministic serialization: sorted keys, no incidental whitespace,
    so the same logical payload always hashes to the same digest."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=_json_default)


def _record_payload(
    *,
    case_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    action: str,
    before_state: dict | None,
    after_state: dict | None,
    metadata: dict,
    occurred_at: datetime,
    prev_hash: str,
) -> dict:
    return {
        "case_id": str(case_id),
        "actor_id": str(actor_id) if actor_id else None,
        "action": action,
        "before_state": before_state,
        "after_state": after_state,
        "metadata": metadata,
        "occurred_at": occurred_at.isoformat(),
        "prev_hash": prev_hash,
    }


def _record_hash(payload: dict) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


class AuditLedger:
    def __init__(self, session: Session):
        self.session = session

    def _last_record(self, case_id: uuid.UUID) -> AuditRecord | None:
        return self.session.scalars(
            select(AuditRecord).where(AuditRecord.case_id == case_id).order_by(AuditRecord.occurred_at.desc())
        ).first()

    def append(
        self,
        *,
        case_id: uuid.UUID,
        actor_id: uuid.UUID | None,
        action: str,
        before_state: dict | None = None,
        after_state: dict | None = None,
        metadata: dict | None = None,
        occurred_at: datetime | None = None,
    ) -> AuditRecord:
        if action not in VALID_ACTIONS:
            raise ValueError(f"unknown audit action: {action!r}")

        prev = self._last_record(case_id)
        prev_hash = prev.record_hash if prev is not None else GENESIS_HASH

        occurred_at = occurred_at or datetime.now(UTC)
        if prev is not None and occurred_at <= prev.occurred_at:
            occurred_at = prev.occurred_at + timedelta(microseconds=1)

        metadata = metadata or {}
        payload = _record_payload(
            case_id=case_id,
            actor_id=actor_id,
            action=action,
            before_state=before_state,
            after_state=after_state,
            metadata=metadata,
            occurred_at=occurred_at,
            prev_hash=prev_hash,
        )
        record_hash = _record_hash(payload)

        record = AuditRecord(
            case_id=case_id,
            actor_id=actor_id,
            action=action,
            before_state=before_state,
            after_state=after_state,
            audit_metadata=metadata,
            prev_hash=prev_hash,
            record_hash=record_hash,
            occurred_at=occurred_at,
        )
        self.session.add(record)
        self.session.flush()
        return record

    def verify_chain(self, case_id: uuid.UUID) -> dict:
        """Recomputes every record's hash in chain order. Returns
        `{"valid": True, "broken_at": None, "reason": None}` if the chain
        is intact, or the id and reason of the first record where it
        breaks (either a bad `prev_hash` link or a `record_hash` that no
        longer matches the record's own stored data)."""
        records = self.session.scalars(
            select(AuditRecord).where(AuditRecord.case_id == case_id).order_by(AuditRecord.occurred_at.asc())
        ).all()

        expected_prev = GENESIS_HASH
        for record in records:
            if record.prev_hash != expected_prev:
                return {
                    "valid": False,
                    "broken_at": str(record.id),
                    "reason": (
                        f"broken chain link: record {record.id} has prev_hash "
                        f"{record.prev_hash!r} but the preceding record's hash is {expected_prev!r}"
                    ),
                }

            payload = _record_payload(
                case_id=record.case_id,
                actor_id=record.actor_id,
                action=record.action,
                before_state=record.before_state,
                after_state=record.after_state,
                metadata=record.audit_metadata,
                occurred_at=record.occurred_at,
                prev_hash=record.prev_hash,
            )
            recomputed = _record_hash(payload)
            if recomputed != record.record_hash:
                return {
                    "valid": False,
                    "broken_at": str(record.id),
                    "reason": (
                        f"tampered record: stored hash {record.record_hash!r} does not match "
                        f"recomputed hash {recomputed!r} for record {record.id} (action={record.action!r})"
                    ),
                }

            expected_prev = record.record_hash

        return {"valid": True, "broken_at": None, "reason": None}
