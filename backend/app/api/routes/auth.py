from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.database.connection import get_db
from app.database.models import User, Account
from app.schemas.auth import CreateAccountRequest, CreateAccountResponse


from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.core.security import (
    verify_password,
    create_access_token,
    create_refresh_token,
    hash_refresh_token,
)
from app.database.models import RefreshToken
from app.schemas.auth import LoginRequest, LoginResponse



router = APIRouter(
    prefix="/api/v1/auth",
    tags=["Authentication"]
)

# Create account route

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

# Login route

@router.post("/login", response_model=LoginResponse)
def login(
    request: LoginRequest,
    db: Session = Depends(get_db),
):
    # Find the user by email
    user = db.query(User).filter(
        User.email == request.email
    ).first()

    # Use the same response for unknown email and wrong password
    if not user or not verify_password(
        request.password,
        user.password_hash,
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password",
        )

    # Reject inactive users
    if not user.is_active:
        raise HTTPException(
            status_code=403,
            detail="Account is inactive",
        )

    # Generate tokens
    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token()

    # Store only the refresh token hash
    stored_token = RefreshToken(
        user_id=user.id,
        token_hash=hash_refresh_token(refresh_token),
        expires_at=datetime.now(timezone.utc)
        + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )

    try:
        db.add(stored_token)
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Unable to complete login",
        )

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
    )

