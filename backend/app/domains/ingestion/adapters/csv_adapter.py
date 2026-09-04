from pathlib import Path

import pandas as pd

from app.domains.ingestion.adapters.base import RawRecord


def parse(path: Path, *, sheet_name: str | None = None) -> list[RawRecord]:
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    return [RawRecord(row_number=i, data=row) for i, row in enumerate(df.to_dict(orient="records"), start=1)]
