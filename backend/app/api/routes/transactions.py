
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.database.models import Account, Transaction, User
from app.api.dependencies import get_current_user
from app.schemas.transactions import TransferRequest, TransferResponse


router = APIRouter(prefix="/transactions", tags=["Transactions"])


@router.post("/transfer", response_model=TransferResponse)
def transfer_money(
    request: TransferRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        # Find the sender's account
        sender_account = (
            db.query(Account)
            .filter(Account.user_id == current_user.id)
            .first()
        )

        if not sender_account:
            raise HTTPException(
                status_code=404,
                detail="Sender account not found",
            )

        # Find the recipient's account
        recipient_account = (
            db.query(Account)
            .filter(
                Account.account_number == request.recipient_account_number
            )
            .first()
        )

        if not recipient_account:
            raise HTTPException(
                status_code=404,
                detail="Recipient account not found",
            )

        if sender_account.id == recipient_account.id:
            raise HTTPException(
                status_code=400,
                detail="You cannot transfer money to your own account",
            )

        # Lock both accounts in a consistent order to protect balances
        account_ids = [sender_account.id, recipient_account.id]

        locked_accounts = (
            db.query(Account)
            .filter(Account.id.in_(account_ids))
            .order_by(Account.id)
            .with_for_update()
            .all()
        )

        accounts_by_id = {account.id: account for account in locked_accounts}
        sender = accounts_by_id[sender_account.id]
        recipient = accounts_by_id[recipient_account.id]

        # Validate account status
        if sender.status != "ACTIVE":
            raise HTTPException(
                status_code=400,
                detail="Sender account is not active",
            )

        if recipient.status != "ACTIVE":
            raise HTTPException(
                status_code=400,
                detail="Recipient account is not active",
            )

        # Check the sender's available balance
        if sender.balance < request.amount:
            raise HTTPException(
                status_code=400,
                detail="Insufficient balance",
            )

        # Generate one reference for both transaction records
        transfer_reference = str(uuid4())

        # Update both balances
        sender.balance -= request.amount
        recipient.balance += request.amount

        # Create the sender's debit record
        debit_transaction = Transaction(
            account_id=sender.id,
            transfer_reference=transfer_reference,
            transaction_type="DEBIT",
            amount=request.amount,
            description=request.description or "Transfer to another account",
        )

        # Create the recipient's credit record
        credit_transaction = Transaction(
            account_id=recipient.id,
            transfer_reference=transfer_reference,
            transaction_type="CREDIT",
            amount=request.amount,
            description=request.description or "Transfer received",
        )

        db.add_all([debit_transaction, credit_transaction])

        # Save both balance changes and records together
        db.commit()

        return TransferResponse(
            message="Transaction successful",
            transfer_reference=transfer_reference,
            amount=request.amount,
            sender_balance=sender.balance,
            recipient_account_number=recipient.account_number,
            transaction_date=debit_transaction.transaction_date,
        )

    except HTTPException:
        db.rollback()
        raise

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Transaction failed",
        )
