"""
Test suite for SecurityValidator functionality.

This module provides unit tests for the security analysis capabilities
of the config-check tool, ensuring that security vulnerabilities are
correctly identified and appropriate remediation recommendations are provided.
"""

import unittest
from typing import Dict, Any

from .security_validator import SecurityValidator, SecurityAnalysisResult


class TestSecurityValidator(unittest.TestCase):
    """Test cases for SecurityValidator."""

    def setUp(self):
        """Set up test fixtures."""
        self.validator = SecurityValidator()

    def test_path_traversal_detection_unix(self):
        """Test detection of Unix-style path traversal patterns."""
        config = {
            "web": {
                "upload_dir": "../../../etc/passwd"
            }
        }

        result = self.validator.validate_security(config)
        
        # Should have one error for path traversal
        self.assertEqual(len(result.errors), 1)
        self.assertEqual(result.errors[0].code, "security-path-traversal-risk")
        self.assertIn("../", result.errors[0].message)

    def test_path_traversal_detection_windows(self):
        """Test detection of Windows-style path traversal patterns."""
        config = {
            "watch_folder": {
                "dir": "..\\..\\Windows\\System32"
            }
        }

        result = self.validator.validate_security(config)
        
        # Should have one error for path traversal
        self.assertEqual(len(result.errors), 1)
        self.assertEqual(result.errors[0].code, "security-path-traversal-risk")
        self.assertIn("..\\", result.errors[0].message)

    def test_suspicious_system_path_detection(self):
        """Test detection of suspicious system paths."""
        config = {
            "web": {
                "upload_dir": "/etc/sensitive-data"
            },
            "watch_folder": {
                "dir": "C:\\Windows\\Temp\\uploads"
            }
        }

        result = self.validator.validate_security(config)
        
        # Should have warnings for suspicious system paths
        warnings = [w for w in result.warnings if w.code == "security-suspicious-system-path"]
        self.assertEqual(len(warnings), 2)
        
        # Check that both paths are flagged
        paths_flagged = [w.details["path"] for w in warnings]
        self.assertIn("/etc/sensitive-data", paths_flagged)
        self.assertIn("C:\\Windows\\Temp\\uploads", paths_flagged)

    def test_task_parameter_security_validation(self):
        """Test security validation of task parameters."""
        config = {
            "tasks": {
                "store_data": {
                    "module": "standard_step.storage.store_json",
                    "params": {
                        "data_dir": "../../../sensitive/data",
                        "filename": "output.json"
                    }
                },
                "update_reference": {
                    "module": "standard_step.rules.update_reference",
                    "params": {
                        "reference_file": "~/../../etc/passwd",
                        "update_field": "status"
                    }
                }
            }
        }

        result = self.validator.validate_security(config)
        
        # Should have errors for dangerous path patterns in task parameters
        errors = [e for e in result.errors if e.code == "security-path-traversal-risk"]
        self.assertEqual(len(errors), 2)
        
        # Check that both task parameters are flagged
        paths_flagged = [e.details["path"] for e in errors]
        self.assertIn("../../../sensitive/data", paths_flagged)
        self.assertIn("~/../../etc/passwd", paths_flagged)

    def test_nested_storage_parameter_validation(self):
        """Test security validation of nested storage parameters."""
        config = {
            "tasks": {
                "store_data": {
                    "module": "standard_step.storage.store_json_v2",
                    "params": {
                        "storage": {
                            "data_dir": "../../../var/log",
                            "filename": "../../output.json"
                        }
                    }
                }
            }
        }

        result = self.validator.validate_security(config)
        
        # Should have warnings for dangerous patterns in nested storage parameters
        issues = [i for i in result.all_issues if i.code == "security-path-traversal-risk"]
        self.assertEqual(len(issues), 2)
        
        # Check that both nested parameters are flagged
        paths_flagged = [i.details["path"] for i in issues]
        self.assertIn("../../../var/log", paths_flagged)
        self.assertIn("../../output.json", paths_flagged)

    def test_command_injection_patterns(self):
        """Test detection of potential command injection patterns."""
        config = {
            "tasks": {
                "malicious_task": {
                    "module": "standard_step.storage.store_file",
                    "params": {
                        "files_dir": "/tmp; rm -rf /",
                        "filename": "output|cat /etc/passwd"
                    }
                }
            }
        }

        result = self.validator.validate_security(config)
        
        # Should have warnings for command injection patterns
        issues = [i for i in result.all_issues if i.code == "security-path-traversal-risk"]
        self.assertEqual(len(issues), 2)
        
        # Check that dangerous patterns are detected
        all_patterns = []
        for issue in issues:
            all_patterns.extend(issue.details.get("dangerous_patterns", []))
        
        self.assertIn(";", all_patterns)
        self.assertIn("|", all_patterns)

    def test_environment_variable_patterns(self):
        """Test detection of environment variable patterns."""
        config = {
            "web": {
                "upload_dir": "$HOME/../sensitive"
            },
            "watch_folder": {
                "dir": "%USERPROFILE%\\..\\system"
            }
        }

        result = self.validator.validate_security(config)
        
        # Should have warnings for environment variable patterns
        issues = [i for i in result.all_issues if i.code == "security-path-traversal-risk"]
        self.assertEqual(len(issues), 2)
        
        # Check that environment variable patterns are detected
        all_patterns = []
        for issue in issues:
            all_patterns.extend(issue.details.get("dangerous_patterns", []))
        
        self.assertIn("$", all_patterns)
        self.assertIn("%", all_patterns)

    def test_unsafe_absolute_path_detection(self):
        """Test detection of unsafe absolute paths."""
        config = {
            "web": {
                "upload_dir": "C:\\Windows\\System32\\uploads"
            },
            "watch_folder": {
                "dir": "/etc/watch-folder"
            }
        }

        result = self.validator.validate_security(config)
        
        # Should have info messages for unsafe absolute paths
        info_messages = [i for i in result.info if i.code == "security-unsafe-absolute-path"]
        self.assertEqual(len(info_messages), 1)  # Only Windows path triggers unsafe absolute path
        
        # Check that Windows system path is flagged as unsafe absolute path
        paths_flagged = [i.details["path"] for i in info_messages]
        self.assertIn("C:\\Windows\\System32\\uploads", paths_flagged)

    def test_unsafe_relative_path_detection(self):
        """Test detection of unsafe relative paths."""
        config = {
            "tasks": {
                "store_data": {
                    "module": "standard_step.storage.store_json",
                    "params": {
                        "data_dir": "../uploads",
                        "filename": "\\..\\output.json"
                    }
                }
            }
        }

        result = self.validator.validate_security(config)
        
        # Should have warnings for unsafe relative paths
        warnings = [w for w in result.warnings if w.code == "security-unsafe-relative-path"]
        self.assertEqual(len(warnings), 2)
        
        # Check that both relative paths are flagged
        paths_flagged = [w.details["path"] for w in warnings]
        self.assertIn("../uploads", paths_flagged)
        self.assertIn("\\..\\output.json", paths_flagged)

    def test_no_security_issues(self):
        """Test configuration with no security issues."""
        config = {
            "web": {
                "upload_dir": "./uploads"
            },
            "watch_folder": {
                "dir": "./watch",
                "processing_dir": "processing"
            },
            "tasks": {
                "extract_data": {
                    "module": "standard_step.extraction.extract_pdf",
                    "params": {
                        "fields": [
                            {"name": "supplier", "alias": "Supplier", "type": "str"}
                        ]
                    }
                },
                "store_data": {
                    "module": "standard_step.storage.store_json",
                    "params": {
                        "data_dir": "./output",
                        "filename": "result.json"
                    }
                }
            }
        }

        result = self.validator.validate_security(config)
        
        # Should have no security issues
        self.assertEqual(len(result.errors), 0)
        self.assertEqual(len(result.warnings), 0)
        self.assertEqual(len(result.info), 0)

    def test_mixed_security_issues(self):
        """Test configuration with mixed security issue severities."""
        config = {
            "web": {
                "upload_dir": "../../../etc/uploads"  # Error: path traversal
            },
            "watch_folder": {
                "dir": "/var/watch",  # Warning: suspicious system path
                "processing_dir": "C:\\Program Files\\processing"  # Info: unsafe absolute path
            },
            "tasks": {
                "store_data": {
                    "module": "standard_step.storage.store_json",
                    "params": {
                        "data_dir": "../output"  # Warning: unsafe relative path
                    }
                }
            }
        }

        result = self.validator.validate_security(config)
        
        # Should have mixed severity issues
        self.assertEqual(len(result.errors), 2)  # Path traversal for upload_dir and data_dir
        self.assertEqual(len(result.warnings), 6)  # Multiple warnings for various issues
        self.assertEqual(len(result.info), 1)  # Unsafe absolute path
        
        # Verify specific issue types
        self.assertEqual(result.errors[0].code, "security-path-traversal-risk")
        
        warning_codes = [w.code for w in result.warnings]
        self.assertIn("security-suspicious-system-path", warning_codes)
        self.assertIn("security-unsafe-relative-path", warning_codes)
        
        self.assertEqual(result.info[0].code, "security-unsafe-absolute-path")


if __name__ == "__main__":
    unittest.main()