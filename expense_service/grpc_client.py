import collections
import os

import grpc
from flask import g, has_request_context

import auth_pb2
import auth_pb2_grpc
from errors import AppError


class _CallDetails(
    collections.namedtuple(
        "_CallDetails",
        ("method", "timeout", "metadata", "credentials", "wait_for_ready", "compression"),
    ),
    grpc.ClientCallDetails,
):
    pass


class AuthMetadataInterceptor(grpc.UnaryUnaryClientInterceptor):
    """Додає заголовок authorization із токена поточного запиту в gRPC Metadata."""

    def intercept_unary_unary(self, continuation, client_call_details, request):
        metadata = list(client_call_details.metadata or [])
        token = getattr(g, "token", None) if has_request_context() else None
        if token:
            metadata.append(("authorization", f"Bearer {token}"))
        details = _CallDetails(
            client_call_details.method,
            client_call_details.timeout,
            metadata,
            client_call_details.credentials,
            client_call_details.wait_for_ready,
            client_call_details.compression,
        )
        return continuation(details, request)


_stub = None


def get_stub():
    global _stub
    if _stub is None:
        address = os.getenv("USER_SERVICE_GRPC_ADDR", "localhost:50051")
        channel = grpc.insecure_channel(address)
        channel = grpc.intercept_channel(channel, AuthMetadataInterceptor())
        _stub = auth_pb2_grpc.AuthServiceStub(channel)
    return _stub


def _call(method, request):
    try:
        return method(request, timeout=5)
    except grpc.RpcError as err:
        code = err.code()
        if code == grpc.StatusCode.UNAUTHENTICATED:
            raise AppError(401, "unauthorized", err.details())
        if code == grpc.StatusCode.PERMISSION_DENIED:
            raise AppError(403, "forbidden", err.details())
        raise AppError(503, "service_unavailable", "User Service is unavailable")


def validate_token(token):
    return _call(get_stub().ValidateToken, auth_pb2.ValidateTokenRequest(token=token))


def validate_user(user_id):
    return _call(get_stub().ValidateUser, auth_pb2.ValidateUserRequest(user_id=user_id))