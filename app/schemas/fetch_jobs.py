"""Pydantic schemas for fetch job functionality."""

from pydantic import BaseModel, validator
from datetime import date, datetime
from typing import Optional, List, Dict, Any


class FetchJobRequest(BaseModel):
    """Request schema for creating a new fetch job."""
    symbols: List[str]
    date_from: date
    date_to: date
    interval: str = "1d"
    force: bool = False
    priority: str = "normal"

    @validator('symbols')
    def validate_symbols(cls, v):
        if len(v) > 100:
            raise ValueError('Too many symbols (max: 100)')
        if len(v) == 0:
            raise ValueError('At least one symbol required')
        
        # Validate symbol format
        import re
        symbol_pattern = re.compile(r'^[A-Z0-9.-]{1,20}$')
        for symbol in v:
            if not symbol_pattern.match(symbol.upper()):
                raise ValueError(f'Invalid symbol format: {symbol}. Must be alphanumeric with dots/dashes (max 20 chars)')
        
        # Remove duplicates and convert to uppercase
        return list(dict.fromkeys([s.upper() for s in v]))

    @validator('date_to')
    def validate_date_range(cls, v, values):
        from datetime import date as date_type
        
        if 'date_from' in values and v < values['date_from']:
            raise ValueError('date_to must be after date_from')
        
        # Check if date_to is in the future
        today = date_type.today()
        if v > today:
            raise ValueError('date_to cannot be in the future')
        
        # 10年制限
        if 'date_from' in values:
            days = (v - values['date_from']).days
            if days > 3650:
                raise ValueError('Date range too large (max: 10 years)')
        return v
    
    @validator('date_from')
    def validate_date_from(cls, v):
        from datetime import date as date_type, timedelta
        
        # Check minimum date (20 years back)
        min_date = date_type.today() - timedelta(days=7300)
        if v < min_date:
            raise ValueError('date_from cannot be more than 20 years ago')
        
        return v

    @validator('interval')
    def validate_interval(cls, v):
        valid_intervals = ['1d', '1wk', '1mo', '3mo']
        if v not in valid_intervals:
            raise ValueError(f'Invalid interval. Must be one of: {valid_intervals}')
        return v

    @validator('priority')
    def validate_priority(cls, v):
        valid_priorities = ['low', 'normal', 'high']
        if v not in valid_priorities:
            raise ValueError(f'Invalid priority. Must be one of: {valid_priorities}')
        return v


class FetchJobProgress(BaseModel):
    """Progress information for a fetch job."""
    total_symbols: int
    completed_symbols: int
    current_symbol: Optional[str] = None
    total_rows: int
    fetched_rows: int
    percent: float

    @validator('percent')
    def validate_percent(cls, v):
        return min(100.0, max(0.0, v))


class FetchJobResult(BaseModel):
    """Result information for a single symbol in a fetch job."""
    symbol: str
    status: str  # 'success', 'failed', 'skipped'
    rows_fetched: int = 0
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    error: Optional[str] = None


class FetchJobResponse(BaseModel):
    """Complete fetch job information response."""
    job_id: str
    status: str  # 'pending', 'processing', 'completed', 'failed', 'cancelled'
    symbols: List[str]
    date_from: date
    date_to: date
    interval: str = "1d"
    force: bool = False
    priority: str = "normal"
    progress: Optional[FetchJobProgress] = None
    results: List[FetchJobResult] = []
    errors: List[Dict[str, Any]] = []
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    created_by: Optional[str] = None

    class Config:
        from_attributes = True


class FetchJobListResponse(BaseModel):
    """List of fetch jobs response."""
    jobs: List[FetchJobResponse]
    total: int
