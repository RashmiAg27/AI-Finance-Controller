import json
from pathlib import Path

from app.core.errors import IngestionError
from app.domains.ingestion.adapters.base import RawRecord


def parse(path: Path, *, sheet_name: str | None = None) -> list[RawRecord]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and "records" in raw:
        raw = raw["records"]
    if not isinstance(raw, list):
        raise IngestionError(f"JSON source file must be a top-level array (or {{'records': [...]}}: {path}")
    records = []
    for i, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise IngestionError(f"JSON record #{i} in {path} is not an object")
        records.append(RawRecord(row_number=i, data={k: ("" if v is None else str(v)) for k, v in item.items()}))
    return records
