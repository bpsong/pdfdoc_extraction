#!/usr/bin/env python3
"""
Config Check CLI Tool - Main Entry Point

A CLI tool for validating configuration YAML files for the PDF processing system.

This implements Task 2.0 from the PRD checklist:
- Complete CLI argument parsing and interface
- Subcommands 'validate' and 'schema' are required
- Proper exit codes and input validation

The module exposes the CLI entry point used by the integration tests and packaging metadata.
"""

import argparse
import logging
import os
import sqlite3
import sys
import yaml
from pathlib import Path
from typing import Optional

from .schema import load_config_schema
from .validator import ConfigValidator
from .reporter import ValidationReporter
from .stored_validator import (
    StoredSourceValidator,
    configured_database_path,
    load_document,
    open_readonly_database,
    portable_contract_schema,
    validate_database_schema,
    validate_portable_file,
)
from .validator import ValidationMessage, ValidationResult

def setup_logging(verbose: bool = False) -> logging.Logger:
    """
    Set up basic logging configuration for the CLI tool.

    Args:
        verbose: Enable verbose logging if True

    Returns:
        Configured logger instance
    """
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG if verbose else logging.INFO)

    # Remove existing handlers to avoid duplication
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create formatter similar to main app
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")

    # Console handler for stdout
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    return root_logger


def validate_format_choice(format_value: str, valid_choices: list) -> str:
    """
    Validate format choice and provide clear error message.

    Args:
        format_value: The format value to validate
        valid_choices: List of valid format options

    Returns:
        The validated format value

    Raises:
        ValueError: For invalid format
    """
    if format_value not in valid_choices:
        error_msg = f"Error: Invalid format '{format_value}'. Valid options are: {', '.join(valid_choices)}"
        raise ValueError(error_msg)
    return format_value


def resolve_config_path(config_path: str) -> tuple[str, bool]:
    """
    Resolve config path to absolute path and check existence.

    Args:
        config_path: The config file path to resolve

    Returns:
        Tuple of (absolute_path, exists)
    """
    try:
        path_obj = Path(config_path)
        absolute_path = str(path_obj.resolve())

        # Check if file exists and warn if not
        if not path_obj.exists():
            print(f"Warning: Config file '{absolute_path}' does not exist. Validation will proceed but may fail.")

        return absolute_path, path_obj.exists()

    except Exception as e:
        error_msg = f"Error: Could not resolve config path '{config_path}': {e}"
        raise ValueError(error_msg)


def create_parser() -> argparse.ArgumentParser:
    """
    Create the main argument parser for the config-check CLI.

    Returns:
        Configured ArgumentParser instance
    """
    parser = argparse.ArgumentParser(
        prog='config-check',
        description=(
            'Validate deployment, stored, and portable configuration for the '
            'PDF processing system'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Usage Examples:
 python -m tools.config_check validate --config config.yaml --verbose
 python -m tools.config_check validate --config ./config.yaml --format json --strict
 python -m tools.config_check validate --config config.yaml --pipeline invoices --version 3
 python -m tools.config_check validate --config config.yaml --all-stored
 python -m tools.config_check validate-file --file pipeline.yaml --kind pipeline
 python -m tools.config_check schema --format json
 python -m tools.config_check validate --config config.yaml --base-dir /app/config --import-checks

Exit Codes:
 0 = Valid (no errors or warnings)
 1 = One or more errors found
 2 = Only warnings found (no errors)
 64 = Usage error (bad flags, invalid paths)
       """
    )

    # Global options
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging output'
    )

    # Require subcommand - fail if missing
    subparsers = parser.add_subparsers(
        dest='command',
        help='Available commands',
        required=True  # This makes subcommands required
    )

    # Validate subcommand
    validate_parser = subparsers.add_parser(
        'validate',
        help='Validate deployment YAML and optional read-only stored definitions',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
 python -m tools.config_check validate --config config.yaml
 python -m tools.config_check validate --config ./config.yaml --format json --strict --base-dir /app
 python -m tools.config_check validate --config config.yaml --pipeline invoices --draft
 python -m tools.config_check validate --config config.yaml --review-schema invoice --version 2
 python -m tools.config_check validate --config config.yaml --all-stored

Exit Codes:
 0 = Valid (no errors or warnings)
 1 = One or more errors found
 2 = Only warnings found (no errors)
 64 = Usage error (bad arguments, invalid paths)
       """
    )

    # --config with default value
    validate_parser.add_argument(
        '--config', '-c',
        default='./config.yaml',
        help='Path to configuration YAML file to validate (default: ./config.yaml)'
    )

    # --format with validation
    validate_parser.add_argument(
        '--format', '-f',
        choices=['text', 'json'],
        default='text',
        help='Output format for validation results (default: text)'
    )

    validate_parser.add_argument(
        '--strict', '-s',
        action='store_true',
        help='Enable strict validation mode (unknown keys are errors)'
    )

    validate_parser.add_argument(
        '--base-dir',
        help='Base directory for resolving relative paths in config'
    )

    validate_parser.add_argument(
        '--import-checks',
        action='store_true',
        help='Enable validation of import references in config'
    )

    validate_parser.add_argument(
        '--check-files',
        action='store_true',
        help='Enable runtime file system validation (check file existence, permissions, CSV structure)'
    )

    validate_parser.add_argument(
        '--performance-analysis',
        action='store_true',
        help='Enable performance impact analysis (check for potential performance issues)'
    )

    validate_parser.add_argument(
        '--security-analysis',
        action='store_true',
        help='Enable security analysis (check for potential security vulnerabilities)'
    )

    validate_parser.add_argument(
        '--pipeline',
        metavar='KEY',
        help='Validate one stored pipeline template by stable key',
    )
    validate_parser.add_argument(
        '--review-schema',
        metavar='KEY',
        help='Validate one stored review-schema template by stable key',
    )
    validate_parser.add_argument(
        '--draft',
        action='store_true',
        help='Validate the selected stored template draft',
    )
    validate_parser.add_argument(
        '--version',
        type=int,
        metavar='N',
        help='Validate the selected stored template version number',
    )
    validate_parser.add_argument(
        '--all-stored',
        action='store_true',
        help='Validate every stored draft/version and enabled binding',
    )

    validate_file_parser = subparsers.add_parser(
        'validate-file',
        help='Validate a runtime or portable YAML/JSON file without importing it',
    )
    validate_file_parser.add_argument('path', nargs='?')
    validate_file_parser.add_argument('--file', dest='file_option')
    validate_file_parser.add_argument(
        '--kind',
        required=True,
        choices=['runtime', 'pipeline', 'review-schema'],
    )
    validate_file_parser.add_argument('--config')
    validate_file_parser.add_argument(
        '--format', '-f', choices=['text', 'json'], default='text'
    )
    validate_file_parser.add_argument('--strict', '-s', action='store_true')
    validate_file_parser.add_argument('--base-dir')
    validate_file_parser.add_argument('--import-checks', action='store_true')
    validate_file_parser.add_argument('--check-files', action='store_true')
    validate_file_parser.add_argument(
        '--performance-analysis', action='store_true'
    )
    validate_file_parser.add_argument('--security-analysis', action='store_true')

    # Schema subcommand
    schema_parser = subparsers.add_parser(
        'schema',
        help='Generate or display configuration JSON schema',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
 python -m tools.config_check schema --format json

Exit Codes:
 0 = Success (schema generated)
 64 = Usage error (bad arguments)
       """
    )

    # Schema only supports json format
    schema_parser.add_argument(
        '--format', '-f',
        choices=['json'],
        default='json',
        help='Output format for schema (only json supported)'
    )
    schema_parser.add_argument(
        '--kind',
        choices=['runtime', 'pipeline', 'review-schema', 'pipeline-bundle'],
        default='runtime',
        help='Contract schema to emit (default: runtime)',
    )

    return parser


def run_validate_command(args, logger: logging.Logger) -> int:
    """
    Execute the validate subcommand with structured reporting.

    Args:
        args: Parsed command line arguments
        logger: Configured logger instance

    Returns:
        Exit code (0=success, 1=errors found, 2=warnings only)
    """
    logger.info("Starting validate command execution")

    # Validate format choice
    try:
        validate_format_choice(args.format, ['text', 'json'])
    except ValueError as e:
        print(e)
        return 64

    # Resolve and validate config path
    try:
        resolved_config_path, config_exists = resolve_config_path(args.config)
    except ValueError as e:
        print(e)
        return 64

    # Print one-line structured summary of effective arguments as required
    args_summary = [
        f"config_path={resolved_config_path}",
        f"format={args.format}",
        f"strict_mode={args.strict}",
        f"verbose={args.verbose}",
        f"base_dir={args.base_dir}" if args.base_dir else None,
        f"import_checks={args.import_checks}",
        f"check_files={args.check_files}",
        f"performance_analysis={args.performance_analysis}",
        f"security_analysis={args.security_analysis}",
        f"pipeline={args.pipeline}" if args.pipeline else None,
        f"review_schema={args.review_schema}" if args.review_schema else None,
        f"draft={args.draft}",
        f"version={args.version}" if args.version is not None else None,
        f"all_stored={args.all_stored}",
    ]
    # Filter out None values and join with spaces for one-line format
    valid_args = [arg for arg in args_summary if arg is not None]
    print(" ".join(valid_args))

    if not config_exists:
        logger.error(f"Configuration file not found: {resolved_config_path}")
        return 64  # Exit code 64: Usage error for unreadable or missing config

    selector_error = _validate_stored_selectors(args)
    if selector_error:
        print(f"Error: {selector_error}")
        return 64

    validator = ConfigValidator(
        strict_mode=args.strict,
        base_dir=args.base_dir,
        import_checks=args.import_checks,
        check_files=args.check_files,
        performance_analysis=args.performance_analysis,
        security_analysis=args.security_analysis,
    )
    validation_result = validator.validate(resolved_config_path)

    try:
        runtime_config = load_document(Path(resolved_config_path))
    except (OSError, ValueError, yaml.YAMLError) as exc:
        runtime_config = {}
        validation_result.errors.append(
            ValidationMessage(
                path="config",
                message=str(exc),
                code="runtime-config-invalid",
            )
        )
    database_path = configured_database_path(
        Path(resolved_config_path), runtime_config
    )
    stored_requested = bool(
        args.pipeline or args.review_schema or args.all_stored
    )
    if database_path is None and stored_requested:
        print(
            "Error: Stored-source validation requires database.path in --config."
        )
        return 64
    if database_path is not None:
        try:
            with open_readonly_database(database_path) as conn:
                schema_result = validate_database_schema(conn)
                _merge_results(validation_result, schema_result)
                if schema_result.is_valid:
                    stored = StoredSourceValidator(
                        conn, runtime_config=runtime_config
                    )
                    if args.pipeline:
                        stored_result = stored.validate_pipeline(
                            args.pipeline,
                            draft=args.draft,
                            version_number=args.version,
                        )
                    elif args.review_schema:
                        stored_result = stored.validate_review_schema(
                            args.review_schema,
                            draft=args.draft,
                            version_number=args.version,
                        )
                    elif args.all_stored:
                        stored_result = stored.validate_all()
                    else:
                        stored_result = stored.validate_default()
                    _merge_results(validation_result, stored_result)
                    for legacy_key in ("pipeline", "tasks"):
                        if legacy_key in runtime_config:
                            validation_result.warnings.append(
                                ValidationMessage(
                                    path=f"deployment_yaml.{legacy_key}",
                                    message=(
                                        f"Legacy root {legacy_key} is migration-only "
                                        "and is not an active runtime definition."
                                    ),
                                    code="legacy-runtime-definition-deprecated",
                                )
                            )
                    schema_config = runtime_config.get("schema")
                    configured_schema_dirs = (
                        schema_config.get("directories")
                        if isinstance(schema_config, dict)
                        else None
                    )
                    schema_roots = []
                    if isinstance(configured_schema_dirs, list):
                        schema_roots.extend(
                            Path(item)
                            if Path(item).is_absolute()
                            else Path(resolved_config_path).parent / item
                            for item in configured_schema_dirs
                            if isinstance(item, str)
                        )
                    default_schema_root = (
                        Path(resolved_config_path).parent / "schemas"
                    )
                    if default_schema_root.exists():
                        schema_roots.append(default_schema_root)
                    if any(
                        root.exists()
                        and any(
                            path.suffix.lower() in {".yaml", ".yml", ".json"}
                            for path in root.iterdir()
                            if path.is_file()
                        )
                        for root in schema_roots
                    ):
                        validation_result.warnings.append(
                            ValidationMessage(
                                path="deployment_yaml.schema.directories",
                                message=(
                                    "Filesystem review schemas are migration/import-only "
                                    "and are not active runtime definitions."
                                ),
                                code="legacy-filesystem-schema-deprecated",
                            )
                        )
        except (FileNotFoundError, sqlite3.DatabaseError) as exc:
            validation_result.errors.append(
                ValidationMessage(
                    path="database",
                    message=str(exc),
                    code="database-unavailable",
                )
            )

    if args.base_dir:
        logger.debug(f"Base directory override: {args.base_dir}")
    if args.import_checks:
        logger.info("Import checks enabled")
    if args.check_files:
        logger.info("Runtime file validation enabled")
    if args.performance_analysis:
        logger.info("Performance analysis enabled")
    if args.security_analysis:
        logger.info("Security analysis enabled")

    # Create reporter based on format choice
    reporter = ValidationReporter(
        output_format=args.format,
        show_suggestions=True  # Enable suggestions for CLI output
    )

    # Add validation results to reporter
    reporter.add_validation_result(validation_result, config_path=resolved_config_path)

    # Generate and display report
    reporter.print_report()

    # Return appropriate exit code based on findings
    return reporter.determine_exit_code()


def run_schema_command(args, logger: logging.Logger) -> int:
    """
    Execute the schema subcommand with placeholder implementation.

    Args:
        args: Parsed command line arguments
        logger: Configured logger instance

    Returns:
        Exit code (0 for success)
    """
    logger.info("Starting schema command execution")

    # Schema only supports JSON format
    try:
        validate_format_choice(args.format, ['json'])
    except ValueError as e:
        print(e)
        return 64

    from json import dumps

    schema_definition = portable_contract_schema(args.kind)
    print(dumps(schema_definition, indent=2))

    logger.info(f"Generated schema in {args.format} format")
    return 0


def _validate_stored_selectors(args) -> str | None:
    """Return a usage error for incompatible stored-source flags."""
    selected = int(bool(args.pipeline)) + int(bool(args.review_schema))
    if args.all_stored and (
        selected or args.draft or args.version is not None
    ):
        return "--all-stored cannot be combined with a template selector."
    if selected > 1:
        return "--pipeline and --review-schema are mutually exclusive."
    if selected == 0 and (args.draft or args.version is not None):
        return "--draft/--version requires --pipeline or --review-schema."
    if selected == 1 and args.draft == (args.version is not None):
        return "A stored template selector requires exactly one of --draft or --version."
    if args.version is not None and args.version < 1:
        return "--version must be a positive integer."
    return None


def _merge_results(target: ValidationResult, source: ValidationResult) -> None:
    target.errors.extend(source.errors)
    target.warnings.extend(source.warnings)


def run_validate_file_command(args, logger: logging.Logger) -> int:
    """Validate a standalone file without importing or writing state."""
    raw_path = args.file_option or args.path
    if not raw_path or (args.file_option and args.path):
        print("Error: validate-file requires exactly one path or --file.")
        return 64
    path = Path(raw_path).resolve()
    if not path.exists() or not path.is_file():
        print(f"Error: Validation file not found: {path}")
        return 64
    runtime_config: dict = {}
    conn = None
    try:
        if args.kind == "runtime":
            validator = ConfigValidator(
                strict_mode=args.strict,
                base_dir=args.base_dir or path.parent,
                import_checks=args.import_checks,
                check_files=args.check_files,
                performance_analysis=args.performance_analysis,
                security_analysis=args.security_analysis,
            )
            result = validator.validate(path)
        else:
            context = None
            if args.config:
                config_path = Path(args.config).resolve()
                if not config_path.exists():
                    print(f"Error: Configuration file not found: {config_path}")
                    return 64
                runtime_config = load_document(config_path)
                database_path = configured_database_path(
                    config_path, runtime_config
                )
                if database_path is None:
                    print("Error: --config does not define database.path.")
                    return 64
                context = open_readonly_database(database_path)
                conn = context.__enter__()
                schema_result = validate_database_schema(conn)
                if not schema_result.is_valid:
                    result = schema_result
                else:
                    result = validate_portable_file(
                        path,
                        kind=args.kind,
                        runtime_config=runtime_config,
                        conn=conn,
                    )
            else:
                result = validate_portable_file(
                    path,
                    kind=args.kind,
                    runtime_config=runtime_config,
                )
        reporter = ValidationReporter(
            output_format=args.format, show_suggestions=True
        )
        reporter.add_validation_result(result, config_path=str(path))
        reporter.print_report()
        return reporter.determine_exit_code()
    except (OSError, ValueError, sqlite3.DatabaseError) as exc:
        logger.error("Validation failed: %s", exc)
        return 1
    finally:
        if 'context' in locals() and context is not None:
            context.__exit__(None, None, None)


def main(argv: Optional[list] = None) -> int:
    """
    Main entry point for the config-check CLI tool.

    Args:
        argv: Optional command line arguments for testing (default: sys.argv)

    Returns:
        Exit code (0=success, 1=errors, 2=warnings-only, 64=usage errors)
    """
    # Handle case where no arguments are provided
    if argv is None:
        argv = sys.argv[1:]  # Exclude script name

    # If no arguments provided, show usage and exit with 64
    if not argv:
        parser = create_parser()
        parser.print_usage(sys.stderr)
        print("config-check: error: the following arguments are required: command", file=sys.stderr)
        return 64

    parser = create_parser()

    # Parse arguments manually to handle errors properly
    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        # This shouldn't happen with normal argparse usage
        return 64

    # Check if command is missing (subcommand not provided)
    if not hasattr(args, 'command') or args.command is None:
        parser.print_usage(sys.stderr)
        print("config-check: error: the following arguments are required: command", file=sys.stderr)
        return 64

    # Set up logging based on verbose flag
    logger = setup_logging(verbose=getattr(args, 'verbose', False))

    # Execute appropriate command
    if args.command == 'validate':
        return run_validate_command(args, logger)
    elif args.command == 'validate-file':
        return run_validate_file_command(args, logger)
    elif args.command == 'schema':
        return run_schema_command(args, logger)
    else:
        print(f"Error: Unknown command '{args.command}'")
        return 64


if __name__ == "__main__":
    sys.exit(main())
