from datetime import datetime

from sqlalchemy import ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import default_clock
from app.core.ids import new_id
from app.db.base import Base


class SourceFile(Base):
    """Metadata about one uploaded raw file. The raw bytes on disk are never
    mutated once written (see app.domains.ingestion.file_store)."""

    __tablename__ = "source_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"), index=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("batches.id"), index=True)
    data_source_id: Mapped[str] = mapped_column(ForeignKey("data_sources.id"))
    original_filename: Mapped[str] = mapped_column(String(512))
    storage_path: Mapped[str] = mapped_column(String(1024))
    checksum_sha256: Mapped[str] = mapped_column(String(64))
    file_format: Mapped[str] = mapped_column(String(16))
    size_bytes: Mapped[int] = mapped_column(Integer)
    uploaded_at: Mapped[datetime] = mapped_column(default=default_clock.now)
    uploaded_by: Mapped[str] = mapped_column(String(128), default="system")


class SourceRecord(Base):
    """One raw row/record exactly as parsed from a source file, before any
    normalization. This is the anchor of the raw->normalized lineage: every
    Transaction points back to exactly one SourceRecord."""

    __tablename__ = "source_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_file_id: Mapped[str] = mapped_column(ForeignKey("source_files.id"), index=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("batches.id"), index=True)
    row_number: Mapped[int] = mapped_column(Integer)
    raw_data: Mapped[dict] = mapped_column(JSON)
    parse_status: Mapped[str] = mapped_column(String(16), default="OK")  # OK | ERROR
    parse_error: Mapped[str | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=default_clock.now)
