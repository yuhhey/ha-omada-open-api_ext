"""Client-action service calls: block/unblock, rate limiting, and a raw snapshot.

These act on `runtime_data.api_client` directly rather than on an entity, so
they also reach clients the user hasn't selected for entity creation
(`CONF_SELECTED_CLIENTS`) — needed by callers that must see or control every
client Omada knows about, not just the ones chosen for the dashboard.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.core import SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
import voluptuous as vol

from .api import OmadaApiError
from .clients import process_client
from .const import DOMAIN
from .types import OmadaRuntimeData

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse

_LOGGER = logging.getLogger(__name__)

SERVICE_BLOCK_CLIENT = "block_client"
SERVICE_UNBLOCK_CLIENT = "unblock_client"
SERVICE_SET_CLIENT_RATE_LIMIT = "set_client_rate_limit"
SERVICE_CLEAR_CLIENT_RATE_LIMIT = "clear_client_rate_limit"
SERVICE_GET_CLIENT_SNAPSHOT = "get_client_snapshot"

ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_SITE_ID = "site_id"
ATTR_MAC = "mac"
ATTR_DOWN_KBPS = "down_kbps"
ATTR_UP_KBPS = "up_kbps"

_SNAPSHOT_PAGE_SIZE = 1000

_CLIENT_TARGET_FIELDS = {
    vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string,
    vol.Optional(ATTR_SITE_ID): cv.string,
    vol.Required(ATTR_MAC): cv.string,
}
_SITE_TARGET_FIELDS = {
    vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string,
    vol.Optional(ATTR_SITE_ID): cv.string,
}

_BLOCK_CLIENT_SCHEMA = vol.Schema(_CLIENT_TARGET_FIELDS)
_UNBLOCK_CLIENT_SCHEMA = vol.Schema(_CLIENT_TARGET_FIELDS)
_SET_CLIENT_RATE_LIMIT_SCHEMA = vol.Schema(
    {
        **_CLIENT_TARGET_FIELDS,
        vol.Required(ATTR_DOWN_KBPS): vol.Coerce(int),
        vol.Required(ATTR_UP_KBPS): vol.Coerce(int),
    }
)
_CLEAR_CLIENT_RATE_LIMIT_SCHEMA = vol.Schema(_CLIENT_TARGET_FIELDS)
_GET_CLIENT_SNAPSHOT_SCHEMA = vol.Schema(_SITE_TARGET_FIELDS)


def _resolve_runtime_data(
    hass: HomeAssistant, config_entry_id: str
) -> OmadaRuntimeData:
    """Return the runtime data for a config entry, or raise a translated error."""
    entry = hass.config_entries.async_get_entry(config_entry_id)
    if entry is None or entry.domain != DOMAIN:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="config_entry_not_found",
            translation_placeholders={"config_entry_id": config_entry_id},
        )
    runtime_data = getattr(entry, "runtime_data", None)
    if not isinstance(runtime_data, OmadaRuntimeData):
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="no_runtime_data",
            translation_placeholders={"config_entry_id": config_entry_id},
        )
    return runtime_data


def _resolve_site_id(
    runtime_data: OmadaRuntimeData, site_id: str | None, config_entry_id: str
) -> str:
    """Return the site to act on, defaulting to the entry's only site."""
    if site_id is not None:
        return site_id
    site_ids = list(runtime_data.coordinators)
    if len(site_ids) == 1:
        return site_ids[0]
    raise ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key="ambiguous_site",
        translation_placeholders={"config_entry_id": config_entry_id},
    )


async def _call_client_action(
    hass: HomeAssistant, call: ServiceCall, action_name: str, *extra_args: Any
) -> None:
    """Resolve the target client and call ``action_name`` on its api_client."""
    config_entry_id = call.data[ATTR_CONFIG_ENTRY_ID]
    runtime_data = _resolve_runtime_data(hass, config_entry_id)
    site_id = _resolve_site_id(
        runtime_data, call.data.get(ATTR_SITE_ID), config_entry_id
    )
    mac = call.data[ATTR_MAC]
    action = getattr(runtime_data.api_client, action_name)
    try:
        await action(site_id, mac, *extra_args)
    except OmadaApiError as err:
        raise HomeAssistantError(f"Failed to {action_name} {mac}: {err}") from err


async def _async_fetch_all_clients(
    runtime_data: OmadaRuntimeData, site_id: str
) -> list[dict[str, Any]]:
    """Fetch every client (scope=0) for a site, following totalRows across pages."""
    rows: list[dict[str, Any]] = []
    page = 1
    while True:
        result = await runtime_data.api_client.get_clients(
            site_id, page=page, page_size=_SNAPSHOT_PAGE_SIZE, scope=0
        )
        data = result.get("data") or []
        rows.extend(data)
        total_rows = result.get("totalRows")
        if not data or not isinstance(total_rows, int) or len(rows) >= total_rows:
            return rows
        page += 1


async def _handle_block_client(hass: HomeAssistant, call: ServiceCall) -> None:
    await _call_client_action(hass, call, "block_client")


async def _handle_unblock_client(hass: HomeAssistant, call: ServiceCall) -> None:
    await _call_client_action(hass, call, "unblock_client")


async def _handle_set_client_rate_limit(hass: HomeAssistant, call: ServiceCall) -> None:
    await _call_client_action(
        hass,
        call,
        "set_client_rate_limit",
        call.data[ATTR_DOWN_KBPS],
        call.data[ATTR_UP_KBPS],
    )


async def _handle_clear_client_rate_limit(
    hass: HomeAssistant, call: ServiceCall
) -> None:
    await _call_client_action(hass, call, "clear_client_rate_limit")


async def _handle_get_client_snapshot(
    hass: HomeAssistant, call: ServiceCall
) -> ServiceResponse:
    config_entry_id = call.data[ATTR_CONFIG_ENTRY_ID]
    runtime_data = _resolve_runtime_data(hass, config_entry_id)
    site_id = _resolve_site_id(
        runtime_data, call.data.get(ATTR_SITE_ID), config_entry_id
    )
    try:
        raw_clients = await _async_fetch_all_clients(runtime_data, site_id)
    except OmadaApiError as err:
        raise HomeAssistantError(f"Failed to fetch client snapshot: {err}") from err
    clients: dict[str, Any] = {
        str(client["mac"]): process_client(client)
        for client in raw_clients
        if client.get("mac")
    }
    return {"clients": clients}


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register the client-action services (idempotent, domain-global)."""

    async def block_client(call: ServiceCall) -> None:
        await _handle_block_client(hass, call)

    async def unblock_client(call: ServiceCall) -> None:
        await _handle_unblock_client(hass, call)

    async def set_client_rate_limit(call: ServiceCall) -> None:
        await _handle_set_client_rate_limit(hass, call)

    async def clear_client_rate_limit(call: ServiceCall) -> None:
        await _handle_clear_client_rate_limit(hass, call)

    async def get_client_snapshot(call: ServiceCall) -> ServiceResponse:
        return await _handle_get_client_snapshot(hass, call)

    hass.services.async_register(
        DOMAIN, SERVICE_BLOCK_CLIENT, block_client, schema=_BLOCK_CLIENT_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_UNBLOCK_CLIENT, unblock_client, schema=_UNBLOCK_CLIENT_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_CLIENT_RATE_LIMIT,
        set_client_rate_limit,
        schema=_SET_CLIENT_RATE_LIMIT_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CLEAR_CLIENT_RATE_LIMIT,
        clear_client_rate_limit,
        schema=_CLEAR_CLIENT_RATE_LIMIT_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_CLIENT_SNAPSHOT,
        get_client_snapshot,
        schema=_GET_CLIENT_SNAPSHOT_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
