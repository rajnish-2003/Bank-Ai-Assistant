from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.database.connection import get_db
from app.database.models import User, Account
from app.schemas.auth import CreateAccountRequest, CreateAccountResponse


router = APIRouter(
    prefix="/api/v1/auth",
    tags=["Authentication"]
)


@router.post(
    "/create-account",
    response_model=CreateAccountResponse
)
def create_account(
    request: CreateAccountRequest,
    db: Session = Depends(get_db)
):
    # Check whether email already exists
    existing_user = db.query(User).filter(
        User.email == request.email
    ).first()

    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="Email already registered"
        )

    # Hash the password
    hashed_password = hash_password(request.password)

    # Create user
    user = User(
        full_name=request.full_name,
        email=request.email,
        password_hash=hashed_password
    )

    db.add(user)
    db.flush()

    # Generate account number
    account_number = f"100000000000"[:-len(str(user.id))] + str(user.id)

    # Create bank account
    account = Account(
        account_number=account_number,
        user_id=user.id,
        account_type="SAVINGS",
        balance=0,
        status="ACTIVE"
    )

    db.add(account)

    # Save both user and account together
    db.commit()

    db.refresh(user)
    db.refresh(account)

    return CreateAccountResponse(
        message="Account created successfully",
        user_id=user.id,
        account_number=account.account_number
    )
