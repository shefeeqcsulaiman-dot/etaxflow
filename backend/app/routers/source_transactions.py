from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Account, AuditLog, PostingJob, SourceTransaction, SourceTransactionLine, TaxCode, TaxLine, User
from app.schemas import PostingJobOut, SourceTransactionCreate, SourceTransactionOut


router = APIRouter(prefix="/source-transactions", tags=["source transactions"])


def recalc(transaction: SourceTransaction) -> None:
    subtotal = Decimal("0.00")
    vat = Decimal("0.00")
    for line in transaction.lines:
        line.amount = line.quantity * line.unit_price
        line.vat_amount = line.amount * (line.vat_rate / Decimal("100"))
        subtotal += line.amount
        vat += line.vat_amount
    transaction.subtotal = subtotal
    transaction.vat = vat
    transaction.total = subtotal + vat


@router.get("", response_model=list[SourceTransactionOut])
def list_sources(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> list[SourceTransaction]:
    return (
        db.query(SourceTransaction)
        .options(joinedload(SourceTransaction.lines))
        .filter(SourceTransaction.company_id == current_user.company_id)
        .order_by(SourceTransaction.created_at.desc())
        .all()
    )


@router.post("", response_model=SourceTransactionOut, status_code=201)
def create_source(
    payload: SourceTransactionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SourceTransaction:
    transaction = SourceTransaction(
        company_id=current_user.company_id,
        module=payload.module,
        reference=payload.reference,
        party_name=payload.party_name,
    )
    transaction.lines = [SourceTransactionLine(**line.model_dump()) for line in payload.lines]
    recalc(transaction)
    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    return transaction


@router.post("/{source_id}/validate", response_model=SourceTransactionOut)
def validate_source(
    source_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SourceTransaction:
    transaction = (
        db.query(SourceTransaction)
        .options(joinedload(SourceTransaction.lines))
        .filter(SourceTransaction.id == source_id, SourceTransaction.company_id == current_user.company_id)
        .first()
    )
    if not transaction:
        raise HTTPException(status_code=404, detail="Source transaction not found")
    account_codes = {line.account_code for line in transaction.lines}
    existing_codes = {
        row[0]
        for row in db.query(Account.code)
        .filter(Account.company_id == current_user.company_id, Account.code.in_(account_codes))
        .all()
    }
    missing = sorted(account_codes - existing_codes)
    if missing:
        transaction.status = "review"
        transaction.validation_result = f"Missing account mappings: {', '.join(missing)}"
    else:
        transaction.status = "validated"
        transaction.validation_result = "All line account mappings and tax calculations are valid"
    recalc(transaction)
    db.commit()
    db.refresh(transaction)
    return transaction


@router.post("/{source_id}/approve", response_model=PostingJobOut, status_code=202)
def approve_source(
    source_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PostingJob:
    transaction = (
        db.query(SourceTransaction)
        .options(joinedload(SourceTransaction.lines))
        .filter(SourceTransaction.id == source_id, SourceTransaction.company_id == current_user.company_id)
        .first()
    )
    if not transaction:
        raise HTTPException(status_code=404, detail="Source transaction not found")
    if transaction.status not in {"validated", "approved"}:
        validate_source(source_id, db, current_user)
        db.refresh(transaction)
    if transaction.status != "validated":
        raise HTTPException(status_code=422, detail=transaction.validation_result or "Source transaction is not valid")

    transaction.status = "approved"
    transaction.approved_by = current_user.id
    transaction.approved_at = datetime.now(timezone.utc)
    job = PostingJob(company_id=current_user.company_id, source_id=transaction.id, status="queued")
    db.add(job)
    tax_code = db.query(TaxCode).filter(TaxCode.company_id == current_user.company_id, TaxCode.code == "VAT5").first()
    if transaction.vat:
        db.add(
            TaxLine(
                company_id=current_user.company_id,
                source_id=transaction.id,
                tax_code_id=tax_code.id if tax_code else None,
                direction="output" if transaction.module == "sales" else "input",
                taxable_amount=transaction.subtotal,
                tax_amount=transaction.vat,
            )
        )
    db.add(AuditLog(company_id=current_user.company_id, user_id=current_user.id, module=transaction.module, action="approved", record_id=transaction.id, detail=transaction.reference))
    db.commit()
    db.refresh(job)
    return job
