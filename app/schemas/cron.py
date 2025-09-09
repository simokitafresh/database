"""
Cron job request/response schemas
"""

from datetime import datetime
from typing import Dict, List, Optional
from pydantic import BaseModel, Field, validator


class CronDailyUpdateRequest(BaseModel):
    """Request model for daily update endpoint"""
    dry_run: bool = Field(default=False, description="If True, return plan without executing")
    date_from: Optional[str] = Field(None, description="Start date (YYYY-MM-DD), defaults to CRON_UPDATE_DAYS ago")
    date_to: Optional[str] = Field(None, description="End date (YYYY-MM-DD), defaults to yesterday")
    
    @validator('date_from', 'date_to', pre=True)
    def validate_date_format(cls, v):
        if v is None:
            return v
        try:
            datetime.strptime(v, '%Y-%m-%d')
            return v
        except ValueError:
            raise ValueError('Date must be in YYYY-MM-DD format')


class CronDailyUpdateResponse(BaseModel):
    """Response model for daily update endpoint"""
    status: str = Field(description="Status of the operation")
    message: str = Field(description="Human readable message")
    total_symbols: int = Field(description="Total number of symbols processed")
    batch_count: int = Field(description="Number of batches created")
    job_ids: Optional[List[int]] = Field(None, description="List of created fetch job IDs")
    date_range: Dict[str, str] = Field(description="Date range processed")
    timestamp: str = Field(description="When the operation started")
    estimated_completion_minutes: Optional[float] = Field(None, description="Estimated time to complete all jobs")
    batch_size: Optional[int] = Field(None, description="Size of each batch for dry run")


class CronStatusResponse(BaseModel):
    """Response model for cron status endpoint"""
    status: str = Field(description="Overall cron system status")
    last_run: Optional[str] = Field(None, description="Timestamp of last cron run")
    recent_job_count: int = Field(description="Number of recent jobs")
    job_status_counts: Dict[str, int] = Field(description="Count of jobs by status")
    settings: Dict[str, int] = Field(description="Current cron settings")
