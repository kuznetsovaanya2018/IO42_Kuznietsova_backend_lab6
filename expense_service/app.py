import os
from datetime import datetime, timezone

from flask import Flask, jsonify, request
from flask_migrate import Migrate
from marshmallow import ValidationError
from sqlalchemy import or_, text

import grpc_client
import services
from auth import current_role, current_user_id, can_see_all, roles_required
from errors import AppError
from models import AccountModel, CategoryModel, db
from schemas import AccountSchema, CategorySchema, RecordSchema, TopUpSchema

from auth import authenticate
from rpc import INVALID_REQUEST, PARSE_ERROR, error_response, process_request

def database_url():
    url = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://expense_svc:expense_svc@localhost:5434/expense_db",
    )
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = database_url()
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)
migrate = Migrate(app, db)

category_schema = CategorySchema()
record_schema = RecordSchema()
account_schema = AccountSchema()
topup_schema = TopUpSchema()


@app.errorhandler(AppError)
def handle_app_error(err):
    db.session.rollback()
    return jsonify({"error": err.error, "message": err.message}), err.status


def validation_error(err):
    return jsonify({"error": "invalid_request", "errors": err.messages}), 400


def not_found(message):
    return jsonify({"error": "not_found", "message": message}), 404


# ---------- Системний стан ----------

@app.route("/healthz/live", methods=["GET"])
def healthz_live():
    return jsonify({
        "status": "alive",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }), 200


@app.route("/healthz/ready", methods=["GET"])
def healthz_ready():
    try:
        db.session.execute(text("SELECT 1"))
    except Exception:
        return jsonify({"status": "not_ready"}), 503
    return jsonify({"status": "ready"}), 200


# ---------- Categories ----------

@app.route("/category", methods=["GET"])
@roles_required("user", "auditor", "admin")
def get_categories():
    query = db.select(CategoryModel).order_by(CategoryModel.id)
    if current_role() == "user":
        query = query.where(
            or_(CategoryModel.user_id.is_(None), CategoryModel.user_id == current_user_id())
        )
    categories = db.session.scalars(query).all()
    return jsonify([c.to_dict() for c in categories]), 200


@app.route("/category", methods=["POST"])
@roles_required("user", "admin")
def create_category():
    try:
        data = category_schema.load(request.get_json(silent=True))
    except ValidationError as err:
        return validation_error(err)
    category = CategoryModel(name=data["name"].strip(), user_id=current_user_id())
    db.session.add(category)
    db.session.commit()
    return jsonify(category.to_dict()), 201


@app.route("/category/global", methods=["POST"])
@roles_required("admin")
def create_global_category():
    try:
        data = category_schema.load(request.get_json(silent=True))
    except ValidationError as err:
        return validation_error(err)
    category = CategoryModel(name=data["name"].strip(), user_id=None)
    db.session.add(category)
    db.session.commit()
    return jsonify(category.to_dict()), 201


@app.route("/category/<int:category_id>", methods=["DELETE"])
@roles_required("admin")
def delete_category(category_id):
    category = db.session.get(CategoryModel, category_id)
    if category is None:
        return not_found("Category not found")
    db.session.delete(category)
    db.session.commit()
    return "", 204


# ---------- Accounts ----------

@app.route("/account", methods=["POST"])
@roles_required("user", "admin")
def create_account():
    try:
        data = account_schema.load(request.get_json(silent=True))
    except ValidationError as err:
        return validation_error(err)

    if current_role() == "user" and data["user_id"] != current_user_id():
        return not_found("User not found")
    if not grpc_client.validate_user(data["user_id"]).exists:
        return not_found("User not found")

    existing = db.session.scalars(
        db.select(AccountModel).where(AccountModel.user_id == data["user_id"])
    ).first()
    if existing is not None:
        return jsonify({"error": "conflict", "message": "User already has an account"}), 409

    account = AccountModel(user_id=data["user_id"], balance=0.0)
    db.session.add(account)
    db.session.commit()
    return jsonify(account.to_dict()), 201


@app.route("/account/<int:account_id>", methods=["GET"])
@roles_required("user", "auditor", "admin")
def get_account(account_id):
    account = db.session.get(AccountModel, account_id)
    if account is None or (not can_see_all() and account.user_id != current_user_id()):
        return not_found("Account not found")
    return jsonify(account.to_dict()), 200


@app.route("/account/<int:account_id>/topup", methods=["POST"])
@roles_required("user", "admin")
def top_up_account(account_id):
    try:
        data = topup_schema.load(request.get_json(silent=True))
    except ValidationError as err:
        return validation_error(err)

    account = db.session.scalars(
        db.select(AccountModel).where(AccountModel.id == account_id).with_for_update()
    ).first()
    if account is None:
        return not_found("Account not found")
    if current_role() == "user" and account.user_id != current_user_id():
        return not_found("Account not found")

    account.balance = round(account.balance + data["amount"], 2)
    db.session.commit()
    return jsonify(account.to_dict()), 200


# ---------- Records ----------

@app.route("/record", methods=["POST"])
@roles_required("user", "admin")
def create_record():
    try:
        data = record_schema.load(request.get_json(silent=True))
    except ValidationError as err:
        return validation_error(err)
    record, remaining = services.create_record(
        data["user_id"], data["category_id"], data["amount"]
    )
    result = record.to_dict()
    result["remaining_balance"] = remaining
    return jsonify(result), 201


@app.route("/record/<int:record_id>", methods=["GET"])
@roles_required("user", "auditor", "admin")
def get_record(record_id):
    return jsonify(services.get_record(record_id).to_dict()), 200


@app.route("/record/<int:record_id>", methods=["DELETE"])
@roles_required("user", "admin")
def delete_record(record_id):
    services.delete_record(record_id)
    return "", 204


@app.route("/record", methods=["GET"])
@roles_required("user", "auditor", "admin")
def get_records():
    try:
        user_id = int(request.args["user_id"]) if "user_id" in request.args else None
        category_id = (
            int(request.args["category_id"]) if "category_id" in request.args else None
        )
    except ValueError:
        raise AppError(
            400, "invalid_request",
            "Query parameters 'user_id' and 'category_id' must be integers",
        )
    records = services.list_records(user_id, category_id)
    return jsonify([r.to_dict() for r in records]), 200

# ---------- JSON-RPC 2.0 ----------

@app.route("/rpc", methods=["POST"])
def rpc_endpoint():
    authenticate()  # без дійсного токена: HTTP 401

    payload = request.get_json(force=True, silent=True)
    if payload is None:
        return jsonify(error_response(None, PARSE_ERROR, "Parse error")), 200

    if isinstance(payload, list):  # Batch
        if not payload:
            return jsonify(error_response(None, INVALID_REQUEST, "Invalid Request")), 200
        responses = [
            response
            for response in (process_request(item) for item in payload)
            if response is not None
        ]
        if not responses:  # усі елементи були notification
            return "", 204
        return jsonify(responses), 200

    response = process_request(payload)  # Single
    if response is None:
        return "", 204
    return jsonify(response), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))