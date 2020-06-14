"""The Teamspeak Server integration."""
import asyncio
from datetime import datetime, timedelta
import logging
from typing import Any, Dict

import ts3
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PORT,
    CONF_USERNAME,
    CONF_PASSWORD,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.typing import ConfigType, HomeAssistantType

from .const import DOMAIN, MANUFACTURER, SCAN_INTERVAL, SIGNAL_NAME_PREFIX

CONFIG_SCHEMA = vol.Schema({DOMAIN: vol.Schema({})}, extra=vol.ALLOW_EXTRA)

PLATFORMS = ["sensor"]

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the Teamspeak Server component."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up Teamspeak Server from a config entry."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    _LOGGER.debug(
        "Creating server instance for '%s' (%s)",
        entry.data[CONF_NAME],
        entry.data[CONF_HOST],
    )
    server = TeamSpeakServer(hass, entry.unique_id, entry.data)
    domain_data[entry.unique_id] = server
    await server.async_update()
    server.start_periodic_update()

    # Set up platforms.
    for component in PLATFORMS:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(entry, component)
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    unload_ok = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(entry, component)
                for component in PLATFORMS
            ]
        )
    )
    if unload_ok:
        hass.data[DOMAIN].pop(entry.unique_id)

    return unload_ok


class TeamSpeakServer:
    """Representation of a TeamSpeak server."""

    # Private constants
    _MAX_RETRIES_STATUS = 3

    def __init__(
        self, hass: HomeAssistantType, unique_id: str, config_data: ConfigType
    ) -> None:
        """Initialize server instance."""
        self._hass = hass

        # Server data
        self.unique_id = unique_id
        self.name = config_data[CONF_NAME]
        self.host = config_data[CONF_HOST]
        self.port = "10011"  # config_data[CONF_PORT]
        self.online = False
        self._last_status_request_failed = False
        self.srv_record_checked = False

        # 3rd party library instance
        self._ts_connection = ts3.query.TS3ServerConnection(
            f"telnet://{config_data[CONF_USERNAME]}:{config_data[CONF_PASSWORD]}@{self.host}:{self.port}"
        )

        # Data provided by 3rd party library
        self.users_online = None

        # Dispatcher signal name
        self.signal_name = f"{SIGNAL_NAME_PREFIX}_{self.unique_id}"

        # Callback for stopping periodic update.
        self._stop_periodic_update = None

    def start_periodic_update(self) -> None:
        """Start periodic execution of update method."""
        self._stop_periodic_update = async_track_time_interval(
            self._hass, self.async_update, timedelta(seconds=SCAN_INTERVAL)
        )

    def stop_periodic_update(self) -> None:
        """Stop periodic execution of update method."""
        self._stop_periodic_update()

    async def async_update(self, now: datetime = None) -> None:
        """Get server data from 3rd party library and update properties."""
        # Check connection status.
        server_online_old = self.online
        server_online = self._ts_connection.is_connected()
        self.online = server_online

        # Inform user once about connection state changes if necessary.
        if server_online_old and not server_online:
            _LOGGER.warning("Connection to '%s:%s' lost", self.host, self.port)
        elif not server_online_old and server_online:
            # Set the sid
            self._ts_connection.exec_("use", sid=1)  # TODO get sid from config

            _LOGGER.info("Connection to '%s:%s' (re-)established", self.host, self.port)

        # Update the server properties if server is online.
        if server_online:
            await self._async_status_request()

        # Notify sensors about new data.
        async_dispatcher_send(self._hass, self.signal_name)

    async def _async_status_request(self) -> None:
        """Request server status and update properties."""
        try:
            # Do not count ourselves.
            self.users_online = len(self._ts_connection.exec_("clientlist").parsed) - 1

            # Inform user once about successful update if necessary.
            if self._last_status_request_failed:
                _LOGGER.info(
                    "Updating the properties of '%s:%s' succeeded again",
                    self.host,
                    self.port,
                )
            self._last_status_request_failed = False
        except OSError as error:
            # No answer to request, set all properties to unknown.
            self.users_online = None

            # Inform user once about failed update if necessary.
            if not self._last_status_request_failed:
                _LOGGER.warning(
                    "Updating the properties of '%s:%s' failed - OSError: %s",
                    self.host,
                    self.port,
                    error,
                )
            self._last_status_request_failed = True


class TeamSpeakServerEntity(Entity):
    """Representation of a Minecraft Server base entity."""

    def __init__(
        self, server: TeamSpeakServer, type_name: str, icon: str, device_class: str
    ) -> None:
        """Initialize base entity."""
        self._server = server
        self._name = f"{server.name} {type_name}"
        self._icon = icon
        self._unique_id = f"{self._server.unique_id}-{type_name}"
        self._device_info = {
            "identifiers": {(DOMAIN, self._server.unique_id)},
            "name": self._server.name,
            "manufacturer": MANUFACTURER,
            # "model": f"Minecraft Server ({self._server.version})",
            # "sw_version": self._server.protocol_version,
        }
        self._device_class = device_class
        self._device_state_attributes = None
        self._disconnect_dispatcher = None

    @property
    def name(self) -> str:
        """Return name."""
        return self._name

    @property
    def unique_id(self) -> str:
        """Return unique ID."""
        return self._unique_id

    @property
    def device_info(self) -> Dict[str, Any]:
        """Return device information."""
        return self._device_info

    @property
    def device_class(self) -> str:
        """Return device class."""
        return self._device_class

    @property
    def icon(self) -> str:
        """Return icon."""
        return self._icon

    @property
    def should_poll(self) -> bool:
        """Disable polling."""
        return False

    async def async_update(self) -> None:
        """Fetch data from the server."""
        raise NotImplementedError()

    async def async_added_to_hass(self) -> None:
        """Connect dispatcher to signal from server."""
        self._disconnect_dispatcher = async_dispatcher_connect(
            self.hass, self._server.signal_name, self._update_callback
        )

    async def async_will_remove_from_hass(self) -> None:
        """Disconnect dispatcher before removal."""
        self._disconnect_dispatcher()

    @callback
    def _update_callback(self) -> None:
        """Triggers update of properties after receiving signal from server."""
        self.async_schedule_update_ha_state(force_refresh=True)
