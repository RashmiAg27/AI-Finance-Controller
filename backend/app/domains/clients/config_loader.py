import hashlib
import json

import yaml
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import record_event
from app.core.clock import default_clock
from app.core.errors import ConfigValidationError, ConfigVersionError, NotFoundError
from app.models.client import Client
from app.models.config_version import ClientConfiguration
from app.models.data_source import DataSource
from app.schemas.config import ClientConfigSchema


def _canonical_hash(parsed: dict) -> str:
    canonical = json.dumps(parsed, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def parse_and_validate(raw_yaml: str) -> ClientConfigSchema:
    try:
        raw = yaml.safe_load(raw_yaml)
    except yaml.YAMLError as exc:
        raise ConfigValidationError(f"invalid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigValidationError("config YAML must parse to a mapping at the top level")
    try:
        return ClientConfigSchema.model_validate(raw)
    except ValidationError as exc:
        raise ConfigValidationError(str(exc)) from exc


def load_config_version(db: Session, client_id: str, raw_yaml: str, created_by: str = "system") -> ClientConfiguration:
    """Parse, validate, version-check, hash, and persist a new DRAFT config
    version. Does not activate it -- see activate_config_version()."""

    client = db.get(Client, client_id)
    if client is None:
        raise NotFoundError("Client", client_id)

    config = parse_and_validate(raw_yaml)
    if config.client_id != client.code:
        raise ConfigValidationError(
            f"config.client_id ({config.client_id!r}) does not match client code ({client.code!r})"
        )

    current_max = db.execute(
        select(func.max(ClientConfiguration.version)).where(ClientConfiguration.client_id == client_id)
    ).scalar_one_or_none() or 0
    expected_next = current_max + 1
    if config.config_version != expected_next:
        raise ConfigVersionError(
            f"config_version in YAML is {config.config_version}, but the next expected version "
            f"for client {client.code!r} is {expected_next}"
        )

    parsed_json = config.model_dump(mode="json", by_alias=True)
    row = ClientConfiguration(
        client_id=client_id,
        version=config.config_version,
        config_hash=_canonical_hash(parsed_json),
        raw_yaml=raw_yaml,
        parsed_json=parsed_json,
        status="DRAFT",
        created_by=created_by,
    )
    db.add(row)
    db.flush()
    record_event(db, entity_type="CONFIG", entity_id=row.id, event_type="CONFIG_LOADED",
                 payload={"client_id": client_id, "version": row.version}, actor=created_by)
    return row


def activate_config_version(db: Session, config_version_id: str, actor: str = "system") -> ClientConfiguration:
    row = db.get(ClientConfiguration, config_version_id)
    if row is None:
        raise NotFoundError("ClientConfiguration", config_version_id)

    previous_active = db.execute(
        select(ClientConfiguration).where(
            ClientConfiguration.client_id == row.client_id,
            ClientConfiguration.status == "ACTIVE",
        )
    ).scalar_one_or_none()
    if previous_active is not None:
        previous_active.status = "ARCHIVED"

    row.status = "ACTIVE"
    row.activated_at = default_clock.now()

    parsed = ClientConfigSchema.model_validate(row.parsed_json)
    _sync_data_sources(db, client_id=row.client_id, config=parsed)

    db.flush()
    record_event(db, entity_type="CONFIG", entity_id=row.id, event_type="CONFIG_ACTIVATED",
                 payload={"client_id": row.client_id, "version": row.version}, actor=actor)
    return row


def _sync_data_sources(db: Session, client_id: str, config: ClientConfigSchema) -> None:
    existing = {
        ds.source_id: ds
        for ds in db.execute(select(DataSource).where(DataSource.client_id == client_id)).scalars()
    }
    for ds_config in config.data_sources:
        if ds_config.source_id in existing:
            row = existing[ds_config.source_id]
            row.name = ds_config.source_id
            row.file_format = ds_config.file_format
            row.role = ds_config.role
            row.is_required = ds_config.is_required
        else:
            db.add(DataSource(
                client_id=client_id,
                source_id=ds_config.source_id,
                name=ds_config.source_id,
                file_format=ds_config.file_format,
                role=ds_config.role,
                is_required=ds_config.is_required,
            ))
