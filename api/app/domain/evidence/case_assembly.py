"""Groups Part 2's Alerts into opened Cases (blueprint §8 Journey B:
`Open -> Drafting -> ...` starts from an opened case).

One case per ACCOUNT, never merged across accounts — including the three
accounts that share a single CIRCULAR_FLOW finding. Each account is its
own distinct financial actor with its own transaction history that an
analyst needs to review on its own terms; treating a shared typology as
grounds to fold them into one investigation is an analytical judgement
call, not something case assembly should make automatically. If two cases
later turn out to describe the same ring, linking or merging them is a
deliberate, later, human/analyst action (and a case for a future part's
UI/audit trail), not an automatic side effect of detection.
"""

import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.alert import Alert
from app.models.case import Case
from app.models.case_subject import CaseSubject

CASE_OPENING_SEVERITIES = ("HIGH", "MEDIUM")
DEFAULT_CASE_DEADLINE_DAYS = 30
CASE_REF_PREFIX = "CASE-"
CASE_REF_DIGITS = 4


def _next_case_ref(session: Session) -> str:
    """Parses existing refs rather than relying on lexicographic MAX(), so
    ordering stays correct even past the zero-padding width (e.g.
    CASE-10000 must not sort before CASE-9999)."""
    existing = session.scalars(select(Case.case_ref)).all()
    max_n = 0
    for ref in existing:
        try:
            max_n = max(max_n, int(ref.removeprefix(CASE_REF_PREFIX)))
        except ValueError:
            continue
    return f"{CASE_REF_PREFIX}{max_n + 1:0{CASE_REF_DIGITS}d}"


def assemble_cases(session: Session) -> dict:
    """For every account with at least one HIGH/MEDIUM alert, ensure an
    OPEN case exists linking all of that account's such alerts, creating
    one if needed. Safe to call repeatedly: an account whose alerts are
    already linked to an open case gets new alerts attached to that same
    case rather than a duplicate one."""

    alerts = session.scalars(select(Alert).where(Alert.severity.in_(CASE_OPENING_SEVERITIES))).all()

    by_account: dict[uuid.UUID, list[Alert]] = defaultdict(list)
    for alert in alerts:
        by_account[alert.account_id].append(alert)

    cases_created = 0
    cases_reused = 0
    alerts_linked = 0

    for account_id, account_alerts in by_account.items():
        existing_case: Case | None = None
        for alert in account_alerts:
            if alert.case_id is None:
                continue
            candidate = session.get(Case, alert.case_id)
            if candidate is not None and candidate.status == "OPEN":
                existing_case = candidate
                break

        if existing_case is None:
            account = session.get(Account, account_id)
            now = datetime.now(UTC)
            case = Case(
                case_ref=_next_case_ref(session),
                status="OPEN",
                risk_score=max(alert.score for alert in account_alerts),
                opened_at=now,
                deadline_at=now + timedelta(days=DEFAULT_CASE_DEADLINE_DAYS),
            )
            session.add(case)
            session.flush()  # assign case.id before the FK use below

            session.add(CaseSubject(case_id=case.id, customer_id=account.customer_id, role="primary"))

            cases_created += 1
            existing_case = case
        else:
            cases_reused += 1

        for alert in account_alerts:
            if alert.case_id != existing_case.id:
                alert.case_id = existing_case.id
                alerts_linked += 1

    session.flush()

    return {
        "accounts_considered": len(by_account),
        "cases_created": cases_created,
        "cases_reused": cases_reused,
        "alerts_linked": alerts_linked,
    }
