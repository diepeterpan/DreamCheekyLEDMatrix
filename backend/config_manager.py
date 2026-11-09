"""
Configuration Manager.
Loads, validates, and persists user settings and active scripts to config.json.
"""

import json
import logging
import os
from typing import Any, Dict
from backend.script_engine import DEFAULT_SCRIPT

logger = logging.getLogger("dcled.config")

CONFIG_FILE_PATH = os.environ.get("DCLED_CONFIG", "config.json")

DEFAULT_CONFIG: Dict[str, Any] = {
    "service_running": True,
    "script_code": DEFAULT_SCRIPT,
    "interval_seconds": 30,
    "effect": "scroll_west",  # scroll_west, scroll_east, scroll_north, scroll_south, static, fire, tv_warmup, squiggle, clock24, clock12, bcdclock, tach
    "speed_ms": 40,
    "brightness": 2,  # 0: Low, 1: Medium, 2: High
    "font": "default",  # default, small, sga, small_inv
    "spacing": "proportional",  # proportional or fixed
    "tach_percentage": 65,
    "dev_settings": {
        "effect": "scroll_west",
        "interval_seconds": 30,
        "speed_ms": 40,
        "brightness": 2,
        "font": "default",
        "spacing": "proportional"
    }
}

class ConfigManager:
    def __init__(self, path: str = CONFIG_FILE_PATH):
        self.path = path
        self.data: Dict[str, Any] = dict(DEFAULT_CONFIG)
        self.load()

    def _resolve_target_file(self) -> str:
        """
        Resolves the configuration file path.
        If Docker created self.path as a directory (because the host file did not exist prior to bind mount),
        stores config.json inside that directory instead of crashing.
        """
        if os.path.isdir(self.path):
            return os.path.join(self.path, "config.json")
        return self.path

    def load(self):
        filepath = self._resolve_target_file()
        if os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if content:
                        saved = json.loads(content)
                        self.data.update(saved)
                        logger.info(f"Loaded configuration from {filepath}")
                    else:
                        logger.warning(f"Configuration file {filepath} is empty. Populating with defaults.")
                        self.save()
            except Exception as e:
                logger.error(f"Failed to load configuration from {filepath}: {e}. Falling back to default config.")
                self.save()
        else:
            self.save()

    def save(self):
        filepath = self._resolve_target_file()
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
            logger.info(f"Saved configuration to {filepath}")
        except Exception as e:
            logger.error(f"Failed to save configuration to {filepath}: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def update(self, new_values: Dict[str, Any]):
        self.data.update(new_values)
        self.save()

