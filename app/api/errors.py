from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def raise_http_error(status_code: int, message: str) -> None:
    """Raise an HTTPException with a unified error structure.

    Parameters
    ----------
    status_code: int
        HTTP status code to raise.
    message: str
        Human readable error message.
    """
    raise HTTPException(status_code=status_code, detail=message)


def _http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    payload = {"error": {"code": str(exc.status_code), "message": message}}
    return JSONResponse(payload, status_code=exc.status_code)


def _validation_exception_handler(
    _: Request, exc: RequestValidationError
) -> JSONResponse:
    message = exc.errors()[0]["msg"] if exc.errors() else "Validation error"
    payload = {"error": {"code": "422", "message": message}}
    return JSONResponse(payload, status_code=422)


def init_error_handlers(app: FastAPI) -> None:
    """Register exception handlers on the given FastAPI app."""
    app.add_exception_handler(HTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_exception_handler)

    async def _not_found(request: Request, exc: HTTPException):
        return _http_exception_handler(request, exc)

    app.add_exception_handler(404, _not_found)
