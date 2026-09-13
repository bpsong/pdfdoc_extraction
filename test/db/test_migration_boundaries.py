"""Migration import boundaries and runtime snapshot refresh regression checks."""

import subprocess
import sys
from pathlib import Path

import yaml

from modules.config_manager import ConfigManager
from modules.services.startup_migration_service import initialize_database
from test.db.test_versioned_config_migration import _legacy_config, _prepare_v2


def test_database_modules_do_not_import_application_services() -> None:
    result = subprocess.run(
        [sys.executable, "-c", "import sys; import modules.db.migrations; "
         "import modules.db.schema_version; "
         "assert not any(n.startswith('modules.services.') for n in sys.modules)"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr


def test_legacy_migration_refreshes_real_config_snapshot(tmp_path: Path) -> None:
    legacy = _legacy_config(tmp_path, review_tasks=0)
    values = legacy.get_all()
    for name in ("uploads", "watch"):
        (tmp_path / name).mkdir()
    values.update({"web": {"upload_dir": "uploads"}, "watch_folder": {"dir": "watch"}})
    legacy._config_path.write_text(yaml.safe_dump(values), encoding="utf-8")
    _prepare_v2(legacy)
    config = ConfigManager(legacy._config_path)
    initialize_database(config)
    assert isinstance(config.get("tasks.extract.params.api_key"), dict)
    assert config.get("tasks.extract.params.api_key") == yaml.safe_load(
        legacy._config_path.read_text(encoding="utf-8")
    )["tasks"]["extract"]["params"]["api_key"]
