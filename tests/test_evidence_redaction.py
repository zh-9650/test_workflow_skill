from __future__ import annotations

import pytest

from conftest import load_script


@pytest.fixture(scope="module")
def execution_control():
    return load_script(
        "test-execution-runtime/scripts/execution_control.py",
        "evidence_redaction_contract",
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"request": {"headers": {"X-Session": "raw-session-secret"}}},
        {"response": {"customer_email": "alice@example.com"}},
        {"response": {"national_id": "123456789"}},
        {"request": {"headers": {"authorization": "Bearer abcdefghijklmnop"}}},
        {"request": {"headers": {"auth": "raw-auth-value"}}},
        {"request": {"credential": "raw-credential-value"}},
        {"request": {"private_key": "raw-private-key-value"}},
        {"response": {"message": "contact alice@example.com"}},
        {"request": {"url": "https://example.test/?access_token=abcdefghijklmnop"}},
        {"request": {"url": "https://example.test/?api_key=abcdefghijklmnop"}},
        {"response": {"message": "-----BEGIN PRIVATE KEY-----\\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASC\\n-----END PRIVATE KEY-----"}},
    ],
)
def test_evidence_contract_rejects_common_unredacted_sensitive_values(
    execution_control, payload
):
    with pytest.raises(AssertionError):
        execution_control._assert_secret_keys_redacted(payload, "evidence.json")


def test_evidence_contract_accepts_redacted_fields(execution_control):
    execution_control._assert_secret_keys_redacted(
        {
            "request": {"headers": {"X-Session": "[REDACTED]"}},
            "response": {"customer_email": "[REDACTED]", "status": "ready"},
        },
        "evidence.json",
    )


def test_evidence_contract_allows_non_sensitive_status_metadata(execution_control):
    execution_control._assert_secret_keys_redacted(
        {
            "email_verified": True,
            "email_delivery_status": "sent",
            "session_status": "closed",
            "token_count": 3,
            "token_type": "Bearer",
            "email_type": "work",
        },
        "evidence.json",
    )


def test_status_metadata_still_rejects_an_embedded_personal_value(execution_control):
    with pytest.raises(AssertionError):
        execution_control._assert_secret_keys_redacted(
            {"email_delivery_status": "sent to alice@example.com"}, "evidence.json"
        )


def test_secret_looking_text_is_not_allowed_in_count_metadata(execution_control):
    with pytest.raises(AssertionError):
        execution_control._assert_secret_keys_redacted(
            {"token_count": "raw-secret-token-value"}, "evidence.json"
        )
