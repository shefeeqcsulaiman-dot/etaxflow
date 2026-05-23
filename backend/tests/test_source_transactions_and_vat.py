from decimal import Decimal


def test_source_transaction_validation_approval_tax_and_audit(client, auth_headers):
    created = client.post(
        "/api/v1/source-transactions",
        headers=auth_headers,
        json={
            "module": "sales",
            "reference": "SRC-SALES-001",
            "party_name": "Source Customer",
            "lines": [{"description": "Sale", "account_code": "3000", "quantity": "1", "unit_price": "100.00", "vat_rate": "5"}],
        },
    )
    assert created.status_code == 201
    source = created.json()
    assert source["subtotal"] == "100.00"
    assert source["vat"] == "5.00"
    assert source["total"] == "105.00"

    validated = client.post(f"/api/v1/source-transactions/{source['id']}/validate", headers=auth_headers)
    assert validated.status_code == 200
    assert validated.json()["status"] == "validated"

    approved = client.post(f"/api/v1/source-transactions/{source['id']}/approve", headers=auth_headers)
    assert approved.status_code == 202
    assert approved.json()["status"] == "queued"

    tax_lines = client.get("/api/v1/tax/lines", headers=auth_headers).json()
    matching = [line for line in tax_lines if line["source_id"] == source["id"]]
    assert len(matching) == 1
    assert matching[0]["direction"] == "output"
    assert Decimal(matching[0]["tax_amount"]) == Decimal("5.00")

    audit_rows = client.get("/api/v1/audit/trail", headers=auth_headers).json()
    assert any(row["record_id"] == source["id"] and row["action"] == "approved" for row in audit_rows)


def test_source_transaction_missing_account_rejected(client, auth_headers):
    created = client.post(
        "/api/v1/source-transactions",
        headers=auth_headers,
        json={
            "module": "sales",
            "reference": "SRC-MISSING-001",
            "party_name": "Source Customer",
            "lines": [{"description": "Sale", "account_code": "NOPE", "quantity": "1", "unit_price": "100.00", "vat_rate": "5"}],
        },
    )
    assert created.status_code == 201

    approved = client.post(f"/api/v1/source-transactions/{created.json()['id']}/approve", headers=auth_headers)
    assert approved.status_code == 422
    assert "missing account" in approved.json()["detail"].lower()


def test_vat_return_reads_tax_lines(client, auth_headers):
    source = client.post(
        "/api/v1/source-transactions",
        headers=auth_headers,
        json={
            "module": "purchase",
            "reference": "SRC-PUR-001",
            "party_name": "Supplier",
            "lines": [{"description": "Purchase", "account_code": "4000", "quantity": "1", "unit_price": "200.00", "vat_rate": "5"}],
        },
    ).json()
    client.post(f"/api/v1/source-transactions/{source['id']}/approve", headers=auth_headers)

    vat_return = client.get("/api/v1/tax/vat-return?period=2024-06", headers=auth_headers)
    assert vat_return.status_code == 200
    payload = vat_return.json()
    assert Decimal(payload["input_vat"]) >= Decimal("10.00")
