"""Bearer token authentication + Dify-spec error codes.

We raise :class:`DifyError` instead of :class:`fastapi.HTTPException` because the
Dify External KB spec requires error bodies at the JSON top level (e.g.
``{"error_code": 1001, ...}``), whereas FastAPI's ``HTTPException`` serialises
its ``detail`` under a ``{"detail": ...}`` wrapper. :func:`main.create_app`
registers an exception handler for :class:`DifyError` that emits the body at
top level.
"""

import os
from typing import Optional


class DifyError(Exception):
    """Error carrying a top-level JSON body + HTTP status for Dify spec errors."""

    def __init__(self, body: dict, status_code: int):
        self.body = body
        self.status_code = status_code
        super().__init__(str(body))


def dify_error(code, http_status: int, message: Optional[str] = None) -> DifyError:
    body: dict = {"error_code": code}
    if message is not None:
        body["error_msg"] = message
    return DifyError(body, http_status)


def _get_allowed_keys() -> set[str]:
    raw = os.environ.get("KB_ADAPTER_ALLOWED_KEYS", "")
    return {token.strip() for token in raw.split(",") if token.strip()}


def verify_bearer(auth_header: Optional[str]) -> None:
    if not auth_header or not auth_header.startswith("Bearer "):
        raise dify_error(1001, 403, "Invalid Authorization header format")
    token = auth_header[len("Bearer "):]
    if token not in _get_allowed_keys():
        raise dify_error(1002, 403, "Authorization failed")
