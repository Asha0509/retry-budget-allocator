"""Unit tests for the live Razorpay client's opt-in gate (Part B2).

Must never make a real network call in this suite - these tests only check
that every public function refuses to run without LIVE_RAZORPAY=1, which is
the actual property that keeps CI and the batch study offline.
"""

import pytest

import api.razorpay_client as client_module
from api.razorpay_client import (
    LiveRazorpayDisabled,
    charge_token,
    create_customer,
    register_mandate,
)


@pytest.fixture(autouse=True)
def _ensure_live_disabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("LIVE_RAZORPAY", raising=False)


def test_create_customer_refuses_without_live_flag() -> None:
    with pytest.raises(LiveRazorpayDisabled, match="LIVE_RAZORPAY"):
        create_customer("x", "x@example.com", "9000000000")


def test_register_mandate_refuses_without_live_flag() -> None:
    with pytest.raises(LiveRazorpayDisabled, match="LIVE_RAZORPAY"):
        register_mandate("cust_x", 100, 500000, 9999999999)


def test_charge_token_refuses_without_live_flag() -> None:
    with pytest.raises(LiveRazorpayDisabled, match="LIVE_RAZORPAY"):
        charge_token("token_x", "order_x", "cust_x", 100)


def test_client_refuses_when_key_id_is_not_test_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIVE_RAZORPAY", "1")
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_live_shouldnotrun")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "whatever")
    with pytest.raises(LiveRazorpayDisabled, match="test-mode"):
        client_module._client()


def test_client_refuses_when_credentials_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIVE_RAZORPAY", "1")
    monkeypatch.delenv("RAZORPAY_KEY_ID", raising=False)
    monkeypatch.delenv("RAZORPAY_KEY_SECRET", raising=False)
    with pytest.raises(LiveRazorpayDisabled, match="not set"):
        client_module._client()
