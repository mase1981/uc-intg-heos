"""
HEOS Integration driver.

:copyright: (c) 2025 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

import asyncio
import logging

from ucapi_framework import BaseIntegrationDriver

from uc_intg_heos.config import HeosDeviceConfig
from uc_intg_heos.device import HeosDevice
from uc_intg_heos.media_player import create_media_players
from uc_intg_heos.remote import create_remotes
from uc_intg_heos.sensor import create_sensors
from uc_intg_heos.select import create_selects

_LOG = logging.getLogger(__name__)

_RETRY_DELAYS = [5, 10, 20, 30, 60, 120, 300]


class HeosDriver(BaseIntegrationDriver[HeosDevice, HeosDeviceConfig]):

    def __init__(self) -> None:
        super().__init__(
            device_class=HeosDevice,
            entity_classes=[
                lambda cfg, dev: create_media_players(cfg, dev),
                lambda cfg, dev: create_remotes(cfg, dev),
                lambda cfg, dev: create_sensors(cfg, dev),
                lambda cfg, dev: create_selects(cfg, dev),
            ],
            require_connection_before_registry=True,
        )
        self._reconnect_tasks: dict[str, asyncio.Task] = {}

    async def on_r2_enter_standby(self) -> None:
        """Keep HEOS connections alive while the Remote is in standby.

        The default behavior disconnects all devices on standby. HEOS only
        registers entities after a successful connect (it discovers players
        dynamically), so a failed reconnect on wake leaves the integration with
        no entities until setup is re-run. Staying connected avoids that fragile
        wake-reconnect; pyheos maintains its own connection in the background.
        """
        _LOG.debug("Enter standby event: keeping HEOS connection(s) alive")

    async def on_r2_exit_standby(self) -> None:
        """Reconnect only devices whose connection dropped while in standby."""
        _LOG.debug("Exit standby event: verifying HEOS connection(s)")
        for device in self._device_instances.values():
            if not device.is_connected:
                self._loop.create_task(device.connect())

    async def on_device_connection_error(self, device_id: str, message: str) -> None:
        """Mark entities unavailable and keep retrying until the device returns.

        Without this, the framework gives up after a few connect attempts and the
        device stays permanently disconnected with no entities, forcing a setup
        re-run. The background retry guarantees eventual self-healing.
        """
        await super().on_device_connection_error(device_id, message)
        self._schedule_reconnect(device_id)

    def _schedule_reconnect(self, device_id: str) -> None:
        existing = self._reconnect_tasks.get(device_id)
        if existing and not existing.done():
            return
        self._reconnect_tasks[device_id] = self._loop.create_task(
            self._reconnect_forever(device_id)
        )

    async def _reconnect_forever(self, device_id: str) -> None:
        attempt = 0
        while True:
            if not self.config_manager:
                return
            config = self.config_manager.get(device_id)
            device = self._device_instances.get(device_id)
            if config is None or device is None:
                return
            if device.is_connected:
                return

            delay = _RETRY_DELAYS[min(attempt, len(_RETRY_DELAYS) - 1)]
            _LOG.warning(
                "[%s] Reconnecting in %ds (attempt #%d)...", device_id, delay, attempt + 1
            )
            await asyncio.sleep(delay)

            try:
                if await self.async_add_configured_device(config):
                    _LOG.info("[%s] Reconnect successful", device_id)
                    return
            except Exception as err:  # pylint: disable=broad-exception-caught
                _LOG.error("[%s] Reconnect attempt failed: %s", device_id, err)
            attempt += 1
