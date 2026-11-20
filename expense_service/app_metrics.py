from opentelemetry import metrics

meter = metrics.get_meter("expense_service")

records_created = meter.create_counter(
    "records_created", unit="1", description="Created expense records"
)
insufficient_funds = meter.create_counter(
    "insufficient_funds", unit="1", description="Records rejected: insufficient balance"
)
record_amount = meter.create_histogram(
    "record_amount", unit="1", description="Amounts of created expense records"
)
jsonrpc_requests = meter.create_counter(
    "jsonrpc_requests", unit="1", description="JSON-RPC calls by method and status"
)
grpc_client_duration = meter.create_histogram(
    "grpc_client_duration", unit="ms", description="Latency of gRPC calls to User Service"
)