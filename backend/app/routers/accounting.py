from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Account, JournalEntry, JournalLine, User
from app.schemas import AccountIn, AccountOut, JournalCreate, JournalOut


router = APIRouter(tags=["accounting"])


@router.get("/accounts", response_model=list[AccountOut])
def list_accounts(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> list[Account]:
    return db.query(Account).filter(Account.company_id == current_user.company_id).order_by(Account.code).all()


@router.post("/accounts", response_model=AccountOut, status_code=201)
def create_account(
    payload: AccountIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Account:
    account = Account(company_id=current_user.company_id, **payload.model_dump())
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


@router.get("/journal", response_model=list[JournalOut])
def list_journals(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> list[JournalEntry]:
    return (
        db.query(JournalEntry)
        .options(joinedload(JournalEntry.lines))
        .filter(JournalEntry.company_id == current_user.company_id)
        .order_by(JournalEntry.created_at.desc())
        .all()
    )


@router.post("/journal", response_model=JournalOut, status_code=201)
def create_journal(
    payload: JournalCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> JournalEntry:
    debit = sum((line.debit for line in payload.lines), Decimal("0.00"))
    credit = sum((line.credit for line in payload.lines), Decimal("0.00"))
    if debit != credit:
        raise HTTPException(status_code=422, detail="Journal must balance: total debit must equal total credit")

    account_ids = {line.account_id for line in payload.lines}
    found = (
        db.query(Account.id)
        .filter(Account.company_id == current_user.company_id, Account.id.in_(account_ids))
        .all()
    )
    if len(found) != len(account_ids):
        raise HTTPException(status_code=422, detail="One or more accounts do not belong to this company")

    journal_data = {
        "company_id": current_user.company_id,
        "entry_number": payload.entry_number,
        "source_module": payload.source_module,
        "source_id": payload.source_id,
        "description": payload.description,
    }
    if payload.entry_date is not None:
        journal_data["entry_date"] = payload.entry_date
    journal = JournalEntry(
        **journal_data,
    )
    journal.lines = [JournalLine(**line.model_dump()) for line in payload.lines]
    db.add(journal)
    db.commit()
    db.refresh(journal)
    return journal
