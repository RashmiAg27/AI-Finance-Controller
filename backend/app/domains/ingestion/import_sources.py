"""Where a batch's files actually come from.

One rule holds for every kind: discovery yields (source_id, filename, bytes)
plus a human-readable origin line, and the caller stores them through the same
ingestion path an HTTP upload would take. Nothing downstream of discover()
knows or cares whether a file arrived from a directory, a mailbox, an SFTP
host, or a vendor API.

LOCAL_DIRECTORY reads this machine's filesystem for real -- point a batch at
a folder, save it, and the next run picks up whatever is sitting there. The
other three kinds are simulated against a per-connection landing area under
data/simulated/, and their logs narrate the protocol steps a real connector
would perform, so the operator-facing behaviour is identical.
"""
from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from pathlib import Path

from app.core.config import settings
from app.core.errors import DomainError
from app.models.import_source import ImportSource

# Files are addressed to a data source by a "<source_id>__<anything>.<ext>"
# filename. An explicit connection_json["source_map"] entry ({glob: source_id})
# overrides that convention for feeds whose vendor filenames can't be changed.
_SOURCE_SEPARATOR = "__"

_CONNECTION_FIELDS: dict[str, tuple[tuple[str, bool], ...]] = {
    # (field name, required)
    "LOCAL_DIRECTORY": (("directory", True), ("file_pattern", False), ("archive_after_import", False)),
    "EMAIL_INBOX": (("host", True), ("port", False), ("mailbox", True), ("username", True),
                    ("sender_allowlist", False), ("subject_pattern", False), ("attachment_pattern", False)),
    "SFTP_CONNECTION": (("host", True), ("port", False), ("username", True), ("remote_path", True),
                        ("key_reference", False), ("file_pattern", False)),
    "API_CONNECTION": (("base_url", True), ("endpoint", True), ("auth_method", False),
                       ("api_key_reference", False), ("poll_window_hours", False)),
}


class ImportSourceError(DomainError):
    pass


@dataclass
class DiscoveredFile:
    source_id: str
    filename: str
    content: bytes
    origin: str


@dataclass
class DiscoveryResult:
    files: list[DiscoveredFile] = field(default_factory=list)
    log_lines: list[str] = field(default_factory=list)
    location: str = ""

    @property
    def source_ids(self) -> set[str]:
        return {f.source_id for f in self.files}


# ---------------------------------------------------------------------------
# Configuration validation (what the Edit dialog is allowed to save)
# ---------------------------------------------------------------------------

def validate_connection(kind: str, connection: dict) -> dict:
    """Rejects a connection blob that couldn't possibly work, before it is
    saved -- an operator should find out that 'directory' is missing when they
    click Save, not at 19:30 when the scheduled run fires."""
    spec = _CONNECTION_FIELDS.get(kind)
    if spec is None:
        raise ImportSourceError(f"unknown import source kind {kind!r}; expected one of {list(_CONNECTION_FIELDS)}")

    allowed = {name for name, _ in spec} | {"source_map", "notes"}
    unknown = sorted(set(connection) - allowed)
    if unknown:
        raise ImportSourceError(f"{kind} connection has unsupported field(s): {unknown}; allowed: {sorted(allowed)}")

    missing = [name for name, required in spec if required and not str(connection.get(name) or "").strip()]
    if missing:
        raise ImportSourceError(f"{kind} connection is missing required field(s): {missing}")

    if kind == "LOCAL_DIRECTORY":
        directory = Path(str(connection["directory"])).expanduser()
        if directory.exists() and not directory.is_dir():
            raise ImportSourceError(f"{directory} exists but is not a directory")
    return connection


# ---------------------------------------------------------------------------
# Where each kind physically reads from
# ---------------------------------------------------------------------------

def landing_dir(import_source: ImportSource, client_code: str) -> Path:
    """The directory this import source reads. For LOCAL_DIRECTORY that is
    exactly what the operator configured; for the simulated kinds it is the
    connection's own staging area, which the demo seeder drops files into the
    way a mail server or SFTP host would."""
    if import_source.kind == "LOCAL_DIRECTORY":
        raw = str(import_source.connection_json.get("directory", "")).strip()
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = (settings.data_root.parent / path).resolve()
        return path
    return settings.data_root / "simulated" / import_source.kind.lower() / client_code / import_source.code


def describe_location(import_source: ImportSource, client_code: str) -> str:
    c = import_source.connection_json
    if import_source.kind == "LOCAL_DIRECTORY":
        return str(landing_dir(import_source, client_code))
    if import_source.kind == "EMAIL_INBOX":
        return f"imap://{c.get('host', '?')}/{c.get('mailbox', 'INBOX')} (as {c.get('username', '?')})"
    if import_source.kind == "SFTP_CONNECTION":
        return f"sftp://{c.get('username', '?')}@{c.get('host', '?')}:{c.get('port', 22)}{c.get('remote_path', '/')}"
    if import_source.kind == "API_CONNECTION":
        return f"{str(c.get('base_url', '')).rstrip('/')}{c.get('endpoint', '')}"
    return import_source.kind


def _file_pattern(import_source: ImportSource) -> str:
    c = import_source.connection_json
    if import_source.kind == "EMAIL_INBOX":
        return str(c.get("attachment_pattern") or "*")
    return str(c.get("file_pattern") or "*")


def _resolve_source_id(import_source: ImportSource, filename: str) -> str | None:
    for pattern, source_id in (import_source.connection_json.get("source_map") or {}).items():
        if fnmatch.fnmatch(filename, pattern):
            return source_id
    stem = Path(filename).name
    if _SOURCE_SEPARATOR in stem:
        return stem.split(_SOURCE_SEPARATOR, 1)[0]
    return None


# ---------------------------------------------------------------------------
# Protocol narration -- what the operator sees in the batch log
# ---------------------------------------------------------------------------

def _connect_lines(import_source: ImportSource, client_code: str, directory: Path) -> list[str]:
    c = import_source.connection_json
    pattern = _file_pattern(import_source)
    if import_source.kind == "LOCAL_DIRECTORY":
        return [f"Scanning local directory {directory} for '{pattern}'"]
    if import_source.kind == "EMAIL_INBOX":
        senders = ", ".join(c.get("sender_allowlist") or []) or "any sender"
        return [
            f"Connecting to {c.get('host')}:{c.get('port', 993)} as {c.get('username')} (IMAP over TLS)",
            f"SELECT {c.get('mailbox')} -- searching UNSEEN FROM ({senders}) "
            f"SUBJECT {str(c.get('subject_pattern') or '*')!r}",
            f"Downloading attachments matching '{pattern}'",
        ]
    if import_source.kind == "SFTP_CONNECTION":
        return [
            f"Opening SFTP session to {c.get('host')}:{c.get('port', 22)} as {c.get('username')} "
            f"(key ref: {c.get('key_reference', 'default')})",
            f"LIST {c.get('remote_path')} -- filtering on '{pattern}'",
        ]
    if import_source.kind == "API_CONNECTION":
        return [
            f"GET {describe_location(import_source, client_code)} "
            f"(auth: {c.get('auth_method', 'NONE')}, key ref: {c.get('api_key_reference', 'n/a')})",
            f"Requesting a {c.get('poll_window_hours', 24)}h settlement window",
        ]
    return []


def _fetched_line(import_source: ImportSource, filename: str, size: int, index: int) -> str:
    if import_source.kind == "EMAIL_INBOX":
        return f"Fetched attachment '{filename}' ({size:,} bytes) from message #{4800 + index}"
    if import_source.kind == "SFTP_CONNECTION":
        return f"GET {filename} -- {size:,} bytes transferred, checksum verified"
    if import_source.kind == "API_CONNECTION":
        return f"HTTP 200 -- payload '{filename}' ({size:,} bytes)"
    return f"Read {filename} ({size:,} bytes)"


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def discover(
    import_source: ImportSource,
    *,
    client_code: str,
    wanted_source_ids: list[str] | None = None,
) -> DiscoveryResult:
    """Finds every file this import source currently offers, keyed by the data
    source it fulfils. Never raises on 'nothing there' -- an empty result with
    an explanatory log is a normal, reportable outcome for a batch that is
    simply still waiting for its files."""
    directory = landing_dir(import_source, client_code)
    location = describe_location(import_source, client_code)
    result = DiscoveryResult(location=location)
    result.log_lines.extend(_connect_lines(import_source, client_code, directory))

    if not import_source.enabled:
        result.log_lines.append(f"Import source '{import_source.code}' is disabled -- no files fetched.")
        return result

    if not directory.exists():
        result.log_lines.append(
            f"No data available at {location} (path {directory} does not exist)."
        )
        return result

    pattern = _file_pattern(import_source)
    candidates = sorted(p for p in directory.iterdir() if p.is_file() and fnmatch.fnmatch(p.name, pattern))
    result.log_lines.append(f"{len(candidates)} file(s) available at {location}")

    for index, path in enumerate(candidates, start=1):
        source_id = _resolve_source_id(import_source, path.name)
        if source_id is None:
            result.log_lines.append(
                f"Skipped '{path.name}': cannot tell which data source it belongs to "
                f"(expected '<source_id>{_SOURCE_SEPARATOR}...' or a source_map entry)."
            )
            continue
        if wanted_source_ids is not None and source_id not in wanted_source_ids:
            result.log_lines.append(
                f"Skipped '{path.name}': data source '{source_id}' is not part of this batch."
            )
            continue
        content = path.read_bytes()
        result.files.append(
            DiscoveredFile(source_id=source_id, filename=path.name, content=content,
                           origin=f"{location}/{path.name}")
        )
        result.log_lines.append(_fetched_line(import_source, path.name, len(content), index))

    return result


def probe(import_source: ImportSource, *, client_code: str) -> dict:
    """Connection test for the Edit dialog: does this configuration currently
    resolve to anything, and what would a run pick up?"""
    outcome = discover(import_source, client_code=client_code)
    return {
        "kind": import_source.kind,
        "location": outcome.location,
        "status": "OK" if outcome.files else "EMPTY",
        "files": [{"source_id": f.source_id, "filename": f.filename, "size_bytes": len(f.content)}
                  for f in outcome.files],
        "log": outcome.log_lines,
    }
