"""Tests for the client-action service actions (block/rate-limit/snapshot)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
import pytest

from custom_components.omada_open_api.api import OmadaApiError
from custom_components.omada_open_api.const import DOMAIN
from custom_components.omada_open_api.services import async_setup_services
from custom_components.omada_open_api.types import OmadaRuntimeData


def _mock_entry(hass, *, entry_id="entry1", domain=DOMAIN, runtime_data=None):
    entry = MagicMock()
    entry.entry_id = entry_id
    entry.domain = domain
    entry.runtime_data = runtime_data
    hass.config_entries.async_get_entry = MagicMock(
        side_effect=lambda eid: entry if eid == entry_id else None
    )
    return entry


def _runtime_data(api_client, site_ids=("site_001",)):
    return OmadaRuntimeData(
        api_client=api_client,
        coordinators={site_id: MagicMock() for site_id in site_ids},
        client_coordinators=[],
        app_traffic_coordinators=[],
        device_stats_coordinators=[],
        has_write_access=True,
        site_devices={},
    )


async def test_async_setup_services_registers_all_actions(hass) -> None:
    """All five client-action services are registered."""
    await async_setup_services(hass)

    for service in (
        "block_client",
        "unblock_client",
        "set_client_rate_limit",
        "clear_client_rate_limit",
        "get_client_snapshot",
    ):
        assert hass.services.has_service(DOMAIN, service)


async def test_block_client_calls_api_with_resolved_site(hass) -> None:
    """block_client resolves the entry's single site and calls the API."""
    api_client = MagicMock()
    api_client.block_client = AsyncMock()
    _mock_entry(hass, runtime_data=_runtime_data(api_client))
    await async_setup_services(hass)

    await hass.services.async_call(
        DOMAIN,
        "block_client",
        {"config_entry_id": "entry1", "mac": "11-22-33-44-55-AA"},
        blocking=True,
    )

    api_client.block_client.assert_awaited_once_with("site_001", "11-22-33-44-55-AA")


async def test_unblock_client_calls_api(hass) -> None:
    """unblock_client calls the matching API method."""
    api_client = MagicMock()
    api_client.unblock_client = AsyncMock()
    _mock_entry(hass, runtime_data=_runtime_data(api_client))
    await async_setup_services(hass)

    await hass.services.async_call(
        DOMAIN,
        "unblock_client",
        {"config_entry_id": "entry1", "site_id": "site_001", "mac": "AA"},
        blocking=True,
    )

    api_client.unblock_client.assert_awaited_once_with("site_001", "AA")


async def test_set_client_rate_limit_passes_kbps(hass) -> None:
    """set_client_rate_limit forwards down/up kbps to the API."""
    api_client = MagicMock()
    api_client.set_client_rate_limit = AsyncMock()
    _mock_entry(hass, runtime_data=_runtime_data(api_client))
    await async_setup_services(hass)

    await hass.services.async_call(
        DOMAIN,
        "set_client_rate_limit",
        {
            "config_entry_id": "entry1",
            "mac": "AA",
            "down_kbps": 1000,
            "up_kbps": 500,
        },
        blocking=True,
    )

    api_client.set_client_rate_limit.assert_awaited_once_with(
        "site_001", "AA", 1000, 500
    )


async def test_clear_client_rate_limit_calls_api(hass) -> None:
    """clear_client_rate_limit calls the matching API method."""
    api_client = MagicMock()
    api_client.clear_client_rate_limit = AsyncMock()
    _mock_entry(hass, runtime_data=_runtime_data(api_client))
    await async_setup_services(hass)

    await hass.services.async_call(
        DOMAIN,
        "clear_client_rate_limit",
        {"config_entry_id": "entry1", "mac": "AA"},
        blocking=True,
    )

    api_client.clear_client_rate_limit.assert_awaited_once_with("site_001", "AA")


async def test_get_client_snapshot_returns_all_clients_by_mac(hass) -> None:
    """get_client_snapshot returns every client regardless of selection, keyed by mac."""
    api_client = MagicMock()
    api_client.get_clients = AsyncMock(
        return_value={
            "data": [
                {"mac": "AA", "active": True, "trafficDown": 10, "trafficUp": 5},
                {"mac": "BB", "active": False, "trafficDown": 0, "trafficUp": 0},
            ],
            "totalRows": 2,
        }
    )
    _mock_entry(hass, runtime_data=_runtime_data(api_client))
    await async_setup_services(hass)

    response = await hass.services.async_call(
        DOMAIN,
        "get_client_snapshot",
        {"config_entry_id": "entry1"},
        blocking=True,
        return_response=True,
    )

    api_client.get_clients.assert_awaited_once_with(
        "site_001", page=1, page_size=1000, scope=0
    )
    assert set(response["clients"]) == {"AA", "BB"}
    assert response["clients"]["AA"]["traffic_down"] == 10
    assert response["clients"]["AA"]["active"] is True


async def test_get_client_snapshot_paginates(hass) -> None:
    """get_client_snapshot follows totalRows across more than one page."""
    api_client = MagicMock()
    api_client.get_clients = AsyncMock(
        side_effect=[
            {"data": [{"mac": "AA"}], "totalRows": 2},
            {"data": [{"mac": "BB"}], "totalRows": 2},
        ]
    )
    _mock_entry(hass, runtime_data=_runtime_data(api_client))
    await async_setup_services(hass)

    response = await hass.services.async_call(
        DOMAIN,
        "get_client_snapshot",
        {"config_entry_id": "entry1"},
        blocking=True,
        return_response=True,
    )

    assert api_client.get_clients.await_count == 2
    assert set(response["clients"]) == {"AA", "BB"}


async def test_unknown_config_entry_raises_validation_error(hass) -> None:
    """An unknown config_entry_id raises a translated validation error."""
    hass.config_entries.async_get_entry = MagicMock(return_value=None)
    await async_setup_services(hass)

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "block_client",
            {"config_entry_id": "nope", "mac": "AA"},
            blocking=True,
        )


async def test_ambiguous_site_without_site_id_raises(hass) -> None:
    """Omitting site_id on a multi-site entry raises a translated validation error."""
    api_client = MagicMock()
    _mock_entry(
        hass, runtime_data=_runtime_data(api_client, site_ids=("site_001", "site_002"))
    )
    await async_setup_services(hass)

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "block_client",
            {"config_entry_id": "entry1", "mac": "AA"},
            blocking=True,
        )


async def test_api_error_is_wrapped_as_home_assistant_error(hass) -> None:
    """An OmadaApiError from the client action surfaces as HomeAssistantError."""
    api_client = MagicMock()
    api_client.block_client = AsyncMock(side_effect=OmadaApiError("boom"))
    _mock_entry(hass, runtime_data=_runtime_data(api_client))
    await async_setup_services(hass)

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN,
            "block_client",
            {"config_entry_id": "entry1", "mac": "AA"},
            blocking=True,
        )
