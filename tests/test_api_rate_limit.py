"""Tests for client rate-limit API access."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from custom_components.omada_open_api.api import OmadaApiClient


@pytest.mark.asyncio
async def test_set_client_rate_limit_sends_custom_rate_limit_payload() -> None:
    """Setting a rate limit PATCHes mode 0 with both directions enabled."""
    client = OmadaApiClient.__new__(OmadaApiClient)
    client._api_url = "https://controller.local"
    client._omada_id = "controller-id"
    client._authenticated_request = AsyncMock(return_value={"errorCode": 0})

    await client.set_client_rate_limit("site-id", "11-22-33-44-55-AA", 1000, 500)

    client._authenticated_request.assert_awaited_once_with(
        "patch",
        "https://controller.local/openapi/v1/controller-id/sites/site-id/"
        "clients/11-22-33-44-55-AA/ratelimit",
        json_data={
            "mode": 0,
            "customRateLimit": {
                "downEnable": True,
                "downUnit": 1,
                "downLimit": 1000,
                "upEnable": True,
                "upUnit": 1,
                "upLimit": 500,
            },
        },
    )


@pytest.mark.asyncio
async def test_clear_client_rate_limit_disables_both_directions() -> None:
    """Clearing a rate limit PATCHes mode 0 with both directions disabled."""
    client = OmadaApiClient.__new__(OmadaApiClient)
    client._api_url = "https://controller.local"
    client._omada_id = "controller-id"
    client._authenticated_request = AsyncMock(return_value={"errorCode": 0})

    await client.clear_client_rate_limit("site-id", "11-22-33-44-55-AA")

    client._authenticated_request.assert_awaited_once_with(
        "patch",
        "https://controller.local/openapi/v1/controller-id/sites/site-id/"
        "clients/11-22-33-44-55-AA/ratelimit",
        json_data={
            "mode": 0,
            "customRateLimit": {
                "downEnable": False,
                "downUnit": 2,
                "downLimit": 1024,
                "upEnable": False,
                "upUnit": 2,
                "upLimit": 1024,
            },
        },
    )
