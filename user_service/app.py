import os
from datetime import datetime, timedelta, timezone

import click
from flask import Flask, jsonify, request
from flask_jwt_extended import JWTManager, create_access_token
from flask_migrate import Migrate
from marshmallow import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from auth import (
    current_role, current_user_id, hash_password, roles_required, verify_password,
)
from grpc_server import start_grpc_server
from models import db, UserModel
from schemas import LoginSchema, RegisterSchema, RoleSchema


def database_url():
    url = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://user_svc:user_svc@localhost:5433/user_db",
    )
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = database_url()
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["JWT_SECRET_KEY"] = os.getenv(
    "JWT_SECRET_KEY", "dev-secret-key-change-me-0123456789abcdef"
)
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=1)

db.init_app(app)
migrate = Migrate(app, db)
jwt = JWTManager(app)

register_schema = RegisterSchema()
login_schema = LoginSchema()
role_schema = RoleSchema()


@jwt.unauthorized_loader
def missing_token(reason):
    return jsonify({"error": "unauthorized", "message": reason}), 401


@jwt.invalid_token_loader
def invalid_token(reason):
    return jsonify({"error": "unauthorized", "message": reason}), 401


@jwt.expired_token_loader
def expired_token(jwt_header, jwt_payload):
    return jsonify({"error": "unauthorized", "message": "Token has expired"}), 401


def validation_error(err):
    return jsonify({"error": "invalid_request", "errors": err.messages}), 400


def not_found(message):
    return jsonify({"error": "not_found", "message": message}), 404


def can_see_all():
    return current_role() in ("auditor", "admin")


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


@app.route("/register", methods=["POST"])
def register():
    try:
        data = register_schema.load(request.get_json(silent=True))
    except ValidationError as err:
        return validation_error(err)

    name = data["name"].strip()
    exists = db.session.scalars(
        db.select(UserModel).where(UserModel.name == name)
    ).first()
    if exists is not None:
        return jsonify({"error": "conflict", "message": "User already exists"}), 409

    user = UserModel(name=name, password_hash=hash_password(data["password"]), role="user")
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "conflict", "message": "User already exists"}), 409
    return jsonify(user.to_dict()), 201


@app.route("/login", methods=["POST"])
def login():
    try:
        data = login_schema.load(request.get_json(silent=True))
    except ValidationError as err:
        return validation_error(err)

    user = db.session.scalars(
        db.select(UserModel).where(UserModel.name == data["name"].strip())
    ).first()
    if user is None or not verify_password(data["password"], user.password_hash):
        return jsonify({"error": "unauthorized", "message": "Invalid credentials"}), 401

    token = create_access_token(
        identity=str(user.id), additional_claims={"roles": [user.role]}
    )
    return jsonify({"access_token": token, "token_type": "Bearer"}), 200


@app.route("/users", methods=["GET"])
@roles_required("auditor", "admin")
def get_users():
    users = db.session.scalars(db.select(UserModel).order_by(UserModel.id)).all()
    return jsonify([u.to_dict() for u in users]), 200


@app.route("/user/<int:user_id>", methods=["GET"])
@roles_required("user", "auditor", "admin")
def get_user(user_id):
    if not can_see_all() and user_id != current_user_id():
        return not_found("User not found")
    user = db.session.get(UserModel, user_id)
    if user is None:
        return not_found("User not found")
    return jsonify(user.to_dict()), 200


@app.route("/user/<int:user_id>", methods=["DELETE"])
@roles_required("admin")
def delete_user(user_id):
    user = db.session.get(UserModel, user_id)
    if user is None:
        return not_found("User not found")
    db.session.delete(user)
    db.session.commit()
    return "", 204


@app.route("/user/<int:user_id>/role", methods=["PATCH"])
@roles_required("admin")
def change_role(user_id):
    try:
        data = role_schema.load(request.get_json(silent=True))
    except ValidationError as err:
        return validation_error(err)
    user = db.session.get(UserModel, user_id)
    if user is None:
        return not_found("User not found")
    user.role = data["role"]
    db.session.commit()
    return jsonify(user.to_dict()), 200


@app.cli.command("create-admin")
@click.argument("name")
@click.argument("password")
def create_admin(name, password):
    """Створює адміністратора (або підвищує існуючого користувача до admin)."""
    if len(password) < 8:
        raise click.ClickException("Password must be at least 8 characters long")
    user = db.session.scalars(db.select(UserModel).where(UserModel.name == name)).first()
    if user is None:
        user = UserModel(name=name, password_hash=hash_password(password), role="admin")
        db.session.add(user)
        click.echo(f"Admin '{name}' created")
    else:
        user.role = "admin"
        click.echo(f"User '{name}' promoted to admin")
    db.session.commit()


if __name__ == "__main__":
    grpc_srv = start_grpc_server(app, int(os.getenv("GRPC_PORT", "50051")))
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5001")))