"""FastAPI router for corporate events API."""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.schemas.events import (
    CorporateEventResponse,
    CorporateEventListResponse,
    EventTypeEnum,
    EventStatusEnum,
)
from app.services import event_service

router = APIRouter(prefix="/events", tags=["events"])



@router.get("", response_model=CorporateEventListResponse)
async def get_events(
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    event_type: Optional[EventTypeEnum] = Query(None, description="Filter by event type"),
    status: Optional[EventStatusEnum] = Query(None, description="Filter by status"),
    from_date: Optional[date] = Query(None, alias="from", description="Filter events from date"),
    to_date: Optional[date] = Query(None, alias="to", description="Filter events to date"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page"),
    session: AsyncSession = Depends(get_session),
):
    """Get paginated list of corporate events with filters."""
    return await event_service.get_events(
        session=session,
        symbol=symbol,
        event_type=event_type,
        status=status,
        from_date=from_date,
        to_date=to_date,
        page=page,
        page_size=page_size,
    )


@router.get("/pending", response_model=list[CorporateEventResponse])
async def get_pending_events(
    session: AsyncSession = Depends(get_session),
):
    """Get all pending (not fixed/ignored) events."""
    events = await event_service.get_pending_events(session)
    return [CorporateEventResponse.model_validate(e) for e in events]


@router.get("/dividends", response_model=list[CorporateEventResponse])
async def get_dividend_calendar(
    from_date: Optional[date] = Query(None, alias="from", description="Start date"),
    to_date: Optional[date] = Query(None, alias="to", description="End date"),
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    session: AsyncSession = Depends(get_session),
):
    """Get dividend calendar."""
    events = await event_service.get_dividend_calendar(
        session=session,
        from_date=from_date,
        to_date=to_date,
        symbol=symbol,
    )
    return [CorporateEventResponse.model_validate(e) for e in events]


@router.get("/splits", response_model=list[CorporateEventResponse])
async def get_split_history(
    from_date: Optional[date] = Query(None, alias="from", description="Start date"),
    to_date: Optional[date] = Query(None, alias="to", description="End date"),
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    session: AsyncSession = Depends(get_session),
):
    """Get split history."""
    events = await event_service.get_split_history(
        session=session,
        from_date=from_date,
        to_date=to_date,
        symbol=symbol,
    )
    return [CorporateEventResponse.model_validate(e) for e in events]


@router.get("/{symbol}", response_model=list[CorporateEventResponse])
async def get_events_by_symbol(
    symbol: str,
    session: AsyncSession = Depends(get_session),
):
    """Get all events for a specific symbol."""
    events = await event_service.get_events_by_symbol(session, symbol)
    return [CorporateEventResponse.model_validate(e) for e in events]


@router.post("/{event_id}/confirm", response_model=CorporateEventResponse)
async def confirm_event(
    event_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Confirm an event (mark as confirmed status)."""
    event = await event_service.confirm_event(session, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return CorporateEventResponse.model_validate(event)


@router.post("/{event_id}/ignore", response_model=CorporateEventResponse)
async def ignore_event(
    event_id: int,
    reason: Optional[str] = Query(None, description="Reason for ignoring"),
    session: AsyncSession = Depends(get_session),
):
    """Ignore an event (mark as ignored status)."""
    event = await event_service.ignore_event(session, event_id, reason)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return CorporateEventResponse.model_validate(event)
