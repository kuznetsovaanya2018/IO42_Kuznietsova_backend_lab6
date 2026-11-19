from marshmallow import Schema, fields, validate


def id_field(required=True):
    return fields.Int(
        required=required, strict=True, validate=validate.Range(min=1, max=2147483647)
    )


class CategorySchema(Schema):
    name = fields.Str(
        required=True,
        validate=[
            validate.Length(min=1, max=100),
            validate.Regexp(r".*\S.*", error="Name must not be blank."),
        ],
    )


class AccountSchema(Schema):
    user_id = id_field()


class TopUpSchema(Schema):
    amount = fields.Float(required=True, validate=validate.Range(min=0.01))


class RecordSchema(Schema):
    user_id = id_field()
    category_id = id_field()
    amount = fields.Float(required=True, validate=validate.Range(min=0.01))


class RecordIdSchema(Schema):
    record_id = id_field()


class RecordFilterSchema(Schema):
    user_id = id_field(required=False)
    category_id = id_field(required=False)