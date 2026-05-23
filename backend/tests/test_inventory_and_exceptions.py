from decimal import Decimal

from app.models import InventoryValuationLayer, StockMovement, StockProductMapping


def test_inventory_unit_conversion_records(client, auth_headers):
    unit_box = client.post(
        "/api/v1/item-units",
        headers=auth_headers,
        json={
            "item_code": "COKE",
            "unit_code": "BOX",
            "unit_name": "Box",
            "conversion_factor": "12",
            "is_base_unit": False,
            "purchase_default": True,
            "sales_default": False,
        },
    )
    unit_pcs = client.post(
        "/api/v1/item-units",
        headers=auth_headers,
        json={
            "item_code": "COKE",
            "unit_code": "PCS",
            "unit_name": "Pieces",
            "conversion_factor": "1",
            "is_base_unit": True,
            "purchase_default": False,
            "sales_default": True,
        },
    )
    conversion = client.post(
        "/api/v1/item-unit-conversions",
        headers=auth_headers,
        json={"item_code": "COKE", "from_unit_code": "BOX", "to_unit_code": "PCS", "conversion_factor": "12"},
    )

    assert unit_box.status_code == 201
    assert unit_pcs.status_code == 201
    assert conversion.status_code == 201
    assert Decimal(conversion.json()["conversion_factor"]) == Decimal("12.0000")


def test_purchase_record_syncs_line_quantity_to_stock_tables(client, auth_headers, db):
    payload = {
        "collection": "purchaseRecords",
        "record": {
            "ref": "PUR-QTY-008",
            "supplier": "QA Supplier",
            "status": "Pending Payment",
            "net_amount": 1480,
            "tax_amount": 74,
            "total": 1554,
            "lines": [
                {
                    "sku": "PAPER-A4",
                    "product": "A4 Paper Box",
                    "unit_of_measure": "BOX",
                    "quantity": 8,
                    "unit_cost": 185,
                    "unit_cost_before_tax": 185,
                    "line_total": 1480,
                }
            ],
        },
    }

    response = client.post("/api/v1/app-data?action=save", headers=auth_headers, json=payload)

    assert response.status_code == 200
    mapping = db.query(StockProductMapping).filter(StockProductMapping.sku == "PAPER-A4").one()
    movement = db.query(StockMovement).filter(StockMovement.mapping_id == mapping.id).one()
    layer = db.query(InventoryValuationLayer).filter(InventoryValuationLayer.item_code == "PAPER-A4").one()
    assert movement.reference == "PUR-QTY-008"
    assert movement.quantity == Decimal("8.00")
    assert layer.quantity_in == Decimal("8.00")
    assert layer.quantity_remaining == Decimal("8.00")

    stock_levels = client.get("/api/v1/inventory/stock-levels", headers=auth_headers)
    assert stock_levels.status_code == 200
    stock_level = next(row for row in stock_levels.json() if row["code"] == "PAPER-A4")
    assert Decimal(str(stock_level["current_stock"])) == Decimal("8.00")


def test_exception_center_accepts_manual_exception(client, auth_headers):
    created = client.post(
        "/api/v1/exceptions",
        headers=auth_headers,
        json={
            "module": "Accounting",
            "category": "Failed posting",
            "severity": "high",
            "source_record": "QA-JOB-001",
            "message": "Posting failed during QA simulation",
        },
    )
    assert created.status_code == 201

    listed = client.get("/api/v1/exceptions", headers=auth_headers)
    assert listed.status_code == 200
    payload = listed.json()
    assert payload["summary"]["high"] >= 1
    assert any(row["source_record"] == "QA-JOB-001" for row in payload["exceptions"])
