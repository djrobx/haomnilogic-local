from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from pyomnilogic_local import Heater

from .const import DOMAIN, KEY_COORDINATOR
from .entity import OmniLogicEntity

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import OmniLogicCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up the climate platform."""
    coordinator: OmniLogicCoordinator = hass.data[DOMAIN][entry.entry_id][KEY_COORDINATOR]
    entities: list[ClimateEntity] = []

    for _, _, heater in coordinator.omni.all_heaters.items():
        entities.append(OmniLogicClimateEntity(coordinator=coordinator, equipment=heater))

    async_add_entities(entities)


class OmniLogicClimateEntity(OmniLogicEntity[Heater], ClimateEntity):
    """Climate entity for heater control."""

    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.TURN_OFF | ClimateEntityFeature.TURN_ON
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
    _attr_name = "Heater"

    @property
    def temperature_unit(self) -> str:
        # Heaters always return their values in Fahrenheit, no matter what units the system is set to
        # https://github.com/cryptk/haomnilogic-local/issues/96
        return UnitOfTemperature.FAHRENHEIT

    @property
    def min_temp(self) -> float:
        return self.equipment.min_temp

    @property
    def max_temp(self) -> float:
        return self.equipment.max_temp

    @property
    def target_temperature(self) -> float | None:
        return self.equipment.current_set_point

    @property
    def current_temperature(self) -> float | None:
        if self.equipment.bow_id is None:
            return None
        bow = self.coordinator.omni.all_bows.get(self.equipment.bow_id)
        if bow is None:
            return None
        current_temp = bow.water_temp
        return current_temp if current_temp != -1 else None

    @property
    def hvac_mode(self) -> HVACMode:
        """Return current HVAC mode."""
        return HVACMode.HEAT if self.equipment.is_on else HVACMode.OFF

    @property
    def hvac_action(self) -> HVACAction:
        """Return the current running HVAC operation."""
        if not self.equipment.is_on:
            return HVACAction.OFF
        if any(heater_equip.is_on for _, _, heater_equip in self.equipment.heater_equipment.items()):
            return HVACAction.HEATING
        return HVACAction.IDLE

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set target temperature."""
        await self.equipment.set_temperature(int(kwargs[ATTR_TEMPERATURE]))
        self.coordinator.do_next_refresh_after()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set HVAC mode."""
        match hvac_mode:
            case HVACMode.HEAT:
                await self.equipment.turn_on()
            case HVACMode.OFF:
                await self.equipment.turn_off()
            case _:
                _LOGGER.error("Unrecognized HVAC mode: %s", hvac_mode)
                return
        self.coordinator.do_next_refresh_after()

    async def async_turn_on(self) -> None:
        """Turn the heater on."""
        await self.async_set_hvac_mode(HVACMode.HEAT)

    async def async_turn_off(self) -> None:
        """Turn the heater off."""
        await self.async_set_hvac_mode(HVACMode.OFF)

    @property
    def _extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        extra_state_attributes: dict[str, Any] = {
            "omni_solar_set_point": self.equipment.solar_set_point,
            "omni_why_on": self.equipment.why_on,
        }
        for _, system_id, heater_equip in self.equipment.heater_equipment.items():
            name = heater_equip.name or "unknown"
            prefix = f"omni_heater_equip_{name}_"
            extra_state_attributes |= {
                f"{prefix}_enabled": heater_equip.enabled,
                f"{prefix}_system_id": system_id,
                f"{prefix}_bow_id": heater_equip.bow_id,
                f"{prefix}_state": str(heater_equip.state),
                f"{prefix}_current_temp": heater_equip.current_temp,
            }
        return extra_state_attributes
