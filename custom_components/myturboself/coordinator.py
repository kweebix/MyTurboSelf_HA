"""Data coordinator for MyTurboSelf."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    AccountSnapshot,
    MyTurboSelfApiError,
    MyTurboSelfAuthError,
    TurboSelfPortalClient,
)
from .const import DOMAIN, SCAN_INTERVAL

LOGGER = logging.getLogger(__name__)


class MyTurboSelfDataUpdateCoordinator(DataUpdateCoordinator[AccountSnapshot]):
    """Fetch and normalize MyTurboSelf account data."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the coordinator."""

        super().__init__(
            hass,
            LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
            always_update=False,
        )
        self._client = TurboSelfPortalClient(
            config_entry.data[CONF_USERNAME],
            config_entry.data[CONF_PASSWORD],
        )

    async def _async_update_data(self) -> AccountSnapshot:
        """Fetch new data from TurboSelf."""

        try:
            return await self.hass.async_add_executor_job(self._client.fetch_snapshot)
        except MyTurboSelfAuthError as err:
            raise ConfigEntryAuthFailed("TurboSelf authentication failed") from err
        except MyTurboSelfApiError as err:
            raise UpdateFailed(str(err)) from err
