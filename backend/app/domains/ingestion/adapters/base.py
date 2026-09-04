from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass
class RawRecord:
    row_number: int
    data: dict  # original column names -> original (string/number) values, untouched


class SourceAdapter(Protocol):
    def parse(self, path: Path, *, sheet_name: str | None = None) -> list[RawRecord]:
        ...
