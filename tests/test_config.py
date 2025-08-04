import pytest
import json
from pathlib import Path

from pmail.config import Config


class TestConfig:
    def test_config_creates_directories(self, temp_config_dir):
        config = Config(config_dir=temp_config_dir)

        # Check all directories are created
        assert Path(temp_config_dir).exists()
        assert (Path(temp_config_dir) / "workflows").exists()
        assert (Path(temp_config_dir) / "history").exists()
        assert (Path(temp_config_dir) / "backups").exists()

    def test_default_settings(self, temp_config_dir):
        config = Config(config_dir=temp_config_dir)

        # Check default settings
        assert "feature_weights" in config.settings
        assert "ui" in config.settings
        assert "learning" in config.settings

        # Check specific defaults
        assert config.settings["feature_weights"]["from_domain"] == 0.3
        assert config.settings["ui"]["max_suggestions"] == 5
        assert config.settings["learning"]["min_confidence_threshold"] == 0.3

    def test_save_and_load_config(self, temp_config_dir):
        config = Config(config_dir=temp_config_dir)

        # Modify settings
        config.settings["ui"]["max_suggestions"] = 10
        config.save_config()

        # Create new config instance and check it loads the saved settings
        config2 = Config(config_dir=temp_config_dir)
        assert config2.settings["ui"]["max_suggestions"] == 10

    def test_backup_file(self, temp_config_dir):
        config = Config(config_dir=temp_config_dir)

        # Create a test file
        test_file = Path(temp_config_dir) / "test.json"
        test_file.write_text('{"test": true}')

        # Backup the file
        config.backup_file(test_file)

        # Check backup exists
        backups = list((Path(temp_config_dir) / "backups").glob("test_*.json"))
        assert len(backups) == 1
        assert backups[0].read_text() == '{"test": true}'
