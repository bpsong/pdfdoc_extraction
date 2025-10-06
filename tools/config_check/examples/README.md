# Configuration Examples

This directory contains example configuration files for the config-check tool, demonstrating both valid configurations and common error scenarios.

## Valid Configuration Examples

### `complete_config.yaml`
A comprehensive example showing all available configuration options including:
- All web server settings (host, port, upload_dir, secret_key)
- All watch folder settings (dir, recursive, validate_pdf_header, processing_dir)
- Complete task definitions with all parameter types
- Full pipeline with multiple processing steps

Use this as a reference for understanding all available configuration options.

### `minimal_config.yaml`
A minimal working configuration showing only required fields with default values for optional settings. This demonstrates:
- Minimum required web configuration
- Basic watch folder setup
- Simple task definitions
- Minimal pipeline

Use this as a starting point for new configurations.

### `valid_config.yaml` (Legacy)
The original valid configuration example, maintained for backward compatibility.

## Invalid Configuration Examples

The `invalid_configs/` directory contains examples that demonstrate common configuration errors:

### `invalid_web_host.yaml`
Demonstrates web host validation errors:
- Empty host string (triggers `web-host-invalid`)

### `invalid_web_port.yaml`
Demonstrates web port validation errors:
- Port number outside valid range 1-65535 (triggers `web-port-invalid`)

### `invalid_watch_folder_fields.yaml`
Demonstrates watch folder validation errors:
- Non-boolean value for `validate_pdf_header`
- Empty string for `processing_dir`

### `invalid_import_errors.yaml`
Demonstrates import validation errors (requires `--import-checks` flag):
- Module not found errors
- Class not found errors
- Non-class attribute errors

### `invalid_missing_paths.yaml` (Legacy)
The original invalid configuration example showing path and dependency errors.

## Testing Examples

You can test these examples with the config-check tool:

```powershell
# Test valid configurations
config-check validate examples/complete_config.yaml
config-check validate examples/minimal_config.yaml

# Test invalid configurations (should show errors)
config-check validate examples/invalid_configs/invalid_web_host.yaml
config-check validate examples/invalid_configs/invalid_web_port.yaml
config-check validate examples/invalid_configs/invalid_watch_folder_fields.yaml

# Test import validation (requires --import-checks flag)
config-check validate --import-checks examples/invalid_configs/invalid_import_errors.yaml
```

## Error Code Reference

See `ERROR_CODES.md` for a comprehensive reference of all validation error codes and their meanings.

## Using Examples as Templates

These examples can serve as templates for creating your own configurations:

1. **Start with `minimal_config.yaml`** for basic setups
2. **Reference `complete_config.yaml`** for advanced features
3. **Check `invalid_configs/`** to understand common mistakes
4. **Use `ERROR_CODES.md`** to troubleshoot validation errors

## Configuration Best Practices

Based on these examples, follow these best practices:

1. **Always specify required fields** explicitly rather than relying on defaults
2. **Use meaningful task names** that describe their purpose
3. **Include error handling** with appropriate `on_error` settings
4. **Validate import paths** using `--import-checks` before deployment
5. **Test configurations** with the config-check tool before using them
6. **Document custom configurations** with comments explaining non-obvious settings