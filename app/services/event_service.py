"""Service layer for corporate events management."""

from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CorporateEvent
from app.schemas.events import (
    CorporateEventCreate,
    CorporateEventUpdate,
    CorporateEventResponse,
    CorporateEventListResponse,
    EventStatusEnum,
    EventTypeEnum,
)


async def create_event(
    session: AsyncSession,
    event_data: CorporateEventCreate,
) -> CorporateEvent:
    """Create a new corporate event.
    
    Args:
        session: Database session
        event_data: Event data to create
        
    Returns:
        Created event
    """
    event = CorporateEvent(
        symbol=event_data.symbol,
        event_date=event_data.event_date,
        event_type=event_data.event_type.value,
        ratio=event_data.ratio,
        amount=event_data.amount,
        currency=event_data.currency,
        ex_date=event_data.ex_date,
        severity=event_data.severity.value if event_data.severity else None,
        notes=event_data.notes,
        detection_method=event_data.detection_method,
        db_price_at_detection=event_data.db_price_at_detection,
        yf_price_at_detection=event_data.yf_price_at_detection,
        pct_difference=event_data.pct_difference,
        source_data=event_data.source_data,
    )
    session.add(event)
    await session.commit()
    await session.refresh(event)
    return event


async def get_event_by_id(
    session: AsyncSession,
    event_id: int,
) -> Optional[CorporateEvent]:
    """Get event by ID.
    
    Args:
        session: Database session
        event_id: Event ID
        
    Returns:
        Event if found, None otherwise
    """
    result = await session.execute(
        select(CorporateEvent).where(CorporateEvent.id == event_id)
    )
    return result.scalar_one_or_none()


async def get_events(
    session: AsyncSession,
    symbol: Optional[str] = None,
    event_type: Optional[EventTypeEnum] = None,
    status: Optional[EventStatusEnum] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    page: int = 1,
    page_size: int = 50,
) -> CorporateEventListResponse:
    """Get paginated list of events with filters.
    
    Args:
        session: Database session
        symbol: Filter by symbol
        event_type: Filter by event type
        status: Filter by status
        from_date: Filter events from this date
        to_date: Filter events to this date
        page: Page number (1-indexed)
        page_size: Number of items per page
        
    Returns:
        Paginated event list
    """
    # Build query
    query = select(CorporateEvent)
    
    # Apply filters
    conditions = []
    if symbol:
        conditions.append(CorporateEvent.symbol == symbol)
    if event_type:
        conditions.append(CorporateEvent.event_type == event_type.value)
    if status:
        conditions.append(CorporateEvent.status == status.value)
    if from_date:
        conditions.append(CorporateEvent.event_date >= from_date)
    if to_date:
        conditions.append(CorporateEvent.event_date <= to_date)
    
    if conditions:
        query = query.where(and_(*conditions))
    
    # Get total count
    count_query = select(func.count()).select_from(CorporateEvent)
    if conditions:
        count_query = count_query.where(and_(*conditions))
    total_result = await session.execute(count_query)
    total = total_result.scalar()
    
    # Apply pagination and ordering
    query = query.order_by(CorporateEvent.detected_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    
    # Execute query
    result = await session.execute(query)
    events = result.scalars().all()
    
    return CorporateEventListResponse(
        events=[CorporateEventResponse.model_validate(e) for e in events],
        total=total,
        page=page,
        page_size=page_size,
    )


async def get_events_by_symbol(
    session: AsyncSession,
    symbol: str,
) -> List[CorporateEvent]:
    """Get all events for a symbol.
    
    Args:
        session: Database session
        symbol: Stock symbol
        
    Returns:
        List of events
    """
    result = await session.execute(
        select(CorporateEvent)
        .where(CorporateEvent.symbol == symbol)
        .order_by(CorporateEvent.event_date.desc())
    )
    return list(result.scalars().all())


async def get_pending_events(
    session: AsyncSession,
) -> List[CorporateEvent]:
    """Get all pending (not fixed/ignored) events.
    
    Args:
        session: Database session
        
    Returns:
        List of pending events
    """
    result = await session.execute(
        select(CorporateEvent)
        .where(
            and_(
                CorporateEvent.status != 'fixed',
                CorporateEvent.status != 'ignored',
            )
        )
        .order_by(CorporateEvent.detected_at.desc())
    )
    return list(result.scalars().all())


async def update_event(
    session: AsyncSession,
    event_id: int,
    event_data: CorporateEventUpdate,
) -> Optional[CorporateEvent]:
    """Update event.
    
    Args:
        session: Database session
        event_id: Event ID
        event_data: Update data
        
    Returns:
        Updated event if found, None otherwise
    """
    event = await get_event_by_id(session, event_id)
    if not event:
        return None
    
    if event_data.status:
        event.status = event_data.status.value
    if event_data.notes is not None:
        event.notes = event_data.notes
    
    event.updated_at = datetime.utcnow()
    await session.commit()
    await session.refresh(event)
    return event


async def confirm_event(
    session: AsyncSession,
    event_id: int,
) -> Optional[CorporateEvent]:
    """Confirm an event (mark as confirmed status).
    
    Args:
        session: Database session
        event_id: Event ID
        
    Returns:
        Updated event if found, None otherwise
    """
    return await update_event(
        session,
        event_id,
        CorporateEventUpdate(status=EventStatusEnum.CONFIRMED),
    )


async def ignore_event(
    session: AsyncSession,
    event_id: int,
    reason: Optional[str] = None,
) -> Optional[CorporateEvent]:
    """Ignore an event (mark as ignored status).
    
    Args:
        session: Database session
        event_id: Event ID
        reason: Optional reason for ignoring
        
    Returns:
        Updated event if found, None otherwise
    """
    notes = f"Ignored: {reason}" if reason else "Ignored"
    return await update_event(
        session,
        event_id,
        CorporateEventUpdate(status=EventStatusEnum.IGNORED, notes=notes),
    )


async def get_dividend_calendar(
    session: AsyncSession,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    symbol: Optional[str] = None,
) -> List[CorporateEvent]:
    """Get dividend calendar.
    
    Args:
        session: Database session
        from_date: Start date filter
        to_date: End date filter
        symbol: Symbol filter
        
    Returns:
        List of dividend events
    """
    query = select(CorporateEvent).where(
        or_(
            CorporateEvent.event_type == 'dividend',
            CorporateEvent.event_type == 'special_dividend',
        )
    )
    
    conditions = []
    if from_date:
        conditions.append(CorporateEvent.event_date >= from_date)
    if to_date:
        conditions.append(CorporateEvent.event_date <= to_date)
    if symbol:
        conditions.append(CorporateEvent.symbol == symbol)
    
    if conditions:
        query = query.where(and_(*conditions))
    
    query = query.order_by(CorporateEvent.event_date.desc())
    
    result = await session.execute(query)
    return list(result.scalars().all())


async def get_split_history(
    session: AsyncSession,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    symbol: Optional[str] = None,
) -> List[CorporateEvent]:
    """Get split history.
    
    Args:
        session: Database session
        from_date: Start date filter
        to_date: End date filter
        symbol: Symbol filter
        
    Returns:
        List of split events
    """
    query = select(CorporateEvent).where(
        or_(
            CorporateEvent.event_type == 'stock_split',
            CorporateEvent.event_type == 'reverse_split',
        )
    )
    
    conditions = []
    if from_date:
        conditions.append(CorporateEvent.event_date >= from_date)
    if to_date:
        conditions.append(CorporateEvent.event_date <= to_date)
    if symbol:
        conditions.append(CorporateEvent.symbol == symbol)
    
    if conditions:
        query = query.where(and_(*conditions))
    
    query = query.order_by(CorporateEvent.event_date.desc())
    
    result = await session.execute(query)
    return list(result.scalars().all())


async def check_event_exists(
    session: AsyncSession,
    symbol: str,
    event_date: date,
    event_type: str,
) -> bool:
    """Check if event already exists (for duplicate prevention).
    
    Args:
        session: Database session
        symbol: Stock symbol
        event_date: Event date
        event_type: Event type
        
    Returns:
        True if event exists
    """
    result = await session.execute(
        select(func.count())
        .select_from(CorporateEvent)
        .where(
            and_(
                CorporateEvent.symbol == symbol,
                CorporateEvent.event_date == event_date,
                CorporateEvent.event_type == event_type,
            )
        )
    )
    return result.scalar() > 0


async def record_event(
    session: AsyncSession,
    event_data: CorporateEventCreate,
) -> CorporateEvent:
    """Record an event, handling duplicates.
    
    Args:
        session: Database session
        event_data: Event data
        
    Returns:
        Created or existing event
    """
    # Check for duplicates
    exists = await check_event_exists(
        session,
        event_data.symbol,
        event_data.event_date,
        event_data.event_type.value,
    )
    
    if exists:
        # If it exists, we return the existing event.
        # But check_event_exists returns bool in current implementation!
        # I need to change check_event_exists to return the event, or query it.
        # The current check_event_exists returns bool.
        
        # So I need to fetch it.
        query = select(CorporateEvent).where(
            and_(
                CorporateEvent.symbol == event_data.symbol,
                CorporateEvent.event_date == event_data.event_date,
                CorporateEvent.event_type == event_data.event_type.value,
            )
        )
        result = await session.execute(query)
        existing_event = result.scalar_one_or_none()
        if existing_event:
            return existing_event
            
    # Create new
    return await create_event(session, event_data)
