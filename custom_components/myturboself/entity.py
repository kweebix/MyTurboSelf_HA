"""Shared entity helpers for MyTurboSelf."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEFAULT_NAME, DOMAIN, MANUFACTURER, MODEL
from .coordinator import MyTurboSelfDataUpdateCoordinator


class MyTurboSelfEntity(CoordinatorEntity[MyTurboSelfDataUpdateCoordinator]):
    """Base entity for MyTurboSelf."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: MyTurboSelfDataUpdateCoordinator,
        config_entry: ConfigEntry,
        key: str,
    ) -> None:
        """Initialize the shared entity state."""

        super().__init__(coordinator)
        self._config_entry = config_entry
        self._attr_unique_id = f"{config_entry.entry_id}_{key}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return the pseudo-device grouping the account entities."""

        return DeviceInfo(
            identifiers={(DOMAIN, self._config_entry.entry_id)},
            manufacturer=MANUFACTURER,
            model=MODEL,
            name=self._config_entry.title or DEFAULT_NAME,
            configuration_url="https://espacenumerique.turbo-self.com/Connexion.aspx",
        )
