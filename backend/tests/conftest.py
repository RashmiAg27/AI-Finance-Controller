import os
import shutil
import tempfile
from pathlib import Path

import pytest

_tmp_db_fd, _tmp_db_path = tempfile.mkstemp(suffix=".db")
os.close(_tmp_db_fd)
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_tmp_db_path).as_posix()}"

_tmp_data_root = Path(tempfile.mkdtemp(prefix="afc_test_data_"))
os.environ["DATA_ROOT"] = str(_tmp_data_root)

from app.db.session import SessionLocal, create_all_tables, engine  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.domains.tax.rules_seed import ensure_seed_rules  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _schema_lifecycle():
    create_all_tables()
    yield
    engine.dispose()
    os.unlink(_tmp_db_path)
    shutil.rmtree(_tmp_data_root, ignore_errors=True)


@pytest.fixture(autouse=True)
def _reset_schema_per_test():
    """Each test gets a clean database. Tests intentionally reuse realistic
    client codes like 'client_a' across files (matching the real YAML fixture
    configs), so isolation has to come from resetting state, not from
    inventing unique codes per test."""
    Base.metadata.drop_all(bind=engine)
    create_all_tables()
    with SessionLocal() as db:
        ensure_seed_rules(db)
        db.commit()
    shutil.rmtree(_tmp_data_root, ignore_errors=True)
    _tmp_data_root.mkdir(parents=True, exist_ok=True)
    yield


@pytest.fixture()
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture()
def api_client():
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        yield client
