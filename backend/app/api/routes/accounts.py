
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.database.connection import get_db
from app.database.models import Account, User
from app.schemas.accounts import AccountResponse


router = APIRouter(
    prefix="/accounts",
    tags=["Accounts"],
)


@router.get("/me", response_model=AccountResponse)
def get_my_account(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AccountResponse:

    account = (
        db.query(Account)
        .filter(Account.user_id == current_user.id)
        .first()
    )

    if account is None:
        raise HTTPException(
            status_code=404,
            detail="Account not found",
        )

    return account
