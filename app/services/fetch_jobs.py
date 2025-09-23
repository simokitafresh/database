"""Fetch job management service."""

import uuid
import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select, insert, update
from sqlalchemy.exc import NoResultFound

from app.db.models import FetchJob
from app.schemas.fetch_jobs import (
    FetchJobRequest, 
    FetchJobResponse, 
    FetchJobProgress, 
    FetchJobResult,
    FetchJobListResponse
)


async def create_fetch_job(
    session: AsyncSession,
    request: FetchJobRequest,
    created_by: Optional[str] = None
) -> str:
    """
    Create a new fetch job.
    
    Args:
        session: Database session
        request: Job creation request
        created_by: User who created the job
        
    Returns:
        Created job ID
    """
    # Generate unique job ID
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    job_id = f"job_{timestamp}_{uuid.uuid4().hex[:6]}"
    
    # Create job record
    job_data = {
        'job_id': job_id,
        'status': 'pending',
        'symbols': request.symbols,
        'date_from': request.date_from,
        'date_to': request.date_to,
        'interval': request.interval,
        'force_refresh': request.force,
        'priority': request.priority,
        'progress': None,
        'results': [],
        'errors': [],
        'created_at': datetime.utcnow(),
        'started_at': None,
        'completed_at': None,
        'created_by': created_by
    }
    
    stmt = insert(FetchJob).values(**job_data)
    await session.execute(stmt)
    await session.commit()
    
    return job_id


async def get_job_status(
    session: AsyncSession,
    job_id: str
) -> Optional[FetchJobResponse]:
    """
    Get job status and details.
    
    Args:
        session: Database session
        job_id: Job ID to retrieve
        
    Returns:
        Job response or None if not found
    """
    stmt = select(FetchJob).where(FetchJob.job_id == job_id)
    result = await session.execute(stmt)
    
    try:
        job = result.scalar_one()
    except NoResultFound:
        return None
    
    # Calculate duration if started
    duration_seconds = None
    if job.started_at:
        end_time = job.completed_at or datetime.utcnow()
        duration_seconds = int((end_time - job.started_at).total_seconds())
    
    # Parse progress JSON
    progress = None
    if job.progress:
        progress_data = job.progress if isinstance(job.progress, dict) else json.loads(job.progress)
        progress = FetchJobProgress(**progress_data)
    
    # Parse results JSON
    results = []
    if job.results:
        results_data = job.results if isinstance(job.results, list) else json.loads(job.results)
        results = [FetchJobResult(**r) for r in results_data]
    
    # Parse errors JSON
    errors = []
    if job.errors:
        errors = job.errors if isinstance(job.errors, list) else json.loads(job.errors)
    
    return FetchJobResponse(
        job_id=job.job_id,
        status=job.status,
        symbols=job.symbols,
        date_from=job.date_from,
        date_to=job.date_to,
        interval=job.interval,
        force=job.force_refresh,
        priority=job.priority,
        progress=progress,
        results=results,
        errors=errors,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        duration_seconds=duration_seconds,
        created_by=job.created_by
    )


async def update_job_progress(
    session: AsyncSession,
    job_id: str,
    progress: FetchJobProgress
) -> None:
    """
    Update job progress information.
    
    Args:
        session: Database session
        job_id: Job ID to update
        progress: Progress information
    """
    progress_data = progress.dict()
    
    stmt = update(FetchJob).where(
        FetchJob.job_id == job_id
    ).values(
        progress=progress_data
    )
    
    await session.execute(stmt)
    await session.commit()


async def update_job_status(
    session: AsyncSession,
    job_id: str,
    status: str,
    started_at: Optional[datetime] = None,
    completed_at: Optional[datetime] = None
) -> None:
    """
    Update job status and timestamps.
    
    Args:
        session: Database session
        job_id: Job ID to update
        status: New status
        started_at: Job start time
        completed_at: Job completion time
    """
    update_data = {'status': status}
    
    if started_at:
        update_data['started_at'] = started_at
    
    if completed_at:
        update_data['completed_at'] = completed_at
    
    stmt = update(FetchJob).where(
        FetchJob.job_id == job_id
    ).values(**update_data)
    
    await session.execute(stmt)
    await session.commit()


async def save_job_results(
    session: AsyncSession,
    job_id: str,
    results: List[FetchJobResult],
    errors: Optional[List[Dict[str, Any]]] = None
) -> None:
    """
    Save job results and errors.
    
    Args:
        session: Database session
        job_id: Job ID to update
        results: List of job results
        errors: List of errors (optional)
    """
    results_data = []
    for r in results:
        result_dict = r.dict()
        # Remove date fields to avoid JSON serialization issues
        result_dict.pop('date_from', None)
        result_dict.pop('date_to', None)
        results_data.append(result_dict)
    errors_data = errors or []
    
    stmt = update(FetchJob).where(
        FetchJob.job_id == job_id
    ).values(
        results=results_data,
        errors=errors_data
    )
    
    await session.execute(stmt)
    await session.commit()


async def list_jobs(
    session: AsyncSession,
    status: Optional[str] = None,
    date_from: Optional[datetime] = None,
    limit: int = 20,
    offset: int = 0
) -> FetchJobListResponse:
    """
    List fetch jobs with filtering.
    
    Args:
        session: Database session
        status: Filter by status
        date_from: Filter by creation date
        limit: Maximum number of jobs to return
        offset: Number of jobs to skip
        
    Returns:
        List of jobs with total count
    """
    # Build query conditions
    conditions = []
    params = {}
    
    if status:
        conditions.append("status = :status")
        params["status"] = status
    
    if date_from:
        conditions.append("created_at >= :date_from")
        params["date_from"] = date_from
    
    # Build WHERE clause
    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)
    
    # Get total count
    count_query = f"SELECT COUNT(*) FROM fetch_jobs {where_clause}"
    count_result = await session.execute(text(count_query), params)
    total = count_result.scalar() or 0
    
    # Get jobs
    jobs_query = f"""
    SELECT * FROM fetch_jobs 
    {where_clause}
    ORDER BY created_at DESC 
    LIMIT :limit OFFSET :offset
    """
    params.update({"limit": limit, "offset": offset})
    
    result = await session.execute(text(jobs_query), params)
    rows = result.fetchall()
    
    jobs = []
    for row in rows:
        # Calculate duration
        duration_seconds = None
        if row.started_at:
            end_time = row.completed_at or datetime.utcnow()
            duration_seconds = int((end_time - row.started_at).total_seconds())
        
        # Parse JSON fields
        progress = None
        if row.progress:
            progress_data = row.progress if isinstance(row.progress, dict) else json.loads(row.progress)
            progress = FetchJobProgress(**progress_data)
        
        results = []
        if row.results:
            results_data = row.results if isinstance(row.results, list) else json.loads(row.results)
            # Remove date fields that may cause JSON serialization issues
            for r in results_data:
                r.pop('date_from', None)
                r.pop('date_to', None)
            results = [FetchJobResult(**r) for r in results_data]
        
        errors = row.errors or []
        
        job_response = FetchJobResponse(
            job_id=row.job_id,
            status=row.status,
            symbols=row.symbols,
            date_from=row.date_from,
            date_to=row.date_to,
            interval=row.interval,
            force=row.force_refresh,
            priority=row.priority,
            progress=progress,
            results=results,
            errors=errors,
            created_at=row.created_at,
            started_at=row.started_at,
            completed_at=row.completed_at,
            duration_seconds=duration_seconds,
            created_by=row.created_by
        )
        
        jobs.append(job_response)
    
    return FetchJobListResponse(jobs=jobs, total=total)


async def cancel_job(
    session: AsyncSession,
    job_id: str
) -> bool:
    """
    Cancel a pending or processing job.
    
    Args:
        session: Database session
        job_id: Job ID to cancel
        
    Returns:
        True if job was cancelled, False if not found or already completed
    """
    # Check current status
    stmt = select(FetchJob.status).where(FetchJob.job_id == job_id)
    result = await session.execute(stmt)
    row = result.first()
    
    if not row:
        return False
    
    current_status = row[0]
    if current_status in ['completed', 'failed', 'cancelled']:
        return False
    
    # Update to cancelled
    await update_job_status(session, job_id, 'cancelled', completed_at=datetime.utcnow())
    return True


async def cleanup_old_jobs(
    session: AsyncSession,
    days_old: int = 30,
    keep_failed: bool = True
) -> int:
    """
    Clean up old completed jobs.
    
    Args:
        session: Database session
        days_old: Age threshold in days
        keep_failed: Whether to keep failed jobs
        
    Returns:
        Number of jobs deleted
    """
    cutoff_date = datetime.utcnow() - timedelta(days=days_old)
    
    conditions = ["created_at < :cutoff_date", "status IN ('completed')"]
    params = {"cutoff_date": cutoff_date}
    
    if not keep_failed:
        conditions[1] = "status IN ('completed', 'cancelled')"
    
    delete_query = f"DELETE FROM fetch_jobs WHERE {' AND '.join(conditions)}"
    
    result = await session.execute(text(delete_query), params)
    await session.commit()
    
    return result.rowcount
