"""Configuration management (copy variant).

Singleton YAML configuration loader with path validation and
pre-creation of required directories. Responsibilities include:
- Loading YAML config once (singleton) and exposing dot-notation accessors.
- Static validation for required paths (e.g., web.upload_dir).
- Pre-creating commonly used directories before strict validation
  (web.upload_dir, watch_folder.dir, parent of logging.log_file, and
   selected task-specific directories).
- Dynamic validation for any keys ending with *_dir and *_file within
  nested dicts/lists.

Note: This 'copy' variant reflects behavior in this file and may differ
from [modules/config_manager.py](modules/config_manager.py) regarding specific validation
or pre-creation coverage. Review both modules if relying on nuanced differences.

Process exits on validation failure.
"""

import yaml
import sys
import logging
from pathlib import Path

class ConfigManager:
    """Singleton configuration manager.

    Provides one-time YAML loading, path validations, and directory
    pre-creation. Subsequent instantiations return the same instance.

    Initialization sequence:
    1) Load YAML configuration.
    2) Validate static core paths (web.upload_dir).
    3) Pre-create required directories (upload, watch folder, log parent,
       and selected storage task directories).
    4) Validate dynamic *_dir and *_file paths recursively.

    Key features:
    - Singleton semantics via __new__ to ensure a single loaded config.
    - Dot-notation lookup for nested configuration values.
    - Pre-creation of directories prior to strict dynamic validation.
    - Critical logging and process termination on validation failures.
    """

    _instance = None

    def __new__(cls, config_path: Path):
        """Create or return the singleton instance.

        Ensures only one instance exists. On first call, allocates the
        instance and triggers one-time initialization.

        Args:
            config_path (Path): Path to the YAML configuration file.

        Returns:
            ConfigManager: The singleton configuration manager.
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.__init__(config_path)
        return cls._instance

    def __init__(self, config_path: Path):
        """One-time initialization.

        Loads and validates configuration only once; subsequent calls
        are no-ops. Performs YAML parsing, static validation,
        directory pre-creation, and dynamic path validation.

        Args:
            config_path (Path): Path to the YAML configuration file.

        Notes:
            Process exits on validation failure.
        """
        # Initialize only once
        if hasattr(self, "_initialized") and self._initialized:
            return
        self._config_path = config_path
        self.logger = logging.getLogger("ConfigManager")
        self._initialized = True
        self._load_config()

    def get(self, key_path, default=None):
        """Get a configuration value using dot-notation.

        Traverses nested dictionaries using a dotted key path.

        Args:
            key_path (str): Dotted path to the value (e.g., "web.upload_dir").
            default (Any, optional): Value returned if path is missing
                or traversal encounters a non-dict. Defaults to None.

        Returns:
            Any: The resolved value or the default if not found.

        Edge cases:
            - If an intermediate node is not a dict, returns default.
            - If any key is missing, returns default.
        """
        keys = key_path.split(".")
        value = self.config
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key, default)
            else:
                return default
        return value

    def get_all(self) -> dict:
        """Return the entire configuration mapping.

        Returns:
            dict: The full configuration dictionary loaded from YAML.
        """
        return self.config

    def _load_config(self):
        """Load YAML configuration and run validations.

        Parsing sequence:
        1) Read and parse YAML via yaml.safe_load.
        2) Ensure root is a dict.
        3) Validate static paths.
        4) Pre-create required directories.
        5) Validate dynamic *_dir and *_file paths.

        Logging:
            - Logs critical errors for YAML parse issues or IO errors.

        Notes:
            Process exits on validation failure.
        """
        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                self.config = yaml.safe_load(f)
        except yaml.YAMLError as e:
            self.logger.critical(f"Invalid YAML in configuration file: {e}")
            sys.exit(1)
        except Exception as e:
            self.logger.critical(f"Error reading configuration file: {e}")
            sys.exit(1)

        if not isinstance(self.config, dict):
            self.logger.critical("Configuration file root must be a dictionary")
            sys.exit(1)

        # Validate static core paths
        self._validate_static_paths()

        # Pre-create required directories before strict validation
        self._precreate_required_directories()

        # Validate dynamic pipeline parameters ending with _dir or _file
        self._validate_dynamic_paths()

    def _validate_static_paths(self):
        """Validate required static paths.

        Ensures that web.upload_dir is configured, exists, and is a directory.

        Notes:
            Process exits on validation failure.
        """
        # Validate web.upload_dir
        upload_dir = self.get("web.upload_dir")
        if not upload_dir:
            self.logger.critical("Missing required static path in config: 'web.upload_dir'")
            sys.exit(1)
        upload_dir_path = Path(upload_dir)
        if not upload_dir_path.exists():
            self.logger.critical(f"Static path does not exist: 'web.upload_dir' -> {upload_dir_path}")
            sys.exit(1)
        if not upload_dir_path.is_dir():
            self.logger.critical(f"Static path is not a directory: 'web.upload_dir' -> {upload_dir_path}")
            sys.exit(1)

    def _precreate_required_directories(self):
        """Pre-create required directories based on configuration.

        Creates:
            - web.upload_dir
            - watch_folder.dir
            - Parent directory of logging.log_file
            - Selected task directories from pipeline:
              * standard_step.storage.store_metadata_as_csv/json -> params.data_dir
              * standard_step.storage.store_file_to_localdrive -> params.files_dir

        Side effects:
            - Creates directories with parents=True, exist_ok=True.
            - Logs info on successful creation, critical on failure.

        Notes:
            Process exits on validation failure (directory creation errors).
        """
        # Pre-create directories from config keys and pipeline steps
        dirs_to_create = []

        # web_upload directory
        web_upload_dir = self.get("web.upload_dir")
        if web_upload_dir:
            dirs_to_create.append(Path(web_upload_dir))

        # watch_folder directory
        watch_folder_dir = self.get("watch_folder.dir")
        if watch_folder_dir:
            dirs_to_create.append(Path(watch_folder_dir))

        # Parent directory of the log file
        log_file = self.get("logging.log_file")
        if log_file:
            log_file_path = Path(log_file)
            if log_file_path.parent:
                dirs_to_create.append(log_file_path.parent)

        # data directories from pipeline steps store_metadata_as_csv and store_metadata_as_json
        tasks_config = self.get("tasks", {})
        if not isinstance(tasks_config, dict):
            self.logger.warning("Configuration 'tasks' section is not a dictionary. Skipping directory pre-creation for tasks.")
            tasks_config = {} # Ensure it's a dictionary for safe access

        pipeline = self.get("pipeline", [])
        if isinstance(pipeline, list):
            for step_name in pipeline:
                if not isinstance(step_name, str):
                    self.logger.warning(f"Pipeline step name '{step_name}' is not a string. Skipping.")
                    continue

                task_definition = tasks_config.get(step_name, {})
                if not isinstance(task_definition, dict):
                    self.logger.warning(f"Task definition for '{step_name}' is not a dictionary. Skipping.")
                    continue

                module_name = task_definition.get("module", "")
                params = task_definition.get("params", {})

                # data directories from pipeline steps store_metadata_as_csv and store_metadata_as_json
                if module_name in ["standard_step.storage.store_metadata_as_csv", "standard_step.storage.store_metadata_as_json"]:
                    data_dir = params.get("data_dir")
                    if data_dir:
                        dirs_to_create.append(Path(data_dir))

                # files_dir from pipeline steps store_file_to_localdrive
                elif module_name == "standard_step.storage.store_file_to_localdrive":
                    files_dir = params.get("files_dir")
                    if files_dir:
                        dirs_to_create.append(Path(files_dir))

        # Create directories with parents=True and exist_ok=True
        for directory in dirs_to_create:
            try:
                directory.mkdir(parents=True, exist_ok=True)
                self.logger.info(f"Pre-created directory: {directory}")
            except Exception as e:
                self.logger.critical(f"Failed to create directory {directory}: {e}")
                sys.exit(1)

    def _validate_dynamic_paths(self):
        """Recursively validate dynamic *_dir and *_file paths.

        Traverses nested dicts and lists under the 'pipeline' section,
        ensuring:
            - *_dir points to an existing directory.
            - *_file points to an existing file.

        Notes:
            Process exits on validation failure.
        """
        # Recursively validate keys ending with _dir or _file in the config dictionary
        def recursive_validate(d, parent_keys=[]):
            if isinstance(d, dict):
                for k, v in d.items():
                    if isinstance(v, (dict, list)): # Handle both dicts and lists
                        recursive_validate(v, parent_keys + [k])
                    else:
                        if k.endswith("_dir"):
                            path_obj = Path(v)
                            if not path_obj.exists():
                                self.logger.critical(
                                    f"Dynamic directory path does not exist: {'.'.join(parent_keys + [k])} -> {path_obj}"
                                )
                                sys.exit(1)
                            if not path_obj.is_dir():
                                self.logger.critical(
                                    f"Dynamic path is not a directory: {'.'.join(parent_keys + [k])} -> {path_obj}"
                                )
                                sys.exit(1)
                        elif k.endswith("_file"):
                            path_obj = Path(v)
                            if not path_obj.exists():
                                self.logger.critical(
                                    f"Dynamic file path does not exist: {'.'.join(parent_keys + [k])} -> {path_obj}"
                                )
                                sys.exit(1)
                            if not path_obj.is_file():
                                self.logger.critical(
                                    f"Dynamic path is not a file: {'.'.join(parent_keys + [k])} -> {path_obj}"
                                )
                                sys.exit(1)
            elif isinstance(d, list): # New: Handle lists
                for item in d:
                    recursive_validate(item, parent_keys) # Recurse on each item in the list

        recursive_validate(self.config.get("pipeline", {}))