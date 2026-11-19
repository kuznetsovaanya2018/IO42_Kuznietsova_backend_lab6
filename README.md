# Лабораторна робота №5: Мікросервісна декомпозиція

Застосунок обліку витрат розділено на два автономні мікросервіси з власними базами PostgreSQL. Сервіси взаємодіють по gRPC (HTTP/2), а зовнішнє публічне API витрат доступне також за протоколом JSON-RPC 2.0.

## Архітектура

| Сервіс | Відповідальність | Порти |
|---|---|---|
| User Service | користувачі, `/register`, `/login`, видача та перевірка JWT, gRPC-сервер | REST 5001, gRPC 50051 |
| Expense Service | категорії, рахунки, записи витрат, JSON-RPC `POST /rpc`, gRPC-клієнт | REST 5000 |

Кожен сервіс має окрему базу (`user_db`, `expense_db`) з власними обліковими даними; доступ до чужої бази відсутній.

### Міжсервісна взаємодія (gRPC)

Контракт описано в `proto/auth.proto` (сервіс `AuthService`):

- `ValidateToken(token)` — перевіряє JWT і повертає `is_valid`, `user_id`, `roles`. Expense Service викликає його для автентифікації кожного запиту.
- `ValidateUser(user_id)` — повертає `exists` і `role`. Токен передається в gRPC Metadata (`authorization: Bearer <token>`). Викликається при створенні записів і рахунків.

Авторизація на рівні gRPC:

- серверний перехоплювач `RBACServerInterceptor` (User Service) перевіряє токен і роль у Metadata до виклику методу (`UNAUTHENTICATED` / `PERMISSION_DENIED`);
- клієнтський перехоплювач `AuthMetadataInterceptor` (Expense Service) додає токен поточного запиту до кожного gRPC-виклику.

Для генерації stubs використано: `python -m grpc_tools.protoc -I proto --python_out=<service> --grpc_python_out=<service> proto/auth.proto`.

### JSON-RPC 2.0

`POST /rpc` у Expense Service (заголовок `Authorization: Bearer <token>`) підтримує поодинокі та пакетні запити, notification (запити без `id`), а також стандартні помилки (`-32700`, `-32600`, `-32601`, `-32602`, `-32603`). Методи: `create_record`, `get_record`, `delete_record`, `list_records`. Код `-32600` також використовується для помилки «недостатньо прав» (згідно з діаграмою завдання).

Приклад пакетного запиту:

```json
[
  {"jsonrpc": "2.0", "method": "create_record", "params": {"user_id": 2, "category_id": 1, "amount": 100.0}, "id": 1},
  {"jsonrpc": "2.0", "method": "create_record", "params": {"user_id": 2, "category_id": 1, "amount": 45.5}, "id": 2}
]
```

## Запуск

```
docker compose up -d --build
docker compose exec user_service flask --app app create-admin <name> <password>
```

Міграції застосовуються автоматично під час старту кожного сервісу. Секрет JWT задається змінною `JWT_SECRET_KEY`.

## Обмеження

Між сервісами відсутні зовнішні ключі: видалення користувача в User Service не видаляє його рахунки та записи в Expense Service (узгодженість між базами не забезпечується автоматично).

## Тестування

Колекція Bruno в папці `bruno_collection/` містить запити для REST обох сервісів, JSON-RPC (single, batch, помилки) та gRPC. Оберіть середовище `local` (змінні `baseUrl`, `userUrl`, `grpcUrl`).