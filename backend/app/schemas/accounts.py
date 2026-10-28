from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class AccountResponse(BaseModel):
    account_number: str
    account_type: str
    balance: Decimal

    model_config = ConfigDict(from_attributes=True)