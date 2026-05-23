def _accounts(client, headers):
    return {row["code"]: row for row in client.get("/api/v1/accounts", headers=headers).json()}


def test_unbalanced_journal_is_rejected(client, auth_headers):
    accounts = _accounts(client, auth_headers)

    response = client.post(
        "/api/v1/journal",
        headers=auth_headers,
        json={
            "entry_number": "JRN-BAD-001",
            "description": "Bad journal",
            "lines": [
                {"account_id": accounts["1100"]["id"], "debit": "100.00", "credit": "0"},
                {"account_id": accounts["3000"]["id"], "debit": "0", "credit": "90.00"},
            ],
        },
    )

    assert response.status_code == 422
    assert "balance" in response.json()["detail"].lower()


def test_balanced_journal_is_accepted(client, auth_headers):
    accounts = _accounts(client, auth_headers)

    response = client.post(
        "/api/v1/journal",
        headers=auth_headers,
        json={
            "entry_number": "JRN-OK-001",
            "description": "Balanced journal",
            "lines": [
                {"account_id": accounts["1100"]["id"], "debit": "105.00", "credit": "0"},
                {"account_id": accounts["3000"]["id"], "debit": "0", "credit": "100.00"},
                {"account_id": accounts["2200"]["id"], "debit": "0", "credit": "5.00"},
            ],
        },
    )

    assert response.status_code == 201
    lines = response.json()["lines"]
    assert sum(float(line["debit"]) for line in lines) == sum(float(line["credit"]) for line in lines)


def test_journal_rejects_other_tenant_account(client, auth_headers, second_tenant_headers):
    other_accounts = _accounts(client, second_tenant_headers)

    response = client.post(
        "/api/v1/journal",
        headers=auth_headers,
        json={
            "entry_number": "JRN-XTENANT-001",
            "description": "Cross tenant account",
            "lines": [
                {"account_id": other_accounts["1100"]["id"], "debit": "100.00", "credit": "0"},
                {"account_id": other_accounts["3000"]["id"], "debit": "0", "credit": "100.00"},
            ],
        },
    )

    assert response.status_code == 422
    assert "company" in response.json()["detail"].lower()
