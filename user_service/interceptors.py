import grpc
import jwt


class TokenError(Exception):
    pass


def decode_jwt(token, secret):
    token = (token or "").strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    if not token:
        raise TokenError("Missing token")
    try:
        return jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise TokenError("Token has expired")
    except jwt.InvalidTokenError:
        raise TokenError("Invalid token")


def _deny(code, message):
    def handler(request, context):
        context.abort(code, message)
    return grpc.unary_unary_rpc_method_handler(handler)


class RBACServerInterceptor(grpc.ServerInterceptor):
    """Перевіряє токен і роль із gRPC Metadata до виклику методу."""

    def __init__(self, method_roles_map, secret):
        self.method_roles_map = method_roles_map
        self.secret = secret

    def intercept_service(self, continuation, handler_call_details):
        required_roles = self.method_roles_map.get(handler_call_details.method)
        if not required_roles:
            return continuation(handler_call_details)

        metadata = dict(handler_call_details.invocation_metadata)
        try:
            claims = decode_jwt(metadata.get("authorization"), self.secret)
        except TokenError as err:
            return _deny(grpc.StatusCode.UNAUTHENTICATED, str(err))

        roles = claims.get("roles", [])
        if not any(role in roles for role in required_roles):
            return _deny(
                grpc.StatusCode.PERMISSION_DENIED,
                "Access denied by gRPC RBAC Interceptor",
            )
        return continuation(handler_call_details)