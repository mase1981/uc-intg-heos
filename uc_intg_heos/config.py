"""
HEOS Configuration Management 

:copyright: (c) 2025 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, asdict

_LOG = logging.getLogger(__name__)


@dataclass
class HeosAccountConfig:
    """HEOS account configuration."""
    username: str
    password: str
    host: str  # IP of any HEOS device for connection


class HeosConfig:
    """Configuration manager for HEOS integration."""
    
    def __init__(self, config_dir: str = None):
        """
        Initialize configuration manager.
        
        :param config_dir: Directory to store configuration files
        """
        self._config_dir = Path(config_dir) if config_dir else Path.cwd() / "data"
        self._config_file = self._config_dir / "heos_config.json"
        self._account_config: Optional[HeosAccountConfig] = None
        self._configured: bool = False
        
        # Ensure config directory exists
        self._config_dir.mkdir(parents=True, exist_ok=True)
        
        # Load existing configuration
        self._load_config()
    
    def _load_config(self) -> None:
        """Load configuration from disk."""
        try:
            if self._config_file.exists():
                with open(self._config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Load HEOS account
                account_data = data.get('heos_account')
                if account_data:
                    self._account_config = HeosAccountConfig(**account_data)
                    self._configured = True
                
                _LOG.info("Loaded HEOS configuration")
            else:
                _LOG.info("No existing HEOS configuration found")
                
        except Exception as e:
            _LOG.error(f"Failed to load HEOS configuration: {e}")
            self._account_config = None
            self._configured = False
    
    def _save_config(self) -> None:
        """Save configuration to disk."""
        try:
            config_data = {
                'version': '1.0.0'
            }
            
            if self._account_config:
                config_data['heos_account'] = asdict(self._account_config)
            
            # Write to file atomically
            temp_file = self._config_file.with_suffix('.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)
            
            # Replace original file
            temp_file.replace(self._config_file)
            
            _LOG.info("HEOS configuration saved successfully")
            
        except Exception as e:
            _LOG.error(f"Failed to save HEOS configuration: {e}")
    
    def reload_from_disk(self) -> None:
        """Reload configuration from disk (for reboot survival)."""
        _LOG.info("Reloading HEOS configuration from disk")
        self._account_config = None
        self._configured = False
        self._load_config()
    
    def set_heos_account(self, username: str, password: str, host: str) -> bool:
        """
        Set HEOS account configuration.
        
        :param username: HEOS account username
        :param password: HEOS account password
        :param host: IP address of HEOS device
        :return: True if saved successfully
        """
        try:
            self._account_config = HeosAccountConfig(
                username=username,
                password=password,
                host=host
            )
            self._configured = True
            self._save_config()
            
            _LOG.info("HEOS account configuration saved")
            return True
            
        except Exception as e:
            _LOG.error(f"Failed to save HEOS account configuration: {e}")
            return False
    
    def get_heos_account(self) -> Optional[HeosAccountConfig]:
        """
        Get HEOS account configuration.
        
        :return: HEOS account config or None
        """
        return self._account_config
    
    def get_host(self) -> str:
        """Get the current host."""
        return self._account_config.host if self._account_config else ""
    
    def update_host(self, new_host: str) -> None:
        """Update the host (for failover scenarios)."""
        if self._account_config:
            self._account_config.host = new_host
            self._save_config()
    
    def clear_configuration(self) -> bool:
        """
        Clear all configuration.
        
        :return: True if cleared successfully
        """
        try:
            self._account_config = None
            self._configured = False
            
            if self._config_file.exists():
                self._config_file.unlink()
            
            _LOG.info("HEOS configuration cleared")
            return True
            
        except Exception as e:
            _LOG.error(f"Failed to clear HEOS configuration: {e}")
            return False
    
    def is_configured(self) -> bool:
        """
        Check if integration is configured.
        
        :return: True if configured
        """
        return self._configured and self._account_config is not None
    
    @property
    def config_dir(self) -> Path:
        """Get configuration directory path."""
        return self._config_dir
    
    @property
    def config_file(self) -> Path:
        """Get configuration file path."""
        return self._config_file