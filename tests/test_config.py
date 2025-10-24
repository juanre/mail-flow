from pathlib import Path

from mailflow.config import Config


class TestConfig:
    def test_config_creates_directories(self, temp_config_dir):
        config = Config(config_dir=temp_config_dir)

        # Check all XDG directories are created
        assert Path(temp_config_dir).exists()
        assert (Path(temp_config_dir) / "workflows").exists()
        assert (Path(temp_config_dir) / "backups").exists()
        assert (Path(temp_config_dir) / "data").exists()
        assert (Path(temp_config_dir) / "state").exists()
        assert (Path(temp_config_dir) / "state" / "history").exists()
        assert (Path(temp_config_dir) / "state" / "logs").exists()
        assert (Path(temp_config_dir) / "cache").exists()

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

    def test_invalid_config_structure_missing_keys(self, temp_config_dir, capsys):
        """Test that missing required keys are detected and config is restored to defaults"""
        # Create config with missing keys
        config_file = Path(temp_config_dir) / "config.json"
        config_file.write_text('{"feature_weights": {}, "ui": {}}')

        # Load config - should detect invalid structure
        config = Config(config_dir=temp_config_dir)

        # Should use defaults
        assert "learning" in config.settings
        assert "storage" in config.settings
        assert "security" in config.settings
        assert "llm" in config.settings

        # Should backup invalid config
        invalid_backups = list(Path(temp_config_dir).glob("config.json.invalid*"))
        assert len(invalid_backups) == 1

        # Should print warning to user
        captured = capsys.readouterr()
        assert "WARNING" in captured.out
        assert "Invalid config.json structure" in captured.out

    def test_invalid_config_structure_wrong_type(self, temp_config_dir, capsys):
        """Test that wrong types for required keys are detected"""
        # Create config with wrong type (string instead of dict)
        config_file = Path(temp_config_dir) / "config.json"
        config_file.write_text('{"feature_weights": "not a dict", "ui": {}, "learning": {}, "storage": {}, "security": {}, "llm": {}}')

        # Load config - should detect invalid structure
        config = Config(config_dir=temp_config_dir)

        # Should use defaults
        assert isinstance(config.settings["feature_weights"], dict)

        # Should backup invalid config
        invalid_backups = list(Path(temp_config_dir).glob("config.json.invalid*"))
        assert len(invalid_backups) == 1

        # Should print warning to user
        captured = capsys.readouterr()
        assert "WARNING" in captured.out
        assert "Invalid config.json structure" in captured.out

    def test_invalid_json_syntax(self, temp_config_dir, capsys):
        """Test that invalid JSON syntax is handled gracefully"""
        # Create config with invalid JSON
        config_file = Path(temp_config_dir) / "config.json"
        config_file.write_text('{"feature_weights": {')

        # Load config - should detect invalid JSON
        config = Config(config_dir=temp_config_dir)

        # Should use defaults
        assert "feature_weights" in config.settings
        assert isinstance(config.settings["feature_weights"], dict)

        # Should backup invalid config
        invalid_backups = list(Path(temp_config_dir).glob("config.json.invalid*"))
        assert len(invalid_backups) == 1

        # Should print warning to user
        captured = capsys.readouterr()
        assert "WARNING" in captured.out
        assert "Invalid JSON" in captured.out

    def test_valid_config_structure_loaded_correctly(self, temp_config_dir):
        """Test that valid config structure is loaded without backup"""
        # Create valid config with custom values
        config_file = Path(temp_config_dir) / "config.json"
        config_file.write_text('''{
            "feature_weights": {"from_domain": 0.5, "subject_similarity": 0.5},
            "ui": {"max_suggestions": 8},
            "learning": {"min_confidence_threshold": 0.4},
            "storage": {"max_criteria_instances": 5000},
            "security": {"allowed_directories": ["~"]},
            "llm": {"enabled": true},
            "archive": {"enabled": true, "base_path": "~/Archive"}
        }''')

        # Load config
        config = Config(config_dir=temp_config_dir)

        # Should load custom values
        assert config.settings["ui"]["max_suggestions"] == 8
        assert config.settings["learning"]["min_confidence_threshold"] == 0.4

        # Should NOT create backup
        invalid_backups = list(Path(temp_config_dir).glob("config.json.invalid*"))
        assert len(invalid_backups) == 0
