import json
import logging
import os
import sys
from datetime import datetime, timezone

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.grpc import GrpcInstrumentorServer
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

_service_name = "unknown"


class OTelTraceContextFilter(logging.Filter):
    """Підставляє trace_id і span_id з поточного контексту OpenTelemetry."""

    def filter(self, record):
        span = trace.get_current_span()
        if span and span.get_span_context().is_valid:
            ctx = span.get_span_context()
            record.trace_id = f"{ctx.trace_id:032x}"
            record.span_id = f"{ctx.span_id:016x}"
        else:
            record.trace_id = "0"
            record.span_id = "0"
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "service": _service_name,
            "logger": record.name,
            "message": record.getMessage(),
            "trace_id": getattr(record, "trace_id", "0"),
            "span_id": getattr(record, "span_id", "0"),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging():
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(OTelTraceContextFilter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    logging.getLogger("opentelemetry").setLevel(logging.WARNING)


def init_telemetry(service_name: str):
    global _service_name
    _service_name = service_name
    configure_logging()

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")
    resource = Resource.create({"service.name": service_name})

    # Tracing
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True))
    )
    trace.set_tracer_provider(tracer_provider)

    # Metrics
    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=endpoint, insecure=True),
        export_interval_millis=5000,
    )
    metrics.set_meter_provider(
        MeterProvider(resource=resource, metric_readers=[metric_reader])
    )

    # gRPC-сервер: витягує W3C Trace Context із gRPC Metadata
    GrpcInstrumentorServer().instrument()