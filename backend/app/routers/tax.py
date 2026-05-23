from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import TaxCode, TaxLine, User
from app.schemas import TaxCodeIn, TaxCodeOut, TaxLineOut


router = APIRouter(prefix="/tax", tags=["tax"])


@router.get("/codes", response_model=list[TaxCodeOut])
def list_tax_codes(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> list[TaxCode]:
    return db.query(TaxCode).filter(TaxCode.company_id == current_user.company_id).order_by(TaxCode.code).all()


@router.post("/codes", response_model=TaxCodeOut, status_code=201)
def create_tax_code(
    payload: TaxCodeIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TaxCode:
    code = TaxCode(company_id=current_user.company_id, **payload.model_dump())
    db.add(code)
    db.commit()
    db.refresh(code)
    return code


@router.get("/lines", response_model=list[TaxLineOut])
def list_tax_lines(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> list[TaxLine]:
    return db.query(TaxLine).filter(TaxLine.company_id == current_user.company_id).order_by(TaxLine.created_at.desc()).all()


@router.get("/vat-return")
def vat_return(
    period: str = "2024-06",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    output_vat = (
        db.query(func.coalesce(func.sum(TaxLine.tax_amount), 0))
        .filter(TaxLine.company_id == current_user.company_id, TaxLine.period == period, TaxLine.direction == "output")
        .scalar()
    )
    input_vat = (
        db.query(func.coalesce(func.sum(TaxLine.tax_amount), 0))
        .filter(TaxLine.company_id == current_user.company_id, TaxLine.period == period, TaxLine.direction == "input")
        .scalar()
    )
    net = Decimal(str(output_vat)) - Decimal(str(input_vat))
    return {
        "period": period,
        "output_vat": f"{Decimal(str(output_vat)):.2f}",
        "input_vat": f"{Decimal(str(input_vat)):.2f}",
        "net_vat_payable": f"{net:.2f}",
    }
