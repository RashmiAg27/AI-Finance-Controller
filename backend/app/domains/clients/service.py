from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.client import Client


def create_client(db: Session, *, code: str, name: str) -> Client:
    client = Client(code=code, name=name)
    db.add(client)
    db.flush()
    return client


def get_client(db: Session, client_id: str) -> Client:
    client = db.get(Client, client_id)
    if client is None:
        raise NotFoundError("Client", client_id)
    return client


def get_client_by_code(db: Session, code: str) -> Client:
    client = db.execute(select(Client).where(Client.code == code)).scalar_one_or_none()
    if client is None:
        raise NotFoundError("Client", code)
    return client


def list_clients(db: Session) -> list[Client]:
    return list(db.execute(select(Client).order_by(Client.created_at)).scalars())
