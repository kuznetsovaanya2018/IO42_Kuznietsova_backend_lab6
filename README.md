## Спостережуваність (Observability)

Обидва сервіси інструментовано за допомогою OpenTelemetry. Телеметрія надсилається по OTLP (gRPC) в OpenTelemetry Collector, який передає трасування в Jaeger, а метрики віддає для Prometheus. Grafana візуалізує метрики з Prometheus.

| Компонент | Адреса |
|---|---|
| Jaeger UI | http://localhost:16686 |
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3000 (admin / admin) |

### Розподілене трасування

- Flask-запити інструментовано `opentelemetry-instrumentation-flask`, gRPC-виклики `opentelemetry-instrumentation-grpc` (серверний інструментатор у User Service, клієнтський в Expense Service).
- W3C Trace Context (`traceparent`) передається в HTTP-заголовках та gRPC Metadata, тому запит `POST /record` або `POST /rpc` відображається в Jaeger одним деревом spans, що охоплює `expense-service` та `user-service`.

### Метрики (OpenTelemetry → Collector → Prometheus)

| Метрика | Тип | Опис |
|---|---|---|
| `records_created` | Counter | створені витрати (мітка `category_type`) |
| `record_amount` | Histogram | розподіл сум витрат |
| `insufficient_funds` | Counter | відхилені через брак коштів |
| `jsonrpc_requests` | Counter | JSON-RPC виклики (мітки `method`, `status`) |
| `grpc_client_duration` | Histogram | затримка gRPC-викликів до User Service |
| `users_registered` | Counter | зареєстровані користувачі |
| `login_attempts` | Counter | спроби входу (мітка `result`) |
| `grpc_validations` | Counter | gRPC-перевірки в User Service |

### Структуроване логування

Логи пишуться у форматі JSON; фільтр `OTelTraceContextFilter` автоматично додає `trace_id` та `span_id` з контексту OpenTelemetry:

```json
{"timestamp": "...", "level": "INFO", "service": "expense-service", "logger": "expense_service", "message": "Record created: ...", "trace_id": "...", "span_id": "..."}
```

`trace_id` з логу можна вставити в Jaeger (Lookup by Trace ID) і побачити відповідне трасування.

### Grafana Provisioning

Дашборд експортовано у `monitoring/grafana/dashboards/observability-overview.json`. Каталог змонтовано в контейнер Grafana через `docker-compose.yaml`, а `monitoring/grafana/provisioning/dashboards/dashboards.yaml` налаштовує його автоімпорт. Джерело даних Prometheus також розгортається автоматично (`provisioning/datasources/datasources.yaml`).

### Запуск

```
docker compose up -d --build
docker compose exec user_service flask --app app create-admin <name> <password>
```