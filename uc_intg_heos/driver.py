"""
HEOS Integration Driver.

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

from pyheos import HeosPlayer

from uc_intg_heos.config import HeosConfig
from uc_intg_heos.coordinator import HeosCoordinator  
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
coordinator: Optional[HeosCoordinator] = None
media_players: Dict[int, HeosMediaPlayer] = {}
remotes: Dict[int, HeosRemote] = {}

entities_ready = False
initialization_lock = asyncio.Lock()

setup_manager: Optional[HeosSetupManager] = None


async def _initialize_integration():
    """Initialize integration entities."""
    global config, api, coordinator, media_players, remotes, entities_ready
    
    async with initialization_lock:
        if entities_ready:
            _LOG.debug("Entities already initialized")
            return
            
        if not config or not config.is_configured():
            _LOG.info("No configuration found")
            return

        _LOG.info("Initializing HEOS integration...")
        await api.set_device_state(DeviceStates.CONNECTING)
        
        try:
            api.available_entities.clear()
            media_players.clear()
            remotes.clear()
            
            coordinator = HeosCoordinator(api, config)
            await coordinator.async_setup()
            
            players = coordinator.heos.players
            if not players:
                _LOG.warning("No HEOS devices found")
                await api.set_device_state(DeviceStates.ERROR)
                return

            _LOG.info(f"Found {len(players)} HEOS device(s)")
            
            for player_id, player in players.items():
                _LOG.info(f"Setting up device: {player.name} (ID: {player_id})")
                
                media_player = HeosMediaPlayer(coordinator, player, api)
                await media_player.initialize()
                
                media_players[player_id] = media_player
                api.available_entities.add(media_player)
                
                _LOG.info(f"Created media player: {media_player.id}")
            
            if len(players) > 1:
                _LOG.info("Creating remote entities for multi-device setup")
                for player_id, player in players.items():
                    remote = HeosRemote(
                        heos_player=player,
                        device_name=player.name,
                        api=api,
                        all_players=players
                    )
                    
                    remote.set_heos(coordinator.heos)
                    await remote.initialize()
                    
                    remotes[player_id] = remote
                    api.available_entities.add(remote)
                    
                    _LOG.info(f"Created remote: {remote.id}")
            
            entities_ready = True
            await api.set_device_state(DeviceStates.CONNECTED)
            _LOG.info(f"Integration initialized: {len(media_players)} players, {len(remotes)} remotes")
            
        except Exception as e:
            _LOG.error(f"Failed to initialize: {e}", exc_info=True)
            entities_ready = False
            await api.set_device_state(DeviceStates.ERROR)
            if coordinator:
                await coordinator.async_shutdown()
                coordinator = None


async def setup_handler(msg: ucapi.SetupDriver) -> ucapi.SetupAction:
    """Handle setup flow."""
    global setup_manager
    
    if not setup_manager:
        return SetupError()
    
    action = await setup_manager.handle_setup(msg)
    
    if isinstance(action, SetupComplete):
        _LOG.info("Setup complete")
        await _initialize_integration()
    
    return action


async def on_subscribe_entities(entity_ids: List[str]):
    """Handle entity subscription."""
    global media_players, remotes, entities_ready
    
    _LOG.info(f"Subscription requested: {entity_ids}")
    
    if not entities_ready:
        _LOG.error("Entities not ready, initializing now")
        await _initialize_integration()
        if not entities_ready:
            return
    
    for entity_id in entity_ids:
        for player_id, media_player in media_players.items():
            if media_player.id == entity_id:
                _LOG.info(f"Subscribing media player: {entity_id}")
                api.configured_entities.add(media_player)
                await media_player.update_attributes()
                break
        
        for player_id, remote in remotes.items():
            if remote.id == entity_id:
                _LOG.info(f"Subscribing remote: {entity_id}")
                api.configured_entities.add(remote)
                await remote.update_attributes()
                break


async def on_unsubscribe_entities(entity_ids: List[str]):
    """Handle entity unsubscription."""
    _LOG.info(f"Unsubscribed: {entity_ids}")


async def on_connect():
    """Handle Remote connection."""
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
    
    _LOG.info("Starting HEOS integration v1.0.29")
    
    try:
        loop = asyncio.get_running_loop()
        config = HeosConfig()
        config.load()
        
        driver_path = os.path.join(os.path.dirname(__file__), "..", "driver.json")
        api = IntegrationAPI(loop)
        
        if config.is_configured():
            _LOG.info("Pre-initializing entities")
            asyncio.create_task(_initialize_integration())
        
        api.add_listener(Events.SUBSCRIBE_ENTITIES, on_subscribe_entities)
        api.add_listener(Events.UNSUBSCRIBE_ENTITIES, on_unsubscribe_entities)
        api.add_listener(Events.CONNECT, on_connect)
        api.add_listener(Events.DISCONNECT, on_disconnect)
        
        setup_manager = HeosSetupManager(config)
        
        await api.init(os.path.abspath(driver_path), setup_handler)
        
        if not config.is_configured():
            await api.set_device_state(DeviceStates.DISCONNECTED)
        
        await asyncio.Future()
        
    except Exception as e:
        _LOG.error(f"Fatal error: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())