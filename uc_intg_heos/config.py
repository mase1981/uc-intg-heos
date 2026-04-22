"""
HEOS Integration configuration.

:copyright: (c) 2025 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

from dataclasses import dataclass


@dataclass
class HeosDeviceConfig:
    """Configuration for a HEOS system (account-based)."""

    identifier: str = ""
    name: str = ""
    host: str = ""
    username: str = ""
    password: str = ""
