"""
HEOS Integration Driver - Direct Connection Pattern.

:copyright: (c) 2025 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

import asyncio
import logging
import os
from typing import Dict, List, Optional

import ucapi
from ucapi import DeviceStates, Events, IntegrationAPI, StatusCodes
from ucapi.api_definitions import SetupAction, SetupComplete, SetupError

from pyheos import Heos, HeosOptions, Credentials, HeosError

from uc_intg_heos.config import HeosConfig
from uc_intg_heos.setup import HeosSetupManager
from uc_intg_heos.media_player import HeosMediaPlayer
from uc_intg_heos.remote import HeosRemote

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
_LOG = logging.getLogger(__name__)

api: Optional[IntegrationAPI] = None
config: Optional[HeosConfig] = None
heos: Optional[Heos] = None
media_players: Dict[int, HeosMediaPlayer] = {}
remotes: Dict[int, HeosRemote] = {}

entities_ready = False
initialization_lock = asyncio.Lock()

setup_manager: Optional[HeosSetupManager] = None


async def _initialize_integration():
    """Initialize integration entities - direct pattern like Naim/MusicCast."""
    global config, api, heos, media_players, remotes, entities_ready
    
    async with initialization_lock:
        if entities_ready:
            _LOG.debug("Entities already initialized")
            return
            
        if not config or not config.is_configured():
            _LOG.info("No configuration found")
            return

        _LOG.info("Initializing HEOS integration (direct pattern)...")
        await api.set_device_state(DeviceStates.CONNECTING)
        
        try:
            api.available_entities.clear()
            media_players.clear()
            remotes.clear()
            
            # Get configuration
            account_config = config.get_heos_account()
            if not account_config:
                raise HeosError("No HEOS account configuration found")
            
            # Create Heos connection directly (FAST - no coordinator bottleneck)
            credentials = Credentials(account_config.username, account_config.password)
            heos_options = HeosOptions(
                host=account_config.host,
                all_progress_events=False,
                auto_reconnect=True,
                auto_failover=True,
                credentials=credentials
            )
            
            heos = Heos(heos_options)
            
            # Connect (this is fast - ~500ms)
            _LOG.info(f"Connecting to HEOS at {account_config.host}...")
            await heos.connect()
            
            # Get players immediately
            await heos.get_players()
            
            players = heos.players
            if not players:
                _LOG.warning("No HEOS devices found")
                await api.set_device_state(DeviceStates.ERROR)
                return

            _LOG.info(f"Connected - found {len(players)} HEOS device(s)")
            
            # Create entities immediately (also fast)
            for player_id, player in players.items():
                media_player = HeosMediaPlayer(heos, player, api)
                await media_player.initialize()
                
                media_players[player_id] = media_player
                api.available_entities.add(media_player)
                
                _LOG.debug(f"Created media player: {media_player.id}")
            
            # Create remotes if multiple devices
            if len(players) > 1:
                for player_id, player in players.items():
                    remote = HeosRemote(
                        heos=heos,
                        heos_player=player,
                        device_name=player.name,
                        api=api,
                        all_players=players
                    )
                    
                    await remote.initialize()
                    
                    remotes[player_id] = remote
                    api.available_entities.add(remote)
                    
                    _LOG.debug(f"Created remote: {remote.id}")
            
            entities_ready = True
            await api.set_device_state(DeviceStates.CONNECTED)
            _LOG.info(f"Integration initialized: {len(media_players)} players, {len(remotes)} remotes")
            
        except Exception as e:
            _LOG.error(f"Failed to initialize: {e}", exc_info=True)
            entities_ready = False
            await api.set_device_state(DeviceStates.ERROR)
            if heos:
                try:
                    await heos.disconnect()
                except:
                    pass
                heos = None


async def setup_handler(msg: ucapi.SetupDriver) -> ucapi.SetupAction:
    """Handle setup flow."""
    global setup_manager
    
    if not setup_manager:
        return SetupError()
    
    action = await setup_manager.handle_setup(msg)
    
    if isinstance(action, SetupComplete):
        _LOG.info("Setup complete - initializing entities")
        await _initialize_integration()
    
    return action


async def on_subscribe_entities(entity_ids: List[str]):
    """Handle entity subscription with race condition protection."""
    global media_players, remotes, entities_ready, config
    
    _LOG.info(f"Subscription requested for {len(entity_ids)} entities")
    
    if not entities_ready:
        _LOG.warning("Subscription before entities ready - attempting recovery")
        
        if config and config.is_configured():
            await _initialize_integration()
            
            if not entities_ready:
                _LOG.error("Recovery failed - entities still not ready")
                return
        else:
            _LOG.error("Cannot recover - no configuration available")
            return
    
    subscribed_count = 0
    for entity_id in entity_ids:
        for player_id, media_player in media_players.items():
            if media_player.id == entity_id:
                api.configured_entities.add(media_player)
                await media_player.update_attributes()
                subscribed_count += 1
                break
        
        for player_id, remote in remotes.items():
            if remote.id == entity_id:
                api.configured_entities.add(remote)
                await remote.update_attributes()
                subscribed_count += 1
                break
    
    _LOG.info(f"Subscribed to {subscribed_count}/{len(entity_ids)} entities")


async def on_unsubscribe_entities(entity_ids: List[str]):
    """Handle entity unsubscription."""
    _LOG.info(f"Unsubscribed from {len(entity_ids)} entities")


async def on_connect():
    """Handle Remote connection with reboot survival."""
    global entities_ready, config
    
    _LOG.info("Remote connected")
    
    if config:
        config.load()
    
    if config and config.is_configured():
        if not entities_ready:
            _LOG.info("Initializing entities")
            await _initialize_integration()
        else:
            await api.set_device_state(DeviceStates.CONNECTED)
    else:
        await api.set_device_state(DeviceStates.DISCONNECTED)


async def on_disconnect():
    """Handle Remote disconnection."""
    _LOG.info("Remote disconnected")


async def main():
    """Main entry point."""
    global api, config, setup_manager
    
    _LOG.info("Starting HEOS Integration v1.0.30")
    
    try:
        loop = asyncio.get_running_loop()
        api = IntegrationAPI(loop)
        
        driver_path = os.path.join(os.path.dirname(__file__), "..", "driver.json")
        
        # Register listeners before init
        api.add_listener(Events.SUBSCRIBE_ENTITIES, on_subscribe_entities)
        api.add_listener(Events.UNSUBSCRIBE_ENTITIES, on_unsubscribe_entities)
        api.add_listener(Events.CONNECT, on_connect)
        api.add_listener(Events.DISCONNECT, on_disconnect)
        
        # Create temporary config
        config = HeosConfig()
        setup_manager = HeosSetupManager(config)
        
        # Initialize API
        await api.init(os.path.abspath(driver_path), setup_handler)
        
        # Update config path
        from pathlib import Path
        config._config_dir = Path(api.config_dir_path)
        config._config_file = config._config_dir / "heos_config.json"
        
        try:
            config._config_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        
        config.load()
        
        # Pre-initialize if configured
        if config.is_configured():
            _LOG.info("Pre-initializing entities")
            asyncio.create_task(_initialize_integration())
        else:
            await api.set_device_state(DeviceStates.DISCONNECTED)
        
        await asyncio.Future()
        
    except Exception as e:
        _LOG.error(f"Fatal error: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())