"""Sensor platform for MyTurboSelf."""

from __future__ import annotations

from datetime import date, timedelta
import math
from typing import Any

import holidays
from vacances_scolaires_france import SchoolHolidayDates

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CURRENCY_EURO
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .api import AccountSnapshot
from .const import (
    ATTR_CONFIGURED_MEALS_PER_WEEK,
    ATTR_DATA_SOURCE,
    ATTR_EFFECTIVE_MEAL_PRICE,
    ATTR_LAST_EVENT,
    ATTR_REMOTE_MEALS_LEFT,
    ATTR_SCHEDULE,
    ATTR_USER_DATA,
    CONF_MANUAL_MEAL_PRICE,
    CONF_SCHOOL_ZONE,
    CONF_SKIP_HOLIDAYS,
    CONF_SKIP_VACATION,
    DEFAULT_MANUAL_MEAL_PRICE,
    DEFAULT_WEEKDAY_MEALS,
    DOMAIN,
    MEAL_DAY_OPTIONS,
    MEAL_TYPES,
    WEEKDAY_LABELS,
)
from .coordinator import MyTurboSelfDataUpdateCoordinator
from .entity import MyTurboSelfEntity


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up MyTurboSelf sensors."""

    coordinator: MyTurboSelfDataUpdateCoordinator = hass.data[DOMAIN][
        config_entry.entry_id
    ]

    async_add_entities(
        [
            MyTurboSelfBalanceSensor(coordinator, config_entry),
            MyTurboSelfUnitPriceSensor(coordinator, config_entry),
            MyTurboSelfMealsLeftSensor(coordinator, config_entry),
            MyTurboSelfServiceDaysLeftSensor(coordinator, config_entry),
            MyTurboSelfEstimatedEmptyDateSensor(coordinator, config_entry),
        ]
    )


def _account_attributes(snapshot: AccountSnapshot) -> dict[str, Any]:
    """Build shared account attributes."""

    attributes: dict[str, Any] = {}

    if snapshot.user_data:
        attributes[ATTR_USER_DATA] = dict(sorted(snapshot.user_data.items()))

    if snapshot.latest_event:
        attributes[ATTR_LAST_EVENT] = {
            "name": snapshot.latest_event.name,
            "value": snapshot.latest_event.value,
            "date": snapshot.latest_event.date.isoformat(),
        }

    attributes[ATTR_DATA_SOURCE] = snapshot.source

    return attributes


def _manual_meal_price(config_entry: ConfigEntry) -> float | None:
    """Return the configured manual meal price when enabled."""

    value = float(
        config_entry.options.get(
            CONF_MANUAL_MEAL_PRICE,
            DEFAULT_MANUAL_MEAL_PRICE,
        )
    )
    if value <= 0:
        return None

    return value


def _effective_meal_price(
    snapshot: AccountSnapshot,
    config_entry: ConfigEntry,
) -> float | None:
    """Return the meal price used for calculations."""

    manual_price = _manual_meal_price(config_entry)
    if manual_price is not None:
        return manual_price

    return snapshot.meal_price


def _schedule(config_entry: ConfigEntry) -> dict[int, int]:
    """Return the configured meals per weekday."""

    schedule: dict[int, int] = {}
    for weekday_index, key in enumerate(MEAL_DAY_OPTIONS):
        meals = config_entry.options.get(key, DEFAULT_WEEKDAY_MEALS[key])
        # Handle transition from old int format if necessary
        if isinstance(meals, int):
            schedule[weekday_index] = meals
        else:
            schedule[weekday_index] = len(meals)

    return schedule


def _schedule_attributes(config_entry: ConfigEntry) -> dict[str, str]:
    """Return the schedule in a user-friendly format."""

    attributes: dict[str, str] = {}
    for weekday_index, key in enumerate(MEAL_DAY_OPTIONS):
        meals = config_entry.options.get(key, DEFAULT_WEEKDAY_MEALS[key])
        label = WEEKDAY_LABELS[weekday_index]
        if isinstance(meals, int):
            attributes[label] = str(meals)
        elif not meals:
            attributes[label] = "None"
        else:
            attributes[label] = ", ".join(MEAL_TYPES.get(m, m) for m in meals)

    return attributes


def _configured_meals_per_week(config_entry: ConfigEntry) -> int:
    """Return the total configured meals over a week."""

    return sum(_schedule(config_entry).values())


def _computed_meals_left(
    snapshot: AccountSnapshot,
    config_entry: ConfigEntry,
) -> int | None:
    """Return the number of meals left."""

    effective_price = _effective_meal_price(snapshot, config_entry)
    if effective_price and effective_price > 0:
        return max(0, math.floor(snapshot.balance / effective_price))

    return snapshot.remote_meals_left


def _coverage(
    snapshot: AccountSnapshot,
    config_entry: ConfigEntry,
) -> tuple[int | None, date | None]:
    """Return the number of service days covered and the last covered date."""

    meals_left = _computed_meals_left(snapshot, config_entry)
    if meals_left is None or meals_left <= 0:
        return 0, None

    schedule = _schedule(config_entry)
    if not any(schedule.values()):
        return None, None

    skip_holidays = config_entry.options.get(CONF_SKIP_HOLIDAYS, True)
    fr_holidays = holidays.France() if skip_holidays else {}

    skip_vacation = config_entry.options.get(CONF_SKIP_VACATION, True)
    school_zone = config_entry.options.get(CONF_SCHOOL_ZONE, "C")
    school_dates = SchoolHolidayDates() if skip_vacation else None

    remaining = meals_left
    service_days = 0
    last_date: date | None = None
    current = dt_util.now().date()

    for _ in range(366 * 3):
        if skip_holidays and current in fr_holidays:
            current += timedelta(days=1)
            continue

        if skip_vacation and school_dates and school_dates.is_holiday_for_zone(current, school_zone):
            current += timedelta(days=1)
            continue

        meals_today = schedule[current.weekday()]
        if meals_today > 0:
            if remaining < meals_today:
                break
            remaining -= meals_today
            service_days += 1
            last_date = current

        current += timedelta(days=1)

    return service_days, last_date


class MyTurboSelfBalanceSensor(MyTurboSelfEntity, SensorEntity):
    """Expose the current account balance."""

    _attr_translation_key = "balance"
    _attr_icon = "mdi:wallet"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = CURRENCY_EURO

    def __init__(
        self,
        coordinator: MyTurboSelfDataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the balance sensor."""

        super().__init__(coordinator, config_entry, "balance")

    @property
    def native_value(self) -> float:
        """Return the current account balance."""

        return self.coordinator.data.balance

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return account metadata."""

        attributes = _account_attributes(self.coordinator.data)
        attributes[ATTR_EFFECTIVE_MEAL_PRICE] = _effective_meal_price(
            self.coordinator.data,
            self._config_entry,
        )
        attributes[ATTR_REMOTE_MEALS_LEFT] = self.coordinator.data.remote_meals_left
        attributes[ATTR_CONFIGURED_MEALS_PER_WEEK] = _configured_meals_per_week(
            self._config_entry
        )
        attributes[ATTR_SCHEDULE] = _schedule_attributes(self._config_entry)
        return attributes


class MyTurboSelfMealsLeftSensor(MyTurboSelfEntity, SensorEntity):
    """Expose the number of remaining meals."""

    _attr_translation_key = "meals_left"
    _attr_icon = "mdi:silverware-fork-knife"
    _attr_native_unit_of_measurement = "meals"

    def __init__(
        self,
        coordinator: MyTurboSelfDataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the meals-left sensor."""

        super().__init__(coordinator, config_entry, "meals_left")

    @property
    def native_value(self) -> int:
        """Return the number of meals left."""

        return _computed_meals_left(self.coordinator.data, self._config_entry)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return calculation metadata."""

        return {
            ATTR_EFFECTIVE_MEAL_PRICE: _effective_meal_price(
                self.coordinator.data,
                self._config_entry,
            ),
            ATTR_REMOTE_MEALS_LEFT: self.coordinator.data.remote_meals_left,
            ATTR_CONFIGURED_MEALS_PER_WEEK: _configured_meals_per_week(
                self._config_entry
            ),
            ATTR_SCHEDULE: _schedule_attributes(self._config_entry),
        }


class MyTurboSelfUnitPriceSensor(MyTurboSelfEntity, SensorEntity):
    """Expose the price of one meal."""

    _attr_translation_key = "unit_price"
    _attr_icon = "mdi:currency-eur"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = CURRENCY_EURO

    def __init__(
        self,
        coordinator: MyTurboSelfDataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the unit-price sensor."""

        super().__init__(coordinator, config_entry, "unit_price")

    @property
    def native_value(self) -> float:
        """Return the price of a single meal."""

        return _effective_meal_price(self.coordinator.data, self._config_entry)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the auto/manual price details."""

        return {
            "automatic_meal_price": self.coordinator.data.meal_price,
            "manual_meal_price": _manual_meal_price(self._config_entry),
        }


class MyTurboSelfServiceDaysLeftSensor(MyTurboSelfEntity, SensorEntity):
    """Expose the number of service days remaining."""

    _attr_translation_key = "service_days_left"
    _attr_icon = "mdi:calendar-range"
    _attr_native_unit_of_measurement = "days"

    def __init__(
        self,
        coordinator: MyTurboSelfDataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the service-days-left sensor."""

        super().__init__(coordinator, config_entry, "service_days_left")

    @property
    def native_value(self) -> int | None:
        """Return the number of configured service days covered."""

        service_days, _ = _coverage(self.coordinator.data, self._config_entry)
        return service_days

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the configured schedule."""

        return {
            ATTR_SCHEDULE: _schedule_attributes(self._config_entry),
            ATTR_CONFIGURED_MEALS_PER_WEEK: _configured_meals_per_week(
                self._config_entry
            ),
        }


class MyTurboSelfEstimatedEmptyDateSensor(MyTurboSelfEntity, SensorEntity):
    """Expose the estimated last covered service date."""

    _attr_translation_key = "estimated_empty_date"
    _attr_icon = "mdi:calendar-clock"
    _attr_device_class = SensorDeviceClass.DATE

    def __init__(
        self,
        coordinator: MyTurboSelfDataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the empty-date sensor."""

        super().__init__(coordinator, config_entry, "estimated_empty_date")

    @property
    def native_value(self) -> date | None:
        """Return the last date fully covered by the balance."""

        _, last_date = _coverage(self.coordinator.data, self._config_entry)
        return last_date

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the calculation details."""

        service_days, _ = _coverage(self.coordinator.data, self._config_entry)
        return {
            "service_days_left": service_days,
            ATTR_EFFECTIVE_MEAL_PRICE: _effective_meal_price(
                self.coordinator.data,
                self._config_entry,
            ),
            ATTR_SCHEDULE: _schedule_attributes(self._config_entry),
        }
