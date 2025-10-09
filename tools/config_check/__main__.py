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
import sys
from pathlib import Path
from typing import Optional

from .schema import load_config_schema
from .validator import ConfigValidator
from .reporter import ValidationReporter

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
        description='Validate configuration YAML files for PDF processing system',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Usage Examples:
 python -m tools.config_check validate --config config.yaml --verbose
 python -m tools.config_check validate --config ./config.yaml --format json --strict
 python -m tools.config_check schema --format json
 python -m tools.config_check validate --config config.yaml --base-dir /app/config --import-checks

Exit Codes:
 0 = Valid (no errors; warnings allowed)
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
        help='Validate configuration file against schema and requirements',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
 python -m tools.config_check validate --config config.yaml
 python -m tools.config_check validate --config ./config.yaml --format json --strict --base-dir /app

Exit Codes:
 0 = Valid (no errors; warnings allowed)
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
        f"security_analysis={args.security_analysis}"
    ]
    # Filter out None values and join with spaces for one-line format
    valid_args = [arg for arg in args_summary if arg is not None]
    print(" ".join(valid_args))

    if not config_exists:
        logger.error(f"Configuration file not found: {resolved_config_path}")
        return 64  # Exit code 64: Usage error for unreadable or missing config

    validator = ConfigValidator(
        strict_mode=args.strict,
        base_dir=args.base_dir,
        import_checks=args.import_checks,
        check_files=args.check_files,
        performance_analysis=args.performance_analysis,
        security_analysis=args.security_analysis,
    )
    validation_result = validator.validate(resolved_config_path)

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

    schema_definition = load_config_schema()
    print(dumps(schema_definition, indent=2))

    logger.info(f"Generated schema in {args.format} format")
    return 0


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
    elif args.command == 'schema':
        return run_schema_command(args, logger)
    else:
        print(f"Error: Unknown command '{args.command}'")
        return 64


if __name__ == "__main__":
    sys.exit(main())