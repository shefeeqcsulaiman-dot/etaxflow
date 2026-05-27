from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.accounting_posting import create_gl_entries_from_journal, money, post_source_transaction
from app.database import get_db
from app.dependencies import get_current_user
from app.models import (
    Account,
    AuditLog,
    BankAccount,
    BankReconciliationMatch,
    BankStatementLine,
    GeneralLedgerEntry,
    JournalEntry,
    JournalLine,
    Payment,
    PeriodLock,
    PostingJob,
    Receipt,
    User,
    Voucher,
    VoucherLine,
    VoucherType,
)
from app.schemas import (
    AccountIn,
    AccountOut,
    BankAccountCreate,
    BankAccountOut,
    BankMatchCreate,
    BankMatchOut,
    BankStatementLineCreate,
    BankStatementLineOut,
    GeneralLedgerEntryOut,
    JournalCreate,
    JournalOut,
    PaymentCreate,
    PaymentOut,
    PeriodLockIn,
    PeriodLockOut,
    PostingJobOut,
    ReceiptCreate,
    ReceiptOut,
    VoucherCreate,
    VoucherOut,
    VoucherTypeIn,
    VoucherTypeOut,
)


router = APIRouter(tags=["accounting"])


def next_number(db: Session, company_id: str, prefix: str, model: object, field: object) -> str:
    total = db.query(func.count(model.id)).filter(model.company_id == company_id).scalar() or 0
    return f"{prefix}-{int(total) + 1:05d}"


def ensure_voucher_type(db: Session, company_id: str, code: str, name: str, prefix: str) -> VoucherType:
    voucher_type = db.query(VoucherType).filter(VoucherType.company_id == company_id, VoucherType.code == code).first()
    if voucher_type:
        return voucher_type
    voucher_type = VoucherType(company_id=company_id, code=code, name=name, prefix=prefix)
    db.add(voucher_type)
    db.flush()
    return voucher_type


def assert_period_open(db: Session, company_id: str, module: str, value: datetime | None) -> None:
    period = (value or datetime.now(timezone.utc)).strftime("%Y-%m")
    lock = (
        db.query(PeriodLock)
        .filter(PeriodLock.company_id == company_id, PeriodLock.module.in_([module, "accounting"]), PeriodLock.period == period, PeriodLock.status == "locked")
        .first()
    )
    if lock:
        raise HTTPException(status_code=423, detail=f"{module.title()} period {period} is locked")


def validate_lines(db: Session, company_id: str, lines: list) -> None:
    debit = sum((line.debit for line in lines), Decimal("0.00"))
    credit = sum((line.credit for line in lines), Decimal("0.00"))
    if money(debit) != money(credit):
        raise HTTPException(status_code=422, detail="Voucher must balance: total debit must equal total credit")
    account_ids = {line.account_id for line in lines}
    found = db.query(Account.id).filter(Account.company_id == company_id, Account.id.in_(account_ids)).all()
    if len(found) != len(account_ids):
        raise HTTPException(status_code=422, detail="One or more voucher accounts do not belong to this company")


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


@router.delete("/accounts/{account_id}", status_code=204)
def delete_account(
    account_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    account = db.query(Account).filter(Account.company_id == current_user.company_id, Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    used = db.query(func.count(JournalLine.id)).filter(JournalLine.account_id == account.id).scalar() or 0
    if used:
        raise HTTPException(status_code=409, detail="Account is used by journal lines")
    db.delete(account)
    db.commit()
    return None


@router.get("/journal", response_model=list[JournalOut])
def list_journals(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> list[JournalEntry]:
    return (
        db.query(JournalEntry)
        .options(joinedload(JournalEntry.lines))
        .filter(JournalEntry.company_id == current_user.company_id)
        .order_by(JournalEntry.created_at.desc())
        .all()
    )


@router.get("/voucher-types", response_model=list[VoucherTypeOut])
def list_voucher_types(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> list[VoucherType]:
    return db.query(VoucherType).filter(VoucherType.company_id == current_user.company_id).order_by(VoucherType.code).all()


@router.post("/voucher-types", response_model=VoucherTypeOut, status_code=201)
def create_voucher_type(
    payload: VoucherTypeIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> VoucherType:
    row = VoucherType(company_id=current_user.company_id, **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.get("/vouchers", response_model=list[VoucherOut])
def list_vouchers(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> list[Voucher]:
    return (
        db.query(Voucher)
        .options(joinedload(Voucher.lines))
        .filter(Voucher.company_id == current_user.company_id)
        .order_by(Voucher.created_at.desc())
        .all()
    )


@router.post("/vouchers", response_model=VoucherOut, status_code=201)
def create_voucher(
    payload: VoucherCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Voucher:
    voucher_type = (
        db.query(VoucherType)
        .filter(VoucherType.company_id == current_user.company_id, VoucherType.id == payload.voucher_type_id)
        .first()
    )
    if not voucher_type:
        raise HTTPException(status_code=404, detail="Voucher type not found")
    validate_lines(db, current_user.company_id, payload.lines)
    voucher_date = payload.voucher_date or datetime.now(timezone.utc)
    assert_period_open(db, current_user.company_id, "accounting", voucher_date)
    voucher = Voucher(
        company_id=current_user.company_id,
        voucher_type_id=voucher_type.id,
        voucher_no=payload.voucher_no or next_number(db, current_user.company_id, voucher_type.prefix, Voucher, Voucher.voucher_no),
        voucher_date=voucher_date,
        party=payload.party,
        cost_center=payload.cost_center,
        narration=payload.narration,
        status="pending_approval" if voucher_type.approval_required else "approved",
    )
    voucher.lines = [VoucherLine(**line.model_dump()) for line in payload.lines]
    db.add(voucher)
    db.commit()
    db.refresh(voucher)
    return voucher


@router.post("/vouchers/{voucher_id}/approve", response_model=VoucherOut)
def approve_voucher(
    voucher_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Voucher:
    voucher = (
        db.query(Voucher)
        .options(joinedload(Voucher.lines), joinedload(Voucher.voucher_type))
        .filter(Voucher.company_id == current_user.company_id, Voucher.id == voucher_id)
        .first()
    )
    if not voucher:
        raise HTTPException(status_code=404, detail="Voucher not found")
    if voucher.status == "posted":
        return voucher
    assert_period_open(db, current_user.company_id, "accounting", voucher.voucher_date)
    validate_lines(db, current_user.company_id, voucher.lines)
    journal = JournalEntry(
        company_id=current_user.company_id,
        entry_number=voucher.voucher_no,
        source_module="voucher",
        source_id=voucher.id,
        entry_date=voucher.voucher_date,
        description=voucher.narration or f"{voucher.voucher_type.name} {voucher.voucher_no}",
    )
    journal.lines = [
        JournalLine(account_id=line.account_id, description=line.narration, debit=money(line.debit), credit=money(line.credit))
        for line in voucher.lines
    ]
    db.add(journal)
    db.flush()
    create_gl_entries_from_journal(db, journal, voucher.voucher_no, voucher.voucher_type.name, voucher.party, voucher.cost_center)
    voucher.status = "posted"
    voucher.approved_by = current_user.id
    voucher.approved_at = datetime.now(timezone.utc)
    voucher.posted_journal_id = journal.id
    db.add(AuditLog(company_id=current_user.company_id, user_id=current_user.id, module="accounting", action="voucher_posted", record_id=voucher.id, detail=voucher.voucher_no))
    db.commit()
    db.refresh(voucher)
    return voucher


@router.get("/general-ledger", response_model=list[GeneralLedgerEntryOut])
def list_general_ledger(
    account_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[GeneralLedgerEntry]:
    query = db.query(GeneralLedgerEntry).filter(GeneralLedgerEntry.company_id == current_user.company_id)
    if account_id:
        query = query.filter(GeneralLedgerEntry.account_id == account_id)
    return query.order_by(GeneralLedgerEntry.entry_date.desc(), GeneralLedgerEntry.created_at.desc()).all()


@router.get("/posting-jobs", response_model=list[PostingJobOut])
def list_posting_jobs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[PostingJob]:
    return (
        db.query(PostingJob)
        .filter(PostingJob.company_id == current_user.company_id)
        .order_by(PostingJob.created_at.desc())
        .all()
    )


@router.post("/posting-jobs/{job_id}/retry", response_model=PostingJobOut)
def retry_posting_job(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PostingJob:
    job = db.query(PostingJob).filter(PostingJob.company_id == current_user.company_id, PostingJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Posting job not found")
    if job.status == "posted":
        return job
    post_source_transaction(db, job, current_user.id)
    db.commit()
    db.refresh(job)
    return job


@router.get("/payments", response_model=list[PaymentOut])
def list_payments(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> list[Payment]:
    return db.query(Payment).filter(Payment.company_id == current_user.company_id).order_by(Payment.created_at.desc()).all()


@router.post("/payments", response_model=PaymentOut, status_code=201)
def create_payment(
    payload: PaymentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Payment:
    payment_date = payload.payment_date or datetime.now(timezone.utc)
    assert_period_open(db, current_user.company_id, "accounting", payment_date)
    payment = Payment(
        company_id=current_user.company_id,
        payment_no=payload.payment_no or next_number(db, current_user.company_id, "PAY", Payment, Payment.payment_no),
        payment_date=payment_date,
        payment_mode=payload.payment_mode,
        cash_bank_account_id=payload.cash_bank_account_id,
        debit_account_id=payload.debit_account_id,
        payee_type=payload.payee_type,
        payee_name=payload.payee_name,
        amount=payload.amount,
        reference_no=payload.reference_no,
        narration=payload.narration,
        attachment=payload.attachment,
        status="draft",
    )
    db.add(payment)
    db.flush()
    if payload.post:
        voucher_type = ensure_voucher_type(db, current_user.company_id, "PAY", "Payment Voucher", "PAY")
        voucher = Voucher(
            company_id=current_user.company_id,
            voucher_type_id=voucher_type.id,
            voucher_no=payment.payment_no,
            voucher_date=payment.payment_date,
            party=payment.payee_name,
            narration=payment.narration or payment.reference_no,
            status="pending_approval",
        )
        voucher.lines = [
            VoucherLine(account_id=payment.debit_account_id, debit=money(payment.amount), credit=Decimal("0.00"), party=payment.payee_name, narration=payment.narration),
            VoucherLine(account_id=payment.cash_bank_account_id, debit=Decimal("0.00"), credit=money(payment.amount), party=payment.payee_name, narration=payment.narration),
        ]
        db.add(voucher)
        db.flush()
        payment.voucher_id = voucher.id
        approve_voucher(voucher.id, db, current_user)
        payment.status = "posted"
    db.commit()
    db.refresh(payment)
    return payment


@router.get("/receipts", response_model=list[ReceiptOut])
def list_receipts(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> list[Receipt]:
    return db.query(Receipt).filter(Receipt.company_id == current_user.company_id).order_by(Receipt.created_at.desc()).all()


@router.post("/receipts", response_model=ReceiptOut, status_code=201)
def create_receipt(
    payload: ReceiptCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Receipt:
    receipt_date = payload.receipt_date or datetime.now(timezone.utc)
    assert_period_open(db, current_user.company_id, "accounting", receipt_date)
    receipt = Receipt(
        company_id=current_user.company_id,
        receipt_no=payload.receipt_no or next_number(db, current_user.company_id, "RCT", Receipt, Receipt.receipt_no),
        receipt_date=receipt_date,
        receipt_mode=payload.receipt_mode,
        cash_bank_account_id=payload.cash_bank_account_id,
        credit_account_id=payload.credit_account_id,
        received_from=payload.received_from,
        amount=payload.amount,
        reference_no=payload.reference_no,
        narration=payload.narration,
        attachment=payload.attachment,
        status="draft",
    )
    db.add(receipt)
    db.flush()
    if payload.post:
        voucher_type = ensure_voucher_type(db, current_user.company_id, "RCT", "Receipt Voucher", "RCT")
        voucher = Voucher(
            company_id=current_user.company_id,
            voucher_type_id=voucher_type.id,
            voucher_no=receipt.receipt_no,
            voucher_date=receipt.receipt_date,
            party=receipt.received_from,
            narration=receipt.narration or receipt.reference_no,
            status="pending_approval",
        )
        voucher.lines = [
            VoucherLine(account_id=receipt.cash_bank_account_id, debit=money(receipt.amount), credit=Decimal("0.00"), party=receipt.received_from, narration=receipt.narration),
            VoucherLine(account_id=receipt.credit_account_id, debit=Decimal("0.00"), credit=money(receipt.amount), party=receipt.received_from, narration=receipt.narration),
        ]
        db.add(voucher)
        db.flush()
        receipt.voucher_id = voucher.id
        approve_voucher(voucher.id, db, current_user)
        receipt.status = "posted"
    db.commit()
    db.refresh(receipt)
    return receipt


@router.get("/bank-accounts", response_model=list[BankAccountOut])
def list_bank_accounts(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> list[BankAccount]:
    return db.query(BankAccount).filter(BankAccount.company_id == current_user.company_id).order_by(BankAccount.bank_name).all()


@router.post("/bank-accounts", response_model=BankAccountOut, status_code=201)
def create_bank_account(
    payload: BankAccountCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BankAccount:
    account = db.query(Account).filter(Account.company_id == current_user.company_id, Account.id == payload.account_id).first()
    if not account:
        raise HTTPException(status_code=422, detail="Bank ledger account does not belong to this company")
    account.is_bank_cash = True
    row = BankAccount(company_id=current_user.company_id, **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.post("/bank-statement-lines", response_model=BankStatementLineOut, status_code=201)
def create_bank_statement_line(
    payload: BankStatementLineCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BankStatementLine:
    bank = db.query(BankAccount).filter(BankAccount.company_id == current_user.company_id, BankAccount.id == payload.bank_account_id).first()
    if not bank:
        raise HTTPException(status_code=404, detail="Bank account not found")
    row = BankStatementLine(company_id=current_user.company_id, **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.post("/bank-reconciliation/matches", response_model=BankMatchOut, status_code=201)
def match_bank_line(
    payload: BankMatchCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BankReconciliationMatch:
    statement = db.query(BankStatementLine).filter(BankStatementLine.company_id == current_user.company_id, BankStatementLine.id == payload.statement_line_id).first()
    ledger = db.query(GeneralLedgerEntry).filter(GeneralLedgerEntry.company_id == current_user.company_id, GeneralLedgerEntry.id == payload.ledger_entry_id).first()
    if not statement or not ledger:
        raise HTTPException(status_code=404, detail="Statement line or ledger entry not found")
    match = BankReconciliationMatch(
        company_id=current_user.company_id,
        bank_account_id=statement.bank_account_id,
        statement_line_id=statement.id,
        ledger_entry_id=ledger.id,
        match_status="matched",
        match_method=payload.match_method,
        difference=payload.difference,
        confirmed_by=current_user.id,
        confirmed_at=datetime.now(timezone.utc),
    )
    statement.status = "matched"
    db.add(match)
    db.commit()
    db.refresh(match)
    return match


@router.post("/period-locks", response_model=PeriodLockOut, status_code=201)
def upsert_period_lock(
    payload: PeriodLockIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PeriodLock:
    lock = (
        db.query(PeriodLock)
        .filter(PeriodLock.company_id == current_user.company_id, PeriodLock.module == payload.module, PeriodLock.period == payload.period)
        .first()
    )
    if not lock:
        lock = PeriodLock(company_id=current_user.company_id, module=payload.module, period=payload.period)
        db.add(lock)
    lock.status = payload.status
    lock.reason = payload.reason
    lock.locked_by = current_user.id if payload.status == "locked" else None
    lock.locked_at = datetime.now(timezone.utc) if payload.status == "locked" else None
    db.commit()
    db.refresh(lock)
    return lock


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
    assert_period_open(db, current_user.company_id, "accounting", payload.entry_date)

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
    db.flush()
    create_gl_entries_from_journal(db, journal, payload.entry_number, payload.source_module)
    db.commit()
    db.refresh(journal)
    return journal
