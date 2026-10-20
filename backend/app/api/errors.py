"""Centralised exception handlers mapping service errors to HTTP responses."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from minio.error import S3Error

from app.auth.dpop import DpopError, DpopNonceRequired
from app.auth.jwt import InvalidTokenError
from app.services.exceptions import (
    ConflictError,
    ForbiddenError,
    InvalidTransitionError,
    NotAvailableError,
    NotFoundError,
    ServiceValueError,
)


def _body(detail: str, **extra: object) -> dict:
    payload: dict = {"detail": detail}
    payload.update(extra)
    return payload


async def _not_found(_: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content=_body(str(exc)))


async def _conflict(_: Request, exc: ConflictError) -> JSONResponse:
    return JSONResponse(status_code=409, content=_body(str(exc)))


async def _forbidden(_: Request, exc: ForbiddenError) -> JSONResponse:
    return JSONResponse(status_code=403, content=_body(str(exc)))


async def _invalid_transition(
    _: Request, exc: InvalidTransitionError,
) -> JSONResponse:
    return JSONResponse(status_code=409, content=_body(str(exc)))


async def _not_available(_: Request, exc: NotAvailableError) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content=_body(str(exc), game_ids=exc.game_ids),
    )


async def _invalid_token(_: Request, exc: InvalidTokenError) -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content=_body("Invalid or expired token"),
        headers={"WWW-Authenticate": "Bearer"},
    )


async def _service_value(_: Request, exc: ServiceValueError) -> JSONResponse:
    return JSONResponse(status_code=422, content=_body(str(exc)))


async def _s3_error(_: Request, exc: S3Error) -> JSONResponse:
    return JSONResponse(status_code=502, content=_body("Object storage error"))


async def _dpop_error(_: Request, exc: DpopError) -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content=_body("Invalid DPoP proof"),
        headers={"WWW-Authenticate": 'DPoP error="invalid_dpop_proof"'},
    )


async def _dpop_nonce_required(
    _: Request, exc: DpopNonceRequired,
) -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content=_body("DPoP nonce required"),
        headers={
            "WWW-Authenticate": 'DPoP error="use_dpop_nonce"',
            "DPoP-Nonce": exc.nonce,
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Attach the domain-to-HTTP mapping to the given app."""
    app.add_exception_handler(NotFoundError, _not_found)
    app.add_exception_handler(ConflictError, _conflict)
    app.add_exception_handler(ForbiddenError, _forbidden)
    app.add_exception_handler(InvalidTransitionError, _invalid_transition)
    app.add_exception_handler(NotAvailableError, _not_available)
    app.add_exception_handler(InvalidTokenError, _invalid_token)
    app.add_exception_handler(ServiceValueError, _service_value)
    app.add_exception_handler(S3Error, _s3_error)
    app.add_exception_handler(DpopError, _dpop_error)
    app.add_exception_handler(DpopNonceRequired, _dpop_nonce_required)