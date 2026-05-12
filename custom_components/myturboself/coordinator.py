"""Data coordinator for MyTurboSelf."""

from __future__ import annotations

from datetime import timedelta
import logging

import holidays
from vacances_scolaires_france import SchoolHolidayDates

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    AccountSnapshot,
    MyTurboSelfApiError,
    MyTurboSelfAuthError,
    TurboSelfPortalClient,
)
from .const import (
    CONF_SCHOOL_ZONE,
    CONF_SKIP_HOLIDAYS,
    CONF_SKIP_VACATION,
    DOMAIN,
    MEAL_DAY_OPTIONS,
    SCAN_INTERVAL,
)

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
        """Fetch new data from TurboSelf and compute next update interval."""

        try:
            snapshot = await self._client.async_fetch_snapshot()
        except MyTurboSelfAuthError as err:
            raise ConfigEntryAuthFailed("TurboSelf authentication failed") from err
        except MyTurboSelfApiError as err:
            raise UpdateFailed(str(err)) from err

        # Dynamic update interval optimization
        self.update_interval = self._calculate_next_interval()
        LOGGER.debug("Next update interval: %s", self.update_interval)

        return snapshot

    def _calculate_next_interval(self) -> timedelta:
        """Calculate the next update interval based on schedule and time."""

        now = dt_util.now()
        current_date = now.date()
        weekday = now.weekday()
        hour = now.hour

        # Default intervals
        active_interval = SCAN_INTERVAL  # 15 minutes
        idle_interval = timedelta(hours=4)

        # Check if today is a meal day
        schedule_key = MEAL_DAY_OPTIONS[weekday]
        meals = self.config_entry.options.get(schedule_key, [])
        
        # Handle legacy int format
        has_meals_today = (isinstance(meals, int) and meals > 0) or (isinstance(meals, list) and len(meals) > 0)

        if not has_meals_today:
            return idle_interval

        # Check holidays
        if self.config_entry.options.get(CONF_SKIP_HOLIDAYS, True):
            if current_date in holidays.France():
                return idle_interval

        # Check vacations
        if self.config_entry.options.get(CONF_SKIP_VACATION, True):
            zone = self.config_entry.options.get(CONF_SCHOOL_ZONE, "C")
            if SchoolHolidayDates().is_holiday_for_zone(current_date, zone):
                return idle_interval

        # Active time: 6:00 to 23:00 on meal days to cover breakfast and dinner
        if 6 <= hour < 23:
            return active_interval

        return idle_interval
