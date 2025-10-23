# ABOUTME: Configuration management using XDG Base Directory specification
# ABOUTME: Handles config files, data storage, state/logs, and cache directories
import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class Config:
    """
    Configuration management for mailflow using XDG Base Directory specification.

    Directories (following XDG standard):
    - Config: $XDG_CONFIG_HOME/mailflow (default: ~/.config/mailflow)
    - Data: $XDG_DATA_HOME/mailflow (default: ~/.local/share/mailflow)
    - State: $XDG_STATE_HOME/mailflow (default: ~/.local/state/mailflow)
    - Cache: $XDG_CACHE_HOME/mailflow (default: ~/.cache/mailflow)
    """

    def __init__(self, config_dir: str | None = None):
        if config_dir is None:
            # Use XDG Base Directory specification
            xdg_config_home = os.environ.get('XDG_CONFIG_HOME', os.path.expanduser('~/.config'))
            config_dir = os.path.join(xdg_config_home, 'mailflow')
            logger.info(f"Using XDG config directory: {config_dir}")

            # Use XDG paths for other directories
            xdg_data_home = os.environ.get('XDG_DATA_HOME', os.path.expanduser('~/.local/share'))
            self.data_dir = Path(xdg_data_home) / 'mailflow'

            xdg_state_home = os.environ.get('XDG_STATE_HOME', os.path.expanduser('~/.local/state'))
            self.state_dir = Path(xdg_state_home) / 'mailflow'

            xdg_cache_home = os.environ.get('XDG_CACHE_HOME', os.path.expanduser('~/.cache'))
            self.cache_dir = Path(xdg_cache_home) / 'mailflow'
        else:
            # When config_dir is explicitly provided (e.g., in tests),
            # derive all other directories from it to keep everything isolated
            logger.info(f"Using custom config directory: {config_dir}")
            self.data_dir = Path(config_dir) / 'data'
            self.state_dir = Path(config_dir) / 'state'
            self.cache_dir = Path(config_dir) / 'cache'

        # Validate config directory path
        self.config_dir = Path(config_dir).resolve()

        # Security check - ensure we're not using system directories
        restricted_dirs = ["/", "/etc", "/usr", "/bin", "/sbin", "/var", "/tmp"]
        if str(self.config_dir) in restricted_dirs:
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
        except Exception as e:
            logger.error(f"Failed to create directories: {e}")
            raise

    def _load_config(self):
        """Load configuration with defaults"""
        config_file = self.config_dir / "config.json"
        if config_file.exists():
            try:
                with open(config_file) as f:
                    self.settings = json.load(f)
                    # Validate loaded settings
                    self._validate_settings()
            except json.JSONDecodeError as e:
                logger.error(f"Invalid config file: {e}")
                self.settings = self._default_settings()
                self.save_config()
            except Exception as e:
                logger.error(f"Failed to load config: {e}")
                self.settings = self._default_settings()
        else:
            self.settings = self._default_settings()
            self.save_config()

    def _default_settings(self) -> dict[str, Any]:
        """Default configuration settings"""
        return {
            "feature_weights": {
                "from_domain": 0.3,
                "subject_similarity": 0.25,
                "has_pdf": 0.2,
                "body_keywords": 0.15,
                "to_address": 0.1,
            },
            "ui": {
                "max_suggestions": 5,
                "show_confidence": True,
                "confirm_before_execute": True,
            },
            "learning": {"min_confidence_threshold": 0.3},
            "storage": {
                "max_criteria_instances": 10000,
                "max_workflows": 100,
            },
            "security": {"allowed_directories": ["~"], "max_email_size_mb": 25},
            "llm": {
                "enabled": False,  # Opt-in, disabled by default
                "model_alias": "balanced",  # fast, balanced, or deep
                "high_confidence_threshold": 0.85,  # Auto-accept above this
                "medium_confidence_threshold": 0.50,  # Offer LLM assist above this
                "fallback_to_similarity": True,  # Fall back if LLM fails
            },
        }

    def _validate_settings(self):
        """Validate settings are within acceptable ranges"""
        # Ensure weights sum to 1.0
        weights = self.settings.get("feature_weights", {})
        total_weight = sum(weights.values())
        if abs(total_weight - 1.0) > 0.01:  # Allow small floating point errors
            logger.warning(f"Feature weights sum to {total_weight}, normalizing to 1.0")
            # Normalize weights
            if total_weight > 0:
                for key in weights:
                    weights[key] = weights[key] / total_weight

        # Ensure reasonable limits
        ui_settings = self.settings.get("ui", {})
        ui_settings["max_suggestions"] = min(max(1, ui_settings.get("max_suggestions", 5)), 20)

        self.settings.get("storage", {})

        # Validate LLM settings
        llm_settings = self.settings.get("llm", {})

        # Validate model alias
        valid_models = ["fast", "balanced", "deep"]
        model_alias = llm_settings.get("model_alias", "balanced")
        if model_alias not in valid_models:
            logger.warning(
                f"Invalid LLM model '{model_alias}', defaulting to 'balanced'. "
                f"Valid options: {', '.join(valid_models)}"
            )
            llm_settings["model_alias"] = "balanced"

        # Validate confidence thresholds (0.0-1.0 range)
        for threshold_key in ["high_confidence_threshold", "medium_confidence_threshold"]:
            threshold = llm_settings.get(threshold_key)
            if threshold is not None:
                if not isinstance(threshold, (int, float)) or not 0.0 <= threshold <= 1.0:
                    logger.warning(
                        f"Invalid LLM {threshold_key}: {threshold}, must be between 0.0 and 1.0. "
                        f"Using default 0.85 for high, 0.50 for medium"
                    )
                    default_val = 0.85 if "high" in threshold_key else 0.50
                    llm_settings[threshold_key] = default_val

        # Validate high threshold is greater than medium
        high = llm_settings.get("high_confidence_threshold", 0.85)
        medium = llm_settings.get("medium_confidence_threshold", 0.50)
        if high <= medium:
            logger.warning(
                f"LLM high_confidence_threshold ({high}) must be > medium_confidence_threshold ({medium}). "
                f"Resetting to defaults: high=0.85, medium=0.50"
            )
            llm_settings["high_confidence_threshold"] = 0.85
            llm_settings["medium_confidence_threshold"] = 0.50

    def save_config(self):
        """Save configuration to disk"""
        config_file = self.config_dir / "config.json"
        try:
            with open(config_file, "w") as f:
                json.dump(self.settings, f, indent=2, sort_keys=True)
            logger.debug("Configuration saved")
        except Exception as e:
            logger.error(f"Failed to save config: {e}")

    def get_workflows_file(self) -> Path:
        return self.config_dir / "workflows.json"

    def get_criteria_instances_file(self) -> Path:
        return self.data_dir / "criteria_instances.json"

    def get_history_dir(self) -> Path:
        return self.state_dir / "history"

    def get_log_dir(self) -> Path:
        return self.state_dir / "logs"

    def backup_file(self, file_path: Path) -> Path:
        """Backup a file into the backups directory with a timestamped name.

        The backup filename pattern is '<stem>_<YYYYmmddHHMMSS><suffix>'.
        """
        backups_dir = self.config_dir / "backups"
        backups_dir.mkdir(exist_ok=True, mode=0o700)

        if not file_path.exists():
            # Nothing to back up; return the intended path
            from datetime import datetime

            ts = datetime.now().strftime("%Y%m%d%H%M%S")
            backup_name = f"{file_path.stem}_{ts}{file_path.suffix}"
            return backups_dir / backup_name

        from datetime import datetime

        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        backup_name = f"{file_path.stem}_{ts}{file_path.suffix}"
        backup_path = backups_dir / backup_name

        try:
            with open(file_path, "rb") as src, open(backup_path, "wb") as dst:
                dst.write(src.read())
        except Exception as e:
            logger.error(f"Failed to backup file {file_path}: {e}")
            raise

        return backup_path
