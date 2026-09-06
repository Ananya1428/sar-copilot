"""SQLAlchemy ORM models — full ERD from blueprint §10.1.

Two table names deliberately deviate from the ERD's singular entity names:
`case` -> `cases` and `user` -> `users`, both reserved words in PostgreSQL
that would otherwise need quoting everywhere. Every other table follows the
ERD's singular naming (customer, account, transaction, ...). This module
imports every model so `Base.metadata` is complete for Alembic autogenerate.
"""

from app.models.account import Account
from app.models.alert import Alert
from app.models.audit import AuditRecord
from app.models.base import Base
from app.models.case import Case
from app.models.case_note import CaseNote
from app.models.case_subject import CaseSubject
from app.models.customer import Customer
from app.models.evidence import EvidenceItem, EvidencePack
from app.models.export_artifact import ExportArtifact
from app.models.narrative import Narrative, NarrativeSentence
from app.models.transaction import Transaction
from app.models.user import User
from app.models.verification import VerificationReport

__all__ = [
    "Base",
    "Customer",
    "Account",
    "Transaction",
    "Alert",
    "Case",
    "CaseSubject",
    "EvidencePack",
    "EvidenceItem",
    "Narrative",
    "NarrativeSentence",
    "VerificationReport",
    "AuditRecord",
    "User",
    "CaseNote",
    "ExportArtifact",
]
