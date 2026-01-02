from pathlib import Path

import pytest

from mailflow.config import Config, ConfigurationError


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

        # Check SOT-defined sections exist
        assert "archive" in config.settings
        assert "archivist" in config.settings
        assert "llmemory" in config.settings

    def test_load_toml_config(self, temp_config_dir):
        """Test loading config from TOML file."""
        config_file = Path(temp_config_dir) / "config.toml"
        config_file.write_text('''
[archive]
base_path = "~/MyArchive"

[archivist]
database_url = "postgresql://localhost/test"
db_schema = "test_schema"

[ui]
max_suggestions = 10
''')

        config = Config(config_dir=temp_config_dir)

        # Check loaded values override defaults
        assert config.settings["archive"]["base_path"] == "~/MyArchive"
        assert config.settings["archivist"]["database_url"] == "postgresql://localhost/test"
        assert config.settings["archivist"]["db_schema"] == "test_schema"
        assert config.settings["ui"]["max_suggestions"] == 10

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

    def test_invalid_toml_syntax(self, temp_config_dir):
        """Test that invalid TOML syntax raises ConfigurationError."""
        config_file = Path(temp_config_dir) / "config.toml"
        config_file.write_text('[archive\nbase_path = "broken"')

        with pytest.raises(ConfigurationError) as exc_info:
            Config(config_dir=temp_config_dir)

        assert "Invalid TOML" in str(exc_info.value)

    def test_valid_config_loaded_correctly(self, temp_config_dir):
        """Test that valid config is loaded correctly."""
        config_file = Path(temp_config_dir) / "config.toml"
        config_file.write_text('''
[archive]
base_path = "~/Archive"

[feature_weights]
from_domain = 0.5
subject_similarity = 0.5

[ui]
max_suggestions = 8

[learning]
min_confidence_threshold = 0.4

[llm]
model_alias = "fast"
''')

        config = Config(config_dir=temp_config_dir)

        # Check loaded values
        assert config.settings["ui"]["max_suggestions"] == 8
        assert config.settings["learning"]["min_confidence_threshold"] == 0.4
        assert config.settings["llm"]["model_alias"] == "fast"

    def test_uses_docflow_directory(self, monkeypatch, tmp_path):
        """Test that default config uses docflow instead of mailflow."""
        xdg_config = tmp_path / "config"
        xdg_config.mkdir()
        monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_config))

        config = Config()

        # Should use docflow, not mailflow
        assert "docflow" in str(config.config_dir)
        assert "mailflow" not in str(config.config_dir)


class TestArchivistPreflight:
    """Test archivist preflight checks."""

    def test_preflight_missing_database_url(self, temp_config_dir):
        """Test preflight fails when database_url is missing."""
        config = Config(config_dir=temp_config_dir)

        with pytest.raises(ConfigurationError) as exc_info:
            config.preflight_archivist()

        assert "archivist.database_url" in str(exc_info.value)

    def test_preflight_missing_db_schema(self, temp_config_dir):
        """Test preflight fails when db_schema is missing."""
        config_file = Path(temp_config_dir) / "config.toml"
        config_file.write_text('''
[archivist]
database_url = "postgresql://localhost/test"
''')

        config = Config(config_dir=temp_config_dir)

        with pytest.raises(ConfigurationError) as exc_info:
            config.preflight_archivist()

        assert "archivist.db_schema" in str(exc_info.value)

    def test_preflight_passes_with_all_required(self, temp_config_dir):
        """Test preflight passes when all required settings present."""
        config_file = Path(temp_config_dir) / "config.toml"
        config_file.write_text('''
[archivist]
database_url = "postgresql://localhost/test"
db_schema = "test_schema"
''')

        config = Config(config_dir=temp_config_dir)

        # Should not raise
        config.preflight_archivist()

    def test_get_archivist_database_url(self, temp_config_dir):
        """Test getting archivist database URL with preflight."""
        config_file = Path(temp_config_dir) / "config.toml"
        config_file.write_text('''
[archivist]
database_url = "postgresql://localhost/docflow"
db_schema = "archivist"
''')

        config = Config(config_dir=temp_config_dir)

        assert config.get_archivist_database_url() == "postgresql://localhost/docflow"
        assert config.get_archivist_db_schema() == "archivist"
