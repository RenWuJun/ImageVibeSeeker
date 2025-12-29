import json
import os
from utils.logger import get_logger

# Optional import for file locking to allow launcher to run without it
try:
    from filelock import FileLock
    HAS_FILELOCK = True
except ImportError:
    HAS_FILELOCK = False

logger = get_logger(__name__)

class Config:
    _instance = None
    _config_data = None
    CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.json')
    LOCK_PATH = CONFIG_PATH + ".lock"

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Config, cls).__new__(cls)
            cls._instance._load_config()
        return cls._instance

    def _load_config(self):
        if not os.path.exists(self.CONFIG_PATH):
            logger.error(f"Configuration file not found at {self.CONFIG_PATH}")
            raise FileNotFoundError(f"Configuration file not found at {self.CONFIG_PATH}")
        
        if HAS_FILELOCK:
            lock = FileLock(self.LOCK_PATH)
            with lock:
                self._do_load()
        else:
            self._do_load()

    def reload(self):
        """Public method to force a reload from disk."""
        self._load_config()

    def _do_load(self):
        try:
            with open(self.CONFIG_PATH, 'r') as f:
                self._config_data = json.load(f)
            logger.info(f"Configuration loaded from {self.CONFIG_PATH}")
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON from config file {self.CONFIG_PATH}: {e}")
            raise
        except IOError as e:
            logger.error(f"I/O error reading config file {self.CONFIG_PATH}: {e}")
            raise

    def get(self, key, default=None):
        return self._config_data.get(key, default)

    def __getitem__(self, key):
        return self._config_data[key]

    def __getattr__(self, name):
        if name in self._config_data:
            if isinstance(self._config_data[name], dict):
                return ConfigSection(self._config_data[name], self, name)
            return self._config_data[name]
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

    def _do_save(self):
        """Internal method to perform the actual disk write."""
        try:
            with open(self.CONFIG_PATH, 'w') as f:
                json.dump(self._config_data, f, indent=2)
            logger.info(f"Configuration saved to {self.CONFIG_PATH}")
        except IOError as e:
            logger.error(f"I/O error writing config file {self.CONFIG_PATH}: {e}")
            raise

    def update_section(self, section_key, new_values):
        """Atomically reloads, updates, and saves a section."""
        def _perform_update():
            self._do_load()
            if section_key in self._config_data and isinstance(self._config_data[section_key], dict):
                self._config_data[section_key].update(new_values)
            else:
                self._config_data[section_key] = new_values
            self._do_save()

        if HAS_FILELOCK:
            with FileLock(self.LOCK_PATH):
                _perform_update()
        else:
            _perform_update()
        
        logger.info(f"Updated and Saved config section '{section_key}'")

    def save_config(self):
        """Manually trigger a save of current in-memory state. 
        Usually redundant if update_section is used.
        """
        if HAS_FILELOCK:
            with FileLock(self.LOCK_PATH):
                self._do_save()
        else:
            self._do_save()

class ConfigSection:
    def __init__(self, data, parent_config, section_name):
        self._data = data
        self._parent = parent_config
        self._name = section_name

    def get(self, key, default=None):
        return self._data.get(key, default)

    def __getitem__(self, key):
        return self._data[key]

    def __getattr__(self, name):
        if name in self._data:
            val = self._data[name]
            if isinstance(val, dict):
                return ConfigSection(val, self._parent, f"{self._name}.{name}")
            return val
        raise AttributeError(f"Config section '{self._name}' has no attribute '{name}'")

    def update(self, new_values):
        self._parent.update_section(self._name, new_values)

# Global instance for easy access
config = Config()

# Example usage (for testing/demonstration)
if __name__ == "__main__":
    logger.info("Testing Config class...")
    logger.info(f"Database Host: {config.database.host}")
    logger.info(f"Root Folder: {config.paths.root_folder}")
    logger.info(f"CLIP Model: {config.clip.model}")
    logger.info(f"Score Rules: {config.scores.rules}")

    # Test update and save
    original_score_range = config.get('score_range')
    logger.info(f"Original score_range: {original_score_range}")

    config.update_section('score_range', {'above': 5, 'below': 1})
    config.save_config()
    logger.info("Updated score_range and saved.")

    # Reload config to verify
    config._load_config() # Force reload for test
    logger.info(f"Reloaded score_range: {config.get('score_range')}")

    # Revert for clean test
    if original_score_range:
        config.update_section('score_range', original_score_range)
        config.save_config()
        logger.info("Reverted score_range.")
