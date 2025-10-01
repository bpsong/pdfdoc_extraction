# Project Agents.md Guide for AI Agents (Python/Windows)

This document provides guidance for AI agents working on this Python project. Adherence to these guidelines ensures consistency and quality.

## Project Structure Overview

Familiarize yourself with the project layout before making changes.

-   `/modules`: Contains the main application's source code, organized by modules.
-   `/test`: Houses all test files.
-   `/tasks`: Houses product requirement document, task document and any other useful documents.
-   `/standard_step`: Houses all code for tasks.
-   `/docs`: Project documentation.
-   `requirements.txt`: A list of project dependencies.
-   `main.py`: The primary entry point for the application.

## Development Environment Setup (Windows)

The environment is windows os based.

1.  **Use full python path to run code**
    e.g. To run a test
    ```
    C:\Python313\python.exe -m pytest -v test/test_extract_pdf/test_extraction.py
    ```


## Coding Conventions

Follow these standards to maintain clean and readable code.

### General Conventions
-   Adhere to **PEP 8** style guidelines for all Python code.
-   Use **type hints** for all function signatures and complex variables.
-   Write clear and concise **docstrings** for all modules, classes, and functions, following the Google Python Style Guide.
-   Keep functions short and focused on a single task.
-   Use f-strings for string formatting (e.g., `f"Hello, {name}"`).
-   Manage dependencies by adding new packages to `requirements.txt`.

### Error Handling
-   Use specific exception types instead of generic `Exception`.
-   Log errors with sufficient context to aid in debugging.

## Testing Requirements

Testing is a critical part of our workflow.

-   Use the **pytest** framework for all tests.
-   Test files must be named `test_*.py` or `*_test.py`.
-   Test functions must be prefixed with `test_`.
-   Every new feature or bug fix must be accompanied by corresponding tests.
-   Run tests using the following command from the project root

    Example: 
    ```powershell
    C:\Python313\python.exe  -m pytest -v path\to\test_file.py
    ```



