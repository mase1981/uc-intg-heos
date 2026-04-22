"""
HEOS Integration setup flow.

:copyright: (c) 2025 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

import logging
from typing import Any

from ucapi import RequestUserInput

from pyheos import Heos, HeosError, HeosOptions

from ucapi_framework import BaseSetupFlow

from uc_intg_heos.config import HeosDeviceConfig

_LOG = logging.getLogger(__name__)


class HeosSetupFlow(BaseSetupFlow[HeosDeviceConfig]):
    """HEOS account-based setup flow."""

    def get_manual_entry_form(self) -> RequestUserInput:
        return RequestUserInput(
            {"en": "HEOS Account Setup"},
            [
                {
                    "id": "host",
                    "label": {"en": "HEOS Device IP Address"},
                    "field": {
                        "text": {
                            "value": "",
                            "regex": r"^(\d{1,3}\.){3}\d{1,3}$",
                        }
                    },
                },
                {
                    "id": "username",
                    "label": {"en": "HEOS Account Email"},
                    "field": {"text": {"value": ""}},
                },
                {
                    "id": "password",
                    "label": {"en": "HEOS Account Password"},
                    "field": {"password": {"value": ""}},
                },
            ],
        )

    async def query_device(
        self, input_values: dict[str, Any]
    ) -> HeosDeviceConfig | RequestUserInput:
        host = input_values.get("host", "").strip()
        username = input_values.get("username", "").strip()
        password = input_values.get("password", "").strip()

        if not host:
            raise ValueError("IP address is required")

        heos = Heos(HeosOptions(
            host=host,
            auto_reconnect=False,
            events=False,
            heart_beat=False,
        ))

        try:
            await heos.connect()
            _LOG.info("Connected to HEOS device at %s", host)

            if username and password:
                await heos.sign_in(username, password)
                _LOG.info("Signed in to HEOS account")

            players = await heos.get_players()
            player_count = len(players) if players else 0
            _LOG.info("Discovered %d HEOS player(s)", player_count)

            for pid, p in (players or {}).items():
                _LOG.info("  - %s (Model: %s, ID: %d)", p.name, p.model, pid)

        except HeosError as err:
            error_str = str(err).lower()
            if "sign_in" in error_str or "auth" in error_str:
                raise ValueError(f"Authentication failed: {err}") from err
            raise ConnectionError(f"Cannot connect to HEOS at {host}: {err}") from err
        finally:
            try:
                await heos.disconnect()
            except Exception:
                pass

        identifier = f"heos_{host.replace('.', '_')}"
        name = f"HEOS ({host})"

        return HeosDeviceConfig(
            identifier=identifier,
            name=name,
            host=host,
            username=username,
            password=password,
        )
