import uuid


def new_id() -> str:
    """Stable string UUID4 primary key, portable across SQLite and PostgreSQL."""
    return str(uuid.uuid4())
