import re
from dataclasses import dataclass

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from src.models.user import UserRole
from src.services.auth import InvalidAccessTokenError, auth_service


@dataclass(frozen=True)
class RoutePolicy:
    method: str
    pattern: re.Pattern[str]
    roles: frozenset[UserRole]


PATIENT = frozenset({UserRole.PATIENT})
NURSE = frozenset({UserRole.NURSE})
AUTHENTICATED = frozenset({UserRole.PATIENT, UserRole.NURSE})

ROUTE_POLICIES = (
    RoutePolicy("POST", re.compile(r"^/api/v1/chat/?$"), PATIENT),
    RoutePolicy("GET", re.compile(r"^/api/v1/me/?$"), AUTHENTICATED),
    RoutePolicy("GET", re.compile(r"^/api/v1/tools/?$"), NURSE),
    RoutePolicy("POST", re.compile(r"^/api/v1/tools/[^/]+/call/?$"), NURSE),
    RoutePolicy("GET", re.compile(r"^/api/v1/nurse/queue/?$"), NURSE),
    RoutePolicy("POST", re.compile(r"^/api/v1/cases/?$"), PATIENT),
    RoutePolicy("POST", re.compile(r"^/api/v1/cases/[^/]+/responses/?$"), PATIENT),
    RoutePolicy("GET", re.compile(r"^/api/v1/cases/[^/]+/result/?$"), PATIENT),
    RoutePolicy("GET", re.compile(r"^/api/v1/cases/[^/]+/?$"), AUTHENTICATED),
    RoutePolicy("POST", re.compile(r"^/api/v1/cases/[^/]+/review/?$"), NURSE),
    RoutePolicy("POST", re.compile(r"^/api/v1/cases/[^/]+/approve/?$"), NURSE),
    RoutePolicy("POST", re.compile(r"^/api/v1/cases/[^/]+/override/?$"), NURSE),
    RoutePolicy("POST", re.compile(r"^/api/v1/cases/[^/]+/escalate/?$"), NURSE),
    RoutePolicy("GET", re.compile(r"^/api/v1/queue/?$"), NURSE),
)


class RoleAuthorizationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method == "OPTIONS":
            return await call_next(request)

        policy = next(
            (
                item
                for item in ROUTE_POLICIES
                if item.method == request.method and item.pattern.fullmatch(request.url.path)
            ),
            None,
        )
        if policy is None:
            return await call_next(request)

        authorization = request.headers.get("Authorization", "")
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            return JSONResponse(
                status_code=401,
                content={"detail": "Thiếu Bearer token"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        try:
            claims = auth_service.decode_access_token(token)
        except InvalidAccessTokenError as error:
            return JSONResponse(
                status_code=401,
                content={"detail": str(error)},
                headers={"WWW-Authenticate": "Bearer"},
            )

        if claims.role not in policy.roles:
            return JSONResponse(
                status_code=403,
                content={"detail": f"Role '{claims.role.value}' không có quyền truy cập"},
            )

        request.state.auth = claims
        return await call_next(request)
