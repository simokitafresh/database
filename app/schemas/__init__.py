"""Data schemas for API request/response models."""

# Import base schemas
from .common import BaseResponse, PaginatedResponse, DateRange

# Import specific schemas (avoiding circular imports)
try:
    from .prices import PriceCreate, PriceResponse
except ImportError:
    pass

try:
    from .symbols import SymbolCreate, SymbolResponse
except ImportError:
    pass

try:
    from .coverage import CoverageResponse
except ImportError:
    pass

try:
    from .fetch_jobs import FetchJobCreate, FetchJobResponse
except ImportError:
    pass

try:
    from .events import (
        EventTypeEnum,
        EventStatusEnum,
        EventSeverityEnum,
        CorporateEventBase,
        CorporateEventCreate,
        CorporateEventUpdate,
        CorporateEventResponse,
        CorporateEventListResponse,
    )
except ImportError:
    pass

__all__ = [
    # Common schemas
    "BaseResponse",
    "PaginatedResponse",
    "DateRange",
    # Price schemas
    "PriceCreate", 
    "PriceResponse",
    # Symbol schemas
    "SymbolCreate",
    "SymbolResponse", 
    # Coverage schemas
    "CoverageResponse",
    # Fetch job schemas
    "FetchJobCreate",
    "FetchJobResponse",
    # Event schemas
    "EventTypeEnum",
    "EventStatusEnum",
    "EventSeverityEnum",
    "CorporateEventBase",
    "CorporateEventCreate",
    "CorporateEventUpdate",
    "CorporateEventResponse",
    "CorporateEventListResponse",
]
