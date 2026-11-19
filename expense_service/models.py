from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class CategoryModel(db.Model):
    __tablename__ = "categories"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    user_id = db.Column(db.Integer, nullable=True)  # NULL = глобальна категорія
    records = db.relationship(
        "RecordModel", backref="category", cascade="all, delete-orphan", passive_deletes=True
    )

    def to_dict(self):
        return {"id": self.id, "name": self.name, "user_id": self.user_id}


class AccountModel(db.Model):
    __tablename__ = "accounts"
    __table_args__ = (db.UniqueConstraint("user_id", name="uq_accounts_user_id"),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    balance = db.Column(db.Float, default=0.0, nullable=False)

    def to_dict(self):
        return {"id": self.id, "user_id": self.user_id, "balance": self.balance}


class RecordModel(db.Model):
    __tablename__ = "records"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    category_id = db.Column(
        db.Integer, db.ForeignKey("categories.id", ondelete="CASCADE"), nullable=False
    )
    amount = db.Column(db.Float, nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "category_id": self.category_id,
            "created_at": self.created_at.isoformat(),
            "amount": self.amount,
        }