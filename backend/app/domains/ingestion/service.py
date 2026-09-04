from pathlib import Path

from sqlalchemy.orm import Session

from app.core.errors import IngestionError, NotFoundError
from app.domains.ingestion import file_store
from app.domains.ingestion.adapters import csv_adapter, json_adapter, pdf_adapter, xlsx_adapter
from app.models.batch import Batch, BatchFile
from app.models.client import Client
from app.models.data_source import DataSource
from app.models.source_file import SourceFile, SourceRecord

_ADAPTERS = {
    "CSV": csv_adapter.parse,
    "XLSX": xlsx_adapter.parse,
    "JSON": json_adapter.parse,
    "PDF": pdf_adapter.parse,
}


def store_uploaded_file(db: Session, *, batch: Batch, client: Client, data_source: DataSource,
                         filename: str, content: bytes) -> SourceFile:
    # data_source.file_format (from config), not the upload's file extension,
    # drives which adapter parses this file later.
    path = file_store.raw_file_path(client.code, batch.batch_code, data_source.source_id, filename)
    checksum = file_store.write_raw_file(path, content)

    source_file = SourceFile(
        client_id=client.id,
        batch_id=batch.id,
        data_source_id=data_source.id,
        original_filename=filename,
        storage_path=str(path),
        checksum_sha256=checksum,
        file_format=data_source.file_format,
        size_bytes=len(content),
    )
    db.add(source_file)
    db.flush()
    db.add(BatchFile(batch_id=batch.id, data_source_id=data_source.id, source_file_id=source_file.id))
    db.flush()
    return source_file


def parse_source_file(db: Session, *, source_file: SourceFile, sheet_name: str | None = None) -> list[SourceRecord]:
    adapter = _ADAPTERS.get(source_file.file_format)
    if adapter is None:
        raise IngestionError(f"no ingestion adapter registered for format {source_file.file_format!r}")

    records: list[SourceRecord] = []
    try:
        raw_records = adapter(Path(source_file.storage_path), sheet_name=sheet_name)
    except NotImplementedError:
        raise
    except Exception as exc:  # noqa: BLE001 -- surfaced as a single ERROR source_record, not a crash
        row = SourceRecord(
            source_file_id=source_file.id, batch_id=source_file.batch_id, row_number=0,
            raw_data={}, parse_status="ERROR", parse_error=str(exc),
        )
        db.add(row)
        db.flush()
        return [row]

    for raw in raw_records:
        row = SourceRecord(
            source_file_id=source_file.id,
            batch_id=source_file.batch_id,
            row_number=raw.row_number,
            raw_data=raw.data,
            parse_status="OK",
        )
        db.add(row)
        records.append(row)
    db.flush()
    return records


def get_data_source_by_code(db: Session, *, client_id: str, source_id: str) -> DataSource:
    from sqlalchemy import select

    row = db.execute(
        select(DataSource).where(DataSource.client_id == client_id, DataSource.source_id == source_id)
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError("DataSource", source_id)
    return row
