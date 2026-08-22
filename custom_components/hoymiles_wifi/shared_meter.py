"""Shared meter data handling for multi-DTU Hoymiles systems."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from hoymiles_wifi.hoymiles import generate_inverter_serial_number

from .const import (
    CONF_METER_ENERGY_CONSISTENCY_TOLERANCE,
    DEFAULT_METER_ENERGY_CONSISTENCY_TOLERANCE,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

ENERGY_FIELDS = {
    "energy_total_power",
    "energy_phase_A",
    "energy_phase_B",
    "energy_phase_C",
    "energy_total_consumed",
    "energy_phase_A_consumed",
    "energy_phase_B_consumed",
    "energy_phase_C_consumed",
}

ENERGY_CONSISTENCY_GROUPS = (
    ("energy_total_power", ("energy_phase_A", "energy_phase_B", "energy_phase_C")),
    (
        "energy_total_consumed",
        (
            "energy_phase_A_consumed",
            "energy_phase_B_consumed",
            "energy_phase_C_consumed",
        ),
    ),
)

IGNORED_METER_FIELDS = {"serial_number"}

INSTANTANEOUS_FIELD_LIMITS = {
    # Raw power values are converted with *10 before HA displays them.
    # 200 kW is intentionally generous for this integration and still catches
    # corrupt int32/sentinel samples such as +/-214,748,360 W.
    "phase_total_power": (-20_000, 20_000),
    "phase_A_power": (-20_000, 20_000),
    "phase_B_power": (-20_000, 20_000),
    "phase_C_power": (-20_000, 20_000),
    # Raw voltages/currents are converted with *0.01.
    "voltage_phase_A": (0, 30_000),
    "voltage_phase_B": (0, 30_000),
    "voltage_phase_C": (0, 30_000),
    "current_phase_A": (0, 50_000),
    "current_phase_B": (0, 50_000),
    "current_phase_C": (0, 50_000),
    # Raw power factors are converted with *0.1.
    "power_factor_total": (-1_000, 1_000),
    "power_factor_phase_A": (-1_000, 1_000),
    "power_factor_phase_B": (-1_000, 1_000),
    "power_factor_phase_C": (-1_000, 1_000),
}


class HoymilesSharedMeterCoordinator(DataUpdateCoordinator):
    """Merge meter data reported by multiple DTUs."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the shared meter coordinator."""
        # This coordinator is a push-fed store. DTU coordinators poll at their own
        # configured interval and submit the already received meter data here.
        super().__init__(hass, _LOGGER, name=f"{DOMAIN}_shared_meters")
        self.data = {}

    def update_from_real_data(
        self, real_data: Any, config_entry: ConfigEntry
    ) -> None:
        """Merge meter data from a DTU real-data response."""
        if not real_data or not getattr(real_data, "meter_data", None):
            return

        data = deepcopy(self.data or {})
        changed = False
        dtu_serial = str(getattr(real_data, "device_serial_number", ""))
        timestamp = getattr(real_data, "timestamp", None)
        source = {
            "last_source_dtu": dtu_serial,
            "last_source_host": config_entry.data.get(CONF_HOST),
            "last_source_config_entry_id": config_entry.entry_id,
            "last_source_timestamp": timestamp,
            "last_source_updated_at": datetime.now().isoformat(),
        }
        consistency_tolerance = self._energy_consistency_tolerance(config_entry)

        for meter_data in real_data.meter_data:
            meter_serial = generate_inverter_serial_number(meter_data.serial_number)
            existing_record = data.get(meter_serial) or {}
            existing_values = existing_record.get("values", {})
            present_fields = {field.name for field, _value in meter_data.ListFields()}

            if self._sample_has_invalid_instantaneous_values(
                meter_data,
                meter_serial,
                dtu_serial,
                present_fields,
            ) or self._sample_has_inconsistent_energy(
                meter_data,
                meter_serial,
                dtu_serial,
                present_fields,
                consistency_tolerance,
            ) or self._sample_has_stale_energy(
                meter_data, meter_serial, dtu_serial, existing_values, present_fields
            ):
                continue

            record = data.setdefault(
                meter_serial,
                {
                    "values": {},
                    "last_source_dtu": None,
                    "last_source_host": None,
                    "last_source_config_entry_id": None,
                    "last_source_timestamp": None,
                    "last_source_updated_at": None,
                    "last_energy_source_dtu": None,
                    "last_energy_source_host": None,
                    "last_energy_source_config_entry_id": None,
                    "last_energy_source_timestamp": None,
                    "last_energy_updated_at": None,
                },
            )
            values = record.setdefault("values", {})
            source_is_newest = self._is_newest_source(
                timestamp, record.get("last_source_timestamp")
            )
            energy_source_is_newest = self._is_newest_source(
                timestamp, record.get("last_energy_source_timestamp")
            )
            accepted_sample = False
            accepted_energy = False
            changed_energy = False

            for field in meter_data.DESCRIPTOR.fields:
                field_name = field.name
                if field_name in IGNORED_METER_FIELDS:
                    continue

                if field_name in ENERGY_FIELDS:
                    if field_name not in present_fields:
                        continue

                    value = getattr(meter_data, field_name)
                    previous = values.get(field_name)
                    if previous != value:
                        values[field_name] = value
                        changed = True
                        changed_energy = True
                    accepted_energy = True
                    accepted_sample = True
                    continue

                value = getattr(meter_data, field_name)
                if source_is_newest and values.get(field_name) != value:
                    values[field_name] = value
                    changed = True
                if source_is_newest:
                    accepted_sample = True

            if accepted_sample and source_is_newest:
                for key, value in source.items():
                    if record.get(key) != value:
                        record[key] = value
                        changed = True

            if accepted_energy and (changed_energy or energy_source_is_newest):
                energy_source = {
                    "last_energy_source_dtu": dtu_serial,
                    "last_energy_source_host": config_entry.data.get(CONF_HOST),
                    "last_energy_source_config_entry_id": config_entry.entry_id,
                    "last_energy_source_timestamp": timestamp,
                    "last_energy_updated_at": datetime.now().isoformat(),
                }
                for key, value in energy_source.items():
                    if record.get(key) != value:
                        record[key] = value
                        changed = True

        if changed:
            self.async_set_updated_data(data)

    def remove_meter(self, meter_serial: str) -> None:
        """Remove a meter from the shared in-memory store."""
        data = deepcopy(self.data or {})
        if data.pop(str(meter_serial).lower(), None) is not None:
            self.async_set_updated_data(data)

    @staticmethod
    def _energy_consistency_tolerance(config_entry: ConfigEntry) -> int:
        """Return the configured allowed total-vs-phase energy mismatch."""
        try:
            return max(
                0,
                int(
                    config_entry.data.get(
                        CONF_METER_ENERGY_CONSISTENCY_TOLERANCE,
                        DEFAULT_METER_ENERGY_CONSISTENCY_TOLERANCE,
                    )
                ),
            )
        except (TypeError, ValueError):
            return DEFAULT_METER_ENERGY_CONSISTENCY_TOLERANCE

    @staticmethod
    def _sample_has_stale_energy(
        meter_data: Any,
        meter_serial: str,
        dtu_serial: str,
        values: dict[str, Any],
        present_fields: set[str],
    ) -> bool:
        """Return true if any present cumulative meter value moves backward."""
        for field in meter_data.DESCRIPTOR.fields:
            field_name = field.name
            if field_name not in ENERGY_FIELDS or field_name not in present_fields:
                continue

            value = getattr(meter_data, field_name)
            previous = values.get(field_name)
            if previous is not None and value < previous:
                _LOGGER.debug(
                    "Ignoring stale meter sample for meter %s from DTU %s because %s moved backward: %s < %s",
                    meter_serial,
                    dtu_serial,
                    field_name,
                    value,
                    previous,
                )
                return True

        return False

    @staticmethod
    def _sample_has_invalid_instantaneous_values(
        meter_data: Any,
        meter_serial: str,
        dtu_serial: str,
        present_fields: set[str],
    ) -> bool:
        """Return true if any present instantaneous meter value is implausible."""
        for field_name, (minimum, maximum) in INSTANTANEOUS_FIELD_LIMITS.items():
            if field_name not in present_fields:
                continue

            value = getattr(meter_data, field_name)
            if minimum <= value <= maximum:
                continue

            _LOGGER.debug(
                "Ignoring invalid meter sample for meter %s from DTU %s because %s=%s is outside %s..%s",
                meter_serial,
                dtu_serial,
                field_name,
                value,
                minimum,
                maximum,
            )
            return True

        return False

    @staticmethod
    def _sample_has_inconsistent_energy(
        meter_data: Any,
        meter_serial: str,
        dtu_serial: str,
        present_fields: set[str],
        tolerance: int,
    ) -> bool:
        """Return true if complete cumulative totals do not match phase sums."""
        for total_field, phase_fields in ENERGY_CONSISTENCY_GROUPS:
            required_fields = {total_field, *phase_fields}
            if not required_fields.issubset(present_fields):
                continue

            total = getattr(meter_data, total_field)
            phase_sum = sum(getattr(meter_data, field) for field in phase_fields)
            if abs(total - phase_sum) > tolerance:
                _LOGGER.debug(
                    "Ignoring inconsistent meter sample for meter %s from DTU %s because %s=%s does not match phase sum %s within tolerance %s",
                    meter_serial,
                    dtu_serial,
                    total_field,
                    total,
                    phase_sum,
                    tolerance,
                )
                return True

        return False

    @staticmethod
    def _is_newest_source(new_timestamp: Any, current_timestamp: Any) -> bool:
        """Return true when a source sample is not older than the current one."""
        if current_timestamp is None or new_timestamp is None:
            return True
        try:
            return float(new_timestamp) >= float(current_timestamp)
        except (TypeError, ValueError):
            pass
        try:
            return new_timestamp >= current_timestamp
        except TypeError:
            return str(new_timestamp) >= str(current_timestamp)
