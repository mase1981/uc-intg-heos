"""
HEOS Select entities.

:copyright: (c) 2025 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

import logging
from typing import Any

from ucapi import select, StatusCodes

from pyheos import HeosError

from ucapi_framework import SelectEntity

from uc_intg_heos.config import HeosDeviceConfig
from uc_intg_heos.device import HeosDevice

_LOG = logging.getLogger(__name__)


class HeosInputSelect(SelectEntity):
    """Select entity for HEOS input source switching."""

    def __init__(
        self, device_config: HeosDeviceConfig, device: HeosDevice, player_id: int, player_name: str
    ) -> None:
        self._device = device
        self._player_id = player_id

        entity_id = f"select.{device_config.identifier}.{player_id}.input"

        super().__init__(
            entity_id,
            f"{player_name} Input Source",
            {
                select.Attributes.STATE: select.States.UNKNOWN,
                select.Attributes.OPTIONS: [],
                select.Attributes.CURRENT_OPTION: "",
            },
            cmd_handler=self._handle_command,
        )
        self.subscribe_to_device(device)

    async def sync_state(self) -> None:
        if self._device.state == "UNAVAILABLE":
            self.update({select.Attributes.STATE: select.States.UNAVAILABLE})
            return

        player = self._device.get_player(self._player_id)
        if not player:
            self.update({select.Attributes.STATE: select.States.UNAVAILABLE})
            return

        options = [inp.name for inp in self._device.input_sources]
        current = ""
        now = player.now_playing_media
        if now:
            for inp in self._device.input_sources:
                if inp.media_id == (now.media_id or ""):
                    current = inp.name
                    break

        self.update({
            select.Attributes.STATE: select.States.ON,
            select.Attributes.OPTIONS: options,
            select.Attributes.CURRENT_OPTION: current,
        })

    async def _handle_command(
        self, entity: select.Select, cmd_id: str, params: dict[str, Any] | None
    ) -> StatusCodes:
        player = self._device.get_player(self._player_id)
        if not player:
            return StatusCodes.SERVICE_UNAVAILABLE

        try:
            if cmd_id == select.Commands.SELECT_OPTION:
                option = (params or {}).get("option", "")
                for inp in self._device.input_sources:
                    if inp.name == option:
                        await player.play_input_source(inp.media_id)
                        return StatusCodes.OK
                return StatusCodes.BAD_REQUEST
            return StatusCodes.NOT_IMPLEMENTED
        except HeosError as err:
            _LOG.error("[%s] Input select error: %s", entity.id, err)
            return StatusCodes.SERVER_ERROR


def create_selects(
    device_config: HeosDeviceConfig, device: HeosDevice
) -> list[HeosInputSelect]:
    if not device.input_sources:
        return []
    entities = []
    for player in device.players.values():
        entities.append(
            HeosInputSelect(device_config, device, player.player_id, player.name)
        )
    return entities
