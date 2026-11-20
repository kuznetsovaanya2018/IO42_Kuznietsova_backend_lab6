import logging

from opentelemetry import trace

import grpc_client
from app_metrics import insufficient_funds, record_amount, records_created
from auth import can_see_all, current_role, current_user_id, require_roles
from errors import AppError
from models import AccountModel, CategoryModel, RecordModel, db

tracer = trace.get_tracer("expense_service")
log = logging.getLogger("expense_service")


def create_record(user_id, category_id, amount):
    with tracer.start_as_current_span("services.create_record") as span:
        span.set_attribute("record.user_id", user_id)
        span.set_attribute("record.category_id", category_id)
        span.set_attribute("record.amount", amount)
        return _create_record(user_id, category_id, amount)


def _create_record(user_id, category_id, amount):
    require_roles("user", "admin")
    if current_role() == "user" and user_id != current_user_id():
        raise AppError(404, "not_found", "User not found")

    # Синхронний gRPC-виклик до User Service: чи існує користувач
    if not grpc_client.validate_user(user_id).exists:
        raise AppError(404, "not_found", "User not found")

    category = db.session.get(CategoryModel, category_id)
    if category is None or (
        category.user_id is not None and category.user_id != user_id
    ):
        raise AppError(404, "not_found", "Category not found")

    account = db.session.scalars(
        db.select(AccountModel).where(AccountModel.user_id == user_id).with_for_update()
    ).first()
    if account is None:
        raise AppError(404, "not_found", "User has no account")
    if account.balance < amount:
        insufficient_funds.add(1)
        log.warning("Record rejected: insufficient funds for user id=%s", user_id)
        raise AppError(400, "insufficient_funds", "Insufficient account balance")

    account.balance = round(account.balance - amount, 2)
    record = RecordModel(user_id=user_id, category_id=category_id, amount=amount)
    db.session.add(record)
    db.session.commit()

    records_created.add(
        1, {"category_type": "global" if category.user_id is None else "personal"}
    )
    record_amount.record(amount)
    log.info("Record created: id=%s user_id=%s amount=%s", record.id, user_id, amount)
    return record, account.balance


def get_record(record_id):
    require_roles("user", "auditor", "admin")
    record = db.session.get(RecordModel, record_id)
    if record is None or (not can_see_all() and record.user_id != current_user_id()):
        raise AppError(404, "not_found", "Record not found")
    return record


def delete_record(record_id):
    require_roles("user", "admin")
    record = db.session.get(RecordModel, record_id)
    if record is None or (
        current_role() == "user" and record.user_id != current_user_id()
    ):
        raise AppError(404, "not_found", "Record not found")
    db.session.delete(record)
    db.session.commit()
    log.info("Record deleted: id=%s", record_id)


def list_records(user_id, category_id):
    require_roles("user", "auditor", "admin")
    if user_id is None and category_id is None:
        raise AppError(
            400,
            "invalid_request",
            "At least one query parameter ('user_id' or 'category_id') is required for filtration",
        )
    if current_role() == "user":
        if user_id is not None and user_id != current_user_id():
            raise AppError(404, "not_found", "User not found")
        user_id = current_user_id()

    query = db.select(RecordModel).order_by(RecordModel.id)
    if user_id is not None:
        query = query.where(RecordModel.user_id == user_id)
    if category_id is not None:
        query = query.where(RecordModel.category_id == category_id)
    return db.session.scalars(query).all()