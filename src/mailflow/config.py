# ABOUTME: Configuration management using XDG Base Directory specification
# ABOUTME: Handles config files, data storage, state/logs, and cache directories
# ABOUTME: Uses ~/.config/docflow as the unified config root for all docflow components
import logging
import os
import shutil
import tomllib
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ConfigurationError(Exception):
    """Raised when required configuration is missing or invalid."""

    pass


class Config:
    """
    Configuration management for docflow using XDG Base Directory specification.

    Config root: $XDG_CONFIG_HOME/docflow (default: ~/.config/docflow)

    The config.toml file follows the docflow SOT structure with sections:
    - [archive] - Archive storage settings
    - [archivist] - LLM-archivist database settings (required for classification)
    - [llmemory] - LLMory search settings
    - [mailflow] - Mailflow-specific settings
    """

    # Default app name for XDG directories
    APP_NAME = "docflow"

    def __init__(self, config_dir: str | None = None):
        if config_dir is None:
            # Use XDG Base Directory specification with docflow as the app name
            xdg_config_home = os.environ.get('XDG_CONFIG_HOME', os.path.expanduser('~/.config'))
            config_dir = os.path.join(xdg_config_home, self.APP_NAME)
            logger.info(f"Using XDG config directory: {config_dir}")

            # Use XDG paths for other directories
            xdg_data_home = os.environ.get('XDG_DATA_HOME', os.path.expanduser('~/.local/share'))
            self.data_dir = Path(xdg_data_home) / self.APP_NAME

            xdg_state_home = os.environ.get('XDG_STATE_HOME', os.path.expanduser('~/.local/state'))
            self.state_dir = Path(xdg_state_home) / self.APP_NAME

            xdg_cache_home = os.environ.get('XDG_CACHE_HOME', os.path.expanduser('~/.cache'))
            self.cache_dir = Path(xdg_cache_home) / self.APP_NAME
        else:
            # When config_dir is explicitly provided (e.g., in tests),
            # derive all other directories from it to keep everything isolated
            logger.info(f"Using custom config directory: {config_dir}")
            self.data_dir = Path(config_dir) / 'data'
            self.state_dir = Path(config_dir) / 'state'
            self.cache_dir = Path(config_dir) / 'cache'

        # Validate config directory path - resolve FIRST to handle symlinks
        self.config_dir = Path(config_dir).resolve()

        # Security check - ensure we're not using system directories
        restricted_prefixes = ["/etc/", "/usr/", "/bin/", "/sbin/", "/var/", "/tmp/",
                               "/sys/", "/proc/", "/dev/", "/boot/", "/root/"]
        config_str = str(self.config_dir)
        if config_str == "/" or any(config_str.startswith(p) or config_str == p.rstrip("/")
                                     for p in restricted_prefixes):
            raise ValueError(f"Cannot use system directory as config dir: {config_dir}")

        self._ensure_directories()
        self._load_config()

    def _ensure_directories(self):
        """Create necessary XDG directories"""
        try:
            # Create all XDG base directories
            self.config_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            self.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            self.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            self.cache_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

            # Config subdirectories
            (self.config_dir / "workflows").mkdir(exist_ok=True, mode=0o700)
            (self.config_dir / "backups").mkdir(exist_ok=True, mode=0o700)

            # State subdirectories (for logs and history)
            (self.state_dir / "history").mkdir(exist_ok=True, mode=0o700)
            (self.state_dir / "logs").mkdir(exist_ok=True, mode=0o700)
        except (OSError, PermissionError) as e:
            logger.error(f"Failed to create directories: {e}")
            raise ConfigurationError(f"Cannot create config directories: {e}") from e

    def _load_config(self):
        """Load configuration from config.toml.

        The config.toml file must exist and contain valid TOML.
        Uses defaults for mailflow-internal settings while requiring
        SOT-defined settings for cross-component integration.
        """
        config_file = self.config_dir / "config.toml"

        if config_file.exists():
            try:
                with open(config_file, "rb") as f:
                    loaded_settings = tomllib.load(f)
                self.settings = self._merge_with_defaults(loaded_settings)
                self._validate_settings()
            except tomllib.TOMLDecodeError as e:
                raise ConfigurationError(
                    f"Invalid TOML in config file {config_file}: {e}\n"
                    f"Fix the syntax error and try again."
                )
            except (OSError, PermissionError, IOError) as e:
                raise ConfigurationError(f"Failed to load config from {config_file}: {e}") from e
        else:
            # No config.toml found - use defaults for testing/development
            # In production, components that require config will fail at preflight
            logger.warning(f"No config.toml found at {config_file}, using defaults")
            self.settings = self._default_settings()

    def _merge_with_defaults(self, loaded: dict) -> dict:
        """Merge loaded settings with defaults, preserving loaded values."""
        defaults = self._default_settings()

        # Deep merge: loaded values override defaults
        result = defaults.copy()
        for section, values in loaded.items():
            if section in result and isinstance(result[section], dict) and isinstance(values, dict):
                result[section] = {**result[section], **values}
            else:
                result[section] = values

        return result

    def _default_settings(self) -> dict[str, Any]:
        """Default configuration settings.

        Structure includes both SOT-defined sections and internal mailflow settings:
        - [archive] - Archive storage settings (SOT)
        - [archivist] - LLM-archivist database settings (SOT)
        - [llmemory] - LLMory search settings (SOT)
        - Plus internal settings at top level
        """
        return {
            # SOT-defined sections
            "archive": {
                "base_path": "~/Archive",
            },
            "archivist": {
                # These are required for classification - preflight will check
                # "database_url": required,
                # "db_schema": required,
                "similarity_threshold": 0.95,
            },
            "llmemory": {
                # "database_url": optional,
                # "default_owner_id": optional,
            },
            # Internal mailflow settings
            "ui": {
                "max_suggestions": 5,
                "show_confidence": True,
                "confirm_before_execute": True,
            },
            "storage": {
                "max_workflows": 100,
            },
            "security": {"max_email_size_mb": 25},
            "llm": {
                "model_alias": "balanced",  # fast, balanced, or deep
            },
            "classifier": {
                "gate_enabled": False,
                "gate_min_confidence": 0.7,
            },
        }

    def _validate_settings(self):
        """Validate settings are within acceptable ranges."""
        # Ensure reasonable limits for UI settings
        ui_settings = self.settings.get("ui", {})
        if ui_settings:
            ui_settings["max_suggestions"] = min(max(1, ui_settings.get("max_suggestions", 5)), 20)

        # Validate LLM model alias
        llm_settings = self.settings.get("llm", {})
        if llm_settings:
            valid_models = ["fast", "balanced", "deep"]
            model_alias = llm_settings.get("model_alias", "balanced")
            if model_alias not in valid_models:
                logger.warning(
                    f"Invalid LLM model '{model_alias}', defaulting to 'balanced'. "
                    f"Valid options: {', '.join(valid_models)}"
                )
                llm_settings["model_alias"] = "balanced"

    def preflight_archivist(self) -> None:
        """Preflight check for archivist configuration.

        Must be called before any archive writes that require classification.
        Raises ConfigurationError if required archivist settings are missing.
        """
        archivist = self.settings.get("archivist", {})

        missing = []
        if not archivist.get("database_url"):
            missing.append("archivist.database_url")
        if not archivist.get("db_schema"):
            missing.append("archivist.db_schema")

        if missing:
            config_path = self.config_dir / "config.toml"
            raise ConfigurationError(
                f"Missing required archivist configuration: {', '.join(missing)}\n"
                f"Add these to [archivist] section in {config_path}:\n\n"
                f"[archivist]\n"
                f'database_url = "postgresql://user:pass@localhost:5432/docflow"\n'
                f'db_schema = "archivist"\n'
            )

    def get_archivist_database_url(self) -> str:
        """Get archivist database URL, running preflight check first."""
        self.preflight_archivist()
        return self.settings["archivist"]["database_url"]

    def get_archivist_db_schema(self) -> str:
        """Get archivist database schema, running preflight check first."""
        self.preflight_archivist()
        return self.settings["archivist"]["db_schema"]

    def get_workflows_file(self) -> Path:
        return self.config_dir / "workflows.json"

    def get_history_dir(self) -> Path:
        return self.state_dir / "history"

    def get_log_dir(self) -> Path:
        return self.state_dir / "logs"

    def backup_file(self, file_path: Path) -> Path:
        """Backup a file into the backups directory with a timestamped name.

        The backup filename pattern is '<stem>_<YYYYmmddHHMMSS><suffix>'.
        Returns the backup path (even if source doesn't exist).
        """
        backups_dir = self.config_dir / "backups"
        backups_dir.mkdir(exist_ok=True, mode=0o700)

        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        backup_name = f"{file_path.stem}_{ts}{file_path.suffix}"
        backup_path = backups_dir / backup_name

        if not file_path.exists():
            # Nothing to back up; return the intended path without creating a file
            return backup_path

        try:
            shutil.copy2(file_path, backup_path)  # Preserves metadata, streams data
        except (OSError, IOError) as e:
            logger.error(f"Failed to backup file {file_path}: {e}")
            raise ConfigurationError(f"Backup failed: {e}") from e

        return backup_path
