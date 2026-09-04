from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.errors import DomainError, NotFoundError
from app.domains.batches import report, service
from app.schemas.batch import BatchCreateRequest, BatchResponse

router = APIRouter(tags=["batches"])


def _domain_error_to_http(exc: DomainError) -> HTTPException:
    if isinstance(exc, NotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


@router.post("/clients/{client_id}/batches", response_model=BatchResponse)
def create_batch(client_id: str, payload: BatchCreateRequest, db: Session = Depends(get_db)):
    try:
        batch = service.create_batch(db, client_id=client_id, batch_code=payload.batch_code)
        db.commit()
        return batch
    except DomainError as exc:
        db.rollback()
        raise _domain_error_to_http(exc)


@router.get("/batches", response_model=list[BatchResponse])
def list_batches(client_id: str | None = None, status: str | None = None,
                 batch_definition_id: str | None = None, db: Session = Depends(get_db)):
    return service.list_batches(db, client_id=client_id, status=status,
                                batch_definition_id=batch_definition_id)


@router.get("/batches/{batch_id}/report")
def get_batch_report(batch_id: str, include_log: bool = True, db: Session = Depends(get_db)):
    """The full account of a run -- stats, every exception with its evidence,
    settlement decomposition, and the resulting cash position. The agent reads
    exactly this, so its answers and the screen cannot disagree."""
    try:
        return report.build(db, batch_id, include_log=include_log)
    except DomainError as exc:
        raise _domain_error_to_http(exc)


@router.get("/batches/{batch_id}", response_model=BatchResponse)
def get_batch(batch_id: str, db: Session = Depends(get_db)):
    try:
        return service.get_batch(db, batch_id)
    except DomainError as exc:
        raise _domain_error_to_http(exc)


@router.post("/batches/{batch_id}/files", response_model=BatchResponse)
def upload_batch_file(batch_id: str, source_id: str, file: UploadFile, db: Session = Depends(get_db)):
    try:
        batch = service.get_batch(db, batch_id)
        content = file.file.read()
        service.upload_file(db, batch=batch, source_id=source_id, filename=file.filename, content=content)
        db.commit()
        return batch
    except DomainError as exc:
        db.rollback()
        raise _domain_error_to_http(exc)


@router.post("/batches/{batch_id}/files/complete", response_model=BatchResponse)
def complete_batch_files(batch_id: str, db: Session = Depends(get_db)):
    try:
        batch = service.get_batch(db, batch_id)
        service.mark_files_complete(db, batch)
        db.commit()
        return batch
    except DomainError as exc:
        db.rollback()
        raise _domain_error_to_http(exc)


@router.post("/batches/{batch_id}/process", response_model=BatchResponse)
def process_batch(batch_id: str, db: Session = Depends(get_db)):
    try:
        batch = service.get_batch(db, batch_id)
        service.process_batch(db, batch)
        db.commit()
        return batch
    except DomainError as exc:
        db.commit()  # batch was moved to FAILED with a reason -- persist that, don't roll it back
        raise _domain_error_to_http(exc)
