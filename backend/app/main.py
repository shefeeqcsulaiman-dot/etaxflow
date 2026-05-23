from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import Base, SessionLocal, engine
from app.models import Account, AuditLog, Company, Employee, ItemUnit, ItemUnitConversion, StockProductMapping, TaxCode, User, Warehouse
from app.routers import accounting, ai, app_data, audit, auth, companies, corporate_accounting, documents, events, exception_center, inventory, invoices, jobs, module_records, payroll, reports, source_transactions, tax
from app.security import hash_password


settings = get_settings()


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    def startup() -> None:
        Base.metadata.create_all(bind=engine)
        ensure_schema_updates()
        seed_initial_data()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": settings.app_name}

    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(ai.router, prefix="/api/v1")
    app.include_router(companies.router, prefix="/api/v1")
    app.include_router(invoices.router, prefix="/api/v1")
    app.include_router(documents.router, prefix="/api/v1")
    app.include_router(jobs.router, prefix="/api/v1")
    app.include_router(source_transactions.router, prefix="/api/v1")
    app.include_router(accounting.router, prefix="/api/v1")
    app.include_router(corporate_accounting.router, prefix="/api/v1")
    app.include_router(tax.router, prefix="/api/v1")
    app.include_router(inventory.router, prefix="/api/v1")
    app.include_router(payroll.router, prefix="/api/v1")
    app.include_router(reports.router, prefix="/api/v1")
    app.include_router(audit.router, prefix="/api/v1")
    app.include_router(exception_center.router, prefix="/api/v1")
    app.include_router(events.router, prefix="/api/v1")
    app.include_router(module_records.router, prefix="/api/v1")
    app.include_router(app_data.router, prefix="/api/v1")
    return app


def ensure_schema_updates() -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    with engine.begin() as connection:
        if "stock_product_mappings" in table_names:
            existing_columns = {column["name"] for column in inspector.get_columns("stock_product_mappings")}
            required_columns = {
                "supplier_name": "VARCHAR(160)",
                "taxflow_name": "VARCHAR(160)",
                "units_per_outer": "NUMERIC(12, 4) DEFAULT 1",
                "cost": "NUMERIC(12, 2) DEFAULT 0",
                "markup_percent": "NUMERIC(8, 2) DEFAULT 0",
                "tax_rate": "NUMERIC(5, 2) DEFAULT 5",
                "vat_amount": "NUMERIC(12, 2) DEFAULT 0",
                "inc_vat": "NUMERIC(12, 2) DEFAULT 0",
                "price_outer": "NUMERIC(12, 2) DEFAULT 0",
            }
            for column_name, column_type in required_columns.items():
                if column_name not in existing_columns:
                    connection.execute(text(f"ALTER TABLE stock_product_mappings ADD COLUMN {column_name} {column_type}"))
        if "item_units" in table_names:
            existing_columns = {column["name"] for column in inspector.get_columns("item_units")}
            required_columns = {
                "purchase_default": "BOOLEAN DEFAULT 0",
                "sales_default": "BOOLEAN DEFAULT 0",
                "status": "VARCHAR(30) DEFAULT 'active'",
            }
            for column_name, column_type in required_columns.items():
                if column_name not in existing_columns:
                    connection.execute(text(f"ALTER TABLE item_units ADD COLUMN {column_name} {column_type}"))
        if "invoices" in table_names:
            index_names = {index["name"] for index in inspector.get_indexes("invoices")}
            if "uq_invoice_company_number" not in index_names:
                connection.execute(
                    text("CREATE UNIQUE INDEX IF NOT EXISTS uq_invoice_company_number ON invoices (company_id, invoice_number)")
                )


def seed_initial_data() -> None:
    db: Session = SessionLocal()
    try:
        company = db.query(Company).filter(Company.trn == "100000000000003").first()
        if not company:
            company = Company(name="TaxFlow UAE LLC", trn="100000000000003")
            db.add(company)
            db.flush()

        user = db.query(User).filter(User.email == "admin@taxflowapp.com").first()
        legacy_user = db.query(User).filter(User.email == "admin@taxflow.local").first()
        if not user:
            if legacy_user:
                user = legacy_user
                user.email = "admin@taxflowapp.com"
            else:
                user = User(
                    company_id=company.id,
                    email="admin@taxflowapp.com",
                    full_name="Sara Ahmed",
                    role="admin",
                )
                db.add(user)

        user.full_name = "Sara Ahmed"
        user.role = "admin"
        user.password_hash = hash_password("admin123")
        user.company_id = company.id

        seed_accounts(db, company.id)
        seed_tax_codes(db, company.id)
        db.commit()
    finally:
        db.close()


def seed_accounts(db: Session, company_id: str) -> None:
    accounts = [
        ("1000", "Cash and Bank", "asset"),
        ("1100", "Accounts Receivable", "asset"),
        ("1200", "Inventory", "asset"),
        ("2100", "Accounts Payable", "liability"),
        ("2200", "VAT Output Payable", "liability"),
        ("2210", "VAT Input Recoverable", "asset"),
        ("3000", "Sales Income", "revenue"),
        ("4000", "Purchases", "expense"),
        ("5000", "Cost of Goods Sold", "expense"),
        ("6000", "Salary Expense", "expense"),
    ]
    for code, name, account_type in accounts:
        account = db.query(Account).filter(Account.company_id == company_id, Account.code == code).first()
        if not account:
            db.add(Account(company_id=company_id, code=code, name=name, type=account_type))


def seed_tax_codes(db: Session, company_id: str) -> None:
    codes = [
        ("VAT5", "Standard UAE VAT", "5.00", True, "Box 1"),
        ("ZERO", "Zero-rated export", "0.00", False, "Box 4"),
        ("EXEMPT", "Exempt supply", "0.00", False, "Box 6"),
        ("RCM", "Reverse charge", "5.00", True, "Box 3"),
    ]
    for code, name, rate, recoverable, box in codes:
        tax_code = db.query(TaxCode).filter(TaxCode.company_id == company_id, TaxCode.code == code).first()
        if not tax_code:
            db.add(TaxCode(company_id=company_id, code=code, name=name, rate=rate, recoverable=recoverable, reporting_box=box))


def seed_inventory(db: Session, company_id: str) -> None:
    warehouse = db.query(Warehouse).filter(Warehouse.company_id == company_id, Warehouse.name == "Main Store").first()
    if not warehouse:
        db.add(Warehouse(company_id=company_id, name="Main Store", location="Dubai HQ"))
    mapping = db.query(StockProductMapping).filter(StockProductMapping.company_id == company_id, StockProductMapping.sku == "PRD-001").first()
    if not mapping:
        db.add(
            StockProductMapping(
                company_id=company_id,
                sku="PRD-001",
                name="Steel Rods 12mm",
                sales_account_code="3000",
                purchase_account_code="4000",
                inventory_account_code="1200",
                tax_code="VAT5",
                reorder_level=50,
            )
        )
    item_units = [
        ("PRD-001", "PCS", "Pieces", "1.0000", True, False, True),
        ("PRD-001", "BOX", "Box", "12.0000", False, True, False),
    ]
    for item_code, unit_code, unit_name, factor, is_base, purchase_default, sales_default in item_units:
        unit = (
            db.query(ItemUnit)
            .filter(ItemUnit.company_id == company_id, ItemUnit.item_code == item_code, ItemUnit.unit_code == unit_code)
            .first()
        )
        if not unit:
            db.add(
                ItemUnit(
                    company_id=company_id,
                    item_code=item_code,
                    unit_code=unit_code,
                    unit_name=unit_name,
                    conversion_factor=factor,
                    is_base_unit=is_base,
                    purchase_default=purchase_default,
                    sales_default=sales_default,
                )
            )
    conversion = (
        db.query(ItemUnitConversion)
        .filter(
            ItemUnitConversion.company_id == company_id,
            ItemUnitConversion.item_code == "PRD-001",
            ItemUnitConversion.from_unit_code == "BOX",
            ItemUnitConversion.to_unit_code == "PCS",
        )
        .first()
    )
    if not conversion:
        db.add(
            ItemUnitConversion(
                company_id=company_id,
                item_code="PRD-001",
                from_unit_code="BOX",
                to_unit_code="PCS",
                conversion_factor="12.0000",
            )
        )


def seed_employees(db: Session, company_id: str) -> None:
    employees = [
        ("EMP-001", "Sara Al Mansouri", "Management", "General Manager", "22000.00", "AE070331234567890123456", "WPS-001"),
        ("EMP-002", "Ahmed Rashid", "Operations", "Warehouse Manager", "8500.00", "AE150331234567890123456", "WPS-002"),
        ("EMP-003", "Rania Abboud", "Finance", "Accountant", "7200.00", None, "WPS-003"),
        ("EMP-004", "Mohamed Jaber", "Sales", "Sales Executive", "6800.00", "AE460331234567890123456", "WPS-004"),
    ]
    for employee_no, full_name, department, designation, salary, iban, wps_id in employees:
        employee = db.query(Employee).filter(Employee.company_id == company_id, Employee.employee_no == employee_no).first()
        if not employee:
            db.add(
                Employee(
                    company_id=company_id,
                    employee_no=employee_no,
                    full_name=full_name,
                    department=department,
                    designation=designation,
                    basic_salary=salary,
                    iban=iban,
                    wps_id=wps_id,
                )
            )


def seed_audit(db: Session, company_id: str, user_id: str) -> None:
    exists = db.query(AuditLog).filter(AuditLog.company_id == company_id, AuditLog.action == "initial_data_seeded").first()
    if not exists:
        db.add(
            AuditLog(
                company_id=company_id,
                user_id=user_id,
                module="system",
                action="initial_data_seeded",
                detail="Seeded TaxFlow production modules and master data",
            )
        )


app = create_app()
