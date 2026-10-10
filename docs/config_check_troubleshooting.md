# Moved: Config Check Troubleshooting Guide

| Item | Value |
| --- | --- |
| Audience | Readers following an earlier documentation link |
| Owner | Application maintainers |
| Status | Compatibility navigation |
| Last verified | 2026-10-10 — repository/source review; no live deployment check |
| Applies to | Previous documentation addresses; follow current links below |

This address is retained for navigation. Use the
[current documentation](it-support/config-check-troubleshooting.md) or choose another
[reading path](README.md).
The [original document](history/archive/2026-10-10/docs/config_check_troubleshooting.md)
is preserved unchanged for historical reference.

## Previous section links

<a id="config-check-troubleshooting-guide"></a>

[Config Check Troubleshooting Guide](it-support/config-check-troubleshooting.md)

<a id="contents"></a>

[Contents](it-support/config-check-troubleshooting.md#contents)

<a id="choose-the-right-validation-world"></a>

[Choose the right validation world](it-support/config-check-troubleshooting.md#choose-the-right-validation-world)

<a id="fast-symptom-lookup"></a>

[Fast symptom lookup](it-support/config-check-troubleshooting.md#fast-symptom-lookup)

<a id="stored-configuration-and-database-findings"></a>

[Stored Configuration And Database Findings](it-support/config-check-troubleshooting.md#stored-configuration-and-database-findings)

<a id="portable-definition-findings"></a>

[Portable Definition Findings](it-support/config-check-troubleshooting.md#portable-definition-findings)

<a id="missing-directories-or-files"></a>

[Missing Directories Or Files](it-support/config-check-troubleshooting.md#missing-directories-or-files)

<a id="watch-folder-not-prepared"></a>

[Watch Folder Not Prepared](it-support/config-check-troubleshooting.md#watch-folder-not-prepared)

<a id="yaml-parse-errors"></a>

[YAML Parse Errors](it-support/config-check-troubleshooting.md#yaml-parse-errors)

<a id="unknown-keys-in-strict-mode"></a>

[Unknown Keys In Strict Mode](it-support/config-check-troubleshooting.md#unknown-keys-in-strict-mode)

<a id="import-failures"></a>

[Import Failures](it-support/config-check-troubleshooting.md#import-failures)

<a id="unapproved-pipeline-task"></a>

[Unapproved Pipeline Task](it-support/config-check-troubleshooting.md#unapproved-pipeline-task)

<a id="pipeline-cardinality-or-ordering-errors-storedportable-definitions"></a>

[Pipeline Cardinality Or Ordering Errors (Stored/Portable Definitions)](it-support/config-check-troubleshooting.md#pipeline-cardinality-or-ordering-errors-storedportable-definitions)

<a id="duplicate-pipeline-task-type-warnings"></a>

[Duplicate Pipeline Task Type Warnings](it-support/config-check-troubleshooting.md#duplicate-pipeline-task-type-warnings)

<a id="missing-extraction-credentials"></a>

[Missing Extraction Credentials](it-support/config-check-troubleshooting.md#missing-extraction-credentials)

<a id="multiple-table-extraction-fields"></a>

[Multiple Table Extraction Fields](it-support/config-check-troubleshooting.md#multiple-table-extraction-fields)

<a id="glm-ocr-local-provider-configuration-errors"></a>

[GLM-OCR Local Provider Configuration Errors](it-support/config-check-troubleshooting.md#glm-ocr-local-provider-configuration-errors)

<a id="liteparse-local-provider-configuration-errors"></a>

[LiteParse Local Provider Configuration Errors](it-support/config-check-troubleshooting.md#liteparse-local-provider-configuration-errors)

<a id="structured-object-extraction-fields"></a>

[Structured Object Extraction Fields](it-support/config-check-troubleshooting.md#structured-object-extraction-fields)

<a id="local-drive-storage-requirements"></a>

[Local Drive Storage Requirements](it-support/config-check-troubleshooting.md#local-drive-storage-requirements)

<a id="nested-storage-overrides"></a>

[Nested Storage Overrides](it-support/config-check-troubleshooting.md#nested-storage-overrides)

<a id="rules-task-required-configuration"></a>

[Rules Task Required Configuration](it-support/config-check-troubleshooting.md#rules-task-required-configuration)

<a id="deprecated-task-slug"></a>

[Deprecated Task Slug](it-support/config-check-troubleshooting.md#deprecated-task-slug)

<a id="housekeeping-task-configuration-errors"></a>

[Housekeeping Task Configuration Errors](it-support/config-check-troubleshooting.md#housekeeping-task-configuration-errors)

<a id="split-task-configuration-errors"></a>

[Split Task Configuration Errors](it-support/config-check-troubleshooting.md#split-task-configuration-errors)

<a id="review-gate-configuration-errors"></a>

[Review Gate Configuration Errors](it-support/config-check-troubleshooting.md#review-gate-configuration-errors)

<a id="web-server-configuration-errors"></a>

[Web Server Configuration Errors](it-support/config-check-troubleshooting.md#web-server-configuration-errors)

<a id="watch-folder-configuration-errors"></a>

[Watch Folder Configuration Errors](it-support/config-check-troubleshooting.md#watch-folder-configuration-errors)

<a id="enhanced-import-validation-errors"></a>

[Enhanced Import Validation Errors](it-support/config-check-troubleshooting.md#enhanced-import-validation-errors)

<a id="rules-task-validation-errors"></a>

[Rules Task Validation Errors](it-support/config-check-troubleshooting.md#rules-task-validation-errors)

<a id="csv-file-issues"></a>

[CSV File Issues](it-support/config-check-troubleshooting.md#csv-file-issues)

<a id="column-reference-issues"></a>

[Column Reference Issues](it-support/config-check-troubleshooting.md#column-reference-issues)

<a id="clause-configuration-issues"></a>

[Clause Configuration Issues](it-support/config-check-troubleshooting.md#clause-configuration-issues)

<a id="context-path-issues"></a>

[Context Path Issues](it-support/config-check-troubleshooting.md#context-path-issues)

<a id="semantic-validation-issues"></a>

[Semantic Validation Issues](it-support/config-check-troubleshooting.md#semantic-validation-issues)

<a id="runtime-file-validation-issues---check-files-flag"></a>

[Runtime File Validation Issues (--check-files flag)](it-support/config-check-troubleshooting.md#runtime-file-validation-issues---check-files-flag)

<a id="pandas-dependency-issues"></a>

[Pandas Dependency Issues](it-support/config-check-troubleshooting.md#pandas-dependency-issues)

<a id="token-or-dependency-issues"></a>

[Token Or Dependency Issues](it-support/config-check-troubleshooting.md#token-or-dependency-issues)

<a id="performance-analysis-issues"></a>

[Performance Analysis Issues](it-support/config-check-troubleshooting.md#performance-analysis-issues)

<a id="excessive-extraction-fields"></a>

[Excessive Extraction Fields](it-support/config-check-troubleshooting.md#excessive-extraction-fields)

<a id="complex-context-paths"></a>

[Complex Context Paths](it-support/config-check-troubleshooting.md#complex-context-paths)

<a id="pipeline-performance-issues"></a>

[Pipeline Performance Issues](it-support/config-check-troubleshooting.md#pipeline-performance-issues)

<a id="security-analysis-issues"></a>

[Security Analysis Issues](it-support/config-check-troubleshooting.md#security-analysis-issues)

<a id="path-traversal-vulnerabilities"></a>

[Path Traversal Vulnerabilities](it-support/config-check-troubleshooting.md#path-traversal-vulnerabilities)

<a id="suspicious-system-paths"></a>

[Suspicious System Paths](it-support/config-check-troubleshooting.md#suspicious-system-paths)

<a id="command-injection-risks"></a>

[Command Injection Risks](it-support/config-check-troubleshooting.md#command-injection-risks)

<a id="environment-variable-risks"></a>

[Environment Variable Risks](it-support/config-check-troubleshooting.md#environment-variable-risks)

<a id="unsafe-directory-locations"></a>

[Unsafe Directory Locations](it-support/config-check-troubleshooting.md#unsafe-directory-locations)

<a id="still-stuck"></a>

[Still Stuck?](it-support/config-check-troubleshooting.md#still-stuck)
