from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.database.connection import get_db
from app.database.models import User, Account, RefreshToken
from app.schemas.auth import CreateAccountRequest, CreateAccountResponse


from datetime import datetime, timedelta, timezone
import hashlib,secrets


from app.core.config import settings
from app.core.security import (
    verify_password,
    create_access_token,
    create_refresh_token,
    hash_refresh_token,
)
 
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    LogoutResponse,
)

from app.schemas.auth import (
    RefreshTokenRequest,
    RefreshTokenResponse,
)


router = APIRouter(
    prefix="/auth",
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



# Refresh token route

@router.post(
    "/refresh",
    response_model=RefreshTokenResponse,
    status_code=status.HTTP_200_OK,
)
def refresh_access_token(
    request: RefreshTokenRequest,
    db: Session = Depends(get_db),
):
    # Hash the refresh token received from the client.
    token_hash = hashlib.sha256(
        request.refresh_token.encode("utf-8")
    ).hexdigest()

    # Find and lock the matching database record.
    stored_token = (
        db.query(RefreshToken)
        .filter(RefreshToken.token_hash == token_hash)
        .with_for_update()
        .first()
    )

    # Use a generic error to avoid exposing token details.
    invalid_token_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired refresh token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if stored_token is None:
        raise invalid_token_error

    # Reject revoked tokens.
    if stored_token.revoked:
        raise invalid_token_error

    # Reject expired tokens.
    now = datetime.now(timezone.utc)

    if stored_token.expires_at <= now:
        stored_token.revoked = True
        db.commit()
        raise invalid_token_error

    try:
        # Find the user associated with this token.
        user = (
            db.query(User)
            .filter(User.id == stored_token.user_id)
            .first()
        )

        if user is None or not user.is_active:
            stored_token.revoked = True
            db.commit()
            raise invalid_token_error

        # Generate a new access token.
        new_access_token = create_access_token(user.id)

        # Generate a new refresh token.
        new_refresh_token = secrets.token_urlsafe(48)

        new_refresh_token_hash = hashlib.sha256(
            new_refresh_token.encode("utf-8")
        ).hexdigest()

        # Revoke the old refresh token.
        stored_token.revoked = True

        # Store only the new token's hash.
        new_token_record = RefreshToken(
            user_id=user.id,
            token_hash=new_refresh_token_hash,
            expires_at=now + timedelta(
                days=settings.REFRESH_TOKEN_EXPIRE_DAYS
            ),
            revoked=False,
        )

        db.add(new_token_record)

        # Revoke the old token and store the new one atomically.
        db.commit()

        return RefreshTokenResponse(
            access_token=new_access_token,
            refresh_token=new_refresh_token,
            token_type="bearer",
        )

    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to refresh session",
        )


# Logout route

@router.post(
    "/logout",
    response_model=LogoutResponse,
    status_code=status.HTTP_200_OK,
)
def logout(
    request: RefreshTokenRequest,
    db: Session = Depends(get_db),
):
    # Hash the refresh token received from the client.
    token_hash = hashlib.sha256(
        request.refresh_token.encode("utf-8")
    ).hexdigest()

    try:
        # Find the token record and lock it during the update.
        stored_token = (
            db.query(RefreshToken)
            .filter(RefreshToken.token_hash == token_hash)
            .with_for_update()
            .first()
        )

        # Reject unknown tokens.
        if stored_token is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
            )

        # Revoke the token if it hasn't already been revoked.
        if not stored_token.revoked:
            stored_token.revoked = True
            db.commit()

        return LogoutResponse(
            message="Logout successful"
        )

    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to complete logout",
        )