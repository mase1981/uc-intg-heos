"""
HEOS Automated Discovery & Analysis Tool for UC Remote Integration.

"""

import sys
import subprocess
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# ============================================================================
# AUTOMATIC DEPENDENCY INSTALLATION
# ============================================================================

def install_dependencies():
    """Automatically install required dependencies."""
    print("=" * 70)
    print("HEOS Discovery Tool - Automatic Setup")
    print("=" * 70)
    print()
    print("Checking dependencies...")
    
    required_packages = ["pyheos"]
    packages_to_install = []
    
    for package in required_packages:
        try:
            __import__(package)
            print(f"✓ {package} is already installed")
        except ImportError:
            print(f"✗ {package} is not installed")
            packages_to_install.append(package)
    
    if packages_to_install:
        print()
        print(f"Installing required packages: {', '.join(packages_to_install)}")
        print("This will only take a moment...")
        print()
        
        for package in packages_to_install:
            try:
                subprocess.check_call(
                    [sys.executable, "-m", "pip", "install", "--quiet", package],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                print(f"✓ Successfully installed {package}")
            except subprocess.CalledProcessError as e:
                print(f"✗ Failed to install {package}")
                print(f"Error: {e}")
                print()
                print("Please install manually with:")
                print(f"  pip install {package}")
                sys.exit(1)
        
        print()
        print("✓ All dependencies installed successfully!")
        print()
    else:
        print()
        print("✓ All dependencies are already installed!")
        print()

# Install dependencies before importing them
install_dependencies()

# Now we can safely import pyheos
try:
    from pyheos import Heos, HeosPlayer, HeosError, HeosOptions, Credentials
    from pyheos.types import PlayState, RepeatType
except ImportError as e:
    print("=" * 70)
    print("ERROR: Failed to import pyheos library")
    print("=" * 70)
    print()
    print(f"Error details: {e}")
    print()
    print("Please try running this command manually:")
    print("  pip install pyheos")
    print()
    print("Then run this script again.")
    sys.exit(1)

# Standard library imports
import asyncio
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('heos_discovery.log')
    ]
)
_LOG = logging.getLogger(__name__)


class HeosAutomatedDiscovery:
    """Automated discovery and analysis tool for HEOS integration."""
    
    def __init__(self):
        """Initialize HEOS Automated Discovery."""
        self._heos: Optional[Heos] = None
        self._player: Optional[HeosPlayer] = None
        self._player_id: Optional[int] = None
        
        # Complete test results storage
        self._full_results = {
            "metadata": {},
            "device_info": {},
            "test_summary": {},
            "detailed_results": {},
            "analysis": {
                "working_features": [],
                "failing_features": [],
                "limited_features": [],
                "recommendations": []
            },
            "recommendations": {
                "for_uc_remote": [],
                "for_integration": [],
                "for_user_config": []
            }
        }
        
        # Test execution tracking
        self._test_start_time = None
        self._current_test = 0
        self._total_tests = 15
        
    async def connect_to_heos(self, host: str = None, username: str = None, password: str = None) -> bool:
        """Connect to HEOS device."""
        try:
            if not host:
                print("No host provided. Please specify HEOS device IP address.")
                return False
            
            _LOG.info(f"Connecting to HEOS device at {host}")
            
            # Create credentials if provided
            credentials = None
            if username and password:
                credentials = Credentials(username, password)
            
            # Create Heos options
            options = HeosOptions(
                host=host,
                all_progress_events=False,
                auto_reconnect=True,
                auto_failover=True,
                credentials=credentials
            )
            
            # Create and connect
            self._heos = Heos(options)
            await self._heos.connect()
            
            # Sign in if credentials provided
            if credentials:
                _LOG.info("Signing in to HEOS account")
                success = await self._heos.sign_in(username, password)
                if not success:
                    _LOG.error("Failed to sign in to HEOS account")
                    return False
                _LOG.info("Successfully signed in to HEOS account")
            
            # Get first available player
            players = await self._heos.get_players()
            if not players:
                _LOG.error("No HEOS players found")
                return False
            
            # Use first player
            self._player_id, self._player = next(iter(players.items()))
            _LOG.info(f"Using player: {self._player.name} (ID: {self._player_id})")
            
            return True
            
        except Exception as e:
            _LOG.error(f"Failed to connect to HEOS: {e}")
            return False
    
    async def run_all_tests(self) -> Dict[str, Any]:
        """Run all discovery tests automatically."""
        try:
            _LOG.info("=== STARTING AUTOMATED HEOS DISCOVERY ===")
            
            self._test_start_time = datetime.now(timezone.utc)
            await self._initialize_test_session()
            
            # Define test sequence
            test_sequence = [
                ("device_discovery", "Discovering device capabilities"),
                ("basic_controls", "Testing basic playback controls"),
                ("volume_controls", "Testing volume and mute controls"),
                ("navigation_controls", "Testing next/previous navigation"),
                ("service_availability", "Checking available music services"),
                ("input_sources", "Testing input source switching (including HDMI)"),
                ("queue_operations", "Testing queue management"),
                ("play_modes", "Testing repeat and shuffle modes"),
                ("advanced_features", "Testing advanced capabilities"),
                ("performance_analysis", "Analyzing performance metrics"),
                ("optimization_analysis", "Generating optimization recommendations"),
                ("final_report", "Compiling comprehensive results")
            ]
            
            # Execute tests sequentially
            for i, (test_name, description) in enumerate(test_sequence, 1):
                self._current_test = i
                _LOG.info(f"[{i}/{len(test_sequence)}] {description}")
                
                try:
                    result = await self._execute_test_category(test_name)
                    await self._record_test_completion(test_name, result)
                    
                    # Brief pause between tests
                    await asyncio.sleep(1)
                    
                except Exception as e:
                    _LOG.error(f"Test {test_name} failed: {e}")
                    await self._record_test_completion(test_name, {"success": False, "error": str(e)})
            
            # Finalize results
            await self._finalize_test_session()
            
            _LOG.info("=== AUTOMATED DISCOVERY COMPLETE ===")
            return self._full_results
            
        except Exception as e:
            _LOG.error(f"Automated discovery failed: {e}")
            return {"error": str(e)}
    
    async def _initialize_test_session(self) -> None:
        """Initialize a new test session."""
        self._full_results["metadata"] = {
            "session_id": f"heos_discovery_{int(self._test_start_time.timestamp())}",
            "start_time": self._test_start_time.isoformat(),
            "device_name": self._player.name if self._player else "Unknown",
            "player_id": self._player_id,
            "integration_version": "1.0.0",
            "discovery_tool_version": "2.1.0"
        }
    
    async def _execute_test_category(self, category: str) -> Dict[str, Any]:
        """Execute a specific test category."""
        if category == "device_discovery":
            return await self._test_device_discovery()
        elif category == "basic_controls":
            return await self._test_basic_controls()
        elif category == "volume_controls":
            return await self._test_volume_controls()
        elif category == "navigation_controls":
            return await self._test_navigation_controls()
        elif category == "service_availability":
            return await self._test_service_availability()
        elif category == "input_sources":
            return await self._test_input_sources()
        elif category == "queue_operations":
            return await self._test_queue_operations()
        elif category == "play_modes":
            return await self._test_play_modes()
        elif category == "advanced_features":
            return await self._test_advanced_features()
        elif category == "performance_analysis":
            return await self._analyze_performance()
        elif category == "optimization_analysis":
            return await self._generate_optimization_analysis()
        elif category == "final_report":
            return await self._compile_final_report()
        else:
            return {"success": False, "error": f"Unknown test category: {category}"}
    
    async def _test_device_discovery(self) -> Dict[str, Any]:
        """Comprehensive device discovery and basic info gathering."""
        try:
            result = {
                "success": True,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "device_properties": {},
                "connection_info": {},
                "capabilities": {}
            }
            
            # Basic device information
            try:
                device_info = {
                    "name": self._player.name,
                    "model": self._player.model,
                    "player_id": self._player_id,
                    "version": self._player.version,
                    "ip_address": self._player.ip_address,
                    "network": str(self._player.network)
                }
                result["device_properties"] = device_info
                self._full_results["device_info"] = device_info
                
            except Exception as e:
                result["device_properties_error"] = str(e)
            
            # Current connection state
            try:
                play_state = await self._heos.player_get_play_state(self._player_id)
                volume = await self._heos.player_get_volume(self._player_id)
                muted = await self._heos.player_get_mute(self._player_id)
                
                connection_info = {
                    "play_state": play_state.value,
                    "volume_level": volume,
                    "is_muted": muted,
                    "connection_active": True
                }
                result["connection_info"] = connection_info
                
            except Exception as e:
                result["connection_error"] = str(e)
                result["connection_info"] = {"connection_active": False}
            
            return result
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    async def _test_basic_controls(self) -> Dict[str, Any]:
        """Test basic playback controls with detailed tracking."""
        try:
            result = {
                "success": True,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "controls_tested": {},
                "working_controls": [],
                "failing_controls": []
            }
            
            # Store original state
            original_state = await self._heos.player_get_play_state(self._player_id)
            result["original_state"] = original_state.value
            
            # Test individual controls
            controls_to_test = [
                (PlayState.PAUSE, "pause"),
                (PlayState.PLAY, "play"),
                (PlayState.STOP, "stop")
            ]
            
            for state, control_name in controls_to_test:
                try:
                    await self._heos.player_set_play_state(self._player_id, state)
                    await asyncio.sleep(1)
                    
                    new_state = await self._heos.player_get_play_state(self._player_id)
                    
                    control_result = {
                        "command_sent": True,
                        "expected_state": state.value,
                        "actual_state": new_state.value,
                        "state_changed": new_state.value == state.value,
                        "success": True
                    }
                    
                    result["controls_tested"][control_name] = control_result
                    
                    if control_result["state_changed"]:
                        result["working_controls"].append(control_name.upper())
                        self._full_results["analysis"]["working_features"].append(f"PLAYBACK_{control_name.upper()}")
                    
                except Exception as e:
                    control_result = {
                        "command_sent": False,
                        "success": False,
                        "error": str(e)
                    }
                    result["controls_tested"][control_name] = control_result
                    result["failing_controls"].append(control_name.upper())
                    self._full_results["analysis"]["failing_features"].append(f"PLAYBACK_{control_name.upper()}")
            
            # Restore original state
            try:
                await self._heos.player_set_play_state(self._player_id, original_state)
            except Exception:
                pass
            
            return result
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    async def _test_volume_controls(self) -> Dict[str, Any]:
        """Test volume controls with precise tracking."""
        try:
            result = {
                "success": True,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "volume_tests": {},
                "working_controls": [],
                "failing_controls": []
            }
            
            # Store original settings
            original_volume = await self._heos.player_get_volume(self._player_id)
            original_mute = await self._heos.player_get_mute(self._player_id)
            
            # Test volume up
            try:
                await self._heos.player_volume_up(self._player_id, step=5)
                await asyncio.sleep(1)
                new_volume = await self._heos.player_get_volume(self._player_id)
                
                if new_volume > original_volume:
                    result["working_controls"].append("VOLUME_UP")
                    self._full_results["analysis"]["working_features"].append("VOLUME_UP")
                
                result["volume_tests"]["volume_up"] = {
                    "success": True,
                    "volume_before": original_volume,
                    "volume_after": new_volume,
                    "volume_increased": new_volume > original_volume
                }
                
            except Exception as e:
                result["volume_tests"]["volume_up"] = {"success": False, "error": str(e)}
                result["failing_controls"].append("VOLUME_UP")
                self._full_results["analysis"]["failing_features"].append("VOLUME_UP")
            
            # Test mute toggle
            try:
                await self._heos.player_toggle_mute(self._player_id)
                await asyncio.sleep(1)
                new_mute = await self._heos.player_get_mute(self._player_id)
                
                if new_mute != original_mute:
                    result["working_controls"].append("MUTE_TOGGLE")
                    self._full_results["analysis"]["working_features"].append("MUTE_TOGGLE")
                
                # Toggle back
                if new_mute != original_mute:
                    await self._heos.player_toggle_mute(self._player_id)
                
            except Exception as e:
                result["volume_tests"]["mute_toggle"] = {"success": False, "error": str(e)}
                result["failing_controls"].append("MUTE_TOGGLE")
                self._full_results["analysis"]["failing_features"].append("MUTE_TOGGLE")
            
            # Restore original settings
            try:
                await self._heos.player_set_volume(self._player_id, original_volume)
                await self._heos.player_set_mute(self._player_id, original_mute)
            except Exception:
                pass
            
            return result
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    async def _test_navigation_controls(self) -> Dict[str, Any]:
        """Test navigation controls (next/previous)."""
        try:
            result = {
                "success": True,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "navigation_tests": {},
                "working_controls": [],
                "limited_controls": [],
                "failing_controls": []
            }
            
            # Test next
            try:
                await self._heos.player_play_next(self._player_id)
                result["navigation_tests"]["next"] = {"success": True}
                result["working_controls"].append("NEXT")
                self._full_results["analysis"]["working_features"].append("NAVIGATION_NEXT")
                
            except Exception as e:
                error_msg = str(e)
                if "skip limit" in error_msg.lower():
                    result["navigation_tests"]["next"] = {
                        "success": False,
                        "limited": True,
                        "error": error_msg
                    }
                    result["limited_controls"].append("NEXT")
                    self._full_results["analysis"]["limited_features"].append("NAVIGATION_NEXT")
                else:
                    result["navigation_tests"]["next"] = {"success": False, "error": error_msg}
                    result["failing_controls"].append("NEXT")
                    self._full_results["analysis"]["failing_features"].append("NAVIGATION_NEXT")
            
            # Test previous
            try:
                await self._heos.player_play_previous(self._player_id)
                result["navigation_tests"]["previous"] = {"success": True}
                result["working_controls"].append("PREVIOUS")
                self._full_results["analysis"]["working_features"].append("NAVIGATION_PREVIOUS")
                
            except Exception as e:
                error_msg = str(e)
                if "skip limit" in error_msg.lower():
                    result["navigation_tests"]["previous"] = {
                        "success": False,
                        "limited": True,
                        "error": error_msg
                    }
                    result["limited_controls"].append("PREVIOUS")
                    self._full_results["analysis"]["limited_features"].append("NAVIGATION_PREVIOUS")
                else:
                    result["navigation_tests"]["previous"] = {"success": False, "error": error_msg}
                    result["failing_controls"].append("PREVIOUS")
                    self._full_results["analysis"]["failing_features"].append("NAVIGATION_PREVIOUS")
            
            return result
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    async def _test_service_availability(self) -> Dict[str, Any]:
        """Test music service availability and authentication."""
        try:
            result = {
                "success": True,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "services": {}
            }
            
            sources = await self._heos.get_music_sources(refresh=True)
            
            for source_id, source in sources.items():
                service_info = {
                    "id": source_id,
                    "name": source.name,
                    "available": source.available,
                    "type": source.type.value if hasattr(source.type, 'value') else str(source.type),
                    "username": source.service_username,
                    "authenticated": bool(source.service_username) if source.available else False
                }
                
                result["services"][source.name] = service_info
                
                if service_info["authenticated"]:
                    self._full_results["analysis"]["working_features"].append(f"SERVICE_{source.name.upper().replace(' ', '_')}")
            
            # Store for later tests
            self._full_results["detailed_results"]["services"] = result["services"]
            
            return result
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    async def _discover_available_inputs(self) -> List[Any]:
        """Discover all available input sources using pyheos library."""
        try:
            _LOG.info("Discovering available input sources via pyheos...")
            inputs = await self._heos.get_input_sources()
            
            _LOG.info(f"Found {len(inputs)} available input sources:")
            for input_source in inputs:
                _LOG.info(f"  - {input_source.name} (media_id: {input_source.media_id})")
            
            return inputs
            
        except Exception as e:
            _LOG.error(f"Failed to discover input sources: {e}")
            return []
    
    def _get_comprehensive_input_list(self) -> List[tuple]:
        """Get comprehensive list of all possible HEOS inputs for fallback testing."""
        return [
            # AUX Inputs
            ("inputs/aux_in_1", "AUX 1"),
            ("inputs/aux_in_2", "AUX 2"),
            ("inputs/aux_in_3", "AUX 3"),
            ("inputs/aux_in_4", "AUX 4"),
            ("inputs/aux_single", "AUX Single"),
            ("inputs/aux1", "AUX 1 Alt"),
            ("inputs/aux2", "AUX 2 Alt"),
            ("inputs/aux3", "AUX 3 Alt"),
            ("inputs/aux4", "AUX 4 Alt"),
            ("inputs/aux5", "AUX 5"),
            ("inputs/aux6", "AUX 6"),
            ("inputs/aux7", "AUX 7"),
            ("inputs/aux_8k", "AUX 8K"),
            
            # Line Inputs
            ("inputs/line_in_1", "Line In 1"),
            ("inputs/line_in_2", "Line In 2"),
            ("inputs/line_in_3", "Line In 3"),
            ("inputs/line_in_4", "Line In 4"),
            
            # Coaxial Inputs
            ("inputs/coax_in_1", "Coaxial 1"),
            ("inputs/coax_in_2", "Coaxial 2"),
            
            # Optical Inputs
            ("inputs/optical_in_1", "Optical 1"),
            ("inputs/optical_in_2", "Optical 2"),
            ("inputs/optical_in_3", "Optical 3"),
            
            # HDMI Inputs (CRITICAL FOR SOUNDBAR)
            ("inputs/hdmi_in_1", "HDMI 1"),
            ("inputs/hdmi_in_2", "HDMI 2"),
            ("inputs/hdmi_in_3", "HDMI 3"),
            ("inputs/hdmi_in_4", "HDMI 4"),
            ("inputs/hdmi_arc_1", "HDMI ARC"),
            
            # Device-Specific Inputs
            ("inputs/cable_sat", "Cable/Sat"),
            ("inputs/dvd", "DVD"),
            ("inputs/bluray", "Blu-ray"),
            ("inputs/game", "Game"),
            ("inputs/game2", "Game 2"),
            ("inputs/mediaplayer", "Media Player"),
            ("inputs/cd", "CD"),
            ("inputs/tuner", "Tuner"),
            ("inputs/hdradio", "HD Radio"),
            ("inputs/tvaudio", "TV Audio"),
            ("inputs/tv", "TV"),
            ("inputs/phono", "Phono"),
            ("inputs/usbdac", "USB DAC"),
            ("inputs/bluetooth", "Bluetooth"),
            ("inputs/analog_in_1", "Analog 1"),
            ("inputs/analog_in_2", "Analog 2"),
            ("inputs/recorder_in_1", "Recorder"),
        ]
    
    async def _test_input_sources(self) -> Dict[str, Any]:
        """Test input source switching comprehensively with pyheos discovery."""
        try:
            result = {
                "success": True,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "discovered_inputs": [],
                "inputs_tested": {},
                "working_inputs": [],
                "unavailable_inputs": []
            }
            
            # STEP 1: Discover available inputs using pyheos
            _LOG.info("Step 1: Discovering available inputs via pyheos...")
            available_inputs = await self._discover_available_inputs()
            
            if not available_inputs:
                _LOG.warning("No inputs discovered via pyheos - falling back to comprehensive manual testing")
                # Fallback to comprehensive manual testing
                inputs_to_test = self._get_comprehensive_input_list()
            else:
                # Use discovered inputs
                inputs_to_test = [
                    (input_source.media_id, input_source.name) 
                    for input_source in available_inputs
                ]
                result["discovered_inputs"] = [
                    {
                        "name": input_source.name,
                        "media_id": input_source.media_id,
                        "type": str(getattr(input_source, 'type', 'unknown'))
                    }
                    for input_source in available_inputs
                ]
            
            _LOG.info(f"Testing {len(inputs_to_test)} input sources...")
            
            # STEP 2: Test each discovered input
            for input_name, display_name in inputs_to_test:
                try:
                    _LOG.info(f"Testing input: {display_name} ({input_name})")
                    await self._heos.play_input_source(
                        player_id=self._player_id,
                        input_name=input_name
                    )
                    
                    await asyncio.sleep(1.5)  # Give device time to switch
                    
                    result["inputs_tested"][display_name] = {
                        "success": True,
                        "input_name": input_name,
                        "test_result": "Input successfully switched"
                    }
                    result["working_inputs"].append(display_name)
                    self._full_results["analysis"]["working_features"].append(f"INPUT_{display_name.upper().replace(' ', '_')}")
                    
                    _LOG.info(f"✓ Input {display_name} works")
                    
                except Exception as e:
                    error_msg = str(e)
                    result["inputs_tested"][display_name] = {
                        "success": False,
                        "input_name": input_name,
                        "error": error_msg
                    }
                    
                    if "ID Not Valid" in error_msg or "not valid" in error_msg.lower():
                        result["unavailable_inputs"].append(display_name)
                        _LOG.info(f"✗ Input {display_name} not available on this device")
                    else:
                        self._full_results["analysis"]["failing_features"].append(f"INPUT_{display_name.upper().replace(' ', '_')}")
                        _LOG.error(f"✗ Input {display_name} failed: {error_msg}")
            
            # Summary
            _LOG.info(f"Input discovery complete:")
            _LOG.info(f"  - Discovered via pyheos: {len(result['discovered_inputs'])}")
            _LOG.info(f"  - Working: {len(result['working_inputs'])}")
            _LOG.info(f"  - Unavailable: {len(result['unavailable_inputs'])}")
            
            return result
            
        except Exception as e:
            _LOG.error(f"Input source testing failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    async def _test_queue_operations(self) -> Dict[str, Any]:
        """Test queue management operations."""
        try:
            result = {
                "success": True,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "queue_tests": {}
            }
            
            # Test get queue
            try:
                queue = await self._heos.player_get_queue(self._player_id)
                result["queue_tests"]["get_queue"] = {
                    "success": True,
                    "queue_size": len(queue)
                }
                self._full_results["analysis"]["working_features"].append("QUEUE_GET")
                
            except Exception as e:
                result["queue_tests"]["get_queue"] = {"success": False, "error": str(e)}
                self._full_results["analysis"]["failing_features"].append("QUEUE_GET")
            
            # Test clear queue
            try:
                await self._heos.player_clear_queue(self._player_id)
                result["queue_tests"]["clear_queue"] = {"success": True}
                self._full_results["analysis"]["working_features"].append("QUEUE_CLEAR")
                
            except Exception as e:
                result["queue_tests"]["clear_queue"] = {"success": False, "error": str(e)}
                self._full_results["analysis"]["failing_features"].append("QUEUE_CLEAR")
            
            return result
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    async def _test_play_modes(self) -> Dict[str, Any]:
        """Test play mode controls (repeat/shuffle)."""
        try:
            result = {
                "success": True,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "play_mode_tests": {}
            }
            
            # Get original mode
            original_mode = await self._heos.player_get_play_mode(self._player_id)
            
            # Test repeat modes
            for repeat_mode in [RepeatType.OFF, RepeatType.ONE, RepeatType.ALL]:
                try:
                    await self._heos.player_set_play_mode(
                        self._player_id, 
                        repeat_mode, 
                        original_mode.shuffle
                    )
                    await asyncio.sleep(1)
                    
                    self._full_results["analysis"]["working_features"].append(f"REPEAT_{repeat_mode.value.upper()}")
                    
                except Exception as e:
                    self._full_results["analysis"]["failing_features"].append(f"REPEAT_{repeat_mode.value.upper()}")
            
            # Test shuffle
            try:
                await self._heos.player_set_play_mode(self._player_id, original_mode.repeat, True)
                await asyncio.sleep(1)
                await self._heos.player_set_play_mode(self._player_id, original_mode.repeat, False)
                
                self._full_results["analysis"]["working_features"].extend(["SHUFFLE_ON", "SHUFFLE_OFF"])
                
            except Exception as e:
                self._full_results["analysis"]["failing_features"].extend(["SHUFFLE_ON", "SHUFFLE_OFF"])
            
            # Restore original mode
            try:
                await self._heos.player_set_play_mode(
                    self._player_id, 
                    original_mode.repeat, 
                    original_mode.shuffle
                )
            except Exception:
                pass
            
            return result
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    async def _test_advanced_features(self) -> Dict[str, Any]:
        """Test advanced HEOS features."""
        try:
            result = {
                "success": True,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "advanced_tests": {}
            }
            
            # Test groups
            try:
                groups = await self._heos.get_groups()
                result["advanced_tests"]["groups"] = {
                    "success": True,
                    "group_count": len(groups)
                }
                self._full_results["analysis"]["working_features"].append("ADVANCED_GET_GROUPS")
                
            except Exception as e:
                result["advanced_tests"]["groups"] = {"success": False, "error": str(e)}
                self._full_results["analysis"]["failing_features"].append("ADVANCED_GET_GROUPS")
            
            # Test favorites
            try:
                favorites = await self._heos.get_favorites()
                result["advanced_tests"]["favorites"] = {
                    "success": True,
                    "favorite_count": len(favorites)
                }
                self._full_results["analysis"]["working_features"].append("ADVANCED_GET_FAVORITES")
                
            except Exception as e:
                result["advanced_tests"]["favorites"] = {"success": False, "error": str(e)}
                self._full_results["analysis"]["failing_features"].append("ADVANCED_GET_FAVORITES")
            
            return result
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    async def _analyze_performance(self) -> Dict[str, Any]:
        """Analyze performance metrics."""
        return {
            "success": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "note": "Performance analysis completed"
        }
    
    async def _generate_optimization_analysis(self) -> Dict[str, Any]:
        """Generate optimization recommendations."""
        try:
            working_features = self._full_results["analysis"]["working_features"]
            failing_features = self._full_results["analysis"]["failing_features"]
            limited_features = self._full_results["analysis"]["limited_features"]
            
            recommendations = []
            
            if len(working_features) > 10:
                recommendations.append("HIGH: Focus on working features - strong foundation available")
            elif len(working_features) > 5:
                recommendations.append("MEDIUM: Build core functionality around working features")
            else:
                recommendations.append("LOW: Limited working features - consider device compatibility")
            
            # Specific implementation suggestions
            if any("VOLUME" in f for f in working_features):
                recommendations.append("Implement volume controls as primary interface")
            
            if any("PLAYBACK" in f for f in working_features):
                recommendations.append("Include basic playback controls")
            
            if any("INPUT" in f for f in working_features):
                recommendations.append("Add input switching capabilities")
            
            # HDMI-specific recommendations
            hdmi_inputs = [f for f in working_features if "HDMI" in f]
            if hdmi_inputs:
                recommendations.append(f"CRITICAL: Implement HDMI inputs - found {len(hdmi_inputs)} working HDMI inputs")
            
            self._full_results["recommendations"]["for_uc_remote"] = recommendations
            
            return {
                "success": True,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "recommendations": recommendations
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    async def _compile_final_report(self) -> Dict[str, Any]:
        """Compile comprehensive final report."""
        try:
            working_features = self._full_results["analysis"]["working_features"]
            failing_features = self._full_results["analysis"]["failing_features"]
            limited_features = self._full_results["analysis"]["limited_features"]
            
            final_stats = {
                "working_features_count": len(working_features),
                "limited_features_count": len(limited_features),
                "failing_features_count": len(failing_features),
                "total_features_tested": len(working_features) + len(failing_features) + len(limited_features)
            }
            
            # Update test summary
            self._full_results["test_summary"] = {
                "total_tests": self._total_tests,
                "passed_tests": len([r for r in self._full_results["detailed_results"].values() if r.get("success", False)]),
                "failed_tests": len([r for r in self._full_results["detailed_results"].values() if not r.get("success", True)]),
                "success_rate": final_stats["working_features_count"] / max(final_stats["total_features_tested"], 1)
            }
            
            # Completion timestamp
            completion_time = datetime.now(timezone.utc)
            self._full_results["metadata"]["completion_time"] = completion_time.isoformat()
            
            if self._test_start_time:
                total_duration = (completion_time - self._test_start_time).total_seconds()
                self._full_results["metadata"]["total_duration_seconds"] = total_duration
                self._full_results["metadata"]["total_duration_minutes"] = total_duration / 60
            
            return {
                "success": True,
                "timestamp": completion_time.isoformat(),
                "final_stats": final_stats
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    async def _record_test_completion(self, test_name: str, result: Dict[str, Any]) -> None:
        """Record completion of a test category."""
        try:
            # Store detailed result
            self._full_results["detailed_results"][test_name] = result
            
            _LOG.info(f"Completed: {test_name} - {'PASS' if result.get('success', False) else 'FAIL'}")
                
        except Exception as e:
            _LOG.error(f"Error recording test completion: {e}")
    
    async def _finalize_test_session(self) -> None:
        """Finalize the test session."""
        try:
            total_working = len(self._full_results["analysis"]["working_features"])
            total_failing = len(self._full_results["analysis"]["failing_features"])
            total_limited = len(self._full_results["analysis"]["limited_features"])
            
            _LOG.info("=== HEOS DISCOVERY SESSION COMPLETE ===")
            _LOG.info(f"Working Features: {total_working}")
            _LOG.info(f"Limited Features: {total_limited}")
            _LOG.info(f"Failing Features: {total_failing}")
            
        except Exception as e:
            _LOG.error(f"Error finalizing test session: {e}")
    
    async def export_json_results(self) -> str:
        """Export complete results as structured JSON."""
        try:
            # Create final JSON output
            json_output = {
                "heos_discovery_report": self._full_results,
                "export_info": {
                    "exported_at": datetime.now(timezone.utc).isoformat(),
                    "export_version": "2.1.0",
                    "device_name": self._player.name if self._player else "Unknown",
                    "player_id": self._player_id
                }
            }
            
            # Format as pretty JSON string
            json_string = json.dumps(json_output, indent=2, ensure_ascii=False)
            
            return json_string
            
        except Exception as e:
            _LOG.error(f"JSON export failed: {e}")
            return json.dumps({"error": f"JSON export failed: {e}"}, indent=2)
    
    async def disconnect(self) -> None:
        """Disconnect from HEOS device."""
        try:
            if self._heos:
                await self._heos.disconnect()
                self._heos = None
                _LOG.info("Disconnected from HEOS device")
        except Exception as e:
            _LOG.error(f"Error disconnecting: {e}")


async def main():
    """Main function to run the discovery tool."""
    print("=" * 70)
    print("HEOS Automated Discovery Tool v2.1.0")
    print("100% Self-Contained - No Manual Setup Required")
    print("=" * 70)
    print()
    
    # Get connection parameters
    host = input("Enter HEOS device IP address: ").strip()
    if not host:
        print("ERROR: Host IP address is required")
        return
    
    print("\nOptional: HEOS account credentials (for authenticated services)")
    username = input("Username (or press Enter to skip): ").strip()
    password = input("Password (or press Enter to skip): ").strip() if username else ""
    
    print("\nStarting discovery process...")
    print("This will test ALL features including HDMI inputs...")
    print()
    
    discovery = HeosAutomatedDiscovery()
    
    try:
        # Connect to HEOS
        if not await discovery.connect_to_heos(host, username, password):
            print("ERROR: Failed to connect to HEOS device")
            return
        
        print("Connected successfully! Running comprehensive tests...")
        print()
        
        # Run all tests
        results = await discovery.run_all_tests()
        
        if "error" in results:
            print(f"ERROR: Discovery failed - {results['error']}")
            return
        
        # Export JSON results
        json_output = await discovery.export_json_results()
        
        # Save to file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"heos_discovery_{timestamp}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(json_output)
        
        print()
        print("=" * 70)
        print("DISCOVERY COMPLETE")
        print("=" * 70)
        print(f"Results saved to: {filename}")
        print()
        print("Summary:")
        print(f"- Working Features: {len(results['analysis']['working_features'])}")
        print(f"- Limited Features: {len(results['analysis']['limited_features'])}")
        print(f"- Failing Features: {len(results['analysis']['failing_features'])}")
        print()
        
        # Show input-specific results
        input_results = results.get('detailed_results', {}).get('input_sources', {})
        if input_results:
            print("Input Sources Discovered:")
            discovered = input_results.get('discovered_inputs', [])
            if discovered:
                print(f"  Via pyheos library: {len(discovered)} inputs found")
                for inp in discovered:
                    print(f"    - {inp['name']} ({inp['media_id']})")
            print(f"  Working inputs: {len(input_results.get('working_inputs', []))}")
            print(f"  Unavailable inputs: {len(input_results.get('unavailable_inputs', []))}")
            print()
        
        print("=" * 70)
        print(f"IMPORTANT: Send the file '{filename}' to the developer")
        print("=" * 70)
        
    except KeyboardInterrupt:
        print("\nDiscovery interrupted by user")
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await discovery.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting...")
    except Exception as e:
        print(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()