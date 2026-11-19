from functools import wraps

from flask import g, request

import grpc_client
from errors import AppError


def authenticate():
    """Перевіряє Bearer-токен через gRPC виклик до User Service."""
    header = request.headers.get("Authorization", "")
    token = header[7:].strip() if header.lower().startswith("bearer ") else ""
    if not token:
        raise AppError(401, "unauthorized", "Missing or malformed Authorization header")
    g.token = token
    result = grpc_client.validate_token(token)
    if not result.is_valid:
        raise AppError(401, "unauthorized", "Invalid or expired token")
    g.user_id = int(result.user_id)
    g.roles = list(result.roles)


def require_roles(*required_roles):
    if not any(role in g.roles for role in required_roles):
        raise AppError(403, "forbidden", "Access denied: insufficient privileges")


def roles_required(*required_roles):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            authenticate()
            require_roles(*required_roles)
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def current_user_id():
    return g.user_id


def current_role():
    return g.roles[0] if g.roles else None


def can_see_all():
    return current_role() in ("auditor", "admin")