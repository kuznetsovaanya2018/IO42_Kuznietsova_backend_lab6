from marshmallow import Schema, fields, validate


class RegisterSchema(Schema):
    name = fields.Str(
        required=True,
        validate=[
            validate.Length(min=1, max=100),
            validate.Regexp(r".*\S.*", error="Name must not be blank."),
        ],
    )
    password = fields.Str(required=True, validate=validate.Length(min=8, max=128))


class LoginSchema(Schema):
    name = fields.Str(required=True)
    password = fields.Str(required=True)


class RoleSchema(Schema):
    role = fields.Str(required=True, validate=validate.OneOf(["user", "auditor", "admin"]))