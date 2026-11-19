from functools import wraps

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from flask import jsonify
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, password)
    except (VerificationError, InvalidHashError):
        return False


def current_user_id() -> int:
    return int(get_jwt_identity())


def current_role():
    roles = get_jwt().get("roles", [])
    return roles[0] if roles else None


def roles_required(*required_roles):
    def decorator(fn):
        @wraps(fn)
        @jwt_required()
        def wrapper(*args, **kwargs):
            user_roles = get_jwt().get("roles", [])
            if not any(role in user_roles for role in required_roles):
                return jsonify({
                    "error": "forbidden",
                    "message": "Access denied: insufficient privileges",
                }), 403
            return fn(*args, **kwargs)
        return wrapper
    return decorator