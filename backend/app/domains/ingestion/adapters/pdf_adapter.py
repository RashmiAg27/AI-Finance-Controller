from pathlib import Path

from app.domains.ingestion.adapters.base import RawRecord


def parse(path: Path, *, sheet_name: str | None = None) -> list[RawRecord]:
    raise NotImplementedError(
        "PDF ingestion is explicitly out of scope for this build (see docs/architecture.md's "
        "deprioritized-for-MVP list) -- no PDF parsing logic is implemented."
    )
