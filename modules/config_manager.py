"""Singleton configuration loader that parses YAML, validates required paths,
and prepares directories for runtime.

Responsibilities:
- Load YAML configuration once (singleton semantics).
- Validate static paths such as web.upload_dir and watch_folder.dir.
- Pre-create directories for keys ending with *_dir across the config, excluding watch_folder.dir.
- Recursively validate dynamic *_dir and *_file paths after pre-creation.
- On validation or parsing failures, log at CRITICAL level and exit the process.

Notes:
The watch folder directory (watch_folder.dir) must pre-exist; it is not auto-created.

Example configuration:
web:
  host: "127.0.0.1"
  port: 8000
  secret_key: "your_secret_key"
  upload_dir: "web_upload"

watch_folder:
  dir: "watch_folder"
  validate_pdf_header: true
  processing_dir: "processing"

authentication:
  username: "admin"
  password_hash: "$2b$12$example_hash_for_secure_password"

logging:
  log_file: "app.log"
  log_level: "INFO"
  

tasks:
  extract_document_data:
    module: standard_step.extraction.extract_pdf
    class: ExtractPdfTask
    params:
      api_key: "your_llama_cloud_api_key"
      agent_id: "your_agent_id"
      fields:
        supplier_name:
          alias: "Supplier name"
          type: "str"
        invoice_amount:
          alias: "Invoice Amount"
          type: "float"
    on_error: stop

pipeline:
  - extract_document_data
"""

import yaml
import sys
import logging
from pathlib import Path


class ConfigManager:
    """Singleton manager for application configuration.

    The first instantiation loads and validates a YAML configuration file,
    caches the parsed dictionary, and performs path validation and directory
    pre-creation. Subsequent instantiations return the same instance without
    re-initializing.

    Initialization flow:
    1) Parse YAML from the provided path.
    2) Validate required static paths.
    3) Ensure watch_folder.dir exists (no auto-creation).
    4) Pre-create all directories referenced by *_dir keys, excluding watch_folder.dir.
    5) Recursively validate all *_dir and *_file paths.

    Features:
    - Dot-notation lookups via get().
    - Access to the entire configuration via get_all().
    - Critical logging and process exit on invalid configuration states.

    Example configuration:
    web:
      host: "127.0.0.1"
      port: 8000
      secret_key: "your_secret_key"
      upload_dir: "web_upload"

    watch_folder:
      dir: "watch_folder"
      validate_pdf_header: true
      processing_dir: "processing"

    authentication:
      username: "admin"
      password_hash: "$2b$12$example_hash_for_secure_password"

    logging:
      log_file: "app.log"
      log_level: "INFO"
      

    tasks:
      extract_document_data:
        module: standard_step.extraction.extract_pdf
        class: ExtractPdfTask
        params:
          api_key: "your_llama_cloud_api_key"
          agent_id: "your_agent_id"
          fields:
            supplier_name:
              alias: "Supplier name"
              type: "str"
            invoice_amount:
              alias: "Invoice Amount"
              type: "float"
        on_error: stop

    pipeline:
      - extract_document_data
    """
    _instance = None

    def __new__(cls, config_path: Path):
        """Create or return the singleton instance.

        Args:
            config_path (Path): Filesystem path to the YAML configuration file.

        Returns:
            ConfigManager: The singleton instance.

        Notes:
            The first call constructs and initializes the instance. Subsequent
            calls return the same instance without reinitialization.
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.__init__(config_path)
        return cls._instance

    def __init__(self, config_path: Path):
        """Initialize the configuration manager on first construction only.

        Args:
            config_path (Path): Filesystem path to the YAML configuration file.

        Notes:
            Side effects:
            - Loads YAML into memory.
            - Validates static and dynamic paths.
            - Creates required directories for *_dir keys (excluding watch_folder.dir).
            Subsequent calls are no-ops due to the singleton guard.
        """
        # Initialize only once
        if hasattr(self, "_initialized") and self._initialized:
            return
        self._config_path = config_path
        self.logger = logging.getLogger("ConfigManager")
        self._initialized = True
        self._load_config()

    def get(self, key_path, default=None):
        """Retrieve a value using dot-notation path.

        Args:
            key_path (str): Dot-separated path to a nested key (e.g., "web.upload_dir").
            default (Any, optional): Value to return if the key is missing or a non-dict
                segment is encountered. Defaults to None.

        Returns:
            Any: The value at key_path if found; otherwise default.

        Notes:
            If an intermediate value is not a dict, the lookup stops and returns default.
        """
        keys = key_path.split('.')
        value = self.config
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key, default)
            else:
                return default
        return value

    def get_all(self) -> dict:
        """Return the entire configuration dictionary.

        Returns:
            dict: Parsed configuration data.
        """
        return self.config

    def _load_config(self):
        """Load configuration from YAML and perform validation.

        Sequence:
        1) Parse YAML from self._config_path.
        2) Ensure root is a dictionary.
        3) Validate static paths (e.g., web.upload_dir).
        4) Validate watch_folder.dir exists (no auto-creation).
        5) Pre-create directories for *_dir (excluding watch_folder.dir).
        6) Recursively validate *_dir and *_file paths.

        Notes:
            On any parsing or validation failure, logs at CRITICAL level and
            exits the process (sys.exit(1)).
        """
        try:
            with open(self._config_path, 'r', encoding='utf-8') as f:
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

        # Validate critical watch folder must pre-exist (no auto-creation)
        self._validate_watch_folder()

        # Pre-create required directories before strict validation
        # Note: watch_folder.dir is intentionally excluded from pre-creation
        self._precreate_required_directories()

        # Validate dynamic pipeline parameters ending with _dir or _file
        self._validate_dynamic_paths()

    def _validate_static_paths(self):
        """Validate presence and existence of required static paths.

        Currently enforced:
        - web.upload_dir must be present and must be an existing directory.

        Notes:
            On failure, logs at CRITICAL level and exits the process.
        """
        # Validate web.upload_dir
        upload_dir = self.get('web.upload_dir')
        if not upload_dir:
            self.logger.critical("Missing required static path in config: 'web.upload_dir'")
            sys.exit(1)
        upload_dir_path = Path(upload_dir)
        if not upload_dir_path.exists() or not upload_dir_path.is_dir():
            self.logger.critical(f"Static path invalid: 'web.upload_dir' -> {upload_dir_path}")
            sys.exit(1)

    def _validate_watch_folder(self):
        """Ensure watch_folder.dir exists and is a directory.

        Notes:
            The directory must pre-exist; it will not be auto-created.
            On failure, logs at CRITICAL level and exits the process.
        """
        watch_dir = self.get('watch_folder.dir')
        if not watch_dir:
            self.logger.critical("Missing required static path in config: 'watch_folder.dir'")
            sys.exit(1)
        watch_dir_path = Path(watch_dir)
        if not watch_dir_path.exists() or not watch_dir_path.is_dir():
            self.logger.critical(f"Static path invalid: 'watch_folder.dir' -> {watch_dir_path}")
            sys.exit(1)

    def _precreate_required_directories(self):
        """Pre-create directories for any *_dir values across the configuration.

        Behavior:
        - Recursively collects keys ending with '_dir' whose values are strings.
        - Excludes the specific key 'watch_folder.dir' from auto-creation.
        - Creates missing directories with parents as needed.
        - Logs created directories at INFO level.

        Notes:
            On failure to create any directory, logs at CRITICAL level and exits.
        """
        dirs_to_create = set()

        def collect_dirs(obj, path_stack=None):
            if path_stack is None:
                path_stack = []
            if isinstance(obj, dict):
                for key, val in obj.items():
                    current_stack = path_stack + [key]
                    # Build dotted path to check exclusion
                    dotted = ".".join(current_stack)
                    if key.endswith('_dir') and isinstance(val, str):
                        # Exclude the specific key 'watch_folder.dir' from auto-creation
                        if dotted != "watch_folder.dir":
                            dirs_to_create.add(Path(val))
                    else:
                        collect_dirs(val, current_stack)
            elif isinstance(obj, list):
                for idx, item in enumerate(obj):
                    collect_dirs(item, path_stack + [f"[{idx}]"])

        collect_dirs(self.config)

        for d in dirs_to_create:
            try:
                d.mkdir(parents=True, exist_ok=True)
                self.logger.info(f"Pre-created directory: {d}")
            except Exception as e:
                self.logger.critical(f"Could not create directory {d}: {e}")
                sys.exit(1)

    def _validate_dynamic_paths(self):
        """Recursively validate *_dir and *_file paths throughout the configuration.

        Rules:
        - Keys ending with '_dir' must reference existing directories.
        - Keys ending with '_file' must reference existing files.

        Notes:
            On any invalid path, logs at CRITICAL level and exits the process.
        """
        def recursive_validate(obj, path_trace='root'):
            if isinstance(obj, dict):
                for key, val in obj.items():
                    current_trace = f"{path_trace}.{key}"
                    if key.endswith('_dir') and isinstance(val, str):
                        p = Path(val)
                        if not p.exists() or not p.is_dir():
                            self.logger.critical(
                                f"Configured directory '{current_trace}' ({val}) does not exist or isn’t a directory"
                            )
                            sys.exit(1)
                    elif key.endswith('_file') and isinstance(val, str):
                        p = Path(val)
                        if not p.exists() or not p.is_file():
                            self.logger.critical(
                                f"Configured file '{current_trace}' ({val}) does not exist or isn’t a file"
                            )
                            sys.exit(1)
                    else:
                        recursive_validate(val, current_trace)
            elif isinstance(obj, list):
                for idx, item in enumerate(obj):
                    recursive_validate(item, f"{path_trace}[{idx}]")

        recursive_validate(self.config)
