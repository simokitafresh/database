# Oldest Data Fallback API Documentation

## Overview

This document describes the "Oldest Data Fallback" behavior implemented in the Price Data API. This feature ensures that API requests remain robust and user-friendly when requested date ranges precede the oldest available data for symbols.

## Fallback Behavior Summary

When a price data request is made with a `from` date that is earlier than the oldest available data for a symbol, the API automatically adjusts the response to return data from the actual oldest available date instead of returning an error or empty result.

### Key Principles

1. **Graceful Degradation**: Instead of failing, the API returns the best available data
2. **Natural Trimming**: The response is naturally trimmed to available date ranges
3. **Transparent Operation**: The fallback happens automatically without requiring client-side logic
4. **Consistent Sorting**: Results are always sorted by (date, symbol) regardless of fallback

## API Endpoint Behavior

### GET /v1/prices

#### Fallback Scenarios

**Scenario 1: Partial Fallback**
- **Request**: `from` date before oldest, `to` date after oldest
- **Behavior**: Returns data from oldest available date to `to` date
- **Example**:
  ```http
  GET /v1/prices?symbols=AAPL&from=2019-01-01&to=2021-12-31
  ```
  If AAPL's oldest data is 2020-01-02, returns data from 2020-01-02 to 2021-12-31

**Scenario 2: Complete Fallback (Empty Result)**
- **Request**: Both `from` and `to` dates before oldest
- **Behavior**: Returns empty array
- **Example**:
  ```http
  GET /v1/prices?symbols=AAPL&from=2018-01-01&to=2019-12-31
  ```
  If AAPL's oldest data is 2020-01-02, returns `[]`

**Scenario 3: Normal Operation**
- **Request**: `from` date at or after oldest available date
- **Behavior**: Standard operation, returns requested range
- **Example**:
  ```http
  GET /v1/prices?symbols=AAPL&from=2020-06-01&to=2021-12-31
  ```
  Returns data for the exact requested range

**Scenario 4: Multi-Symbol Fallback**
- **Request**: Multiple symbols with different oldest dates
- **Behavior**: Each symbol's data starts from its respective oldest date
- **Example**:
  ```http
  GET /v1/prices?symbols=AAPL,MSFT&from=2019-01-01&to=2022-12-31
  ```
  - AAPL data: starts from AAPL's oldest date
  - MSFT data: starts from MSFT's oldest date
  - Combined result sorted by (date, symbol)

#### Response Format

The response format remains unchanged from the standard API specification:

```json
{
  "data": [
    {
      "symbol": "AAPL",
      "date": "2020-01-02",
      "open": 100.00,
      "high": 105.00,
      "low": 99.00,
      "close": 103.00,
      "volume": 1000000,
      "source": "yfinance",
      "last_updated": "2024-01-15T10:30:00Z"
    }
  ],
  "meta": {
    "total_rows": 1,
    "symbols": ["AAPL"],
    "date_range": {
      "from": "2020-01-02",
      "to": "2021-12-31"
    }
  }
}
```

Note: The `meta.date_range.from` reflects the actual data start date, which may differ from the requested `from` parameter due to fallback.

## Symbol Change Handling

The fallback mechanism integrates seamlessly with the symbol change resolution system:

### 1-Hop Symbol Changes

When a symbol has undergone changes (e.g., AAPL_OLD → AAPL), the fallback considers the combined data history:

- **Oldest Date**: Determined from the earliest date across all symbol variations
- **Data Integration**: Historical data from old symbols is included in the response
- **Unified Response**: All data is returned under the current (requested) symbol name

**Example**:
```http
GET /v1/prices?symbols=AAPL&from=2019-01-01&to=2021-12-31
```

If AAPL had a symbol change on 2020-06-01 (AAPL_OLD → AAPL):
- Data from 2020-01-02 to 2020-05-31: sourced from AAPL_OLD
- Data from 2020-06-01 onwards: sourced from AAPL
- All returned with `symbol: "AAPL"`

## Performance Characteristics

### Optimization Features

1. **Batch Oldest Date Lookup**: Single query to fetch oldest dates for multiple symbols
2. **Early Filtering**: Symbols with no data in the requested range are skipped
3. **Parallel Processing**: Database queries for multiple symbols execute in parallel
4. **Connection Pooling**: Limited concurrent connections to prevent database overload

### Performance Expectations

- **Single Symbol**: < 100ms for typical requests
- **Multiple Symbols (5-10)**: < 500ms for typical requests  
- **Large Datasets**: Response time scales linearly with result size
- **Fallback Overhead**: < 10% additional latency compared to normal requests

## Error Handling

### Fallback-Related Errors

The fallback mechanism is designed to minimize errors, but certain conditions still result in error responses:

#### Database Errors
- **Status**: 500 Internal Server Error
- **Cause**: Database connectivity issues, SQL function failures
- **Fallback Impact**: No fallback processing occurs; request fails immediately

#### Symbol Registration Errors
- **Status**: 404 Not Found (if auto-registration disabled) or 500 (if registration fails)
- **Cause**: Requested symbol not in database and cannot be registered
- **Fallback Impact**: Unknown symbols are skipped; partial results may be returned for known symbols

#### Resource Limit Errors
- **Status**: 413 Payload Too Large
- **Cause**: Result set exceeds `API_MAX_ROWS` configuration
- **Fallback Impact**: May occur more frequently with fallback due to expanded date ranges

### Error Response Format

```json
{
  "error": {
    "code": "DATABASE_ERROR",
    "message": "Failed to fetch price data",
    "details": {
      "symbols": ["AAPL", "MSFT"],
      "requested_range": {
        "from": "2019-01-01",
        "to": "2021-12-31"
      },
      "fallback_attempted": true
    }
  }
}
```

## Configuration Parameters

### Application Settings

These settings in `app/core/config.py` affect fallback behavior:

```python
# Symbol and result limits
API_MAX_SYMBOLS = 50          # Maximum symbols per request
API_MAX_ROWS = 50000          # Maximum result rows

# Auto-registration behavior  
ENABLE_AUTO_REGISTRATION = True  # Enable automatic symbol registration

# Performance tuning
YF_REQ_CONCURRENCY = 5        # Concurrent data fetching operations
YF_REFETCH_DAYS = 5           # Recent data refresh window
```

### Database Configuration

- **Connection Pool Size**: Affects parallel query performance
- **Query Timeout**: Determines maximum wait time for fallback queries
- **Advisory Locks**: Used in coverage checking to prevent race conditions

## Monitoring and Observability

### Logging

Fallback operations generate structured logs for monitoring:

```json
{
  "event_type": "date_adjusted",
  "timestamp": "2024-01-15T10:30:00Z",
  "symbols": ["AAPL"],
  "date_from": "2019-01-01",
  "adjusted_from": "2020-01-02", 
  "adjustment_days": 367,
  "duration_ms": 245.3,
  "result_count": 456
}
```

### Metrics

Key metrics for monitoring fallback performance:

- **Fallback Rate**: Percentage of requests requiring date adjustment
- **Average Adjustment**: Mean number of days adjusted forward
- **Performance Impact**: Latency increase due to fallback processing
- **Error Rate**: Proportion of fallback requests resulting in errors

### Health Checks

The `/health` endpoint includes fallback system status:

```json
{
  "status": "healthy",
  "components": {
    "database": "healthy",
    "fallback_system": "healthy"
  },
  "metrics": {
    "fallback_rate_24h": 15.3,
    "avg_adjustment_days": 45.2,
    "error_rate_24h": 0.1
  }
}
```

## Client Integration Guidelines

### Handling Fallback Responses

Clients should be prepared to handle responses where the actual date range differs from the requested range:

#### 1. Check Response Metadata
```javascript
const response = await fetch('/v1/prices?symbols=AAPL&from=2019-01-01&to=2021-12-31');
const data = await response.json();

// Check if fallback occurred
const requestedFrom = '2019-01-01';
const actualFrom = data.meta.date_range.from;

if (actualFrom !== requestedFrom) {
  console.log(`Data starts from ${actualFrom} instead of requested ${requestedFrom}`);
}
```

#### 2. Handle Empty Results Gracefully
```javascript
if (data.data.length === 0) {
  // Requested date range is entirely before oldest available data
  console.log('No data available for the requested date range');
}
```

#### 3. Multi-Symbol Considerations
```javascript
// When requesting multiple symbols, each may have different start dates
const symbolStartDates = {};
data.data.forEach(row => {
  if (!symbolStartDates[row.symbol]) {
    symbolStartDates[row.symbol] = row.date;
  }
});

console.log('Actual start dates by symbol:', symbolStartDates);
```

### Best Practices

1. **Request Reasonable Ranges**: Avoid requesting data from excessively early dates
2. **Handle Partial Data**: Be prepared for responses that don't match exact requested ranges
3. **Cache Oldest Dates**: If making frequent requests, cache symbol oldest dates to predict fallback
4. **Monitor Response Metadata**: Use `meta` fields to understand actual vs. requested ranges
5. **Implement Retry Logic**: Handle transient database errors with exponential backoff

## Future Enhancements

### Planned Features

1. **Response Metadata Enhancement**:
   - Add `date_adjustments` array showing per-symbol adjustments
   - Include `fallback_applied` boolean flag
   
2. **Query Parameter Extensions**:
   - `strict_dates=true`: Return error instead of fallback
   - `include_adjustments=true`: Include adjustment details in response

3. **Performance Optimizations**:
   - Redis caching for frequently accessed oldest dates
   - Predictive prefetching based on request patterns
   - Advanced query optimization for large symbol sets

### Backward Compatibility

All future enhancements will maintain backward compatibility with existing client implementations. New features will be opt-in via query parameters or configuration settings.
