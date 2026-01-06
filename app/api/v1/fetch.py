"""Fetch job API endpoints for data retrieval operations."""

from typing import Optional, List, Dict, Any
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import get_session
from app.api.errors import (
    JobNotFoundError,
    JobLimitExceededError,
    DatabaseError,
    raise_http_error
)
from app.schemas.fetch_jobs import (
    FetchJobRequest, 
    FetchJobResponse,
    FetchJobListResponse
)
from app.services.fetch_jobs import (
    create_fetch_job,
    get_job_status,
    list_jobs,
    cancel_job
)
from app.services.fetch_worker import process_fetch_job


router = APIRouter()


@router.post("/fetch", response_model=Dict[str, Any])
async def create_fetch_job_endpoint(
    request: FetchJobRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session)
):
    """
    Create a new background data fetch job.
    
    Submits a job to fetch historical price data for specified symbols from Yahoo Finance.
    The job runs asynchronously in the background and can be monitored using the job ID.
    
    **Request Body:**
    - **symbols**: List of stock symbols to fetch (1-100 symbols)
    - **date_from**: Start date for historical data (YYYY-MM-DD)
    - **date_to**: End date for historical data (YYYY-MM-DD, max 10 years from date_from)
    - **interval**: Data frequency - '1d', '1wk', '1mo' (optional, default: '1d')
    - **force**: Overwrite existing data (optional, default: false)
    - **priority**: Job priority - 'low', 'normal', 'high' (optional, default: 'normal')
    
    **Response:**
    Returns job information including:
    - **job_id**: Unique identifier for tracking the job
    - **status**: Current job status ('pending', 'processing', 'completed', 'completed_errors', 'failed', 'cancelled')
    - **symbols_count**: Number of symbols to process
    - **date_range**: Date range being fetched
    - **created_at**: Job creation timestamp
    
    **Examples:**
    ```json
    {
        "symbols": ["AAPL", "MSFT", "GOOGL"],
        "date_from": "2024-01-01",
        "date_to": "2024-12-31",
        "interval": "1d",
        "force": false,
        "priority": "normal"
    }
    ```
    
    **Error Responses:**
    - 422: Validation error (invalid dates, too many symbols, etc.)
    - 400: Job limit exceeded or other business logic error
    - 500: Internal server error
    """
    try:
        # Create the job
        job_id = await create_fetch_job(session, request)
        
        # Start background processing
        background_tasks.add_task(
            process_fetch_job,
            job_id=job_id,
            symbols=request.symbols,
            date_from=request.date_from,
            date_to=request.date_to,
            interval=request.interval,
            force=request.force,
            max_concurrency=4  # Increased: Direct/Session Pooler supports concurrent connections
        )
        
        return {
            "job_id": job_id,
            "status": "pending",
            "message": f"Fetch job created for {len(request.symbols)} symbols",
            "symbols_count": len(request.symbols),
            "date_range": {
                "from": request.date_from.isoformat(),
                "to": request.date_to.isoformat()
            }
        }
        
    except SQLAlchemyError as e:
        raise DatabaseError(f"Database error while creating job: {str(e)}")
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "JOB_CREATION_FAILED",
                    "message": f"Failed to create fetch job: {str(e)}"
                }
            }
        )


@router.get("/fetch/{job_id}", response_model=FetchJobResponse)
async def get_fetch_job_status(
    job_id: str,
    session: AsyncSession = Depends(get_session)
):
    """
    Get fetch job status and details.
    
    Returns comprehensive information about a specific fetch job including:
    - Current status and progress
    - Individual symbol results
    - Error information if any
    - Timing information
    
    ## Path Parameters
    
    - **job_id**: The job ID returned when creating the job
    
    ## Response
    
    Returns detailed job information including progress, results, and any errors.
    Status values:
    - 'pending': Job is queued for processing
    - 'processing': Job is currently running
    - 'completed': Job finished successfully
    - 'completed_errors': Job finished but some symbols failed
    - 'failed': Job failed completely
    - 'cancelled': Job was cancelled
    """
    try:
        job = await get_job_status(session, job_id)
        
        if not job:
            raise JobNotFoundError(job_id)
            
        return job
        
    except SQLAlchemyError as e:
        raise DatabaseError(f"Database error while retrieving job: {str(e)}")
    except JobNotFoundError:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "JOB_STATUS_ERROR",
                    "message": f"Failed to retrieve job status: {str(e)}"
                }
            }
        )


@router.get("/fetch", response_model=FetchJobListResponse)
async def list_fetch_jobs(
    status: Optional[str] = None,
    date_from: Optional[datetime] = None,
    limit: int = 20,
    offset: int = 0,
    session: AsyncSession = Depends(get_session)
):
    """
    List fetch jobs with optional filtering.
    
    Returns a list of fetch jobs with optional status and date filtering.
    Results are ordered by creation date (newest first).
    
    ## Query Parameters
    
    - **status**: Filter by job status ('pending', 'processing', 'completed', etc.)
    - **date_from**: Show only jobs created after this timestamp
    - **limit**: Maximum number of jobs to return (1-100, default: 20)
    - **offset**: Number of jobs to skip for pagination (default: 0)
    
    ## Response
    
    Returns a list of jobs with total count for pagination.
    Each job includes basic information and current status.
    """
    try:
        # Validate parameters
        if limit < 1 or limit > 100:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": {
                        "code": "INVALID_LIMIT",
                        "message": f"Limit must be between 1 and 100, got {limit}",
                        "details": {
                            "limit": limit,
                            "min": 1,
                            "max": 100
                        }
                    }
                }
            )
        
        if offset < 0:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": {
                        "code": "INVALID_OFFSET", 
                        "message": f"Offset must be non-negative, got {offset}",
                        "details": {
                            "offset": offset
                        }
                    }
                }
            )
        
        # Validate status if provided
        if status:
            valid_statuses = ['pending', 'processing', 'completed', 'completed_errors', 'failed', 'cancelled']
            if status not in valid_statuses:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": {
                            "code": "INVALID_STATUS",
                            "message": f"Invalid status '{status}'",
                            "details": {
                                "status": status,
                                "valid_statuses": valid_statuses
                            }
                        }
                    }
                )
        
        # Get jobs
        result = await list_jobs(
            session=session,
            status=status,
            date_from=date_from,
            limit=limit,
            offset=offset
        )
        
        return result
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error listing jobs: {e}", exc_info=True)
        
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "JOB_LIST_ERROR",
                    "message": "Failed to retrieve job list",
                    "details": {
                        "timestamp": datetime.utcnow().isoformat()
                    }
                }
            }
        )


@router.post("/fetch/{job_id}/cancel")
async def cancel_fetch_job(
    job_id: str,
    session: AsyncSession = Depends(get_session)
):
    """
    Cancel a pending or processing fetch job.
    
    Attempts to cancel a job that is currently pending or processing.
    Jobs that are already completed, failed, or cancelled cannot be cancelled.
    
    ## Path Parameters
    
    - **job_id**: The job ID to cancel
    
    ## Response
    
    Returns success status and updated job information.
    """
    try:
        success = await cancel_job(session, job_id)
        
        if not success:
            # Check if job exists first
            job = await get_job_status(session, job_id)
            if not job:
                raise JobNotFoundError(job_id)
            else:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": {
                            "code": "JOB_NOT_CANCELLABLE",
                            "message": f"Job '{job_id}' cannot be cancelled (status: {job.status})",
                            "details": {
                                "job_id": job_id,
                                "status": job.status,
                                "reason": "Job is already completed, failed, or cancelled"
                            }
                        }
                    }
                )
        
        return {
            "success": True,
            "message": f"Job {job_id} has been cancelled",
            "job_id": job_id,
            "cancelled_at": datetime.utcnow().isoformat()
        }
        
    except JobNotFoundError:
        raise
    except SQLAlchemyError as e:
        raise DatabaseError(f"Database error while cancelling job: {str(e)}")
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "CANCEL_ERROR",
                    "message": f"Failed to cancel job: {str(e)}"
                }
            }
        )
