"""History API endpoints."""

import logging

from fastapi import APIRouter, HTTPException, Request, Response, status

from app.models.schemas import (
    HistoryCreateRequest,
    HistoryListResponse,
    HistoryRecordResponse,
)
from app.services.history_service import history_service
from app.utils import get_user_id

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/history",
    response_model=HistoryRecordResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_history_record(
    request: Request, body: HistoryCreateRequest, response: Response
):
    """Create a new history record.

    Idempotent: Identische Einträge innerhalb von 60 Sekunden werden nicht doppelt gespeichert.
    Bei einem Duplikat wird 200 OK zurückgegeben (statt 201 Created) und der existierende
    Eintrag zurückgegeben.
    """
    user_id = get_user_id(request)
    record, created = history_service.add_record(
        user_id=user_id,
        operation_type=body.operation_type,
        source_text=body.source_text,
        target_text=body.target_text,
        source_lang=body.source_lang,
        target_lang=body.target_lang,
    )
    if not created:
        # Duplikat: 200 OK statt 201 Created, existierenden Eintrag zurückgeben
        response.status_code = status.HTTP_200_OK
    return HistoryRecordResponse.model_validate(record)


@router.get("/history", response_model=HistoryListResponse)
async def get_history(request: Request, limit: int = 100, offset: int = 0):
    """Get translation history for the current user."""
    # SEC-002: Add bounds checking on pagination parameters
    limit = min(max(limit, 1), 100)  # Clamp between 1 and 100
    offset = max(offset, 0)  # Ensure non-negative

    user_id = get_user_id(request)
    records, total = history_service.get_history(user_id, limit=limit, offset=offset)
    return HistoryListResponse(
        records=[HistoryRecordResponse.model_validate(r) for r in records],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/history/{record_id}", response_model=HistoryRecordResponse)
async def get_history_record(request: Request, record_id: int):
    """Get a single history record by ID."""
    user_id = get_user_id(request)
    record = history_service.get_record(user_id, record_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ERR_HISTORY_NOT_FOUND",
        )
    return HistoryRecordResponse.model_validate(record)


@router.delete("/history/{record_id}")
async def delete_history_record(request: Request, record_id: int):
    """Delete a single history record."""
    user_id = get_user_id(request)
    deleted = history_service.delete_record(user_id, record_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ERR_HISTORY_NOT_FOUND",
        )
    return {"message": "Record deleted successfully."}


@router.delete("/history")
async def delete_all_history(request: Request):
    """Delete all history records for the current user."""
    user_id = get_user_id(request)
    count = history_service.delete_all(user_id)
    return {"message": f"Deleted {count} records."}
