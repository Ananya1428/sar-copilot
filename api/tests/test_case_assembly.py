"""Case-assembly tests run against the live dev Postgres (see conftest.py)
inside a rolled-back SAVEPOINT — but the table can already hold genuine
HIGH/MEDIUM Alert rows committed by earlier manual `run-detection` CLI
runs, still unlinked to any case. `assemble_cases` correctly scans the
WHOLE alerts table (that's its actual job), so it will create cases for
those too whenever a test calls it — meaning `summary["cases_created"]`
is a whole-database count, not something a test can assert an exact value
of. Every assertion here is instead scoped to the specific alert(s)/
case(s) THIS test created (see Part 1/2's own lessons on this same
mistake with whole-table counts)."""

import re

from app.domain.evidence.case_assembly import assemble_cases
from app.models import Case, CaseSubject
from tests.factories import make_account, make_alert, make_customer


def _seed_account_with_alert(db_session, severity, rule_code="STRUCTURING", score="0.8000"):
    customer = make_customer()
    account = make_account(customer=customer)
    db_session.add(customer)
    db_session.add(account)
    db_session.flush()

    alert = make_alert(account, rule_code=rule_code, severity=severity, score=score)
    db_session.add(alert)
    db_session.flush()
    return customer, account, alert


def test_high_severity_alert_gets_a_case(db_session):
    customer, account, alert = _seed_account_with_alert(db_session, severity="HIGH")

    summary = assemble_cases(db_session)
    assert summary["cases_created"] >= 1

    db_session.refresh(alert)
    assert alert.case_id is not None

    case = db_session.get(Case, alert.case_id)
    assert case.status == "OPEN"
    assert case.risk_score == alert.score
    assert re.fullmatch(r"CASE-\d{4}", case.case_ref)

    subjects = db_session.query(CaseSubject).filter(CaseSubject.case_id == case.id).all()
    assert len(subjects) == 1
    assert subjects[0].customer_id == customer.id
    assert subjects[0].role == "primary"


def test_low_severity_alert_gets_no_case(db_session):
    _, _, alert = _seed_account_with_alert(db_session, severity="LOW")

    assemble_cases(db_session)

    db_session.refresh(alert)
    assert alert.case_id is None


def test_medium_severity_alert_gets_a_case(db_session):
    _, _, alert = _seed_account_with_alert(db_session, severity="MEDIUM")

    assemble_cases(db_session)

    db_session.refresh(alert)
    assert alert.case_id is not None


def test_rerunning_assembly_does_not_duplicate_open_cases(db_session):
    _, account, alert1 = _seed_account_with_alert(db_session, severity="HIGH")

    assemble_cases(db_session)
    db_session.refresh(alert1)
    case_id_after_first_run = alert1.case_id
    assert case_id_after_first_run is not None

    # A second detection run adds a new alert for the same account.
    alert2 = make_alert(account, rule_code="RAPID_MOVEMENT", severity="MEDIUM", score="0.6000")
    db_session.add(alert2)
    db_session.flush()

    assemble_cases(db_session)

    db_session.refresh(alert1)
    db_session.refresh(alert2)
    assert alert1.case_id == case_id_after_first_run  # unchanged, not a new case
    assert alert2.case_id == case_id_after_first_run  # new alert joined the SAME case


def test_multiple_accounts_each_get_their_own_case(db_session):
    _, _, alert1 = _seed_account_with_alert(db_session, severity="HIGH")
    _, _, alert2 = _seed_account_with_alert(db_session, severity="MEDIUM")

    assemble_cases(db_session)

    db_session.refresh(alert1)
    db_session.refresh(alert2)
    assert alert1.case_id is not None
    assert alert2.case_id is not None
    assert alert1.case_id != alert2.case_id


def test_circular_flow_accounts_get_separate_cases(db_session):
    """Three accounts sharing one CIRCULAR_FLOW finding must each get their
    own case, not be merged into one (case_assembly.py's documented choice)."""
    alerts = []
    for _ in range(3):
        _, _, alert = _seed_account_with_alert(
            db_session, severity="HIGH", rule_code="CIRCULAR_FLOW", score="0.9000"
        )
        alerts.append(alert)

    assemble_cases(db_session)

    for a in alerts:
        db_session.refresh(a)
    case_ids = {a.case_id for a in alerts}
    assert None not in case_ids
    assert len(case_ids) == 3
