import logging

from marshmallow import ValidationError

import services
from errors import AppError
from models import db
from schemas import RecordFilterSchema, RecordIdSchema, RecordSchema

log = logging.getLogger(__name__)

# Стандартні коди помилок JSON-RPC 2.0
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

# Заборонено: код -32600 узято з діаграми завдання
FORBIDDEN = -32600

# Помилки сервера (діапазон -32000..-32099) за HTTP-статусом
HTTP_TO_RPC_CODE = {
    400: INVALID_PARAMS,
    401: -32001,
    403: FORBIDDEN,
    404: -32004,
    409: -32009,
    503: -32010,
}

record_schema = RecordSchema()
record_id_schema = RecordIdSchema()
record_filter_schema = RecordFilterSchema()


def error_response(request_id, code, message, data=None):
    error = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "error": error, "id": request_id}


def rpc_create_record(params):
    data = record_schema.load(params)
    record, _ = services.create_record(
        data["user_id"], data["category_id"], data["amount"]
    )
    return {"record_id": record.id, "status": "created"}


def rpc_get_record(params):
    data = record_id_schema.load(params)
    return services.get_record(data["record_id"]).to_dict()


def rpc_delete_record(params):
    data = record_id_schema.load(params)
    services.delete_record(data["record_id"])
    return {"status": "deleted"}


def rpc_list_records(params):
    data = record_filter_schema.load(params)
    records = services.list_records(data.get("user_id"), data.get("category_id"))
    return [r.to_dict() for r in records]


METHODS = {
    "create_record": rpc_create_record,
    "get_record": rpc_get_record,
    "delete_record": rpc_delete_record,
    "list_records": rpc_list_records,
}


def process_request(item):
    """Обробляє один об'єкт запиту. Для notification (без id) повертає None."""
    request_id = item.get("id") if isinstance(item, dict) else None
    id_is_valid = request_id is None or (
        isinstance(request_id, (str, int, float)) and not isinstance(request_id, bool)
    )
    if (
        not isinstance(item, dict)
        or item.get("jsonrpc") != "2.0"
        or not isinstance(item.get("method"), str)
        or not id_is_valid
    ):
        return error_response(
            request_id if id_is_valid else None, INVALID_REQUEST, "Invalid Request"
        )

    is_notification = "id" not in item
    handler = METHODS.get(item["method"])
    if handler is None:
        if is_notification:
            return None
        return error_response(request_id, METHOD_NOT_FOUND, "Method not found")

    params = item.get("params", {})
    try:
        if not isinstance(params, dict):
            raise ValidationError(
                {"params": ["Params must be an object with named parameters"]}
            )
        result = handler(params)
    except ValidationError as err:
        db.session.rollback()
        response = error_response(request_id, INVALID_PARAMS, "Invalid params", err.messages)
    except AppError as err:
        db.session.rollback()
        response = error_response(
            request_id,
            HTTP_TO_RPC_CODE.get(err.status, INTERNAL_ERROR),
            err.message,
            {"error": err.error},
        )
    except Exception:
        db.session.rollback()
        log.exception("Unhandled error in JSON-RPC method %s", item["method"])
        response = error_response(request_id, INTERNAL_ERROR, "Internal error")
    else:
        response = {"jsonrpc": "2.0", "result": result, "id": request_id}

    return None if is_notification else response