"""
HEOS Integration driver.

:copyright: (c) 2025 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

from ucapi_framework import BaseIntegrationDriver

from uc_intg_heos.config import HeosDeviceConfig
from uc_intg_heos.device import HeosDevice
from uc_intg_heos.media_player import create_media_players
from uc_intg_heos.remote import create_remotes
from uc_intg_heos.sensor import create_sensors
from uc_intg_heos.select import create_selects


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
