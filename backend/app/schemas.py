from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class CompanyOut(BaseModel):
    id: str
    name: str
    trn: str | None
    country: str

    model_config = {"from_attributes": True}


class UserOut(BaseModel):
    id: str
    email: EmailStr
    full_name: str
    role: str
    company: CompanyOut

    model_config = {"from_attributes": True}


class InvoiceLineIn(BaseModel):
    description: str
    quantity: Decimal = Field(default=1, ge=0)
    unit_price: Decimal = Field(default=0, ge=0)
    vat_rate: Decimal = Field(default=5, ge=0)


class InvoiceCreate(BaseModel):
    customer_name: str
    invoice_number: str
    lines: list[InvoiceLineIn]


class InvoiceLineOut(InvoiceLineIn):
    id: str

    model_config = {"from_attributes": True}


class InvoiceOut(BaseModel):
    id: str
    customer_name: str
    invoice_number: str
    status: str
    subtotal: Decimal
    vat: Decimal
    total: Decimal
    created_at: datetime
    lines: list[InvoiceLineOut] = []

    model_config = {"from_attributes": True}


class DocumentOut(BaseModel):
    id: str
    filename: str
    content_type: str
    storage_key: str
    created_at: datetime

    model_config = {"from_attributes": True}


class JobOut(BaseModel):
    id: str
    kind: str
    status: str
    result: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AccountIn(BaseModel):
    code: str
    name: str
    type: str
    is_active: bool = True


class AccountOut(AccountIn):
    id: str
    created_at: datetime

    model_config = {"from_attributes": True}


class JournalLineIn(BaseModel):
    account_id: str
    description: str | None = None
    debit: Decimal = Field(default=0, ge=0)
    credit: Decimal = Field(default=0, ge=0)


class JournalCreate(BaseModel):
    entry_number: str
    entry_date: datetime | None = None
    description: str
    source_module: str = "manual"
    source_id: str | None = None
    lines: list[JournalLineIn]


class JournalLineOut(JournalLineIn):
    id: str

    model_config = {"from_attributes": True}


class JournalOut(BaseModel):
    id: str
    entry_number: str
    source_module: str
    source_id: str | None
    entry_date: datetime
    description: str
    status: str
    created_at: datetime
    lines: list[JournalLineOut] = []

    model_config = {"from_attributes": True}


class SourceLineIn(BaseModel):
    description: str
    account_code: str
    quantity: Decimal = Field(default=1, ge=0)
    unit_price: Decimal = Field(default=0, ge=0)
    vat_rate: Decimal = Field(default=5, ge=0)


class SourceTransactionCreate(BaseModel):
    module: str
    reference: str
    party_name: str | None = None
    lines: list[SourceLineIn]


class SourceLineOut(BaseModel):
    id: str
    description: str
    account_code: str
    quantity: Decimal
    unit_price: Decimal
    vat_rate: Decimal
    amount: Decimal
    vat_amount: Decimal

    model_config = {"from_attributes": True}


class SourceTransactionOut(BaseModel):
    id: str
    module: str
    reference: str
    party_name: str | None
    status: str
    subtotal: Decimal
    vat: Decimal
    total: Decimal
    validation_result: str | None
    created_at: datetime
    lines: list[SourceLineOut] = []

    model_config = {"from_attributes": True}


class PostingJobOut(BaseModel):
    id: str
    source_id: str
    status: str
    retry_count: int
    error_message: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TaxCodeIn(BaseModel):
    code: str
    name: str
    rate: Decimal = Field(default=5, ge=0)
    recoverable: bool = True
    reporting_box: str | None = None


class TaxCodeOut(TaxCodeIn):
    id: str

    model_config = {"from_attributes": True}


class TaxLineOut(BaseModel):
    id: str
    source_id: str | None
    direction: str
    taxable_amount: Decimal
    tax_amount: Decimal
    period: str
    created_at: datetime

    model_config = {"from_attributes": True}


class WarehouseIn(BaseModel):
    name: str
    location: str | None = None


class WarehouseOut(WarehouseIn):
    id: str

    model_config = {"from_attributes": True}


class StockMappingIn(BaseModel):
    sku: str
    name: str
    supplier_name: str | None = None
    taxflow_name: str | None = None
    sales_account_code: str = "3000"
    purchase_account_code: str = "4000"
    inventory_account_code: str = "1200"
    tax_code: str = "VAT5"
    reorder_level: Decimal = Field(default=0, ge=0)
    units_per_outer: Decimal = Field(default=1, gt=0)
    cost: Decimal = Field(default=0, ge=0)
    markup_percent: Decimal = Field(default=0, ge=0)
    tax_rate: Decimal = Field(default=5, ge=0)
    vat_amount: Decimal = Field(default=0, ge=0)
    inc_vat: Decimal = Field(default=0, ge=0)
    price_outer: Decimal = Field(default=0, ge=0)


class StockMappingOut(StockMappingIn):
    id: str

    model_config = {"from_attributes": True}


class ItemUnitIn(BaseModel):
    item_code: str
    unit_code: str
    unit_name: str
    conversion_factor: Decimal = Field(default=1, ge=0)
    is_base_unit: bool = False
    purchase_default: bool = False
    sales_default: bool = False
    status: str = "active"


class ItemUnitOut(ItemUnitIn):
    id: str

    model_config = {"from_attributes": True}


class ItemUnitConversionIn(BaseModel):
    item_code: str
    from_unit_code: str
    to_unit_code: str
    conversion_factor: Decimal = Field(default=1, gt=0)
    status: str = "active"


class ItemUnitConversionOut(ItemUnitConversionIn):
    id: str

    model_config = {"from_attributes": True}


class InventoryValuationLayerOut(BaseModel):
    id: str
    item_code: str
    warehouse_id: str | None
    source_module: str
    source_id: str | None
    quantity_in: Decimal
    quantity_remaining: Decimal
    unit_cost: Decimal
    valuation_method: str
    created_at: datetime

    model_config = {"from_attributes": True}


class StockAdjustmentApprovalIn(BaseModel):
    item_code: str
    warehouse_id: str | None = None
    quantity_delta: Decimal
    reason: str


class StockAdjustmentApprovalOut(StockAdjustmentApprovalIn):
    id: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class EmployeeOut(BaseModel):
    id: str
    employee_no: str
    full_name: str
    department: str
    designation: str
    basic_salary: Decimal
    iban: str | None
    wps_id: str | None
    status: str

    model_config = {"from_attributes": True}


class PayrollGenerate(BaseModel):
    period: str = "2024-06"


class PayrollItemOut(BaseModel):
    id: str
    employee_id: str
    basic: Decimal
    allowances: Decimal
    overtime: Decimal
    deductions: Decimal
    net_pay: Decimal
    wps_status: str

    model_config = {"from_attributes": True}


class PayrollRunOut(BaseModel):
    id: str
    period: str
    status: str
    gross_total: Decimal
    deductions_total: Decimal
    net_total: Decimal
    items: list[PayrollItemOut] = []

    model_config = {"from_attributes": True}


class WpsBatchOut(BaseModel):
    id: str
    payroll_run_id: str
    batch_number: str
    status: str
    sif_content: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AuditLogOut(BaseModel):
    id: str
    module: str
    action: str
    record_id: str | None
    detail: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AppRecordIn(BaseModel):
    record_key: str | None = None
    payload: dict


class AppRecordOut(BaseModel):
    id: str
    record_key: str | None
    payload: dict
    created_at: datetime
    updated_at: datetime


class ExceptionEventIn(BaseModel):
    module: str
    category: str
    severity: str = "medium"
    source_record: str | None = None
    message: str
    status: str = "open"


class ExceptionEventOut(ExceptionEventIn):
    id: str
    created_at: datetime

    model_config = {"from_attributes": True}


class DomainEventIn(BaseModel):
    event_name: str
    source_module: str
    source_id: str | None = None
    payload: dict | None = None
    correlation_id: str | None = None


class DomainEventOut(BaseModel):
    id: str
    event_name: str
    source_module: str
    source_id: str | None
    payload: str | None
    correlation_id: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AIAssistRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


class AITransactionValidationRequest(BaseModel):
    source: SourceTransactionCreate
    supplier_trn: str | None = None
    evidence_present: bool = False
    tax_treatment: str = "standard"


class AIExceptionExplainRequest(BaseModel):
    module: str
    category: str
    severity: str = "medium"
    source_record: str | None = None
    message: str


class AIResponse(BaseModel):
    answer: str
    confidence: int = Field(ge=0, le=100)
    controls: list[str] = []
    suggested_actions: list[str] = []
    context: dict = {}
