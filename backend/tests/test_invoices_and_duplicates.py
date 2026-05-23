def test_invoice_vat_calculation(client, auth_headers):
    response = client.post(
        "/api/v1/invoices",
        headers=auth_headers,
        json={
            "customer_name": "VAT Customer",
            "invoice_number": "VAT-INV-001",
            "lines": [{"description": "Service", "quantity": "2", "unit_price": "100.00", "vat_rate": "5"}],
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["subtotal"] == "200.00"
    assert payload["vat"] == "10.00"
    assert payload["total"] == "210.00"


def test_duplicate_invoice_number_rejected_per_tenant(client, auth_headers):
    body = {
        "customer_name": "Duplicate Customer",
        "invoice_number": "DUP-INV-001",
        "lines": [{"description": "Service", "quantity": "1", "unit_price": "50.00", "vat_rate": "5"}],
    }
    first = client.post("/api/v1/invoices", headers=auth_headers, json=body)
    second = client.post("/api/v1/invoices", headers=auth_headers, json=body)

    assert first.status_code == 201
    assert second.status_code == 409
    assert "already exists" in second.json()["detail"]
