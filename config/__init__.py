"""Configuration management."""
import os
import yaml
from pathlib import Path

_config = None
_DEFAULT_CONFIG = Path(__file__).parent / "default_config.yaml"


def load_config(path=None):
    """Load config from YAML, merging defaults with optional overrides."""
    global _config

    with open(_DEFAULT_CONFIG) as f:
        config = yaml.safe_load(f)

    if path and Path(path).exists():
        with open(path) as f:
            overrides = yaml.safe_load(f) or {}
        config = _deep_merge(config, overrides)

    # Environment variable overrides
    env_map = {
        "BTC_MONITOR_DB_PATH": ("database", "path"),
        "BTC_MONITOR_FETCH_INTERVAL": ("monitor", "fetch_interval"),
        "BTC_MONITOR_LOG_LEVEL": ("logging", "level"),
    }
    for env_key, config_path in env_map.items():
        val = os.environ.get(env_key)
        if val:
            d = config
            for k in config_path[:-1]:
                d = d.setdefault(k, {})
            try:
                d[config_path[-1]] = int(val)
            except ValueError:
                d[config_path[-1]] = val

    _validate_config(config)
    _config = config
    return config


def get_config():
    """Return cached config, loading defaults if needed."""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def _deep_merge(base, override):
    """Recursively merge override into base dict."""
    result = base.copy()
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result


def _validate_config(config):
    """Basic config validation."""
    required_sections = ["api", "monitor", "dca", "alerts", "dashboard", "database"]
    for section in required_sections:
        if section not in config:
            raise ValueError(f"Missing required config section: {section}")

    if config["monitor"]["fetch_interval"] < 60:
        raise ValueError("fetch_interval must be >= 60 seconds")
