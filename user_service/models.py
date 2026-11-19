from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class UserModel(db.Model):
    __tablename__ = "users"
    __table_args__ = (db.UniqueConstraint("name", name="uq_users_name"),)
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="user", server_default="user")

    def to_dict(self):
        return {"id": self.id, "name": self.name, "role": self.role}