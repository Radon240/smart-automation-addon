"""
Configuration management for the Diploma addon.

Home Assistant supervisor automatically saves addon options to /data/options.json.
This module reads configuration from there and provides defaults.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional


class Config:
    """Configuration loader for the addon."""

    # Default values for all parameters
    DEFAULTS = {
        "log_level": "info",
        "min_support": 5,
        "min_confidence": 0.6,
        "history_days": 7,
        "train_hour": 3,
    }

    def __init__(self):
        """Initialize config by reading from options file or environment."""
        self._config: Dict[str, Any] = self.DEFAULTS.copy()
        self._load()

    def _load(self) -> None:
        """Load configuration from /data/options.json or environment variables."""
        # Try to read from Home Assistant options file first
        options_file = Path("/data/options.json")
        if options_file.exists():
            try:
                with open(options_file, "r") as f:
                    data = json.load(f)
                    self._config.update(data)
                    print(f"[diploma_addon] Loaded config from {options_file}")
            except Exception as e:
                print(f"[diploma_addon] Error reading {options_file}: {e}, using defaults")

        # Override with environment variables if set
        # (useful for local development and testing)
        env_mapping = {
            "LOG_LEVEL": "log_level",
            "MIN_SUPPORT": "min_support",
            "MIN_CONFIDENCE": "min_confidence",
            "HISTORY_DAYS": "history_days",
            "TRAIN_HOUR": "train_hour",
        }
        for env_var, config_key in env_mapping.items():
            if env_var in os.environ:
                value = os.environ[env_var]
                # Type conversion based on key
                if config_key in ("min_support", "history_days", "train_hour"):
                    self._config[config_key] = int(value)
                elif config_key == "min_confidence":
                    self._config[config_key] = float(value)
                else:
                    self._config[config_key] = value
                print(f"[diploma_addon] Override from env: {config_key}={self._config[config_key]}")

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value by key."""
        return self._config.get(key, default or self.DEFAULTS.get(key))

    def get_all(self) -> Dict[str, Any]:
        """Get all configuration values."""
        return self._config.copy()

    def reload(self) -> None:
        """Reload configuration from file."""
        self._config = self.DEFAULTS.copy()
        self._load()
        print("[diploma_addon] Configuration reloaded")


# Global config instance
config = Config()


def get_config() -> Config:
    """Get the global config instance."""
    return config
