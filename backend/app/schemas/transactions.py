
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, Field, ConfigDict


class TransferRequest(BaseModel):
    recipient_account_number: str = Field(
        min_length=1,
        max_length=20,
    )
    amount: Decimal = Field(
        gt=0,
        max_digits=15,
        decimal_places=2,
    )
    description: str | None = Field(
        default=None,
        max_length=255,
    )


class TransferResponse(BaseModel):
    message: str
    transfer_reference: str
    amount: Decimal
    sender_balance: Decimal
    recipient_account_number: str
    transaction_date: datetime


class TransactionHistoryItem(BaseModel):
    transaction_id: int
    transfer_reference: str
    transaction_type: str
    amount: Decimal
    description: str | None
    transaction_date: datetime

    model_config = ConfigDict(from_attributes=True)
