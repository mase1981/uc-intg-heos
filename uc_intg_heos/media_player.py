"""
HEOS Media Player Entity.

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

from pyheos import HeosError, HeosPlayer, AddCriteriaType, PlayState, RepeatType, const as heos_const
from pyheos.types import MediaType as HeosMediaType

from uc_intg_heos.coordinator import HeosCoordinator

_LOG = logging.getLogger(__name__)

# State mapping from HEOS to ucapi
PLAY_STATE_TO_STATE = {
    None: States.STANDBY,
    PlayState.UNKNOWN: States.STANDBY,
    PlayState.PLAY: States.PLAYING,
    PlayState.STOP: States.STANDBY,
    PlayState.PAUSE: States.PAUSED,
}

# Repeat mode mapping
HEOS_HA_REPEAT_TYPE_MAP = {
    RepeatType.OFF: RepeatMode.OFF,
    RepeatType.ON_ALL: RepeatMode.ALL,
    RepeatType.ON_ONE: RepeatMode.ONE,
}
HA_HEOS_REPEAT_TYPE_MAP = {v: k for k, v in HEOS_HA_REPEAT_TYPE_MAP.items()}


class HeosMediaPlayer(MediaPlayer):
    """HEOS Media Player with comprehensive functionality."""

    def __init__(self, coordinator: HeosCoordinator, player: HeosPlayer, api: ucapi.IntegrationAPI):
        """Initialize the HEOS media player."""
        entity_id = f"heos_{player.name.lower().replace(' ', '_').replace('-', '_')}"
        
        # Build comprehensive feature list
        features = self._build_feature_list(player)
        
        # Initial attributes
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
            # Group information
            "group_members": [],
            "is_grouped": False,
            # HEOS specific attributes
            "media_station": "",
            "media_source_id": 0,
            "media_queue_id": 0,
            "heos_player_id": player.player_id,
        }
        
        # Add grouping-specific simple commands
        simple_commands = [
            # Favorites (first 10)
            "PLAY_FAVORITE_1", "PLAY_FAVORITE_2", "PLAY_FAVORITE_3", "PLAY_FAVORITE_4", "PLAY_FAVORITE_5",
            "PLAY_FAVORITE_6", "PLAY_FAVORITE_7", "PLAY_FAVORITE_8", "PLAY_FAVORITE_9", "PLAY_FAVORITE_10",
            # Input sources
            "AUX_1", "AUX_2", "OPTICAL_1", "OPTICAL_2", "BLUETOOTH",
            "HDMI_ARC", "CD", "TUNER", "PHONO", "USB",
            # Grouping commands
            "CREATE_GROUP", "LEAVE_GROUP",
            # Music services
            "SPOTIFY", "PANDORA", "TUNEIN", "SOUNDCLOUD", "AMAZON_MUSIC",
            # Queue management
            "CLEAR_QUEUE",
        ]
        
        # Store references
        self._coordinator = coordinator
        self._player = player
        self._player_id = player.player_id
        self._api = api
        self._media_position_updated_at: Optional[datetime] = None
        
        # Device information
        model_parts = player.model.split(maxsplit=1)
        manufacturer = model_parts[0] if len(model_parts) == 2 else "HEOS"
        model = model_parts[1] if len(model_parts) == 2 else player.model
        
        super().__init__(
            identifier=entity_id,
            name=player.name,
            features=features,
            attributes=attributes,
            device_class=DeviceClasses.SPEAKER,
            cmd_handler=self._command_handler,
            options={"simple_commands": simple_commands}
        )
        
        # Add to coordinator callback list
        self._coordinator.add_entity_callback(self._on_coordinator_update)
        
        _LOG.info(f"Created HEOS Media Player: {player.name} ({entity_id})")

    def _build_feature_list(self, player: HeosPlayer) -> List[Features]:
        """Build feature list based on player capabilities."""
        features = [
            # Basic playback
            Features.ON_OFF,
            Features.PLAY_PAUSE,
            Features.STOP,
            
            # Volume control
            Features.VOLUME,
            Features.VOLUME_UP_DOWN,
            Features.MUTE_TOGGLE,
            Features.MUTE,
            Features.UNMUTE,
            
            # Navigation
            Features.NEXT,
            Features.PREVIOUS,
            
            # Advanced features
            Features.REPEAT,
            Features.SHUFFLE,
            Features.SELECT_SOURCE,
            
            # Media information
            Features.MEDIA_DURATION,
            Features.MEDIA_POSITION,
            Features.MEDIA_TITLE,
            Features.MEDIA_ARTIST,
            Features.MEDIA_ALBUM,
            Features.MEDIA_IMAGE_URL,
            Features.MEDIA_TYPE,
        ]
        
        return features

    async def initialize(self) -> None:
        """Initialize the media player and set up event listeners."""
        # Set up player event listener
        self._player.add_on_player_event(self._on_player_event)
        
        # Initial state update
        await self.push_update()
        
        _LOG.info(f"HEOS Media Player initialized: {self.name}")

    async def _on_player_event(self, event: str) -> None:
        """Handle player-specific events."""
        if event == heos_const.EVENT_PLAYER_NOW_PLAYING_PROGRESS:
            self._media_position_updated_at = datetime.now()
        
        # Update state and push to Remote
        await self.push_update()

    def _on_coordinator_update(self) -> None:
        """Handle coordinator updates (groups, sources, etc.)."""
        asyncio.create_task(self.push_update())

    async def update_attributes(self) -> None:
    """Update entity state and push to Remote."""
    try:
        await self._update_device_state()
        
        if self._api and self._api.configured_entities.contains(self.id):
            self._api.configured_entities.update_attributes(self.id, self.attributes)
        
    except Exception as e:
        _LOG.error(f"Error updating {self.name}: {e}")

    async def _update_device_state(self) -> None:
        """Update device state from HEOS player."""
        try:
            # Refresh player state
            await self._player.refresh()
            
            # Map play state
            self.attributes[Attributes.STATE] = PLAY_STATE_TO_STATE.get(
                self._player.state, States.STANDBY
            )
            
            # Volume and mute
            self.attributes[Attributes.VOLUME] = self._player.volume
            self.attributes[Attributes.MUTED] = self._player.is_muted
            
            # Now playing media
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
                
                # HEOS specific attributes
                self.attributes["media_station"] = now_playing.station or ""
                self.attributes["media_source_id"] = now_playing.source_id or 0
                self.attributes["media_queue_id"] = now_playing.queue_id or 0
            
            # Repeat and shuffle
            self.attributes[Attributes.REPEAT] = HEOS_HA_REPEAT_TYPE_MAP.get(
                self._player.repeat, RepeatMode.OFF
            )
            self.attributes[Attributes.SHUFFLE] = self._player.shuffle
            
            # Source list and current source
            self.attributes[Attributes.SOURCE_LIST] = self._coordinator.get_source_list()
            self.attributes[Attributes.SOURCE] = self._coordinator.get_current_source(now_playing)
            
            # Group information
            await self._update_group_state()
            
        except HeosError as e:
            _LOG.error(f"Failed to update device state for {self.name}: {e}")
            self.attributes[Attributes.STATE] = States.UNAVAILABLE
        except Exception as e:
            _LOG.error(f"Unexpected error updating device state for {self.name}: {e}", exc_info=True)
            self.attributes[Attributes.STATE] = States.UNAVAILABLE

    async def _update_group_state(self):
        """Update group state information."""
        try:
            group_members = []
            is_grouped = False
            
            # Check if we have any groups
            if self._coordinator.heos and self._coordinator.heos.groups:
                _LOG.debug(f"Found {len(self._coordinator.heos.groups)} groups")
                
                for group_id, group in self._coordinator.heos.groups.items():
                    _LOG.debug(f"Checking group {group_id}: leader={group.lead_player_id}, members={group.member_player_ids}")
                    
                    if (self._player_id in group.member_player_ids or 
                        self._player_id == group.lead_player_id):
                        is_grouped = True
                        
                        # Add leader
                        if group.lead_player_id in self._coordinator.heos.players:
                            leader = self._coordinator.heos.players[group.lead_player_id]
                            group_members.append(f"{leader.name} (Leader)")
                        
                        # Add members
                        for member_id in group.member_player_ids:
                            if member_id in self._coordinator.heos.players:
                                member = self._coordinator.heos.players[member_id]
                                group_members.append(member.name)
                        break
            else:
                _LOG.debug("No groups found or no HEOS connection")
            
            self.attributes["group_members"] = group_members if group_members else [self.name]
            self.attributes["is_grouped"] = is_grouped
            
            _LOG.debug(f"Group state - is_grouped: {is_grouped}, members: {group_members}")
            
        except Exception as e:
            _LOG.error(f"Error updating group state for {self.name}: {e}")
            self.attributes["group_members"] = [self.name]
            self.attributes["is_grouped"] = False

    async def _auto_play_from_browse(self, source_name: str, source_id: int) -> bool:
        """
        Intelligently browse and auto-play from a music service.
        Returns True if playback started, False otherwise.
        """
        try:
            # Check if we have a remembered container for this source
            preferred_container = self._coordinator.get_preferred_container(source_name)
            
            if preferred_container:
                # Try the remembered container first
                _LOG.info(f"Using remembered container for {source_name}: {preferred_container}")
                container_items = await self._coordinator.browse_container(source_id, preferred_container)
                if container_items:
                    for item in container_items:
                        if hasattr(item, 'type') and item.type in ['song', 'station']:
                            _LOG.info(f"Auto-playing from remembered container: {item.name}")
                            await self._player.play_media(item)
                            self._coordinator.remember_content(source_name, {'name': item.name, 'type': item.type})
                            return True
            
            # Browse the top level
            _LOG.info(f"Browsing {source_name} for auto-play...")
            browse_items = await self._coordinator.browse_music_source(source_id)
            
            if not browse_items:
                _LOG.warning(f"No items found in {source_name}")
                return False
            
            _LOG.info(f"{source_name} browse result: {len(browse_items)} items found")
            
            # Look for directly playable items first
            for item in browse_items:
                item_type = getattr(item, 'type', 'unknown')
                if item_type in ['song', 'station']:
                    _LOG.info(f"Auto-playing {item_type}: {item.name}")
                    await self._player.play_media(item)
                    self._coordinator.remember_content(source_name, {'name': item.name, 'type': item_type})
                    return True
            
            # No direct playable items - dive into first promising container
            # Prioritize containers in this order
            priority_keywords = [
                ('station', 10),      # Stations highest priority
                ('recommended', 9),   # Recommended content
                ('playlist', 8),      # Playlists
                ('prime', 7),         # Amazon Prime content
                ('my music', 6),      # User's music
                ('new', 5),           # New releases
                ('chart', 4),         # Charts
            ]
            
            scored_containers = []
            for item in browse_items:
                item_name_lower = item.name.lower()
                item_type = getattr(item, 'type', 'unknown')
                
                score = 0
                for keyword, priority in priority_keywords:
                    if keyword in item_name_lower or keyword == item_type:
                        score = max(score, priority)
                
                if hasattr(item, 'container_id') and item.container_id:
                    scored_containers.append((score, item))
            
            # Sort by score (highest first)
            scored_containers.sort(key=lambda x: x[0], reverse=True)
            
            # Try containers in priority order
            for score, item in scored_containers:
                _LOG.info(f"Diving into container: {item.name} (priority: {score})")
                
                try:
                    container_items = await self._coordinator.browse_container(source_id, item.container_id)
                    
                    if container_items:
                        # Remember this container for next time
                        self._coordinator.remember_container(source_name, item.container_id)
                        
                        # Play first playable item
                        for sub_item in container_items:
                            sub_type = getattr(sub_item, 'type', 'unknown')
                            if sub_type in ['song', 'station']:
                                _LOG.info(f"Auto-playing from container: {sub_item.name}")
                                await self._player.play_media(sub_item)
                                self._coordinator.remember_content(source_name, {'name': sub_item.name, 'type': sub_type})
                                return True
                except Exception as e:
                    _LOG.warning(f"Error browsing container {item.name}: {e}")
                    continue
            
            _LOG.warning(f"Could not find playable content in {source_name}")
            return False
            
        except Exception as e:
            _LOG.error(f"Error auto-playing from {source_name}: {e}")
            return False

    async def _command_handler(self, entity: MediaPlayer, cmd_id: str, params: Dict[str, Any] = None) -> StatusCodes:
        """Handle media player commands."""
        try:
            params = params or {}
            _LOG.info(f"Executing HEOS command: {cmd_id} for {self.name}")
            
            # Basic playback commands
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
                
            # Navigation commands
            elif cmd_id == Commands.NEXT:
                await self._player.play_next()
                
            elif cmd_id == Commands.PREVIOUS:
                await self._player.play_previous()
                
            # Volume commands
            elif cmd_id == Commands.VOLUME_UP:
                step = params.get("step", 5)
                await self._player.volume_up(step)
                
            elif cmd_id == Commands.VOLUME_DOWN:
                step = params.get("step", 5)
                await self._player.volume_down(step)
                
            elif cmd_id == Commands.VOLUME:
                volume_level = params.get("volume", 50)
                await self._player.set_volume(int(volume_level))
                
            elif cmd_id == Commands.MUTE_TOGGLE:
                await self._player.toggle_mute()
                
            elif cmd_id == Commands.MUTE:
                await self._player.set_mute(True)
                
            elif cmd_id == Commands.UNMUTE:
                await self._player.set_mute(False)
                
            # Repeat and shuffle
            elif cmd_id == Commands.REPEAT:
                repeat_mode = params.get("repeat", "OFF")
                heos_repeat = HA_HEOS_REPEAT_TYPE_MAP.get(RepeatMode(repeat_mode), RepeatType.OFF)
                await self._player.set_play_mode(heos_repeat, self._player.shuffle)
                
            elif cmd_id == Commands.SHUFFLE:
                shuffle_state = params.get("shuffle", False)
                await self._player.set_play_mode(self._player.repeat, shuffle_state)
                
            # Source selection
            elif cmd_id == Commands.SELECT_SOURCE:
                source_name = params.get("source")
                if source_name:
                    await self._handle_select_source(source_name)
                
            # Grouping commands
            elif cmd_id == "join":
                group_members = params.get("group_members", [])
                await self._handle_join_players(group_members)
                
            elif cmd_id == "unjoin":
                await self._handle_unjoin_player()
                
            # Simple commands (HEOS-specific)
            elif cmd_id.startswith("PLAY_FAVORITE_"):
                favorite_num = int(cmd_id.split("_")[-1])
                await self._handle_play_favorite(favorite_num)
                
            elif cmd_id in ["AUX_1", "AUX_2", "OPTICAL_1", "OPTICAL_2", "BLUETOOTH", "HDMI_ARC", "CD", "TUNER", "PHONO", "USB"]:
                await self._handle_input_source(cmd_id)
                
            elif cmd_id == "CREATE_GROUP":
                available_players = [p.name for p in self._coordinator.heos.players.values() 
                                   if p.player_id != self._player_id]
                _LOG.info(f"CREATE_GROUP command - available players to group with: {available_players}")
                
            elif cmd_id == "LEAVE_GROUP":
                await self._handle_unjoin_player()
                
            elif cmd_id in ["SPOTIFY", "PANDORA", "TUNEIN", "SOUNDCLOUD", "AMAZON_MUSIC"]:
                await self._handle_music_service(cmd_id)
                
            elif cmd_id == "CLEAR_QUEUE":
                await self._player.clear_queue()
                
            else:
                _LOG.warning(f"Unsupported command '{cmd_id}' for HEOS media player")
                return StatusCodes.NOT_IMPLEMENTED

            # Update state after command
            await asyncio.sleep(0.5)  # Give device time to process
            await self.push_update()
            
            return StatusCodes.OK
            
        except HeosError as e:
            _LOG.error(f"HEOS command failed for '{cmd_id}': {e}")
            return StatusCodes.SERVER_ERROR
        except Exception as e:
            _LOG.error(f"Error handling command '{cmd_id}': {e}", exc_info=True)
            return StatusCodes.SERVER_ERROR

    async def _handle_select_source(self, source_name: str) -> None:
        """Handle source selection with intelligent auto-play."""
        _LOG.info(f"Selecting source: {source_name}")
        
        try:
            # First try favorites (preset stations)
            if source_name in [fav.name for fav in self._coordinator.favorites.values()]:
                favorite_index = self._coordinator.get_favorite_index(source_name)
                if favorite_index is not None:
                    _LOG.info(f"Playing favorite preset {favorite_index}: {source_name}")
                    await self._player.play_preset_station(favorite_index)
                    return
            
            # Try input sources
            input_source = self._coordinator.find_input_source(source_name)
            if input_source:
                _LOG.info(f"Playing input source: {source_name}")
                await self._player.play_media(input_source)
                return
            
            # Try playlists
            playlist = self._coordinator.find_playlist(source_name)
            if playlist:
                _LOG.info(f"Playing playlist: {source_name}")
                await self._player.play_media(playlist, AddCriteriaType.REPLACE_AND_PLAY)
                return
            
            # Try music services with intelligent auto-play
            music_source_info = self._coordinator.find_music_source(source_name)
            if music_source_info:
                source_id, music_source = music_source_info
                _LOG.info(f"Found music service: {source_name} (ID: {source_id})")
                
                # Use intelligent auto-play for all services
                success = await self._auto_play_from_browse(source_name, source_id)
                if success:
                    _LOG.info(f"Successfully auto-played from {source_name}")
                    return
                else:
                    _LOG.info(f"Browsed {source_name} but no auto-play occurred")
                    return
            
            raise HeosError(f"Source not found or not available: {source_name}")
            
        except Exception as e:
            _LOG.error(f"Error selecting source {source_name}: {e}")
            raise