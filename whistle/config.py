import json
import os
import pwd
from pathlib import Path

def get_user_config_dir():
    """Gets the user's config directory, handling sudo."""
    if 'SUDO_USER' in os.environ:
        user_name = os.environ['SUDO_USER']
        try:
            # Get home directory of the original user
            user_home = pwd.getpwnam(user_name).pw_dir
            return Path(user_home) / ".config" / "whistle"
        except KeyError:
            # Fallback if user not found, though unlikely
            return Path(f"/home/{user_name}/.config/whistle")
    else:
        return Path.home() / ".config" / "whistle"

CONFIG_DIR = Path(os.environ.get("WHISTLE_CONFIG_DIR", get_user_config_dir()))
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

def is_root():
    return os.geteuid() == 0

def get_config_path():
    if is_root():
        return Path("/etc/whistle/config.json")
    return CONFIG_FILE

def load_config():
    """Loads the configuration from a given path or the default user path."""
    config_path = get_config_path()
    if not config_path.exists():
        return DEFAULT_CONFIG
    with open(config_path, "r") as f:
        return json.load(f)

def save_config(config: dict):
    """Saves the configuration to a given path or the default user path."""
    config_path = get_config_path()
    config_dir = config_path.parent
    config_dir.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w") as f:
        json.dump(config, f, indent=4)
