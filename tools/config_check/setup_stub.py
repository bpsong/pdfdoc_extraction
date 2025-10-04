"""
Legacy packaging placeholder for config-check.

The project now uses pyproject.toml with setuptools for builds. This module
remains to avoid breaking older documentation but is no longer imported
during packaging.
"""

# Placeholder for future setup.py or pyproject.toml content
# For now, the tool is used as: python -m tools.config_check

SETUP_INFO = {
    "name": "config-check",
    "version": "0.1.0",
    "description": "CLI tool for validating PDF processing system configuration files",
    "author": "PDF Document Extraction System",
    "python_requires": ">=3.8",
    "install_requires": [
        "pyyaml>=6.0",
        "pydantic>=2.0",
        "ruamel.yaml>=0.18",
    ],
    "entry_points": {
        "console_scripts": [
            "config-check=tools.config_check.__main__:main",
        ],
    },
}

# For future use when packaging is needed:
# from setuptools import setup
# setup(**SETUP_INFO)
