"""
HEOS Configuration Management.

:copyright: (c) 2025 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

import json
import logging
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, asdict

_LOG = logging.getLogger(__name__)


@dataclass
class HeosAccountConfig:
    """HEOS account configuration."""
    username: str
    password: str
    host: str


class HeosConfig:
    """Configuration manager."""
    
    def __init__(self, config_dir: str = None):
        """Initialize configuration."""
        if config_dir:
            self._config_dir = Path(config_dir)
        else:
            # Fallback to current directory if no config_dir provided
            self._config_dir = Path.cwd()
        
        self._config_file = self._config_dir / "heos_config.json"
        self._account_config: Optional[HeosAccountConfig] = None
        self._configured: bool = False
        
        # Only create directory if it doesn't exist and we have permissions
        try:
            self._config_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            _LOG.warning(f"Could not create config directory {self._config_dir}: {e}")
            # Directory might already exist or be created by UC Remote
    
    def load(self):
        """Load configuration."""
        try:
            if self._config_file.exists():
                with open(self._config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                account_data = data.get('heos_account')
                if account_data:
                    self._account_config = HeosAccountConfig(**account_data)
                    self._configured = True
                
                _LOG.info("Configuration loaded")
            else:
                _LOG.info("No configuration file found")
                
        except Exception as e:
            _LOG.error(f"Failed to load configuration: {e}")
            self._account_config = None
            self._configured = False
    
    def _save(self):
        """Save configuration."""
        try:
            config_data = {'version': '1.0.0'}
            
            if self._account_config:
                config_data['heos_account'] = asdict(self._account_config)
            
            temp_file = self._config_file.with_suffix('.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2)
            
            temp_file.replace(self._config_file)
            _LOG.info("Configuration saved")
            
        except Exception as e:
            _LOG.error(f"Failed to save: {e}")
    
    def reload_from_disk(self):
        """Reload from disk."""
        _LOG.info("Reloading configuration")
        self._account_config = None
        self._configured = False
        self.load()
    
    def set_heos_account(self, username: str, password: str, host: str) -> bool:
        """Set account configuration."""
        try:
            self._account_config = HeosAccountConfig(
                username=username,
                password=password,
                host=host
            )
            self._configured = True
            self._save()
            return True
        except Exception as e:
            _LOG.error(f"Failed to save account: {e}")
            return False
    
    def get_heos_account(self) -> Optional[HeosAccountConfig]:
        """Get account configuration."""
        return self._account_config
    
    def get_host(self) -> str:
        """Get the current host."""
        return self._account_config.host if self._account_config else ""
    
    def update_host(self, new_host: str) -> None:
        """Update the host (for failover scenarios)."""
        if self._account_config:
            self._account_config.host = new_host
            self._save()
    
    def clear_configuration(self) -> bool:
        """Clear all configuration."""
        try:
            self._account_config = None
            self._configured = False
            
            if self._config_file.exists():
                self._config_file.unlink()
            
            _LOG.info("HEOS configuration cleared")
            return True
            
        except Exception as e:
            _LOG.error(f"Failed to clear configuration: {e}")
            return False
    
    def is_configured(self) -> bool:
        """Check if configured."""
        return self._configured and self._account_config is not None