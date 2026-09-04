"""Import every ORM model exactly once so SQLAlchemy's declarative registry
sees all mapped classes (needed for Base.metadata.create_all and for string
forward-refs in relationship() to resolve). Import this module -- not the
individual model modules -- before touching the database."""

from app.models.audit_event import AuditEvent  # noqa: F401
from app.models.batch import Batch, BatchFile  # noqa: F401
from app.models.batch_definition import BatchDefinition  # noqa: F401
from app.models.batch_log import BatchLogEntry  # noqa: F401
from app.models.bank_account import BankAccount  # noqa: F401
from app.models.cash import CashForecast, CashPosition  # noqa: F401
from app.models.import_source import ImportSource  # noqa: F401
from app.models.client import Client  # noqa: F401
from app.models.config_version import ClientConfiguration  # noqa: F401
from app.models.data_source import DataSource  # noqa: F401
from app.models.exception_ import Exception_, ExceptionEvidence, ExceptionTransaction  # noqa: F401
from app.models.ground_truth import GroundTruthEntry  # noqa: F401
from app.models.reconciliation import (  # noqa: F401
    MatchEvidence,
    ReconciliationMatch,
    ReconciliationMatchTransaction,
    ReconciliationRun,
)
from app.models.settlement import Settlement, SettlementComponent  # noqa: F401
from app.models.source_file import SourceFile, SourceRecord  # noqa: F401
from app.models.tax import TaxCalculation, TaxRule  # noqa: F401
from app.models.transaction import Transaction, TransactionIdentifier  # noqa: F401
