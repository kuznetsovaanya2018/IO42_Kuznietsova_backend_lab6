import logging
from concurrent import futures

import grpc
from grpc_reflection.v1alpha import reflection

import auth_pb2
import auth_pb2_grpc
from app_metrics import grpc_validations
from interceptors import RBACServerInterceptor, TokenError, decode_jwt
from models import UserModel, db

log = logging.getLogger("user_service.grpc")

# Які ролі потрібні для захищених gRPC-методів
METHOD_ROLES = {
    "/auth.AuthService/ValidateUser": ["user", "admin"],
}


class AuthService(auth_pb2_grpc.AuthServiceServicer):
    def __init__(self, app):
        self.app = app

    def ValidateToken(self, request, context):
        try:
            claims = decode_jwt(request.token, self.app.config["JWT_SECRET_KEY"])
            user_id = int(claims["sub"])
        except (TokenError, KeyError, ValueError):
            grpc_validations.add(1, {"method": "ValidateToken", "result": "invalid"})
            log.warning("ValidateToken: invalid or expired token")
            return auth_pb2.ValidateTokenResponse(is_valid=False)

        with self.app.app_context():
            user = db.session.get(UserModel, user_id)
            if user is None:
                grpc_validations.add(1, {"method": "ValidateToken", "result": "invalid"})
                log.warning("ValidateToken: user from token does not exist")
                return auth_pb2.ValidateTokenResponse(is_valid=False)
            grpc_validations.add(1, {"method": "ValidateToken", "result": "valid"})
            log.info("ValidateToken: token is valid for user id=%s", user.id)
            return auth_pb2.ValidateTokenResponse(
                is_valid=True, user_id=str(user.id), roles=[user.role]
            )

    def ValidateUser(self, request, context):
        with self.app.app_context():
            user = db.session.get(UserModel, request.user_id)
            if user is None:
                grpc_validations.add(1, {"method": "ValidateUser", "result": "not_found"})
                log.info("ValidateUser: user id=%s not found", request.user_id)
                return auth_pb2.ValidateUserResponse(exists=False, role="")
            grpc_validations.add(1, {"method": "ValidateUser", "result": "found"})
            log.info("ValidateUser: user id=%s found", user.id)
            return auth_pb2.ValidateUserResponse(exists=True, role=user.role)


def start_grpc_server(app, port):
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=10),
        interceptors=[RBACServerInterceptor(METHOD_ROLES, app.config["JWT_SECRET_KEY"])],
    )
    auth_pb2_grpc.add_AuthServiceServicer_to_server(AuthService(app), server)
    service_names = (
        auth_pb2.DESCRIPTOR.services_by_name["AuthService"].full_name,
        reflection.SERVICE_NAME,
    )
    reflection.enable_server_reflection(service_names, server)
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    return server