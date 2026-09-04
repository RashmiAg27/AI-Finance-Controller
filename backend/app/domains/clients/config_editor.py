"""Operator edits to a client's configuration, from the Tax & Fees and
Matching Rules windows.

An edit is never an in-place mutation of the ACTIVE configuration. It writes
a *new version*, validates it against the same schema a hand-written YAML file
goes through, and activates it -- so every saved change is hashed, versioned,
attributable, and reversible by re-activating the previous version. Batches
already in flight are unaffected: a Batch binds its config_version_id when it
is created.
"""
from __future__ import annotations

from typing import Any, get_args

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConfigValidationError, NotFoundError
from app.domains.clients import config_loader
from app.models.config_version import ClientConfiguration
from app.schemas.config import CanonicalField, ClientConfigSchema

# Sections the UI is allowed to replace. Everything else (client_id,
# config_version) is derived, and data_sources is edited through its own
# field-mapping endpoint so a malformed mapping can be rejected with a message
# that names the source it came from.
EDITABLE_SECTIONS = {
    "data_sources", "identifier_linkage", "normalization_rules", "classification_rules",
    "matching_rules", "tolerance_defaults", "exception_rules", "aggregation_rules", "tax_fee_rules",
}


def active_config_row(db: Session, client_id: str) -> ClientConfiguration:
    row = db.execute(
        select(ClientConfiguration).where(
            ClientConfiguration.client_id == client_id, ClientConfiguration.status == "ACTIVE"
        )
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError("ActiveClientConfiguration", client_id)
    return row


def active_config(db: Session, client_id: str) -> ClientConfigSchema:
    return ClientConfigSchema.model_validate(active_config_row(db, client_id).parsed_json)


def patch_active_config(db: Session, client_id: str, patch: dict[str, Any],
                        *, actor: str = "system") -> ClientConfiguration:
    """Replaces whole top-level sections of the active config and activates
    the result as the next version. Returns the newly ACTIVE row."""
    unknown = sorted(set(patch) - EDITABLE_SECTIONS)
    if unknown:
        raise ConfigValidationError(
            f"section(s) {unknown} are not editable; editable sections: {sorted(EDITABLE_SECTIONS)}"
        )

    current = active_config_row(db, client_id)
    parsed = dict(current.parsed_json)
    parsed.update(patch)
    parsed["config_version"] = current.version + 1

    # Round-trip through YAML so the stored raw_yaml is the real, re-loadable
    # source of this version rather than a rendering of it -- an operator must
    # be able to export what the UI saved and load it back unchanged.
    raw_yaml = yaml.safe_dump(parsed, sort_keys=False, allow_unicode=True, default_flow_style=False)

    new_version = config_loader.load_config_version(db, client_id=client_id, raw_yaml=raw_yaml, created_by=actor)
    return config_loader.activate_config_version(db, config_version_id=new_version.id, actor=actor)


# ---------------------------------------------------------------------------
# Section views the windows actually render
# ---------------------------------------------------------------------------

def tax_view(db: Session, client_id: str) -> dict:
    """What the Tax & Fees window shows: the fee, the tax on it, the
    commission, and every statutory charge -- each with the provenance the
    config recorded, so an unverified rate is visibly unverified."""
    row = active_config_row(db, client_id)
    config = ClientConfigSchema.model_validate(row.parsed_json)
    rules = config.tax_fee_rules
    return {
        "client_id": client_id,
        "config_version": row.version,
        "configured": rules is not None,
        "tax_fee_rules": rules.model_dump(mode="json") if rules else None,
    }


def matching_view(db: Session, client_id: str) -> dict:
    """What the Matching Rules window shows: how each source's own field names
    map onto this system's canonical fields, which identifier types are
    declared equivalent and why, and the pass-by-pass matching rules."""
    row = active_config_row(db, client_id)
    config = ClientConfigSchema.model_validate(row.parsed_json)
    return {
        "client_id": client_id,
        "config_version": row.version,
        "data_sources": [ds.model_dump(mode="json") for ds in config.data_sources],
        "identifier_linkage": [r.model_dump(mode="json") for r in config.identifier_linkage],
        "matching_rules": [r.model_dump(mode="json", by_alias=True) for r in config.matching_rules],
        "normalization_rules": config.normalization_rules.model_dump(mode="json"),
        "tolerance_defaults": config.tolerance_defaults.model_dump(mode="json"),
        "aggregation_rules": config.aggregation_rules.model_dump(mode="json") if config.aggregation_rules else None,
        "canonical_fields": list(get_args(CanonicalField)),
    }
