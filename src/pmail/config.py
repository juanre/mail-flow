import os
import json
from pathlib import Path
from typing import Dict, Any, Optional
import logging


logger = logging.getLogger(__name__)


class Config:
    def __init__(self, config_dir: Optional[str] = None):
        if config_dir is None:
            config_dir = os.path.expanduser("~/.pmail")

        # Validate config directory path
        self.config_dir = Path(config_dir).resolve()

        # Security check - ensure we're not using system directories
        restricted_dirs = ["/", "/etc", "/usr", "/bin", "/sbin", "/var", "/tmp"]
        if str(self.config_dir) in restricted_dirs:
            raise ValueError(f"Cannot use system directory as config dir: {config_dir}")

        self._ensure_directories()
        self._load_config()

    def _ensure_directories(self):
        """Create necessary directories"""
        try:
            self.config_dir.mkdir(exist_ok=True, mode=0o700)  # Private directory
            (self.config_dir / "history").mkdir(exist_ok=True, mode=0o700)  # For readline history
        except Exception as e:
            logger.error(f"Failed to create config directories: {e}")
            raise

    def _load_config(self):
        """Load configuration with defaults"""
        config_file = self.config_dir / "config.json"
        if config_file.exists():
            try:
                with open(config_file, "r") as f:
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

    def _default_settings(self) -> Dict[str, Any]:
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

        storage_settings = self.settings.get("storage", {})

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
        return self.config_dir / "criteria_instances.json"

    def get_history_dir(self) -> Path:
        return self.config_dir / "history"
