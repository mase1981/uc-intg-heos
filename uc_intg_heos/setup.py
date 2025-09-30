"""
HEOS Setup Flow Management.

:copyright: (c) 2025 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

import asyncio
import logging
from typing import Any, Dict, Optional

from ucapi.api_definitions import (
    DriverSetupRequest, SetupAction, SetupComplete, SetupError,
    UserDataResponse, RequestUserInput, IntegrationSetupError,
    AbortDriverSetup
)

from pyheos import Heos, HeosError, HeosOptions, Credentials

from uc_intg_heos.config import HeosConfig

_LOG = logging.getLogger(__name__)


class HeosSetupManager:
    """Manages the HEOS setup flow with account authentication."""
    
    def __init__(self, config: HeosConfig):
        """
        Initialize setup manager.
        
        :param config: Configuration manager instance
        """
        self._config = config
        self._setup_state = "start"
        self._heos: Optional[Heos] = None
    
    async def handle_setup(self, msg: SetupAction) -> SetupAction:
        """
        Handle setup flow messages.
        
        :param msg: Setup message from UC Remote
        :return: Setup response action
        """
        try:
            if isinstance(msg, DriverSetupRequest):
                return await self._handle_driver_setup_request(msg)
            elif isinstance(msg, UserDataResponse):
                return await self._handle_user_data_response(msg)
            elif isinstance(msg, AbortDriverSetup):
                _LOG.info("HEOS setup aborted by user")
                await self._cleanup()
                return SetupComplete()
            else:
                _LOG.error(f"Unsupported setup message type: {type(msg)}")
                return SetupError(IntegrationSetupError.OTHER)
                
        except Exception as e:
            _LOG.error(f"HEOS setup error: {e}")
            await self._cleanup()
            return SetupError(IntegrationSetupError.OTHER)
    
    async def _handle_driver_setup_request(self, msg: DriverSetupRequest) -> SetupAction:
        """Handle initial driver setup request."""
        _LOG.info("Starting HEOS integration setup")
        
        # Check if this is a reconfiguration
        if msg.reconfigure and self._config.is_configured():
            return await self._handle_reconfiguration()
        
        # Request HEOS account credentials and device IP
        return await self._request_heos_setup()
    
    async def _handle_reconfiguration(self) -> SetupAction:
        """Handle integration reconfiguration."""
        _LOG.info("Handling HEOS integration reconfiguration")
        
        # Clear existing configuration
        self._config.clear_configuration()
        
        # Request setup info
        return await self._request_heos_setup()
    
    async def _request_heos_setup(self) -> SetupAction:
        """Request HEOS device IP and account credentials."""
        self._setup_state = "heos_setup"
    
        settings = [
            {
                "id": "host",
                "label": {
                    "en": "HEOS Device IP Address"
                },
                "field": {
                    "text": {
                        "value": "",
                        "regex": r"^(\d{1,3}\.){3}\d{1,3}$"  # IP address only, no port
                    }
                }
            },
            {
                "id": "username",
                "label": {
                    "en": "HEOS Account Username/Email"
                },
                "field": {
                    "text": {
                        "value": ""
                    }
                }
            },
            {
                "id": "password", 
                "label": {
                    "en": "HEOS Account Password"
                },
                "field": {
                    "password": {
                        "value": ""
                    }
                }
            }
        ]
    
        title = {
            "en": "HEOS Account Setup"
        }
    
        return RequestUserInput(title=title, settings=settings)
    
    async def _handle_user_data_response(self, msg: UserDataResponse) -> SetupAction:
        """Handle user input responses."""
        if self._setup_state == "heos_setup":
            return await self._handle_heos_setup(msg.input_values)
        else:
            _LOG.error(f"Unexpected user data response in state: {self._setup_state}")
            return SetupError(IntegrationSetupError.OTHER)
    
    async def _handle_heos_setup(self, input_values: Dict[str, str]) -> SetupAction:
        """Handle HEOS setup with account authentication."""
        host = input_values.get("host", "").strip()
        username = input_values.get("username", "").strip()
        password = input_values.get("password", "").strip()
        
        if not host or not username or not password:
            _LOG.error("Missing required HEOS setup information")
            return SetupError(IntegrationSetupError.OTHER)
        
        try:
            _LOG.info(f"Connecting to HEOS device at {host}")
            
            # Create HEOS connection with credentials
            credentials = Credentials(username, password)
            heos_options = HeosOptions(
                host=host,
                credentials=credentials,
                auto_reconnect=False,  # Don't auto-reconnect during setup
                events=False,  # Don't process events during setup
                heart_beat=False  # Don't send heartbeats during setup
            )
            
            self._heos = Heos(heos_options)
            
            # Connect to HEOS device
            await self._heos.connect()
            _LOG.info("Connected to HEOS device")
            
            # Authenticate with HEOS account
            _LOG.info("Signing in to HEOS account")
            success = await self._heos.sign_in(username, password)
            
            if not success:
                _LOG.error("HEOS account authentication failed")
                await self._cleanup()
                return SetupError(IntegrationSetupError.AUTHORIZATION_ERROR)
            
            _LOG.info(f"Successfully signed in to HEOS account: {self._heos.signed_in_username}")
            
            # Discover all players on the account
            players = await self._heos.get_players()
            
            if not players:
                _LOG.warning("No HEOS players found on account")
            else:
                _LOG.info(f"Discovered {len(players)} HEOS player(s) on account:")
                for player_id, player in players.items():
                    _LOG.info(f"  - {player.name} (Model: {player.model}, ID: {player_id})")
            
            # Save configuration
            self._config.set_heos_account(username, password, host)
            
            _LOG.info("HEOS integration setup completed successfully")
            
            await self._cleanup()
            return SetupComplete()
            
        except HeosError as e:
            _LOG.error(f"HEOS error during setup: {e}")
            await self._cleanup()
            
            # Determine appropriate error type
            if "authentication" in str(e).lower() or "sign_in" in str(e).lower():
                return SetupError(IntegrationSetupError.AUTHORIZATION_ERROR)
            else:
                return SetupError(IntegrationSetupError.CONNECTION_REFUSED)
                
        except Exception as e:
            _LOG.error(f"Failed to setup HEOS integration: {e}")
            import traceback
            _LOG.error(f"Traceback: {traceback.format_exc()}")
            await self._cleanup()
            return SetupError(IntegrationSetupError.CONNECTION_REFUSED)
    
    async def _cleanup(self) -> None:
        """Clean up resources."""
        if self._heos:
            try:
                await self._heos.disconnect()
            except Exception:
                pass
            self._heos = None