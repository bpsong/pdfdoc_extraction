"""
Config Check CLI Tool

A CLI tool for validating configuration YAML files for the PDF processing system.
This package provides validation capabilities for configuration files used by the
main PDF document extraction application.

Note: This tool is designed for Windows environment (Windows 11) and uses
Windows-safe path handling (os.path, pathlib) throughout. Tests and examples
use Windows-style invocations.
"""

__version__ = "0.1.0"
__author__ = "PDF Document Extraction System"

from .validator import ConfigValidator, ValidationMessage, ValidationResult
from .parameter_validator import validate_parameters
from .path_validator import PathValidator
from .task_validator import validate_tasks
from .yaml_parser import YAMLParser

__all__ = [
    "ConfigValidator",
    "ValidationMessage",
    "ValidationResult",
    "validate_parameters",
    "PathValidator",
    "validate_tasks",
    "YAMLParser",
]
