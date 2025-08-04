import os
import json
from pathlib import Path
from typing import Dict, Any, Optional


class Config:
    def __init__(self, config_dir: Optional[str] = None):
        if config_dir is None:
            config_dir = os.path.expanduser("~/.pmail")
        self.config_dir = Path(config_dir)
        self._ensure_directories()
        self._load_config()
    
    def _ensure_directories(self):
        self.config_dir.mkdir(exist_ok=True)
        (self.config_dir / "workflows").mkdir(exist_ok=True)
        (self.config_dir / "history").mkdir(exist_ok=True)
        (self.config_dir / "backups").mkdir(exist_ok=True)
    
    def _load_config(self):
        config_file = self.config_dir / "config.json"
        if config_file.exists():
            with open(config_file, 'r') as f:
                self.settings = json.load(f)
        else:
            self.settings = self._default_settings()
            self.save_config()
    
    def _default_settings(self) -> Dict[str, Any]:
        return {
            "feature_weights": {
                "from_domain": 0.3,
                "subject_similarity": 0.25,
                "has_pdf": 0.2,
                "body_keywords": 0.15,
                "to_address": 0.1
            },
            "ui": {
                "max_suggestions": 5,
                "show_confidence": True,
                "confirm_before_execute": True
            },
            "learning": {
                "recency_weight": 0.8,
                "min_confidence_threshold": 0.3
            }
        }
    
    def save_config(self):
        config_file = self.config_dir / "config.json"
        with open(config_file, 'w') as f:
            json.dump(self.settings, f, indent=2)
    
    def get_workflows_file(self) -> Path:
        return self.config_dir / "workflows.json"
    
    def get_criteria_instances_file(self) -> Path:
        return self.config_dir / "criteria_instances.json"
    
    def get_history_dir(self) -> Path:
        return self.config_dir / "history"
    
    def backup_file(self, filepath: Path):
        import shutil
        from datetime import datetime
        if filepath.exists():
            backup_name = f"{filepath.stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{filepath.suffix}"
            backup_path = self.config_dir / "backups" / backup_name
            shutil.copy2(filepath, backup_path)