from datetime import datetime

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import default_clock
from app.core.ids import new_id
from app.db.base import Base


class GroundTruthEntry(Base):
    """Known-correct outcome for one synthetic 'economic event', used only by
    the evaluation harness/tests -- never read by the matching/tax/ML engines
    themselves, so ground truth can never leak into the algorithms it grades.
    """

    __tablename__ = "ground_truth_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    client_id: Mapped[str] = mapped_column(String(36), index=True)
    batch_label: Mapped[str] = mapped_column(String(128), index=True)
    economic_transaction_id: Mapped[str] = mapped_column(String(128), index=True)
    scenario_name: Mapped[str] = mapped_column(String(64), index=True)

    expected_match_group_json: Mapped[dict] = mapped_column(JSON, default=dict)
    expected_exception_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expected_cardinality: Mapped[str | None] = mapped_column(String(16), nullable=True)

    created_at: Mapped[datetime] = mapped_column(default=default_clock.now)
