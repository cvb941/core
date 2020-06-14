"""The TeamSpeak Server sensor platform."""

import logging
from typing import Any, Dict

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.typing import HomeAssistantType

from . import TeamSpeakServerEntity, TeamSpeakServer
from .const import (
    DOMAIN,
    ICON_PLAYERS_ONLINE,
    NAME_PLAYERS_ONLINE,
    UNIT_PLAYERS_ONLINE,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistantType, config_entry: ConfigEntry, async_add_entities
) -> None:
    """Set up the TeamSpeak Server sensor platform."""
    server = hass.data[DOMAIN][config_entry.unique_id]

    # Create entities list.
    entities = [TeamSpeakServerPlayersOnlineSensor(server)]

    # Add sensor entities.
    async_add_entities(entities, True)


class TeamSpeakServerSensorEntity(TeamSpeakServerEntity):
    """Representation of a TeamSpeak Server sensor base entity."""

    def __init__(
        self,
        server: TeamSpeakServer,
        type_name: str,
        icon: str = None,
        unit: str = None,
        device_class: str = None,
    ) -> None:
        """Initialize sensor base entity."""
        super().__init__(server, type_name, icon, device_class)
        self._state = None
        self._unit = unit

    @property
    def available(self) -> bool:
        """Return sensor availability."""
        return self._server.online

    @property
    def state(self) -> Any:
        """Return sensor state."""
        return self._state

    @property
    def unit_of_measurement(self) -> str:
        """Return sensor measurement unit."""
        return self._unit


class TeamSpeakServerPlayersOnlineSensor(TeamSpeakServerSensorEntity):
    """Representation of a TeamSpeak Server online players sensor."""

    def __init__(self, server: TeamSpeakServer) -> None:
        """Initialize online players sensor."""
        super().__init__(
            server=server,
            type_name=NAME_PLAYERS_ONLINE,
            icon=ICON_PLAYERS_ONLINE,
            unit=UNIT_PLAYERS_ONLINE,
        )

    async def async_update(self) -> None:
        """Update online players state and device state attributes."""
        self._state = self._server.users_online
