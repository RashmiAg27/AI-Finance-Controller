from sqlalchemy.orm import Session

from app.models.audit_event import AuditEvent


def record_event(db: Session, *, entity_type: str, entity_id: str, event_type: str,
                  payload: dict | None = None, actor: str = "system") -> AuditEvent:
    event = AuditEvent(
        entity_type=entity_type,
        entity_id=entity_id,
        event_type=event_type,
        payload_json=payload or {},
        actor=actor,
    )
    db.add(event)
    db.flush()
    return event
