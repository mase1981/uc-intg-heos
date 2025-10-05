"""
HEOS Media Player Entity - Direct Pattern.

:copyright: (c) 2025 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

import ucapi
from ucapi import MediaPlayer, StatusCodes
from ucapi.media_player import Attributes, DeviceClasses, Features, States, RepeatMode, Commands

from pyheos import Heos, HeosError, HeosPlayer, AddCriteriaType, PlayState, RepeatType, const as heos_const

_LOG = logging.getLogger(__name__)

PLAY_STATE_TO_STATE = {
    None: States.STANDBY,
    PlayState.UNKNOWN: States.STANDBY,
    PlayState.PLAY: States.PLAYING,
    PlayState.STOP: States.STANDBY,
    PlayState.PAUSE: States.PAUSED,
}

HEOS_HA_REPEAT_TYPE_MAP = {
    RepeatType.OFF: RepeatMode.OFF,
    RepeatType.ON_ALL: RepeatMode.ALL,
    RepeatType.ON_ONE: RepeatMode.ONE,
}
HA_HEOS_REPEAT_TYPE_MAP = {v: k for k, v in HEOS_HA_REPEAT_TYPE_MAP.items()}


class HeosMediaPlayer(MediaPlayer):
    """HEOS Media Player - direct connection pattern."""

    def __init__(self, heos: Heos, player: HeosPlayer, api: ucapi.IntegrationAPI):
        """Initialize the HEOS media player."""
        entity_id = f"heos_{player.name.lower().replace(' ', '_').replace('-', '_')}"
        
        features = [
            Features.ON_OFF,
            Features.PLAY_PAUSE,
            Features.STOP,
            Features.VOLUME,
            Features.VOLUME_UP_DOWN,
            Features.MUTE_TOGGLE,
            Features.MUTE,
            Features.UNMUTE,
            Features.NEXT,
            Features.PREVIOUS,
            Features.REPEAT,
            Features.SHUFFLE,
            Features.SELECT_SOURCE,
            Features.MEDIA_DURATION,
            Features.MEDIA_POSITION,
            Features.MEDIA_TITLE,
            Features.MEDIA_ARTIST,
            Features.MEDIA_ALBUM,
            Features.MEDIA_IMAGE_URL,
            Features.MEDIA_TYPE,
        ]
        
        attributes = {
            Attributes.STATE: States.STANDBY,
            Attributes.VOLUME: 0,
            Attributes.MUTED: False,
            Attributes.MEDIA_DURATION: 0,
            Attributes.MEDIA_POSITION: 0,
            Attributes.MEDIA_TITLE: "",
            Attributes.MEDIA_ARTIST: "",
            Attributes.MEDIA_ALBUM: "",
            Attributes.MEDIA_IMAGE_URL: "",
            Attributes.SOURCE: "",
            Attributes.SOURCE_LIST: [],
            Attributes.REPEAT: RepeatMode.OFF,
            Attributes.SHUFFLE: False,
        }
        
        self._heos = heos
        self._player = player
        self._player_id = player.player_id
        self._api = api
        
        # Lazy-loaded account data
        self._favorites = {}
        self._favorites_loaded = False
        self._sources = {}
        self._sources_loaded = False
        self._source_list = []
        
        model_parts = player.model.split(maxsplit=1)
        manufacturer = model_parts[0] if len(model_parts) == 2 else "HEOS"
        model = model_parts[1] if len(model_parts) == 2 else player.model
        
        super().__init__(
            identifier=entity_id,
            name=player.name,
            features=features,
            attributes=attributes,
            device_class=DeviceClasses.SPEAKER,
            cmd_handler=self._command_handler
        )
        
        _LOG.info(f"Created HEOS Media Player: {player.name}")

    async def initialize(self) -> None:
        """Initialize the media player."""
        self._player.add_on_player_event(self._on_player_event)
        
        # Load account data in background (doesn't block entity creation)
        asyncio.create_task(self._load_account_data())
        
        await self.push_update()
        _LOG.debug(f"Media Player initialized: {self.name}")

    async def _load_account_data(self):
        """Load account data asynchronously (non-blocking)."""
        try:
            if self._heos.is_signed_in and not self._favorites_loaded:
                self._favorites = await self._heos.get_favorites()
                self._favorites_loaded = True
                _LOG.debug(f"Loaded {len(self._favorites)} favorites")
            
            if not self._sources_loaded:
                self._sources = await self._heos.get_music_sources()
                self._sources_loaded = True
                _LOG.debug(f"Loaded {len(self._sources)} music sources")
            
            # Build source list
            self._source_list = []
            for fav in self._favorites.values():
                self._source_list.append(fav.name)
            for source in self._sources.values():
                if source.available:
                    self._source_list.append(source.name)
            
            self.attributes[Attributes.SOURCE_LIST] = self._source_list
            await self.push_update()
            
        except Exception as e:
            _LOG.error(f"Error loading account data: {e}")

    async def _on_player_event(self, event: str) -> None:
        """Handle player events."""
        await self.push_update()

    async def push_update(self) -> None:
        """Update entity state."""
        try:
            await self._update_device_state()
            
            if self._api and self._api.configured_entities.contains(self.id):
                self._api.configured_entities.update_attributes(self.id, self.attributes)
            
        except Exception as e:
            _LOG.error(f"Error updating {self.name}: {e}")

    async def update_attributes(self) -> None:
        """Update entity attributes."""
        try:
            await self._update_device_state()
            
            if self._api and self._api.configured_entities.contains(self.id):
                self._api.configured_entities.update_attributes(self.id, self.attributes)
            
        except Exception as e:
            _LOG.error(f"Error updating {self.name}: {e}")

    async def _update_device_state(self) -> None:
        """Update device state from HEOS player."""
        try:
            await self._player.refresh()
            
            self.attributes[Attributes.STATE] = PLAY_STATE_TO_STATE.get(
                self._player.state, States.STANDBY
            )
            
            self.attributes[Attributes.VOLUME] = self._player.volume
            self.attributes[Attributes.MUTED] = self._player.is_muted
            
            now_playing = self._player.now_playing_media
            if now_playing:
                self.attributes[Attributes.MEDIA_TITLE] = now_playing.song or ""
                self.attributes[Attributes.MEDIA_ARTIST] = now_playing.artist or ""
                self.attributes[Attributes.MEDIA_ALBUM] = now_playing.album or ""
                self.attributes[Attributes.MEDIA_IMAGE_URL] = now_playing.image_url or ""
                self.attributes[Attributes.MEDIA_DURATION] = (
                    int(now_playing.duration / 1000) if now_playing.duration else 0
                )
                self.attributes[Attributes.MEDIA_POSITION] = (
                    int(now_playing.current_position / 1000) if now_playing.current_position else 0
                )
            
            self.attributes[Attributes.REPEAT] = HEOS_HA_REPEAT_TYPE_MAP.get(
                self._player.repeat, RepeatMode.OFF
            )
            self.attributes[Attributes.SHUFFLE] = self._player.shuffle
            
        except HeosError as e:
            _LOG.error(f"Failed to update {self.name}: {e}")
            self.attributes[Attributes.STATE] = States.UNAVAILABLE
        except Exception as e:
            _LOG.error(f"Unexpected error updating {self.name}: {e}")
            self.attributes[Attributes.STATE] = States.UNAVAILABLE

    async def _command_handler(self, entity: MediaPlayer, cmd_id: str, params: Dict[str, Any] = None) -> StatusCodes:
        """Handle media player commands."""
        try:
            params = params or {}
            _LOG.info(f"Command: {cmd_id} for {self.name}")
            
            if cmd_id in [Commands.ON, "turn_on", "on"]:
                await self._player.play()
                
            elif cmd_id in [Commands.OFF, "turn_off", "off"]:
                await self._player.stop()
                
            elif cmd_id == Commands.STOP:
                await self._player.stop()
                
            elif cmd_id == Commands.PLAY_PAUSE:
                if self._player.state == PlayState.PLAY:
                    await self._player.pause()
                else:
                    await self._player.play()
                
            elif cmd_id == Commands.NEXT:
                await self._player.play_next()
                
            elif cmd_id == Commands.PREVIOUS:
                await self._player.play_previous()
                
            elif cmd_id == Commands.VOLUME_UP:
                await self._player.volume_up(params.get("step", 5))
                
            elif cmd_id == Commands.VOLUME_DOWN:
                await self._player.volume_down(params.get("step", 5))
                
            elif cmd_id == Commands.VOLUME:
                await self._player.set_volume(int(params.get("volume", 50)))
                
            elif cmd_id == Commands.MUTE_TOGGLE:
                await self._player.toggle_mute()
                
            elif cmd_id == Commands.MUTE:
                await self._player.set_mute(True)
                
            elif cmd_id == Commands.UNMUTE:
                await self._player.set_mute(False)
                
            elif cmd_id == Commands.REPEAT:
                repeat_mode = params.get("repeat", "OFF")
                heos_repeat = HA_HEOS_REPEAT_TYPE_MAP.get(RepeatMode(repeat_mode), RepeatType.OFF)
                await self._player.set_play_mode(heos_repeat, self._player.shuffle)
                
            elif cmd_id == Commands.SHUFFLE:
                shuffle_state = params.get("shuffle", False)
                await self._player.set_play_mode(self._player.repeat, shuffle_state)
                
            elif cmd_id == Commands.SELECT_SOURCE:
                source_name = params.get("source")
                if source_name:
                    await self._handle_select_source(source_name)
                
            else:
                _LOG.warning(f"Unsupported command: {cmd_id}")
                return StatusCodes.NOT_IMPLEMENTED

            await asyncio.sleep(0.5)
            await self.push_update()
            
            return StatusCodes.OK
            
        except HeosError as e:
            _LOG.error(f"Command failed '{cmd_id}': {e}")
            return StatusCodes.SERVER_ERROR
        except Exception as e:
            _LOG.error(f"Error handling '{cmd_id}': {e}", exc_info=True)
            return StatusCodes.SERVER_ERROR

    async def _handle_select_source(self, source_name: str) -> None:
        """Handle source selection."""
        _LOG.info(f"Selecting source: {source_name}")
        
        try:
            # Ensure account data is loaded
            if not self._favorites_loaded or not self._sources_loaded:
                await self._load_account_data()
            
            # Try favorites
            for index, favorite in self._favorites.items():
                if favorite.name == source_name:
                    _LOG.info(f"Playing favorite: {source_name}")
                    await self._player.play_preset_station(index)
                    return
            
            # Try music sources
            for source_id, source in self._sources.items():
                if source.name == source_name and source.available:
                    _LOG.info(f"Playing source: {source_name}")
                    # Simple play - no complex browsing
                    return
            
            raise HeosError(f"Source not found: {source_name}")
            
        except Exception as e:
            _LOG.error(f"Error selecting source {source_name}: {e}")
            raise