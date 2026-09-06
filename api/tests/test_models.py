from datetime import date
from decimal import Decimal

from app.models import Account, Customer


def test_customer_account_roundtrip(db_session):
    customer = Customer(
        customer_ref="CUS-TEST1",
        legal_name="Test Person",
        entity_type="individual",
        onboarded_at=date(2020, 1, 1),
        risk_rating="LOW",
        occupation="Engineer",
        country="US",
    )
    db_session.add(customer)
    db_session.flush()

    account = Account(
        customer_id=customer.id,
        account_ref="ACC-TEST1",
        account_type="checking",
        currency="USD",
        opened_at=date(2020, 1, 2),
        expected_monthly_volume=Decimal("5000.00"),
        status="active",
    )
    db_session.add(account)
    db_session.flush()

    fetched = db_session.get(Account, account.id)
    assert fetched is not None
    assert fetched.account_ref == "ACC-TEST1"
    assert fetched.expected_monthly_volume == Decimal("5000.00")
    assert fetched.customer.legal_name == "Test Person"
