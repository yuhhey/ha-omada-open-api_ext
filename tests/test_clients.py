"""Tests for client record processing."""

from __future__ import annotations

from custom_components.omada_open_api.clients import process_client


def test_process_client_rate_limited_true_when_enabled_and_a_direction_set() -> None:
    """rate_limited is True when the rate limit is enabled with a direction on."""
    client = {
        "mac": "11-22-33-44-55-AA",
        "rateLimit": {"enable": True, "downEnable": True, "upEnable": False},
    }

    assert process_client(client)["rate_limited"] is True


def test_process_client_rate_limited_false_when_disabled() -> None:
    """rate_limited is False when the rate limit itself is disabled."""
    client = {
        "mac": "11-22-33-44-55-AA",
        "rateLimit": {"enable": False, "downEnable": True, "upEnable": True},
    }

    assert process_client(client)["rate_limited"] is False


def test_process_client_rate_limited_false_when_no_direction_set() -> None:
    """rate_limited is False when enabled but neither direction is on."""
    client = {
        "mac": "11-22-33-44-55-AA",
        "rateLimit": {"enable": True, "downEnable": False, "upEnable": False},
    }

    assert process_client(client)["rate_limited"] is False


def test_process_client_rate_limited_false_when_rate_limit_missing() -> None:
    """rate_limited is False when the controller omits rateLimit entirely."""
    client = {"mac": "11-22-33-44-55-AA"}

    assert process_client(client)["rate_limited"] is False
