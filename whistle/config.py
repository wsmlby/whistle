import json
import os
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("WHISTLE_CONFIG_DIR", Path.home() / ".config" / "whistle"))
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_CONFIG = {
    "llm": {
        "base_url": None,
        "api_key": None,
        "model": None,
    },
    "alert": {
        "slack": None,
    },
    "log": {
        "kernel_only": True,
        "service_units": [],
    },
    "ignore": [],
}

def load_config(path: str = None):
    """Loads the configuration from a given path or the default user path."""
    config_path = Path(path) if path else CONFIG_FILE
    if not config_path.exists():
        if path:
            raise FileNotFoundError(f"Configuration file not found at {path}")
        return DEFAULT_CONFIG
    with open(config_path, "r") as f:
        return json.load(f)

def save_config(config: dict, path: str = None):
    """Saves the configuration to a given path or the default user path."""
    config_path = Path(path) if path else CONFIG_FILE
    config_dir = config_path.parent
    config_dir.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w") as f:
        json.dump(config, f, indent=4)
