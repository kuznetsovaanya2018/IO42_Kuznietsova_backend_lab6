from opentelemetry import metrics

meter = metrics.get_meter("user_service")

users_registered = meter.create_counter(
    "users_registered", unit="1", description="Number of registered users"
)
login_attempts = meter.create_counter(
    "login_attempts", unit="1", description="Login attempts by result"
)
grpc_validations = meter.create_counter(
    "grpc_validations", unit="1", description="gRPC validation calls handled by User Service"
)