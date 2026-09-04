from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.errors import ConfigValidationError, ConfigVersionError, DomainError, NotFoundError
from app.domains.clients import config_loader, service
from app.schemas.client import (
    ClientCreateRequest,
    ClientResponse,
    ConfigVersionCreateRequest,
    ConfigVersionResponse,
)


class DataSourceResponse(BaseModel):
    source_id: str
    name: str
    role: str
    file_format: str
    is_required: bool

    model_config = {"from_attributes": True}

router = APIRouter(prefix="/clients", tags=["clients"])


def _domain_error_to_http(exc: DomainError) -> HTTPException:
    if isinstance(exc, NotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, (ConfigValidationError, ConfigVersionError)):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


@router.post("", response_model=ClientResponse)
def create_client(payload: ClientCreateRequest, db: Session = Depends(get_db)):
    client = service.create_client(db, code=payload.code, name=payload.name)
    db.commit()
    return client


@router.get("", response_model=list[ClientResponse])
def list_clients(db: Session = Depends(get_db)):
    return service.list_clients(db)


@router.get("/{client_id}", response_model=ClientResponse)
def get_client(client_id: str, db: Session = Depends(get_db)):
    try:
        return service.get_client(db, client_id)
    except DomainError as exc:
        raise _domain_error_to_http(exc)


@router.get("/{client_id}/data-sources", response_model=list[DataSourceResponse])
def list_data_sources(client_id: str, db: Session = Depends(get_db)):
    from sqlalchemy import select

    from app.models.data_source import DataSource

    stmt = select(DataSource).where(DataSource.client_id == client_id).order_by(DataSource.source_id)
    return list(db.execute(stmt).scalars())


@router.post("/{client_id}/config-versions", response_model=ConfigVersionResponse)
def create_config_version(client_id: str, payload: ConfigVersionCreateRequest, db: Session = Depends(get_db)):
    try:
        row = config_loader.load_config_version(db, client_id=client_id, raw_yaml=payload.raw_yaml)
        db.commit()
        return row
    except DomainError as exc:
        db.rollback()
        raise _domain_error_to_http(exc)


@router.get("/{client_id}/config-versions", response_model=list[ConfigVersionResponse])
def list_config_versions(client_id: str, db: Session = Depends(get_db)):
    from sqlalchemy import select

    from app.models.config_version import ClientConfiguration

    stmt = select(ClientConfiguration).where(ClientConfiguration.client_id == client_id).order_by(
        ClientConfiguration.version
    )
    return list(db.execute(stmt).scalars())


@router.post("/{client_id}/config-versions/{version}/activate", response_model=ConfigVersionResponse)
def activate_config_version(client_id: str, version: int, db: Session = Depends(get_db)):
    from sqlalchemy import select

    from app.models.config_version import ClientConfiguration

    row = db.execute(
        select(ClientConfiguration).where(
            ClientConfiguration.client_id == client_id, ClientConfiguration.version == version
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"no config version {version} for client {client_id}")
    try:
        activated = config_loader.activate_config_version(db, config_version_id=row.id)
        db.commit()
        return activated
    except DomainError as exc:
        db.rollback()
        raise _domain_error_to_http(exc)
