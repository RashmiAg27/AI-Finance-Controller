"""The last line of defense between what the LLM composed and what a
finance operator sees.

The system prompt (app.agent.controller) instructs the model at length never
to surface internal identifiers, paths, tool names or raw evidence -- but a
prompt is not a guarantee, and this is a user-facing operations panel, not a
place to trust an LLM's instruction-following on faith. Every final answer is
scanned here before it leaves the backend, and anything that looks like
implementation detail is redacted regardless of why it appeared.

This module never touches what the model is given to work with (tool results
still carry real ids so the agent can chain follow-up calls) -- only what
comes back out.
"""
import re
from dataclasses import dataclass

# Matches this app's own id shape (app.core.ids.new_id -- uuid4, dashed hex)
# and, generously, any other dashed-hex token of the same shape a different
# system might have produced.
_UUID = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")

# A bare hex identifier/checksum long enough that it's never a business
# number a user would recognise -- a sha256 (64 chars), a truncated hash, or
# a non-dashed id.
_HEX_BLOB = re.compile(r"\b[0-9a-fA-F]{24,}\b")

# Windows (C:\...) and POSIX (/a/b/c) absolute paths, plus anything shaped
# like a REST path (/api/v1/...) -- all of these are "how", never "what".
_WINDOWS_PATH = re.compile(r"\b[A-Za-z]:\\[^\s\"'`,)]+")
_POSIX_PATH = re.compile(r"(?<![\w.])/(?:[\w.\-]+/){1,}[\w.\-]*")

# `get_batch_report(batch_id=...)`-shaped text -- a function call is never
# something a financial answer legitimately contains.
_FUNCTION_CALL = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\([^()]{0,300}\)")

# A raw (flat) JSON object leaking verbatim, e.g. {"batch_id": "...", ...}.
_JSON_OBJECT = re.compile(r"\{\s*[\"'][A-Za-z_][\w]*[\"']\s*:[^{}]{0,400}\}")

# `batch_id: 145d4d3c` / `client_id=...` -- catches an id reference even when
# the value itself doesn't happen to be full-length hex (e.g. it was
# truncated by the model).
_ID_FIELD_REFERENCE = re.compile(
    r"\b[a-z][a-z_]*_id\s*[:=]\s*['\"`]?[\w-]{4,}['\"`]?", re.IGNORECASE
)

_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("json_object", _JSON_OBJECT),
    ("function_call", _FUNCTION_CALL),
    ("windows_path", _WINDOWS_PATH),
    ("posix_path", _POSIX_PATH),
    ("id_field_reference", _ID_FIELD_REFERENCE),
    ("uuid", _UUID),
    ("hex_blob", _HEX_BLOB),
]

_REDACTION = "[internal reference removed]"


@dataclass
class Leak:
    category: str
    text: str


def find_leaks(text: str) -> list[Leak]:
    """What would be redacted, without redacting it -- used by tests and by
    anything that wants to log/alert on a model that tried to leak detail
    despite the system prompt telling it not to."""
    leaks: list[Leak] = []
    for category, pattern in _PATTERNS:
        for match in pattern.finditer(text):
            leaks.append(Leak(category=category, text=match.group(0)))
    return leaks


def scrub(text: str) -> str:
    """Redacts every internal-implementation-shaped span in `text`, applying
    the JSON/function-call/path patterns before the narrower id patterns so a
    leaked JSON blob or function call is removed as one unit rather than
    leaving a scattering of `[internal reference removed]` fragments where
    its individual id fields were."""
    result = text
    for _category, pattern in _PATTERNS:
        result = pattern.sub(_REDACTION, result)
    # A redaction can leave "( [internal reference removed] )" or doubled
    # punctuation behind; collapse the common cases rather than leaving
    # visibly mangled prose.
    result = re.sub(r"\(\s*" + re.escape(_REDACTION) + r"\s*\)", _REDACTION, result)
    result = re.sub(r"(?:\s*" + re.escape(_REDACTION) + r"){2,}", f" {_REDACTION}", result)
    result = re.sub(r"[ \t]{2,}", " ", result)
    return result
