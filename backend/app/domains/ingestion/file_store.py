import hashlib
from pathlib import Path

from app.core.config import settings


def raw_file_path(client_code: str, batch_code: str, source_id: str, filename: str) -> Path:
    """data/raw/{client}/{batch}/{source}/{filename} -- raw files are never
    mutated once written; a re-upload for the same source in the same batch
    is a new filename or a new batch, never an overwrite of history."""
    directory = settings.data_root / "raw" / client_code / batch_code / source_id
    directory.mkdir(parents=True, exist_ok=True)
    return directory / filename


def write_raw_file(path: Path, content: bytes) -> str:
    if path.exists():
        raise FileExistsError(f"raw file already exists and must not be overwritten: {path}")
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()
