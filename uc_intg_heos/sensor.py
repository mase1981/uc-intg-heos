"""
HEOS Sensor entities.

:copyright: (c) 2025 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

import logging

from ucapi import sensor

from pyheos import HeosPlayer

from ucapi_framework import SensorEntity

from uc_intg_heos.config import HeosDeviceConfig
from uc_intg_heos.device import HeosDevice

_LOG = logging.getLogger(__name__)


class HeosSensor(SensorEntity):
    """Generic HEOS sensor."""

    def __init__(
        self,
        entity_id: str,
        name: str,
        device: HeosDevice,
        player_id: int,
        sensor_key: str,
        unit: str | None = None,
    ) -> None:
        self._device = device
        self._player_id = player_id
        self._sensor_key = sensor_key

        options = {}
        if unit:
            options[sensor.Options.CUSTOM_UNIT] = unit

        super().__init__(
            entity_id,
            name,
            [],
            {sensor.Attributes.STATE: sensor.States.UNKNOWN, sensor.Attributes.VALUE: ""},
            device_class=sensor.DeviceClasses.CUSTOM,
            options=options if options else None,
        )
        self.subscribe_to_device(device)

    async def sync_state(self) -> None:
        if self._device.state == "UNAVAILABLE":
            self.update({sensor.Attributes.STATE: sensor.States.UNAVAILABLE})
            return

        player = self._device.get_player(self._player_id)
        if not player:
            self.update({sensor.Attributes.STATE: sensor.States.UNAVAILABLE})
            return

        value = self._get_value(player)
        self.update({
            sensor.Attributes.STATE: sensor.States.ON,
            sensor.Attributes.VALUE: str(value) if value is not None else "Unknown",
        })

    def _get_value(self, player: HeosPlayer) -> str | None:
        match self._sensor_key:
            case "model":
                return player.model
            case "network":
                return str(player.network) if player.network else None
            case "ip_address":
                return player.ip_address
            case "version":
                return player.version
            case "serial":
                return player.serial
            case "now_playing_source":
                now = player.now_playing_media
                if now and now.source_id is not None:
                    src = self._device.music_sources.get(now.source_id)
                    return src.name if src else str(now.source_id)
                return None
            case _:
                return None


def create_sensors(
    device_config: HeosDeviceConfig, device: HeosDevice
) -> list[HeosSensor]:
    entities = []
    dev_id = device_config.identifier

    sensor_defs = [
        ("model", "Model", None),
        ("network", "Network", None),
        ("ip_address", "IP Address", None),
        ("version", "Firmware", None),
    ]

    for player in device.players.values():
        pid = player.player_id
        for key, label, unit in sensor_defs:
            eid = f"sensor.{dev_id}.{pid}.{key}"
            name = f"{player.name} {label}"
            entities.append(HeosSensor(eid, name, device, pid, key, unit))

    return entities
