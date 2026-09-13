import json
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from flask.json.provider import DefaultJSONProvider


class JsonEncoder(DefaultJSONProvider):
    def default(self, obj):
        if isinstance(obj, (datetime,)):
            return obj.isoformat()
        if isinstance(obj, UUID):
            return str(obj)
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)
