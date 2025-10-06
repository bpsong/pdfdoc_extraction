# Config Check Error Codes Reference

This document provides a comprehensive reference for all error codes returned by the config-check tool, including the new schema validation and import validation error codes.

## Schema Validation Error Codes

### Web Configuration Errors

#### `web-host-invalid`
**Description**: Web host must be a non-empty string  
**Cause**: The `web.host` field is empty, null, or contains only whitespace  
**Solution**: Set `web.host` to a valid hostname or IP address  
**Example Fix**:
```yaml
web:
  host: "127.0.0.1"  # or "localhost" or "0.0.0.0"
```

#### `web-port-invalid`
**Description**: Web port must be an integer between 1 and 65535  
**Cause**: The `web.port` field is not an integer or is outside the valid port range  
**Solution**: Set `web.port` to a valid port number  
**Example Fix**:
```yaml
web:
  port: 8000  # Any integer from 1 to 65535
```

### Watch Folder Configuration Errors

#### `watch-folder-pdf-validation-invalid`
**Description**: PDF header validation must be a boolean value  
**Cause**: The `watch_folder.validate_pdf_header` field is not a boolean (true/false)  
**Solution**: Set the field to `true` or `false`  
**Example Fix**:
```yaml
watch_folder:
  validate_pdf_header: true  # or false
```

#### `watch-folder-processing-dir-invalid`
**Description**: Processing directory must be a non-empty string  
**Cause**: The `watch_folder.processing_dir` field is empty, null, or contains only whitespace  
**Solution**: Provide a valid directory path  
**Example Fix**:
```yaml
watch_folder:
  processing_dir: "processing"  # or any valid directory name
```

## Import Validation Error Codes

These errors only appear when using the `--import-checks` flag.

#### `task-import-module-not-found`
**Description**: Module not found in Python path  
**Cause**: The specified task module cannot be imported  
**Common Reasons**:
- Module name is misspelled
- Module is not installed
- Module is not in the Python path
- Module file doesn't exist

**Solution**: 
- Verify the module name spelling
- Ensure the module is installed or available
- Check Python path configuration
- Verify the module file exists in the expected location

**Example Fix**:
```yaml
tasks:
  my_task:
    module: standard_step.extraction.extract_pdf  # Correct module path
    class: ExtractPdfTask
```

#### `task-import-module-syntax-error`
**Description**: Module contains syntax errors  
**Cause**: The specified module has Python syntax errors that prevent import  
**Solution**: Fix the syntax errors in the module file  
**Common Issues**:
- Missing colons, parentheses, or brackets
- Incorrect indentation
- Invalid Python syntax

#### `task-import-class-not-found`
**Description**: Class not found in module  
**Cause**: The specified class name doesn't exist in the imported module  
**Common Reasons**:
- Class name is misspelled
- Class was renamed or removed
- Class is defined in a different module

**Solution**: 
- Verify the class name spelling
- Check that the class exists in the specified module
- Ensure you're referencing the correct module

**Example Fix**:
```yaml
tasks:
  my_task:
    module: standard_step.extraction.extract_pdf
    class: ExtractPdfTask  # Correct class name
```

#### `task-import-not-callable`
**Description**: Specified attribute is not a callable class  
**Cause**: The specified attribute exists but is not a class (e.g., it's a function, variable, or constant)  
**Solution**: Ensure you're referencing a class, not a function or variable  
**Example of Incorrect Usage**:
```yaml
tasks:
  my_task:
    module: os.path
    class: join  # 'join' is a function, not a class
```

**Example Fix**:
```yaml
tasks:
  my_task:
    module: standard_step.extraction.extract_pdf
    class: ExtractPdfTask  # This is a class
```

## Legacy Error Codes

The config-check tool also includes existing error codes for other validation types:

### Path Validation Errors
- Path-related errors for missing directories and files
- File permission errors
- Invalid path formats

### Parameter Validation Errors
- Task-specific parameter validation errors
- Missing required parameters
- Invalid parameter values

### Pipeline Validation Errors
- Pipeline dependency errors
- Task ordering violations
- Missing pipeline tasks

## Using Error Codes in Automation

When using the `--format json` flag, error codes are included in the JSON output for programmatic processing:

```json
{
  "findings": [
    {
      "path": "web.host",
      "message": "Web host must be a non-empty string",
      "code": "web-host-invalid",
      "level": "error"
    }
  ],
  "exit_code": 1
}
```

This allows automated systems to:
- Parse specific error types
- Implement custom error handling
- Generate targeted fixes
- Track error patterns across configurations