import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import yaml from "js-yaml";
import {
  AlertTriangle,
  Archive,
  ArrowRight,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Copy,
  Database,
  FileJson,
  FileText,
  FolderOpen,
  GitBranch,
  HardDrive,
  Eye,
  EyeOff,
  Info,
  KeyRound,
  ListChecks,
  PanelRight,
  Play,
  Plus,
  RefreshCw,
  Save,
  Scissors,
  Search,
  Settings,
  ShieldCheck,
  Split,
  Trash2,
  Upload,
  Wand2,
  X,
} from "lucide-react";
import "./styles.css";

const SCALAR_FIELD_TYPE_OPTIONS = [
  { value: "str", label: "Text" },
  { value: "int", label: "Integer" },
  { value: "float", label: "Number" },
  { value: "bool", label: "Yes / No" },
  { value: "List[str]", label: "List of text" },
  { value: "List[float]", label: "List of numbers" },
  { value: "Dict[str, str]", label: "Object (text values)" },
];
const TABLE_FIELD_TYPE = "List[Any]";
const FIELD_TYPE_OPTIONS = [
  ...SCALAR_FIELD_TYPE_OPTIONS,
  { value: TABLE_FIELD_TYPE, label: "List of objects" },
];
const FIELD_TYPE_VALUES = SCALAR_FIELD_TYPE_OPTIONS.map((option) => option.value);
const ROW_FIELD_TYPE_OPTIONS = [
  { value: "str", label: "Text (str)" },
  { value: "int", label: "Integer (int)" },
  { value: "float", label: "Number (float)" },
  { value: "bool", label: "Yes / No (bool)" },
];
const ROW_FIELD_TYPE_VALUES = ROW_FIELD_TYPE_OPTIONS.map((option) => option.value);

function unwrapOptionalType(type = "str") {
  const match = String(type).trim().match(/^Optional\[(.*)\]$/);
  return match ? match[1].trim() : String(type).trim();
}

function isOptionalType(type = "str") {
  return String(type).trim().startsWith("Optional[") && String(type).trim().endsWith("]");
}

function withRequiredState(type, required) {
  const baseType = unwrapOptionalType(type);
  return required ? baseType : `Optional[${baseType}]`;
}

function isSupportedFieldType(type, { table = false } = {}) {
  const baseType = unwrapOptionalType(type);
  return table ? baseType === TABLE_FIELD_TYPE : FIELD_TYPE_VALUES.includes(baseType);
}

function isSupportedRowFieldType(type) {
  return ROW_FIELD_TYPE_VALUES.includes(unwrapOptionalType(type));
}

const CONTEXT_TOKENS = ["id", "nanoid", "filename", "source", "original_filename", "file_path"];

const taskTemplates = [
  {
    key: "split_document",
    label: "Split document",
    category: "Split",
    icon: Scissors,
    module: "standard_step.split.llamacloud_split",
    class: "LlamaCloudSplitTask",
    on_error: "stop",
    params: {
      enabled: true,
      api_key: "",
      configuration_id: "",
      project_id: "",
      organization_id: "",
      allow_uncategorized: "forbid",
      split_dir: "processing/split",
      fail_on_confidence_levels: ["low"],
      fail_on_unknown_category: true,
      allowed_categories: [],
      poll_interval_seconds: 1,
      timeout_seconds: 7200,
      categories: [{ name: "invoice", description: "A single invoice document." }],
    },
  },
  {
    key: "extract_document_data",
    label: "Extract document data",
    category: "Extraction",
    icon: Wand2,
    module: "standard_step.extraction.extract_pdf",
    class: "ExtractPdfTask",
    on_error: "stop",
    params: {
      api_key: "",
      configuration_id: "",
      tier: "agentic",
      parse_tier: "",
      extraction_target: "per_doc",
      cite_sources: null,
      confidence_scores: true,
      project_id: "",
      organization_id: "",
      poll_interval_seconds: 2,
      timeout_seconds: 1800,
      fields: {},
    },
  },
  {
    key: "assign_nanoid",
    label: "Assign nanoid",
    category: "Context",
    icon: KeyRound,
    module: "standard_step.context.assign_nanoid",
    class: "AssignNanoidTask",
    on_error: "stop",
    params: { length: 12 },
  },
  {
    key: "store_metadata_csv",
    label: "Store CSV metadata",
    category: "Storage",
    icon: FileText,
    module: "standard_step.storage.store_metadata_as_csv",
    class: "StoreMetadataAsCsv",
    on_error: "continue",
    params: { data_dir: "data", filename: "{id}" },
  },
  {
    key: "store_metadata_json",
    label: "Store JSON metadata",
    category: "Storage",
    icon: FileJson,
    module: "standard_step.storage.store_metadata_as_json",
    class: "StoreMetadataAsJson",
    on_error: "continue",
    params: { data_dir: "data", filename: "{id}" },
  },
  {
    key: "store_file_to_localdrive",
    label: "Save PDF",
    category: "Storage",
    icon: HardDrive,
    module: "standard_step.storage.store_file_to_localdrive",
    class: "StoreFileToLocaldrive",
    on_error: "continue",
    params: { files_dir: "files", filename: "{id}" },
  },
  {
    key: "update_reference",
    label: "Update reference",
    category: "Rules",
    icon: Database,
    module: "standard_step.rules.update_reference",
    class: "UpdateReferenceTask",
    on_error: "continue",
    params: {
      reference_file: "reference_file/reference_file.csv",
      update_field: "MATCHED",
      write_value: "match_all",
      backup: true,
      csv_match: { type: "column_equals_all", clauses: [{ column: "", from_context: "", number: false }] },
    },
  },
  {
    key: "review_gate",
    label: "Review gate",
    category: "Review",
    icon: ShieldCheck,
    module: "standard_step.review.review_gate",
    class: "ReviewGateTask",
    on_error: "stop",
    params: {
      confidence_threshold: 0.95,
      per_document_type_thresholds: {},
      field_threshold_overrides: {},
      split_confidence_levels_requiring_review: [],
      require_review_when_missing_confidence: true,
      require_review_for_missing_required_fields: true,
      always_review: false,
      schema_file: "schemas/invoice.yaml",
      queue_name: "default_review",
      review_scope: "low_confidence_fields",
      allow_operator_to_edit_high_confidence_fields: true,
      resume_policy: "next_task",
    },
  },
  {
    key: "cleanup_task",
    label: "Clean up processed file",
    category: "Housekeeping",
    icon: Trash2,
    module: "standard_step.housekeeping.cleanup_task",
    class: "CleanupTask",
    on_error: "continue",
    params: { processing_dir: "processing" },
  },
  {
    key: "archive_pdf",
    label: "Archive source",
    category: "Archive",
    icon: Archive,
    module: "standard_step.archiver.archive_pdf",
    class: "ArchivePdfTask",
    on_error: "continue",
    params: { archive_dir: "archive_folder" },
  },
];

function clone(value) {
  return structuredClone(value || {});
}

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function taskKind(step) {
  const moduleName = step?.module || "";
  if (step?.class === "LlamaCloudSplitTask" || moduleName.includes(".split.")) return "split";
  if (step?.class === "ExtractPdfTask" || moduleName.includes(".extraction.")) return "extract";
  if (step?.class === "ReviewGateTask" || moduleName.includes(".review.")) return "review";
  if (moduleName.includes(".storage.")) return "storage";
  if (moduleName.includes(".archiver.")) return "archive";
  if (moduleName.includes(".rules.")) return "rules";
  if (moduleName.includes(".context.")) return "context";
  if (step?.class === "CleanupTask" || moduleName.includes(".housekeeping.")) return "housekeeping";
  return "task";
}

function iconFor(step) {
  return taskTemplates.find((task) => task.class === step?.class)?.icon || Settings;
}

function kindBadgeClass(kind) {
  return {
    split: "badge-info",
    extract: "badge-primary",
    review: "badge-warning",
    storage: "badge-success",
    archive: "badge-neutral",
    rules: "badge-secondary",
    context: "badge-accent",
    housekeeping: "badge-ghost",
    task: "badge-ghost",
  }[kind];
}

function labelForStep(key, taskConfig) {
  const template = taskTemplates.find((task) => task.class === taskConfig?.class);
  if (template) return template.label;
  return key.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function taskConfigToStep(key, task, enabled) {
  return {
    key,
    label: labelForStep(key, task),
    module: String(task.module || ""),
    class: String(task.class || ""),
    enabled,
    on_error: task.on_error || "stop",
    params: clone(task.params || {}),
  };
}

function templateToStep(template, key, enabled = true) {
  return {
    key,
    label: template.label,
    module: String(template.module || ""),
    class: String(template.class || ""),
    enabled,
    on_error: template.on_error || "stop",
    params: clone(template.params || {}),
  };
}

function configToSteps(config) {
  const tasks = isPlainObject(config?.tasks) ? config.tasks : {};
  const pipeline = Array.isArray(config?.pipeline) ? config.pipeline : [];
  const used = new Set();
  const ordered = [];
  pipeline.forEach((key) => {
    if (!isPlainObject(tasks[key])) return;
    ordered.push(taskConfigToStep(key, tasks[key], true));
    used.add(key);
  });
  Object.entries(tasks).forEach(([key, task]) => {
    if (!used.has(key) && isPlainObject(task)) ordered.push(taskConfigToStep(key, task, false));
  });
  return ordered;
}

function buildConfig(baseConfig, steps) {
  const config = clone(baseConfig || {});
  const tasks = {};
  const pipeline = [];
  steps.forEach((step) => {
    if (!step.key) return;
    const task = { module: step.module, class: step.class, params: clone(step.params || {}) };
    if (step.on_error) task.on_error = step.on_error;
    tasks[step.key] = task;
    if (step.enabled !== false) pipeline.push(step.key);
  });
  config.tasks = tasks;
  config.pipeline = pipeline;
  return config;
}

function dumpYaml(config) {
  return yaml.dump(config || {}, { lineWidth: 110, noRefs: true, sortKeys: false });
}

function uniqueKey(base, steps, ignoreIndex = -1) {
  const normalized = slugKey(base || "task") || "task";
  const used = new Set(steps.filter((_, index) => index !== ignoreIndex).map((step) => step.key));
  let candidate = normalized;
  let count = 2;
  while (used.has(candidate)) {
    candidate = `${normalized}_${count}`;
    count += 1;
  }
  return candidate;
}

function uniqueObjectKey(base, object, oldKey = "") {
  const normalized = slugKey(base || "field") || "field";
  const used = new Set(Object.keys(object || {}).filter((key) => key !== oldKey));
  let candidate = normalized;
  let count = 2;
  while (used.has(candidate)) {
    candidate = `${normalized}_${count}`;
    count += 1;
  }
  return candidate;
}

function slugKey(value) {
  return String(value || "").replace(/[^A-Za-z0-9_]/g, "_").replace(/^_+|_+$/g, "");
}

function extractTemplateTokens(template) {
  return [...String(template || "").matchAll(/(?<!\{)\{([A-Za-z0-9_]+)\}(?!\})/g)].map((match) => match[1]);
}

function extractionFields(steps) {
  const extractStep = steps.find((step) => taskKind(step) === "extract");
  return isPlainObject(extractStep?.params?.fields) ? extractStep.params.fields : {};
}

function scalarTokens(steps) {
  const fields = extractionFields(steps);
  const tokens = Object.entries(fields)
    .filter(([, field]) => !field?.is_table)
    .map(([key]) => key);
  return [...new Set([...CONTEXT_TOKENS, ...tokens])];
}

function lineDiff(oldText, newText) {
  const oldLines = String(oldText || "").split(/\r?\n/);
  const newLines = String(newText || "").split(/\r?\n/);
  const max = Math.max(oldLines.length, newLines.length);
  const lines = [];
  for (let index = 0; index < max; index += 1) {
    if (oldLines[index] === newLines[index]) {
      if (oldLines[index] !== undefined) lines.push(`  ${oldLines[index]}`);
    } else {
      if (oldLines[index] !== undefined) lines.push(`- ${oldLines[index]}`);
      if (newLines[index] !== undefined) lines.push(`+ ${newLines[index]}`);
    }
  }
  return lines.join("\n");
}

function finding(severity, code, path, message) {
  return { severity, code, path, message };
}

function validateSteps(steps, csvMetadata = {}) {
  const findings = [];
  const keys = new Set();
  const enabled = steps.filter((step) => step.enabled !== false);
  const extractIndex = enabled.findIndex((step) => taskKind(step) === "extract");
  const splitIndex = enabled.findIndex((step) => taskKind(step) === "split");
  const fields = extractionFields(steps);
  const scalarTokenSet = new Set(scalarTokens(steps));

  steps.forEach((step, index) => {
    if (!step.key?.trim()) findings.push(finding("error", "task-key-empty", `steps.${index}.key`, `Step ${index + 1} needs a task key.`));
    if (keys.has(step.key)) findings.push(finding("error", "task-key-duplicate", `steps.${index}.key`, `Task key '${step.key}' is duplicated.`));
    keys.add(step.key);
    if (!step.module?.trim()) findings.push(finding("error", "task-module-empty", `tasks.${step.key}.module`, `${step.key} needs a module.`));
    if (!step.class?.trim()) findings.push(finding("error", "task-class-empty", `tasks.${step.key}.class`, `${step.key} needs a class.`));
    if (!["stop", "continue"].includes(step.on_error)) findings.push(finding("error", "task-on-error-invalid", `tasks.${step.key}.on_error`, `${step.key} must stop or continue after an error.`));
    if (!isPlainObject(step.params)) findings.push(finding("error", "task-params-invalid", `tasks.${step.key}.params`, `${step.key} params must be an object.`));
  });

  if (extractIndex === -1) findings.push(finding("error", "pipeline-missing-extract", "pipeline", "Pipeline must include an extraction task."));
  if (splitIndex > -1 && extractIndex > -1 && splitIndex > extractIndex) {
    findings.push(finding("error", "split-after-extract", "pipeline", "Split needs to run before extraction."));
  }

  steps.forEach((step) => {
    const kind = taskKind(step);
    const params = step.params || {};
    if (kind === "extract") validateExtract(step, findings);
    if (kind === "storage") validateStorage(step, scalarTokenSet, findings);
    if (kind === "rules") validateRules(step, fields, csvMetadata[params.reference_file], findings);
    if (kind === "context") validateContext(step, findings);
    if (kind === "housekeeping") validateHousekeeping(step, findings);
    if (kind === "split") validateSplit(step, findings);
    if (kind === "archive" && !params.archive_dir) {
      findings.push(finding("error", "archive-dir-empty", `tasks.${step.key}.params.archive_dir`, `${step.label} needs an archive directory.`));
    }
    if (kind === "review") validateReview(step, findings);
  });

  if (!findings.some((item) => item.severity === "error")) {
    findings.push(finding("success", "ready-to-publish", "config", "Draft can be written to the prototype YAML file."));
  }
  return findings;
}

function validateExtract(step, findings) {
  const params = step.params || {};
  const fields = isPlainObject(params.fields) ? params.fields : {};
  if (typeof params.api_key !== "string" || !params.api_key.trim()) findings.push(finding("error", "extract-api-key-empty", `tasks.${step.key}.params.api_key`, "Extraction needs an API key."));
  for (const key of ["configuration_id", "tier", "parse_tier", "extraction_target", "project_id", "organization_id"]) {
    if (params[key] !== undefined && (typeof params[key] !== "string" || !params[key].trim())) findings.push(finding("error", `extract-${key}-type`, `tasks.${step.key}.params.${key}`, `${key.replace(/_/g, " ")} must be non-empty text when provided.`));
  }
  for (const key of ["cite_sources", "confidence_scores"]) {
    if (params[key] !== undefined && typeof params[key] !== "boolean") findings.push(finding("error", `extract-${key}-type`, `tasks.${step.key}.params.${key}`, `${key.replace(/_/g, " ")} must be Yes or No.`));
  }
  for (const key of ["poll_interval_seconds", "timeout_seconds"]) {
    if (params[key] !== undefined && (typeof params[key] !== "number" || params[key] <= 0)) findings.push(finding("error", `extract-${key}-range`, `tasks.${step.key}.params.${key}`, `${key.replace(/_/g, " ")} must be a positive number.`));
  }
  if (!Object.keys(fields).length) {
    findings.push(finding("error", "extract-fields-empty", `tasks.${step.key}.params.fields`, "Extraction task must define at least one field."));
  }
  const tableFields = Object.entries(fields).filter(([, field]) => field?.is_table).map(([key]) => key);
  if (tableFields.length > 1) {
    findings.push(finding("error", "extract-multiple-table-fields", `tasks.${step.key}.params.fields`, "Only one table field is supported."));
  }
  Object.entries(fields).forEach(([fieldKey, field]) => {
    const path = `tasks.${step.key}.params.fields.${fieldKey}`;
    if (!fieldKey.trim()) findings.push(finding("error", "extract-field-key-empty", path, "Extraction field keys cannot be empty."));
    if (!isPlainObject(field)) {
      findings.push(finding("error", "extract-field-invalid", path, `Field '${fieldKey}' must be a mapping.`));
      return;
    }
    if (!field.alias?.trim()) findings.push(finding("error", "extract-field-alias-empty", `${path}.alias`, `Field '${fieldKey}' needs an alias.`));
    if (field.description !== undefined && typeof field.description !== "string") findings.push(finding("error", "extract-field-description-type", `${path}.description`, `Field '${fieldKey}' guidance must be text.`));
    if (!isSupportedFieldType(field.type, { table: Boolean(field.is_table) })) findings.push(finding("error", "extract-field-type-invalid", `${path}.type`, `Field '${fieldKey}' must use a supported type.`));
    if (field.is_table) {
      if (unwrapOptionalType(field.type) !== TABLE_FIELD_TYPE) findings.push(finding("error", "extract-table-type", `${path}.type`, "Table fields must use the table row type."));
      if (!isPlainObject(field.item_fields) || !Object.keys(field.item_fields).length) {
        findings.push(finding("error", "extract-table-items-empty", `${path}.item_fields`, `Table field '${fieldKey}' needs item fields.`));
      } else {
        Object.entries(field.item_fields).forEach(([itemKey, itemField]) => {
          if (!isPlainObject(itemField) || !isSupportedRowFieldType(itemField.type)) {
            findings.push(finding("error", "extract-item-field-type-invalid", `${path}.item_fields.${itemKey}.type`, `Column '${itemKey}' must use Text, Integer, Number, or Yes / No.`));
          }
          if (isPlainObject(itemField) && itemField.description !== undefined && typeof itemField.description !== "string") findings.push(finding("error", "extract-item-description-type", `${path}.item_fields.${itemKey}.description`, `Column '${itemKey}' guidance must be text.`));
        });
      }
    }
  });
}

function validateStorage(step, scalarTokenSet, findings) {
  const params = step.params || {};
  const dirParam = step.class === "StoreFileToLocaldrive" ? "files_dir" : "data_dir";
  const nestedStorage = step.class === "StoreMetadataAsCsv" && isPlainObject(params.storage) ? params.storage : null;
  const directory = nestedStorage?.[dirParam] ?? params[dirParam];
  const filename = nestedStorage?.filename ?? params.filename;
  const basePath = nestedStorage ? `tasks.${step.key}.params.storage` : `tasks.${step.key}.params`;
  if (!directory) findings.push(finding("error", "storage-dir-empty", `${basePath}.${dirParam}`, `${step.label} needs an output directory.`));
  if (!filename) {
    findings.push(finding("error", "storage-filename-empty", `tasks.${step.key}.params.filename`, `${step.label} needs a filename template.`));
  }
  extractTemplateTokens(filename).forEach((token) => {
    if (!scalarTokenSet.has(token)) {
      findings.push(finding("error", "storage-token-invalid", `tasks.${step.key}.params.filename`, `Filename token {${token}} is not a scalar extraction/context token.`));
    }
  });
}

function validateRules(step, fields, csvInfo, findings) {
  const params = step.params || {};
  const columns = csvInfo?.columns || [];
  if (!params.reference_file) findings.push(finding("error", "rules-reference-empty", `tasks.${step.key}.params.reference_file`, "Rules task needs a reference CSV file."));
  if (!params.update_field) findings.push(finding("error", "rules-update-field-empty", `tasks.${step.key}.params.update_field`, "Rules task needs an update field."));
  if (params.write_value !== undefined && typeof params.write_value !== "string") findings.push(finding("error", "rules-write-value-type", `tasks.${step.key}.params.write_value`, "Write value must be text."));
  if (params.backup !== undefined && typeof params.backup !== "boolean") findings.push(finding("error", "rules-backup-type", `tasks.${step.key}.params.backup`, "Backup must be Yes or No."));
  if (params.task_slug !== undefined && (typeof params.task_slug !== "string" || !params.task_slug.trim())) findings.push(finding("error", "rules-task-slug-type", `tasks.${step.key}.params.task_slug`, "Task status key must be non-empty text."));
  if (columns.length && params.update_field && !columns.includes(params.update_field)) {
    findings.push(finding("error", "rules-update-field-missing", `tasks.${step.key}.params.update_field`, "Update field is not present in the selected CSV."));
  }
  const clauses = params.csv_match?.clauses;
  if (!Array.isArray(clauses) || clauses.length < 1 || clauses.length > 5) {
    findings.push(finding("error", "rules-clause-count", `tasks.${step.key}.params.csv_match.clauses`, "Rules task needs 1 to 5 match clauses."));
    return;
  }
  const contextTokens = new Set([...Object.keys(fields), ...CONTEXT_TOKENS]);
  clauses.forEach((clause, index) => {
    const path = `tasks.${step.key}.params.csv_match.clauses[${index}]`;
    if (!clause.column) findings.push(finding("error", "rules-clause-column-empty", `${path}.column`, "Clause needs a CSV column."));
    if (columns.length && clause.column && !columns.includes(clause.column)) {
      findings.push(finding("error", "rules-clause-column-missing", `${path}.column`, `Column '${clause.column}' is not present in the selected CSV.`));
    }
    if (!clause.from_context) findings.push(finding("error", "rules-clause-context-empty", `${path}.from_context`, "Clause needs a context field."));
    if (clause.from_context && !contextTokens.has(clause.from_context)) {
      findings.push(finding("error", "rules-clause-context-invalid", `${path}.from_context`, `Context field '${clause.from_context}' is not available.`));
    }
    if (clause.number !== undefined && typeof clause.number !== "boolean") findings.push(finding("error", "rules-clause-number-type", `${path}.number`, "Comparison type must be Auto, Text, or Numeric."));
  });
}

function validateContext(step, findings) {
  const length = step.params.length;
  if (!Number.isInteger(length) || length < 5 || length > 21) {
    findings.push(finding("error", "context-length-range", `tasks.${step.key}.params.length`, "Nanoid length must be an integer from 5 to 21."));
  }
}

function validateHousekeeping(step, findings) {
  const value = step.params?.processing_dir;
  if (value !== undefined && (typeof value !== "string" || !value.trim())) {
    findings.push(finding("error", "housekeeping-processing-dir", `tasks.${step.key}.params.processing_dir`, "Processing directory must be non-empty text."));
  }
}

function validateSplit(step, findings) {
  const params = step.params || {};
  if (!params.split_dir) findings.push(finding("error", "split-dir-empty", `tasks.${step.key}.params.split_dir`, "Split task needs an output directory."));
  if (params.enabled !== undefined && typeof params.enabled !== "boolean") findings.push(finding("error", "split-enabled-type", `tasks.${step.key}.params.enabled`, "Enable document splitting must be Yes or No."));
  if (params.enabled && !params.api_key && !params.adapter) findings.push(finding("error", "split-api-key-empty", `tasks.${step.key}.params.api_key`, "Enabled splitting needs an API key."));
  if (params.enabled && !params.configuration_id && (!Array.isArray(params.categories) || !params.categories.length)) findings.push(finding("error", "split-configuration-empty", `tasks.${step.key}.params.categories`, "Enabled splitting needs a configuration ID or at least one category."));
  if (params.allow_uncategorized !== undefined && !["include", "forbid", "omit"].includes(params.allow_uncategorized)) findings.push(finding("error", "split-uncategorized-policy", `tasks.${step.key}.params.allow_uncategorized`, "Uncategorized policy must keep, stop, or skip pages."));
  if (params.categories !== undefined && (!Array.isArray(params.categories) || params.categories.some((category) => !isPlainObject(category) || !String(category.name || "").trim()))) findings.push(finding("error", "split-categories-invalid", `tasks.${step.key}.params.categories`, "Every split category needs a name."));
  if (params.allowed_categories !== undefined && (!Array.isArray(params.allowed_categories) || params.allowed_categories.some((category) => typeof category !== "string" || !category.trim()))) findings.push(finding("error", "split-allowed-categories-invalid", `tasks.${step.key}.params.allowed_categories`, "Allowed categories must be non-empty names."));
  for (const key of ["configuration_id", "project_id", "organization_id"]) {
    if (params[key] !== undefined && (typeof params[key] !== "string" || !params[key].trim())) findings.push(finding("error", `split-${key}-type`, `tasks.${step.key}.params.${key}`, `${key.replace(/_/g, " ")} must be non-empty text when provided.`));
  }
  for (const key of ["poll_interval_seconds", "timeout_seconds"]) {
    if (params[key] !== undefined && (typeof params[key] !== "number" || params[key] <= 0)) findings.push(finding("error", `split-${key}-range`, `tasks.${step.key}.params.${key}`, `${key.replace(/_/g, " ")} must be a positive number.`));
  }
  const levels = params.fail_on_confidence_levels;
  if (levels !== undefined) {
    const allowed = new Set(["high", "medium", "low"]);
    if (!Array.isArray(levels) || levels.some((level) => !allowed.has(level))) {
      findings.push(finding("error", "split-confidence-level-invalid", `tasks.${step.key}.params.fail_on_confidence_levels`, "Split confidence levels must be high, medium, or low."));
    }
  }
}

function validateThresholdMap(value, path, label, findings) {
  if (value === undefined) return;
  if (!isPlainObject(value)) {
    findings.push(finding("error", "review-threshold-map", path, `${label} must be a key-to-threshold mapping.`));
    return;
  }
  Object.entries(value).forEach(([key, threshold]) => {
    if (!key.trim()) findings.push(finding("error", "review-threshold-key", path, `${label} cannot contain an empty key.`));
    if (typeof threshold !== "number" || threshold < 0 || threshold > 1) {
      findings.push(finding("error", "review-threshold-range", `${path}.${key}`, `${label} values must be between 0 and 1.`));
    }
  });
}

function validateReview(step, findings) {
  const params = step.params || {};
  if (typeof params.confidence_threshold !== "number" || params.confidence_threshold < 0 || params.confidence_threshold > 1) {
    findings.push(finding("error", "review-threshold-range", `tasks.${step.key}.params.confidence_threshold`, "Confidence threshold must be between 0 and 1."));
  }
  validateThresholdMap(params.per_document_type_thresholds, `tasks.${step.key}.params.per_document_type_thresholds`, "Document thresholds", findings);
  validateThresholdMap(params.field_threshold_overrides, `tasks.${step.key}.params.field_threshold_overrides`, "Field thresholds", findings);
  const levels = params.split_confidence_levels_requiring_review;
  if (levels !== undefined && (!Array.isArray(levels) || levels.some((level) => !["high", "medium", "low"].includes(level)))) {
    findings.push(finding("error", "review-split-confidence-level", `tasks.${step.key}.params.split_confidence_levels_requiring_review`, "Review confidence levels must be high, medium, or low."));
  }
  if (params.resume_policy !== undefined && params.resume_policy !== "next_task") {
    findings.push(finding("error", "review-resume-policy", `tasks.${step.key}.params.resume_policy`, "Production currently supports only Continue to next task."));
  }
  if (params.review_scope !== undefined && !["document", "low_confidence_fields", "schema_errors", "split_result"].includes(params.review_scope)) findings.push(finding("error", "review-scope", `tasks.${step.key}.params.review_scope`, "Review scope is not supported by production."));
  for (const key of ["require_review_when_missing_confidence", "require_review_for_missing_required_fields", "always_review", "allow_operator_to_edit_high_confidence_fields"]) {
    if (params[key] !== undefined && typeof params[key] !== "boolean") findings.push(finding("error", `review-${key}-type`, `tasks.${step.key}.params.${key}`, `${key.replace(/_/g, " ")} must be Yes or No.`));
  }
  for (const key of ["schema_file", "queue_name"]) {
    if (params[key] !== undefined && params[key] !== null && typeof params[key] !== "string") findings.push(finding("error", `review-${key}-type`, `tasks.${step.key}.params.${key}`, `${key.replace(/_/g, " ")} must be text.`));
  }
}

function App() {
  const [baseConfig, setBaseConfig] = useState(null);
  const [steps, setSteps] = useState([]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [activeTab, setActiveTab] = useState("properties");
  const [pipelineView, setPipelineView] = useState(null);
  const [search, setSearch] = useState("");
  const [currentYaml, setCurrentYaml] = useState("");
  const [source, setSource] = useState(null);
  const [dirty, setDirty] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [publishMessage, setPublishMessage] = useState("");
  const [simulated, setSimulated] = useState(false);
  const [collapsedPalette, setCollapsedPalette] = useState(false);
  const [csvMetadata, setCsvMetadata] = useState({});

  const selected = steps[selectedIndex] || steps[0] || null;
  const draftConfig = useMemo(() => buildConfig(baseConfig, steps), [baseConfig, steps]);
  const draftYaml = useMemo(() => dumpYaml(draftConfig), [draftConfig]);
  const diffText = useMemo(() => lineDiff(currentYaml, draftYaml), [currentYaml, draftYaml]);
  const findings = useMemo(() => validateSteps(steps, csvMetadata), [steps, csvMetadata]);
  const enabledCount = steps.filter((step) => step.enabled !== false).length;
  const hasErrors = findings.some((item) => item.severity === "error");
  const availableTokens = useMemo(() => scalarTokens(steps), [steps]);

  const markDirty = useCallback(() => {
    setDirty(true);
    setPublishMessage("");
  }, []);

  const loadConfig = useCallback(async () => {
    setLoading(true);
    setLoadError("");
    try {
      const response = await fetch("/api/prototype/config");
      if (!response.ok) throw new Error(`Unable to load prototype config (${response.status}).`);
      const payload = await response.json();
      const loadedSteps = configToSteps(payload.config || {});
      setBaseConfig(payload.config || {});
      setCurrentYaml(payload.rawYaml || "");
      setSource(payload);
      setSteps(loadedSteps);
      setSelectedIndex(0);
      setActiveTab("properties");
      setDirty(false);
      setPublishMessage("");
      preloadCsvMetadata(loadedSteps, setCsvMetadata);
    } catch (error) {
      setLoadError(error.message || "Unable to load prototype config.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadConfig();
  }, [loadConfig]);

  function updateStep(index, patch) {
    setSteps((current) => current.map((step, stepIndex) => (stepIndex === index ? { ...step, ...patch } : step)));
    markDirty();
  }

  function updateParams(index, patch) {
    setSteps((current) =>
      current.map((step, stepIndex) =>
        stepIndex === index ? { ...step, params: { ...step.params, ...patch } } : step,
      ),
    );
    markDirty();
  }

  function replaceParams(index, params) {
    setSteps((current) => current.map((step, stepIndex) => (stepIndex === index ? { ...step, params } : step)));
    markDirty();
  }

  function moveStep(index, direction) {
    const next = [...steps];
    const target = index + direction;
    if (target < 0 || target >= next.length) return;
    [next[index], next[target]] = [next[target], next[index]];
    setSteps(next);
    setSelectedIndex(target);
    markDirty();
  }

  function deleteStep(index) {
    const next = steps.filter((_, stepIndex) => stepIndex !== index);
    setSteps(next);
    setSelectedIndex(Math.max(0, Math.min(index, next.length - 1)));
    markDirty();
  }

  function addTask(task, insertIndex = steps.length) {
    const targetIndex = Math.max(0, Math.min(insertIndex, steps.length));
    const nextTask = templateToStep(task, uniqueKey(task.key, steps), true);
    setSteps((current) => {
      const next = [...current];
      next.splice(targetIndex, 0, nextTask);
      return next;
    });
    setSelectedIndex(targetIndex);
    markDirty();
  }

  function duplicateSelected() {
    if (!selected) return;
    const duplicate = clone(selected);
    duplicate.key = uniqueKey(`${selected.key}_copy`, steps);
    duplicate.label = `${selected.label} copy`;
    delete duplicate.icon;
    setSteps((current) => {
      const next = [...current];
      next.splice(selectedIndex + 1, 0, duplicate);
      return next;
    });
    setSelectedIndex(selectedIndex + 1);
    markDirty();
  }

  async function publishDraft() {
    if (hasErrors || saving) return;
    setSaving(true);
    setPublishMessage("");
    try {
      const response = await fetch("/api/prototype/config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ config: draftConfig }),
      });
      const payload = await response.json();
      if (!response.ok) {
        const details = Array.isArray(payload.findings) ? ` ${payload.findings.join(" ")}` : "";
        throw new Error(`${payload.error || "Publish failed."}${details}`);
      }
      const loadedSteps = configToSteps(payload.config || {});
      setBaseConfig(payload.config || {});
      setCurrentYaml(payload.rawYaml || "");
      setSource(payload);
      setSteps(loadedSteps);
      setDirty(false);
      setPublishMessage("Published to public/config_sample_invoice.yaml. Backup updated.");
      preloadCsvMetadata(loadedSteps, setCsvMetadata);
    } catch (error) {
      setPublishMessage(error.message || "Publish failed.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="min-h-screen bg-base-200 text-base-content">
      <div className="flex min-h-screen">
        <aside className="hidden w-[4.75rem] shrink-0 border-r border-base-300 bg-base-100 px-3 py-4 lg:flex lg:flex-col lg:items-center">
          <div className="mb-5 flex h-10 w-10 items-center justify-center rounded-lg bg-primary text-primary-content">
            <GitBranch size={20} />
          </div>
          {[[Upload, "Upload"], [ListChecks, "Pipeline"], [ShieldCheck, "Review"], [Database, "Reports"], [Settings, "Settings"]].map(([Icon, label], index) => (
            <button className={`btn btn-ghost btn-square btn-sm mb-2 ${index === 1 ? "btn-active text-primary" : ""}`} title={label} key={label}>
              <Icon size={17} />
            </button>
          ))}
        </aside>
        <main className="flex min-w-0 flex-1 flex-col">
          <header className="flex min-h-20 flex-wrap items-center justify-between gap-3 border-b border-base-300 bg-base-100 px-5 py-4">
            <div>
              <div className="flex items-center gap-2">
                <span className="badge badge-primary badge-sm">Prototype</span>
                <span className="text-xs text-base-content/55">public/config_sample_invoice.yaml</span>
              </div>
              <h1 className="mt-1 text-lg font-bold">Visual Pipeline Builder</h1>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <button className="btn btn-ghost btn-sm" onClick={loadConfig} disabled={loading || saving}>
                <RefreshCw size={15} /> Reload file
              </button>
              <button className="btn btn-outline btn-sm" onClick={() => setSimulated(true)}>
                <Play size={15} /> Simulate run
              </button>
              <button className="btn btn-primary btn-sm" onClick={publishDraft} disabled={hasErrors || saving || loading}>
                <Save size={15} /> {saving ? "Publishing" : "Publish YAML"}
              </button>
            </div>
          </header>

          <SourceBar source={source} dirty={dirty} loading={loading} hasErrors={hasErrors} publishMessage={publishMessage} loadError={loadError} />

          <PipelineActionBar
            activeView={pipelineView}
            setActiveView={setPipelineView}
            findings={findings}
            dirty={dirty}
          />

          <section className="grid gap-3 border-b border-base-300 bg-base-100/70 px-5 py-3 md:grid-cols-4">
            <StatusStat label="Enabled steps" value={`${enabledCount}/${steps.length}`} icon={ListChecks} />
            <StatusStat label="Dirty state" value={dirty ? "Unsaved draft" : "Matches file"} icon={dirty ? AlertTriangle : CheckCircle2} tone={dirty ? "warning" : "success"} />
            <StatusStat label="Validation" value={hasErrors ? "Needs fixes" : "Ready"} icon={hasErrors ? AlertTriangle : CheckCircle2} tone={hasErrors ? "warning" : "success"} />
            <StatusStat label="Runtime model" value="tasks + pipeline" icon={FileText} />
          </section>

          {loadError ? (
            <div className="m-4 alert alert-error">{loadError}</div>
          ) : (
            <div className="grid min-h-0 flex-1 grid-cols-1 items-start gap-4 p-4 xl:grid-cols-[minmax(12.5rem,14rem)_minmax(28rem,1fr)_minmax(22rem,26rem)]">
              <TaskPalette collapsed={collapsedPalette} setCollapsed={setCollapsedPalette} search={search} setSearch={setSearch} steps={steps} addTask={addTask} />

              <section className="flex min-h-[640px] min-w-0 flex-col gap-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <h2 className="text-base font-semibold">Ordered pipeline</h2>
                    <p className="text-xs text-base-content/55">Connections are fixed by YAML order. Use controls to change order.</p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button className="btn btn-sm" disabled={selectedIndex === 0} onClick={() => moveStep(selectedIndex, -1)}>
                      <ChevronLeft size={15} /> Earlier
                    </button>
                    <button className="btn btn-sm" disabled={selectedIndex >= steps.length - 1} onClick={() => moveStep(selectedIndex, 1)}>
                      Later <ChevronRight size={15} />
                    </button>
                  </div>
                </div>
                <OrderedPipeline steps={steps} selectedIndex={selectedIndex} onSelect={(index) => setSelectedIndex(index)} onInsert={addTask} />
                {simulated ? <RunSimulation steps={steps} close={() => setSimulated(false)} /> : null}
              </section>

              <PropertiesPanel
                step={selected}
                index={selectedIndex}
                steps={steps}
                activeTab={activeTab}
                setActiveTab={setActiveTab}
                updateStep={updateStep}
                updateParams={updateParams}
                replaceParams={replaceParams}
                duplicateSelected={duplicateSelected}
                deleteStep={deleteStep}
                findings={findings}
                availableTokens={availableTokens}
                csvMetadata={csvMetadata}
                setCsvMetadata={setCsvMetadata}
              />
            </div>
          )}
        </main>
      </div>
      {pipelineView ? (
        <PipelineWorkspace
          activeView={pipelineView}
          setActiveView={setPipelineView}
          close={() => setPipelineView(null)}
          findings={findings}
          draftYaml={draftYaml}
          currentYaml={currentYaml}
          diffText={diffText}
          dirty={dirty}
        />
      ) : null}
    </div>
  );
}

async function preloadCsvMetadata(steps, setCsvMetadata) {
  const references = steps.map((step) => step.params?.reference_file).filter(Boolean);
  const metadata = {};
  await Promise.all(
    references.map(async (referenceFile) => {
      try {
        const response = await fetch(`/api/prototype/fs/csv?path=${encodeURIComponent(referenceFile)}`);
        if (response.ok) metadata[referenceFile] = await response.json();
      } catch {
        // Inline validation will cover missing metadata.
      }
    }),
  );
  setCsvMetadata((current) => ({ ...current, ...metadata }));
}

function SourceBar({ source, dirty, loading, hasErrors, publishMessage, loadError }) {
  return (
    <section className="source-bar">
      <div className="min-w-0">
        <div className="text-xs font-semibold uppercase tracking-wide text-base-content/60">Editable source</div>
        <div className="truncate font-mono text-xs">{source?.relativePath || "public/config_sample_invoice.yaml"}</div>
      </div>
      <div className="source-pill">{loading ? "Loading" : dirty ? "Draft changed" : "Clean"}</div>
      <div className={`source-pill ${hasErrors ? "source-pill-warning" : "source-pill-success"}`}>{hasErrors ? "Publish blocked" : "Publish ready"}</div>
      <div className="min-w-0 text-xs text-base-content/60">
        {loadError || publishMessage || (source?.modifiedTime ? `File modified ${new Date(source.modifiedTime).toLocaleString()}` : "Waiting for file")}
      </div>
    </section>
  );
}

function StatusStat({ label, value, icon: Icon, tone }) {
  return (
    <div className="flex min-w-0 items-center gap-3 rounded-lg border border-base-300 bg-base-100 px-3 py-2">
      <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-md ${tone === "success" ? "bg-success/15 text-success" : tone === "warning" ? "bg-warning/15 text-warning" : "bg-primary/10 text-primary"}`}>
        <Icon size={17} />
      </span>
      <div className="min-w-0">
        <div className="text-xs font-semibold uppercase tracking-wide text-base-content/60">{label}</div>
        <div className="truncate text-sm font-semibold">{value}</div>
      </div>
    </div>
  );
}

function TaskPalette({ collapsed, setCollapsed, search, setSearch, steps, addTask }) {
  const filtered = taskTemplates.filter((task) => `${task.label} ${task.category} ${task.class}`.toLowerCase().includes(search.toLowerCase()));
  return (
    <section className={`min-w-0 rounded-lg border border-base-300 bg-base-100 ${collapsed ? "xl:w-14" : ""}`}>
      <div className="flex items-center justify-between border-b border-base-300 p-3">
        {!collapsed ? (
          <div>
            <h2 className="text-base font-semibold">Task Palette</h2>
            <p className="text-xs text-base-content/55">Approved prototype steps</p>
          </div>
        ) : null}
        <button className="btn btn-ghost btn-square btn-sm" onClick={() => setCollapsed(!collapsed)} title="Toggle palette">
          <PanelRight size={16} />
        </button>
      </div>
      {!collapsed ? (
        <div className="p-3">
          <label className="input input-bordered input-sm mb-3 flex items-center gap-2">
            <Search size={14} />
            <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Find task" />
          </label>
          <div className="space-y-2">
            {filtered.map((task) => {
              const Icon = task.icon;
              const alreadyPresent = steps.some((step) => step.key === task.key);
              return (
                <button key={task.key} className="task-palette-item" onClick={() => addTask(task)}>
                  <span className="flex h-9 w-9 items-center justify-center rounded-md bg-base-200 text-base-content/70">
                    <Icon size={17} />
                  </span>
                  <span className="min-w-0 flex-1 text-left">
                    <span className="block truncate text-sm font-medium">{task.label}</span>
                    <span className="block truncate text-xs text-base-content/60">{task.category} - {task.class}</span>
                  </span>
                  <span className={`btn btn-square btn-xs ${alreadyPresent ? "btn-ghost" : "btn-outline"}`}>
                    <Plus size={13} />
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      ) : null}
    </section>
  );
}

function OrderedPipeline({ steps, selectedIndex, onSelect, onInsert }) {
  return (
    <div className="ordered-canvas">
      {steps.map((step, index) => {
        const Icon = iconFor(step);
        const kind = taskKind(step);
        return (
          <React.Fragment key={`${step.key}-${index}`}>
            <button className={`ordered-node ${index === selectedIndex ? "selected" : ""} ${step.enabled === false ? "disabled" : ""}`} onClick={() => onSelect(index)}>
              <div className="flex items-start justify-between gap-3">
                <span className="node-icon">
                  <Icon size={18} />
                </span>
                <span className={`badge badge-sm ${kindBadgeClass(kind)}`}>{kind}</span>
              </div>
              <div className="mt-3 truncate text-left text-sm font-semibold">{step.label}</div>
              <div className="truncate text-left font-mono text-xs text-base-content/55">{step.key}</div>
              <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
                <Metric label="Order" value={step.enabled === false ? "disabled" : index + 1} />
                <Metric label="On error" value={step.on_error || "default"} />
              </div>
            </button>
            {index < steps.length - 1 ? <PipelineInsertControl position={index + 1} onInsert={onInsert} /> : null}
          </React.Fragment>
        );
      })}
    </div>
  );
}

function PipelineInsertControl({ position, onInsert }) {
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    function handlePointerDown(event) {
      if (!wrapperRef.current?.contains(event.target)) setOpen(false);
    }
    function handleKeyDown(event) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  return (
    <div className="pipeline-insert" ref={wrapperRef}>
      <ArrowRight className="ordered-arrow" size={20} />
      <button className="pipeline-insert-trigger" title="Insert task here" aria-expanded={open} onClick={() => setOpen((current) => !current)}>
        <Plus size={15} />
      </button>
      {open ? (
        <div className="pipeline-insert-popover" role="dialog" aria-label="Insert task here">
          <div className="pipeline-insert-header">
            <span>Insert here</span>
            <button className="pipeline-insert-close" onClick={() => setOpen(false)} title="Close insert menu">
              <X size={14} />
            </button>
          </div>
          <div className="space-y-1">
            {taskTemplates.map((task) => {
              const Icon = task.icon;
              return (
                <button
                  className="pipeline-insert-item"
                  key={task.key}
                  onClick={() => {
                    onInsert(task, position);
                    setOpen(false);
                  }}
                >
                  <Icon size={14} />
                  <span className="min-w-0">
                    <span className="block truncate font-medium">{task.label}</span>
                    <span className="block truncate text-xs text-base-content/60">{task.category}</span>
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function Metric({ label, value }) {
  return (
    <div className="rounded-md bg-base-200 px-2 py-1">
      <div className="text-base-content/60">{label}</div>
      <div className="truncate font-medium">{String(value || "-")}</div>
    </div>
  );
}

function PipelineActionBar({ activeView, setActiveView, findings, dirty }) {
  const errorCount = findings.filter((item) => item.severity === "error").length;
  return (
    <section className="pipeline-action-bar" aria-label="Pipeline tools">
      <div className="min-w-0">
        <div className="text-xs font-semibold uppercase tracking-wide text-base-content/60">Pipeline tools</div>
        <div className="truncate text-sm text-base-content/70">Inspect the complete configuration before publishing.</div>
      </div>
      <div className="pipeline-action-list">
        <button className={`pipeline-action ${activeView === "validate" ? "active" : ""}`} onClick={() => setActiveView("validate")}>
          {errorCount ? <AlertTriangle size={16} /> : <CheckCircle2 size={16} />}
          <span>Validate pipeline</span>
          <span className={`badge badge-sm ${errorCount ? "badge-error" : "badge-success"}`}>{errorCount || "Ready"}</span>
        </button>
        <button className={`pipeline-action ${activeView === "yaml" ? "active" : ""}`} onClick={() => setActiveView("yaml")}>
          <FileJson size={16} />
          <span>Pipeline YAML</span>
        </button>
        <button className={`pipeline-action ${activeView === "diff" ? "active" : ""}`} onClick={() => setActiveView("diff")}>
          <GitBranch size={16} />
          <span>Review changes</span>
          {dirty ? <span className="pipeline-change-dot" aria-label="Unsaved changes" /> : null}
        </button>
      </div>
    </section>
  );
}

function PipelineWorkspace({ activeView, setActiveView, close, findings, draftYaml, currentYaml, diffText, dirty }) {
  const titles = {
    validate: ["Validate pipeline", "Check the complete configuration and follow issues back to their task."],
    yaml: ["Pipeline YAML", "Review the full draft that will be written when you publish."],
    diff: ["Review changes", "Compare the published file with your current pipeline draft."],
  };
  const [title, description] = titles[activeView];
  useEffect(() => {
    function handleKeyDown(event) {
      if (event.key === "Escape") close();
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [close]);
  return (
    <div className="pipeline-workspace-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && close()}>
      <section className="pipeline-workspace" role="dialog" aria-modal="true" aria-labelledby="pipeline-workspace-title">
        <header className="pipeline-workspace-header">
          <div className="min-w-0">
            <div className="text-xs font-semibold uppercase tracking-wide text-primary">Pipeline workspace</div>
            <h2 id="pipeline-workspace-title" className="mt-1 text-base font-semibold">{title}</h2>
            <p className="mt-1 text-sm text-base-content/60">{description}</p>
          </div>
          <button className="btn btn-ghost btn-square btn-sm" onClick={close} aria-label="Close pipeline workspace"><X size={18} /></button>
        </header>
        <nav className="pipeline-workspace-tabs" role="tablist" aria-label="Pipeline workspace views">
          {[["validate", "Validate pipeline", ListChecks], ["yaml", "Pipeline YAML", FileJson], ["diff", "Review changes", GitBranch]].map(([view, label, Icon]) => (
            <button key={view} role="tab" aria-selected={activeView === view} className={activeView === view ? "active" : ""} onClick={() => setActiveView(view)}>
              <Icon size={16} /> {label}
            </button>
          ))}
        </nav>
        <div className="pipeline-workspace-body">
          {activeView === "validate" ? <PipelineValidationPanel findings={findings} /> : null}
          {activeView === "yaml" ? <YamlPanel draftYaml={draftYaml} currentYaml={currentYaml} /> : null}
          {activeView === "diff" ? <DiffPanel diffText={diffText} hasChanges={dirty} /> : null}
        </div>
        <footer className="pipeline-workspace-footer">
          <span>Whole pipeline</span>
          <span className="font-mono">public/config_sample_invoice.yaml</span>
          <span className={`badge badge-sm ${dirty ? "badge-warning" : "badge-success"}`}>{dirty ? "Unsaved draft" : "Matches file"}</span>
        </footer>
      </section>
    </div>
  );
}

function PropertiesPanel(props) {
  const { step, index, activeTab, setActiveTab, findings } = props;
  if (!step) return <section className="rounded-lg border border-base-300 bg-base-100 p-4">No step selected</section>;
  const KindIcon = iconFor(step);
  const taskFindings = findings.filter((item) => item.path.startsWith(`tasks.${step.key}`) || item.path.startsWith(`steps.${index}.`));
  const taskErrorCount = taskFindings.filter((item) => item.severity === "error").length;
  const tabs = [["properties", "Properties"], ["issues", taskErrorCount ? `Issues (${taskErrorCount})` : "Issues"]];
  return (
    <section className="flex min-h-0 flex-col rounded-lg border border-base-300 bg-base-100">
      <div className="border-b border-base-300 p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <KindIcon size={19} />
            </span>
            <div className="min-w-0">
              <h2 className="truncate text-base font-semibold">{step.label}</h2>
              <p className="truncate font-mono text-xs text-base-content/60">{step.key}</p>
            </div>
          </div>
          <span className={`badge badge-sm ${kindBadgeClass(taskKind(step))}`}>{taskKind(step)}</span>
        </div>
        <div className="mt-4 grid grid-cols-2 gap-1 rounded-lg bg-base-200 p-1 text-xs" role="tablist" aria-label="Selected task">
          {tabs.map(([tab, label]) => (
            <button key={tab} role="tab" aria-selected={activeTab === tab} className={`rounded-md px-2 py-1.5 ${activeTab === tab ? "bg-base-100 font-semibold shadow-sm" : "text-base-content/60"}`} onClick={() => setActiveTab(tab)}>
              {label}
            </button>
          ))}
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-auto p-4">
        {activeTab === "properties" ? <StepProperties {...props} /> : null}
        {activeTab === "issues" ? <TaskIssuesPanel findings={taskFindings} step={step} /> : null}
      </div>
    </section>
  );
}

function StepProperties({ step, index, steps, updateStep, updateParams, replaceParams, duplicateSelected, deleteStep, availableTokens, csvMetadata, setCsvMetadata, findings }) {
  const kind = taskKind(step);
  const [confirmRemove, setConfirmRemove] = useState(false);
  useEffect(() => setConfirmRemove(false), [index, step.key]);
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <TextControl label="Label" value={step.label} onChange={(value) => updateStep(index, { label: value })} />
        <TextControl label="Key" value={step.key} onChange={(value) => updateStep(index, { key: uniqueKey(value, steps, index) })} mono />
        <SelectControl
          label="If this task fails"
          value={step.on_error}
          onChange={(value) => updateStep(index, { on_error: value })}
          options={[
            { value: "stop", label: "Stop the pipeline" },
            { value: "continue", label: "Continue to the next task" },
          ]}
          hint={step.on_error === "continue" ? "Later tasks will run even if this task fails." : "No later tasks will run after this failure."}
        />
        <label className="flex items-end gap-3 rounded-lg border border-base-300 px-3 py-2">
          <input type="checkbox" className="toggle toggle-sm" checked={step.enabled !== false} onChange={(event) => updateStep(index, { enabled: event.target.checked })} />
          <span className="pb-1 text-sm">Enabled in pipeline</span>
        </label>
      </div>
      <div className="rounded-lg border border-base-300 bg-base-200/50 p-3">
        <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-base-content/60">Task-specific controls</div>
        {kind === "split" ? <SplitControls step={step} index={index} updateParams={updateParams} findings={findings} /> : null}
        {kind === "extract" ? <ExtractControls step={step} index={index} updateParams={updateParams} findings={findings} /> : null}
        {kind === "storage" ? <StorageControls step={step} index={index} updateParams={updateParams} availableTokens={availableTokens} findings={findings} pipelineFields={extractionFields(steps)} /> : null}
        {kind === "review" ? <ReviewControls step={step} index={index} updateParams={updateParams} findings={findings} steps={steps} /> : null}
        {kind === "archive" ? <ArchiveControls step={step} index={index} updateParams={updateParams} findings={findings} /> : null}
        {kind === "rules" ? <RulesControls step={step} index={index} updateParams={updateParams} steps={steps} csvMetadata={csvMetadata} setCsvMetadata={setCsvMetadata} findings={findings} /> : null}
        {kind === "context" ? <ContextControls step={step} index={index} updateParams={updateParams} findings={findings} /> : null}
        {kind === "housekeeping" ? <HousekeepingControls step={step} index={index} updateParams={updateParams} findings={findings} /> : null}
        {kind === "task" ? <div className="text-sm text-base-content/60">Use advanced params for this task.</div> : null}
      </div>
      <AdvancedParamsEditor step={step} index={index} replaceParams={replaceParams} />
      <div className="grid grid-cols-2 gap-2">
        <button className="btn btn-outline btn-sm" onClick={duplicateSelected}>
          <Copy size={14} /> Duplicate
        </button>
        <button className="btn btn-outline btn-error btn-sm" onClick={() => setConfirmRemove(true)}>
          <Trash2 size={14} /> Remove
        </button>
      </div>
      {confirmRemove ? (
        <div className="rounded-lg border border-error/30 bg-error/10 p-3" role="alert">
          <div className="text-sm font-semibold">Remove {step.label}?</div>
          <p className="mt-1 text-xs text-base-content/65">This removes the task and its settings from the draft pipeline.</p>
          <div className="mt-3 flex justify-end gap-2">
            <button className="btn btn-ghost btn-xs" onClick={() => setConfirmRemove(false)}>Cancel</button>
            <button className="btn btn-error btn-xs" onClick={() => deleteStep(index)}>Confirm remove</button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function SplitControls({ step, index, updateParams, findings }) {
  const params = step.params || {};
  const categories = Array.isArray(params.categories) ? params.categories : [];
  const levels = Array.isArray(params.fail_on_confidence_levels) ? params.fail_on_confidence_levels : [];
  const uncategorizedPolicy = params.allow_uncategorized || "include";
  const uncategorizedHints = {
    include: "Keep pages that the splitter cannot classify.",
    forbid: "Treat any unclassified page as a split failure.",
    omit: "Leave unclassified pages out of generated PDFs.",
  };
  function toggleLevel(level) {
    const next = levels.includes(level) ? levels.filter((item) => item !== level) : [...levels, level];
    updateParams(index, { fail_on_confidence_levels: next });
  }
  function updateCategory(categoryIndex, patch) {
    updateParams(index, { categories: categories.map((category, currentIndex) => currentIndex === categoryIndex ? { ...category, ...patch } : category) });
  }
  function addCategory() {
    updateParams(index, { categories: [...categories, { name: `category_${categories.length + 1}`, description: "" }] });
  }
  function removeCategory(categoryIndex) {
    updateParams(index, { categories: categories.filter((_, currentIndex) => currentIndex !== categoryIndex) });
  }
  return (
    <div className="space-y-3">
      <BooleanSetting checked={params.enabled ?? false} label="Enable document splitting" hint="This runtime switch is separate from including the task in the pipeline." onChange={(value) => updateParams(index, { enabled: value })} />
      <SecretControl label="API key" value={params.api_key || ""} onChange={(value) => updateParams(index, { api_key: value })} />
      <TextControl label="LlamaCloud configuration ID (optional)" value={params.configuration_id || ""} onChange={(value) => updateParams(index, { configuration_id: value || undefined })} mono />
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <TextControl label="Project ID (optional)" value={params.project_id || ""} onChange={(value) => updateParams(index, { project_id: value || undefined })} mono />
        <TextControl label="Organization ID (optional)" value={params.organization_id || ""} onChange={(value) => updateParams(index, { organization_id: value || undefined })} mono />
      </div>
      <SelectControl
        label="When pages cannot be categorized"
        value={uncategorizedPolicy}
        onChange={(value) => updateParams(index, { allow_uncategorized: value })}
        options={[
          { value: "include", label: "Keep uncategorized pages" },
          { value: "forbid", label: "Stop the split" },
          { value: "omit", label: "Skip uncategorized pages" },
        ]}
        hint={uncategorizedHints[uncategorizedPolicy]}
      />
      <DirectoryControl label="Split output directory" hint="Child PDFs created by this task are written here." value={params.split_dir || ""} onChange={(value) => updateParams(index, { split_dir: value })} />
      <InlineFindings findings={findings} path={`tasks.${step.key}.params.split_dir`} />
      <div className="rounded-lg border border-base-300 bg-base-100 p-3">
        <div className="text-sm font-semibold">Stop on confidence levels</div>
        <p className="mt-1 text-xs text-base-content/55">The split fails when any result reports a selected confidence level.</p>
        <div className="mt-3 grid gap-2 sm:grid-cols-3">
          {["high", "medium", "low"].map((level) => (
            <label className={`flex cursor-pointer items-center gap-2 rounded-md border px-2 py-2 text-sm ${levels.includes(level) ? "border-primary bg-primary/5" : "border-base-300"}`} key={level}>
              <input className="checkbox checkbox-sm" type="checkbox" checked={levels.includes(level)} onChange={() => toggleLevel(level)} />
              <span className="capitalize">{level}</span>
            </label>
          ))}
        </div>
      </div>
      <label className="flex items-start gap-3 rounded-lg border border-base-300 bg-base-100 px-3 py-3">
        <input type="checkbox" className="toggle toggle-sm" checked={Boolean(params.fail_on_unknown_category)} onChange={(event) => updateParams(index, { fail_on_unknown_category: event.target.checked })} />
        <span>
          <span className="block text-sm font-medium">Stop on unknown categories</span>
          <span className="mt-1 block text-xs text-base-content/55">{params.fail_on_unknown_category ? "Only configured category names are accepted." : "Unknown category names are allowed."}</span>
        </span>
      </label>
      <div className="rounded-lg border border-base-300 bg-base-100 p-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-sm font-semibold">Document categories</div>
            <p className="mt-1 text-xs text-base-content/55">Define every document type the splitter should recognize.</p>
          </div>
          <button className="btn btn-outline btn-xs" type="button" onClick={addCategory}><Plus size={13} /> Add category</button>
        </div>
        <div className="mt-3 space-y-3">
          {categories.map((category, categoryIndex) => (
            <div className="rounded-md border border-base-300 p-3" key={categoryIndex}>
              <div className="mb-2 flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wide text-base-content/60">Category {categoryIndex + 1}</span>
                <button className="btn btn-ghost btn-square btn-xs text-error" type="button" title={`Remove category ${categoryIndex + 1}`} onClick={() => removeCategory(categoryIndex)}><Trash2 size={13} /></button>
              </div>
              <div className="space-y-3">
                <TextControl label="Category name" value={category?.name || ""} onChange={(value) => updateCategory(categoryIndex, { name: value })} />
                <TextAreaControl label="What belongs in this category?" value={category?.description || ""} onChange={(value) => updateCategory(categoryIndex, { description: value })} />
              </div>
            </div>
          ))}
          {!categories.length ? <div className="empty-panel">No inline categories. Provide a configuration ID or add a category.</div> : null}
        </div>
      </div>
      <TextControl label="Allowed category names (optional)" hint="Comma-separated allow-list. Leave blank to use the category names above." value={Array.isArray(params.allowed_categories) ? params.allowed_categories.join(", ") : ""} onChange={(value) => updateParams(index, { allowed_categories: value.split(",").map((item) => item.trim()).filter(Boolean) })} />
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <NumberControl label="Polling interval (seconds)" value={params.poll_interval_seconds ?? 1} min={0.1} step={0.1} onChange={(value) => updateParams(index, { poll_interval_seconds: value })} />
        <NumberControl label="Timeout (seconds)" value={params.timeout_seconds ?? 7200} min={1} step={1} onChange={(value) => updateParams(index, { timeout_seconds: value })} />
      </div>
    </div>
  );
}

function ExtractControls({ step, index, updateParams, findings }) {
  const fields = isPlainObject(step.params.fields) ? step.params.fields : {};
  const tableFieldKeys = Object.entries(fields).filter(([, field]) => field?.is_table).map(([key]) => key);
  const [editingRowSchema, setEditingRowSchema] = useState(null);
  useEffect(() => {
    if (editingRowSchema && !fields[editingRowSchema]) setEditingRowSchema(null);
  }, [editingRowSchema, fields]);
  function setFields(nextFields) {
    updateParams(index, { fields: nextFields });
  }
  function updateField(key, patch) {
    const nextField = { ...(fields[key] || {}), ...patch };
    Object.entries(patch).forEach(([patchKey, value]) => {
      if (value === undefined) delete nextField[patchKey];
    });
    setFields({ ...fields, [key]: nextField });
  }
  function renameField(oldKey, nextKey) {
    const key = uniqueObjectKey(nextKey, fields, oldKey);
    if (!key || key === oldKey) return;
    const next = {};
    Object.entries(fields).forEach(([fieldKey, value]) => {
      next[fieldKey === oldKey ? key : fieldKey] = value;
    });
    setFields(next);
  }
  function removeField(key) {
    const next = { ...fields };
    delete next[key];
    setFields(next);
    if (editingRowSchema === key) setEditingRowSchema(null);
  }
  function addField() {
    const key = uniqueObjectKey("new_field", fields);
    setFields({ ...fields, [key]: { alias: "New field", type: "str" } });
  }
  return (
    <div className="space-y-3">
      <SecretControl label="API key" value={step.params.api_key || ""} onChange={(value) => updateParams(index, { api_key: value })} />
      <TextControl label="LlamaExtract configuration ID" value={step.params.configuration_id || ""} onChange={(value) => updateParams(index, { configuration_id: value })} mono />
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <SelectControl label="Tier" value={step.params.tier || "agentic"} onChange={(value) => updateParams(index, { tier: value })} options={["agentic", "premium", "balanced"]} />
        <SelectControl label="Target" value={step.params.extraction_target || "per_doc"} onChange={(value) => updateParams(index, { extraction_target: value })} options={["per_doc", "per_page", "per_table_row"]} />
      </div>
      <label className="flex items-center gap-3 rounded-lg border border-base-300 bg-base-100 px-3 py-2">
        <input type="checkbox" className="toggle toggle-sm" checked={step.params.confidence_scores ?? true} onChange={(event) => updateParams(index, { confidence_scores: event.target.checked })} />
        <span className="text-sm">Request confidence scores</span>
      </label>
      <details className="rounded-lg border border-base-300 bg-base-100">
        <summary className="cursor-pointer px-3 py-3 text-sm font-semibold">Advanced extraction settings</summary>
        <div className="space-y-3 border-t border-base-300 p-3">
          <TextControl label="Parse tier (optional)" value={step.params.parse_tier || ""} onChange={(value) => updateParams(index, { parse_tier: value || undefined })} />
          <SelectControl label="Source citations" hint="Use provider default unless this pipeline needs an explicit setting." value={step.params.cite_sources === true ? "true" : step.params.cite_sources === false ? "false" : "default"} onChange={(value) => updateParams(index, { cite_sources: value === "default" ? undefined : value === "true" })} options={[
            { value: "default", label: "Use provider default" },
            { value: "true", label: "Request citations" },
            { value: "false", label: "Do not request citations" },
          ]} />
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <TextControl label="Project ID (optional)" value={step.params.project_id || ""} onChange={(value) => updateParams(index, { project_id: value || undefined })} mono />
            <TextControl label="Organization ID (optional)" value={step.params.organization_id || ""} onChange={(value) => updateParams(index, { organization_id: value || undefined })} mono />
            <NumberControl label="Polling interval (seconds)" value={step.params.poll_interval_seconds ?? 2} min={0.1} step={0.1} onChange={(value) => updateParams(index, { poll_interval_seconds: value })} />
            <NumberControl label="Timeout (seconds)" value={step.params.timeout_seconds ?? 1800} min={1} step={1} onChange={(value) => updateParams(index, { timeout_seconds: value })} />
          </div>
        </div>
      </details>
      {tableFieldKeys.length > 1 ? <div className="alert alert-error text-xs">Only one table field is supported. Disable table mode on extra fields.</div> : null}
      <div className="rounded-lg border border-base-300 bg-base-100">
        <div className="flex items-center justify-between border-b border-base-300 px-3 py-2">
          <span className="text-sm font-semibold">Fields</span>
          <button className="btn btn-outline btn-xs" onClick={addField}>
            <Plus size={13} /> Add field
          </button>
        </div>
        <div className="space-y-3 p-3">
          {Object.entries(fields).map(([key, config]) => (
            <FieldEditor key={key} fieldKey={key} config={isPlainObject(config) ? config : {}} tableFieldKeys={tableFieldKeys} renameField={renameField} updateField={updateField} removeField={removeField} findings={findings} stepKey={step.key} openRowSchema={() => setEditingRowSchema(key)} />
          ))}
          {!Object.keys(fields).length ? <div className="empty-panel">No extraction fields configured</div> : null}
        </div>
      </div>
      {editingRowSchema && isPlainObject(fields[editingRowSchema]) ? (
        <RowSchemaDrawer
          fieldKey={editingRowSchema}
          config={fields[editingRowSchema]}
          onClose={() => setEditingRowSchema(null)}
          onSave={(itemFields) => {
            updateField(editingRowSchema, { item_fields: itemFields });
            setEditingRowSchema(null);
          }}
        />
      ) : null}
    </div>
  );
}

function FieldEditor({ fieldKey, config, tableFieldKeys, renameField, updateField, removeField, findings, stepKey, openRowSchema }) {
  const [keyDraft, setKeyDraft] = useState(fieldKey);
  useEffect(() => setKeyDraft(fieldKey), [fieldKey]);
  const isTable = Boolean(config.is_table);
  const tableBlocked = !isTable && tableFieldKeys.length >= 1;
  function changeType(nextType) {
    const nextBaseType = unwrapOptionalType(nextType);
    if (nextBaseType === TABLE_FIELD_TYPE) {
      if (tableBlocked) return;
      updateField(fieldKey, { is_table: true, type: nextType, item_fields: isPlainObject(config.item_fields) ? config.item_fields : {} });
      if (!isTable) openRowSchema();
    } else {
      updateField(fieldKey, { type: nextType, is_table: undefined, item_fields: undefined });
    }
  }
  return (
    <div className="field-editor">
      <div className="property-field-grid">
        <label className="form-control">
          <span className="label-text mb-1 text-xs">Field key</span>
          <input className="input input-bordered input-sm font-mono" value={keyDraft} onChange={(event) => setKeyDraft(slugKey(event.target.value))} onBlur={() => renameField(fieldKey, keyDraft)} />
        </label>
        <TextControl label="Alias" value={config.alias || ""} onChange={(value) => updateField(fieldKey, { alias: value })} />
        <FieldTypeControl value={config.type || "str"} onChange={changeType} disableTableOption={tableBlocked} />
        <button className="btn btn-ghost btn-square btn-sm self-end text-error" onClick={() => removeField(fieldKey)} title="Remove field">
          <Trash2 size={14} />
        </button>
      </div>
      <InlineFindings findings={findings} pathPrefix={`tasks.${stepKey}.params.fields.${fieldKey}`} />
      <div className="mt-3">
        <TextControl label="Extraction guidance (optional)" value={config.description || ""} onChange={(value) => updateField(fieldKey, { description: value || undefined })} />
      </div>
      {tableBlocked ? <div className="mt-2 text-xs text-base-content/55">Only one List of objects field can be configured.</div> : null}
      {isTable ? (
        <div className="row-schema-summary">
          <div>
            <div className="text-xs font-semibold">Row schema</div>
            <div className="mt-0.5 text-xs text-base-content/55">{Object.keys(config.item_fields || {}).length} flat row fields defined</div>
          </div>
          <button className="btn btn-outline btn-xs" type="button" onClick={openRowSchema}>
            <PanelRight size={13} /> Edit row schema
          </button>
        </div>
      ) : null}
    </div>
  );
}

function RowSchemaDrawer({ fieldKey, config, onClose, onSave }) {
  const [rows, setRows] = useState(() => rowSchemaRows(config.item_fields));
  useEffect(() => setRows(rowSchemaRows(config.item_fields)), [fieldKey, config.item_fields]);
  function updateRow(rowId, patch) {
    setRows((current) => current.map((row) => row.id === rowId ? { ...row, ...patch } : row));
  }
  function updateItem(rowId, patch) {
    setRows((current) => current.map((row) => row.id === rowId ? { ...row, config: { ...row.config, ...patch } } : row));
  }
  function removeItem(rowId) {
    setRows((current) => current.filter((row) => row.id !== rowId));
  }
  function addItem() {
    const existing = Object.fromEntries(rows.map((row) => [row.key, true]));
    const key = uniqueObjectKey("new_field", existing);
    setRows([...rows, { id: `row-${Date.now()}-${rows.length}`, key, config: { alias: "New field", type: "str" } }]);
  }
  const normalizedKeys = rows.map((row) => slugKey(row.key));
  const hasInvalidKeys = normalizedKeys.some((key) => !key) || new Set(normalizedKeys).size !== normalizedKeys.length;
  const preview = Object.fromEntries(rows.filter((row) => row.key).map((row) => [row.key, sampleValueForType(row.config.type)]));
  return (
    <div className="row-schema-backdrop" role="presentation">
      <aside className="row-schema-drawer" role="dialog" aria-modal="true" aria-labelledby="row-schema-title">
        <header className="row-schema-header">
          <div>
            <h3 id="row-schema-title" className="text-base font-semibold">Row schema — <span className="font-mono">{fieldKey}</span></h3>
            <p className="mt-1 text-xs text-base-content/55">Define the flat columns for each object in the list.</p>
          </div>
          <button className="btn btn-ghost btn-circle btn-sm" type="button" aria-label="Close row schema" onClick={onClose}><X size={17} /></button>
        </header>
        <div className="row-schema-body">
          <div className="row-schema-notice"><Info size={16} /><span>Each row is a flat object. Nested objects or lists are not supported.</span></div>
          <div className="row-schema-table">
            <div className="row-schema-columns" aria-hidden="true"><span>Field key</span><span>Type</span><span>Required</span><span>Actions</span></div>
            {rows.map((row) => (
              <RowSchemaField key={row.id} row={row} updateRow={updateRow} updateItem={updateItem} removeItem={removeItem} />
            ))}
            {!rows.length ? <div className="empty-panel m-3">No row fields yet. Add the first field to define the object.</div> : null}
          </div>
          {hasInvalidKeys ? <div className="mt-2 text-xs text-error">Row field keys must be unique and cannot be empty.</div> : null}
          <button className="btn btn-outline btn-sm mt-3" type="button" onClick={addItem}>
            <Plus size={14} /> Add row field
          </button>
          <div className="mt-8">
            <div className="text-sm font-semibold">Row preview (example)</div>
            <div className="mt-1 text-xs text-base-content/55">One sample object from the list</div>
            <pre className="row-schema-preview">{JSON.stringify(preview, null, 2)}</pre>
          </div>
        </div>
        <footer className="row-schema-footer">
          <button className="btn btn-ghost btn-sm" type="button" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary btn-sm" type="button" disabled={hasInvalidKeys} onClick={() => onSave(rowSchemaItemFields(rows))}>Done</button>
        </footer>
      </aside>
    </div>
  );
}

function RowSchemaField({ row, updateRow, updateItem, removeItem }) {
  const itemKey = row.key;
  const itemConfig = isPlainObject(row.config) ? row.config : {};
  const required = !isOptionalType(itemConfig.type);
  const baseType = ROW_FIELD_TYPE_VALUES.includes(unwrapOptionalType(itemConfig.type)) ? unwrapOptionalType(itemConfig.type) : "str";
  return (
    <div className="row-schema-field">
      <input className="input input-bordered input-sm min-w-0 font-mono" aria-label={`Field key ${itemKey || "empty"}`} value={itemKey} onChange={(event) => {
        const nextKey = slugKey(event.target.value);
        updateRow(row.id, { key: nextKey, config: { ...itemConfig, alias: rowFieldAlias(nextKey) } });
      }} />
      <select className="select select-bordered select-sm min-w-0" aria-label={`Type for ${itemKey || "empty"}`} value={baseType} onChange={(event) => updateItem(row.id, { type: withRequiredState(event.target.value, required) })}>
        {ROW_FIELD_TYPE_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
      </select>
      <label className="row-required-toggle">
        <input type="checkbox" className="checkbox checkbox-primary checkbox-sm" aria-label={`Required ${itemKey || "empty"}`} checked={required} onChange={(event) => updateItem(row.id, { type: withRequiredState(baseType, event.target.checked) })} />
        <span className="sr-only">Required</span>
      </label>
      <button className="btn btn-ghost btn-square btn-sm text-error" type="button" aria-label={`Remove ${itemKey || "empty"}`} onClick={() => removeItem(row.id)}><Trash2 size={15} /></button>
      <input className="input input-bordered input-sm col-span-full min-w-0" aria-label={`Extraction guidance for ${itemKey || "empty"}`} placeholder="Extraction guidance (optional)" value={itemConfig.description || ""} onChange={(event) => updateItem(row.id, { description: event.target.value || undefined })} />
    </div>
  );
}

function rowSchemaRows(itemFields) {
  return Object.entries(isPlainObject(itemFields) ? itemFields : {}).map(([key, value], index) => ({
    id: `row-${index}-${key}`,
    key,
    config: isPlainObject(value) ? { ...value } : { alias: key, type: "str" },
  }));
}

function rowSchemaItemFields(rows) {
  return Object.fromEntries(rows.map((row) => [slugKey(row.key), row.config]));
}

function rowFieldAlias(key) {
  const words = String(key || "").split("_").filter(Boolean).join(" ");
  return words ? `${words.charAt(0).toUpperCase()}${words.slice(1)}` : "New field";
}

function sampleValueForType(type) {
  const baseType = unwrapOptionalType(type);
  if (baseType === "int") return 12;
  if (baseType === "float") return 1234.56;
  if (baseType === "bool") return true;
  return "INV-1001";
}

function ObjectJsonControl({ label, hint, value, onChange }) {
  const [text, setText] = useState(() => JSON.stringify(value || {}, null, 2));
  const [error, setError] = useState("");
  useEffect(() => setText(JSON.stringify(value || {}, null, 2)), [value]);
  function apply() {
    try {
      const parsed = JSON.parse(text);
      if (!isPlainObject(parsed)) throw new Error("Value must be an object.");
      onChange(parsed);
      setError("");
    } catch (parseError) {
      setError(parseError.message || "Invalid JSON object.");
    }
  }
  return (
    <div>
      <TextAreaControl label={label} value={text} onChange={setText} mono />
      {hint ? <div className="mt-1 text-xs text-base-content/55">{hint}</div> : null}
      {error ? <div className="mt-1 text-xs text-error">{error}</div> : null}
      <button className="btn btn-outline btn-xs mt-2" type="button" onClick={apply}>Apply field override</button>
    </div>
  );
}

function StorageControls({ step, index, updateParams, availableTokens, findings, pipelineFields }) {
  const isPdf = step.class === "StoreFileToLocaldrive";
  const isCsv = step.class === "StoreMetadataAsCsv";
  const dirParam = isPdf ? "files_dir" : "data_dir";
  const nestedStorage = isCsv && isPlainObject(step.params.storage) ? step.params.storage : null;
  const effectiveDir = nestedStorage?.data_dir ?? step.params[dirParam] ?? "";
  const effectiveFilename = nestedStorage?.filename ?? step.params.filename ?? "";
  const overrideFields = isCsv && isPlainObject(step.params.extraction?.fields) ? step.params.extraction.fields : null;
  function updateStorageValue(key, value) {
    if (nestedStorage) updateParams(index, { storage: { ...nestedStorage, [key]: value } });
    else updateParams(index, { [key]: value });
  }
  function setNestedStorage(enabled) {
    if (enabled) updateParams(index, { storage: { data_dir: effectiveDir, filename: effectiveFilename }, data_dir: undefined, filename: undefined });
    else updateParams(index, { data_dir: effectiveDir, filename: effectiveFilename, storage: undefined });
  }
  function setExtractionOverride(enabled) {
    updateParams(index, { extraction: enabled ? { fields: clone(pipelineFields) } : undefined });
  }
  return (
    <div className="space-y-3">
      {isCsv ? <BooleanSetting checked={Boolean(nestedStorage)} label="Use nested storage overrides" hint="Compatibility format: storage.data_dir and storage.filename." onChange={setNestedStorage} /> : null}
      <DirectoryControl label={isPdf ? "PDF output directory" : "Data output directory"} value={effectiveDir} onChange={(value) => updateStorageValue(dirParam, value)} />
      <InlineFindings findings={findings} path={`tasks.${step.key}.params.${dirParam}`} />
      <FilenameBuilder value={effectiveFilename} onChange={(value) => updateStorageValue("filename", value)} tokens={availableTokens} />
      <InlineFindings findings={findings} path={`tasks.${step.key}.params.filename`} />
      {isCsv ? (
        <details className="rounded-lg border border-base-300 bg-base-100">
          <summary className="cursor-pointer px-3 py-3 text-sm font-semibold">CSV extraction-field override</summary>
          <div className="space-y-3 border-t border-base-300 p-3">
            <BooleanSetting checked={Boolean(overrideFields)} label="Use task-specific field definitions" hint="Normally the CSV task reuses fields from Extract document data." onChange={setExtractionOverride} />
            {overrideFields ? <ObjectJsonControl label="Field definitions" hint="Advanced compatibility setting for this storage task only." value={overrideFields} onChange={(fields) => updateParams(index, { extraction: { fields } })} /> : null}
          </div>
        </details>
      ) : null}
    </div>
  );
}

function FilenameBuilder({ value, onChange, tokens }) {
  const [tokenSearch, setTokenSearch] = useState("");
  const filteredTokens = tokens.filter((token) => token.toLowerCase().includes(tokenSearch.trim().toLowerCase()));
  const preview = value || "No filename template yet";
  return (
    <div className="rounded-lg border border-base-300 bg-base-100 p-3">
      <TextControl label="Filename template" value={value} onChange={onChange} mono />
      <div className="mt-3 rounded-md bg-base-200 px-3 py-2">
        <div className="text-xs font-semibold uppercase tracking-wide text-base-content/60">Preview</div>
        <div className="mt-1 break-all font-mono text-xs">{preview}</div>
      </div>
      <label className="form-control mt-3">
        <span className="label-text mb-1 text-xs font-semibold">Insert a token</span>
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-2 text-base-content/40" size={14} />
          <input className="input input-bordered input-sm w-full pl-8" value={tokenSearch} onChange={(event) => setTokenSearch(event.target.value)} placeholder="Find a field or context token" />
        </div>
      </label>
      <div className="mt-2 flex flex-wrap gap-1">
        {filteredTokens.map((token) => (
          <button className="btn btn-outline btn-xs h-auto min-h-7 font-mono" key={token} onClick={() => onChange(`${value || ""}{${token}}`)} title={`Insert {${token}}`}>
            {`{${token}}`}
          </button>
        ))}
        {!filteredTokens.length ? <div className="text-xs text-base-content/55">No matching tokens.</div> : null}
      </div>
    </div>
  );
}

function RulesControls({ step, index, updateParams, steps, csvMetadata, setCsvMetadata, findings }) {
  const params = step.params || {};
  const csvInfo = csvMetadata[params.reference_file];
  const columns = csvInfo?.columns || [];
  const fieldOptions = [...Object.keys(extractionFields(steps)), ...CONTEXT_TOKENS];
  const clauses = Array.isArray(params.csv_match?.clauses) ? params.csv_match.clauses : [];

  useEffect(() => {
    if (!params.reference_file || csvMetadata[params.reference_file]) return;
    let cancelled = false;
    fetch(`/api/prototype/fs/csv?path=${encodeURIComponent(params.reference_file)}`)
      .then((response) => (response.ok ? response.json() : null))
      .then((metadata) => {
        if (!cancelled && metadata) {
          setCsvMetadata((current) => ({ ...current, [params.reference_file]: metadata }));
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [params.reference_file, csvMetadata, setCsvMetadata]);

  async function selectReference(filePath) {
    updateParams(index, { reference_file: filePath });
    const response = await fetch(`/api/prototype/fs/csv?path=${encodeURIComponent(filePath)}`);
    if (response.ok) {
      const metadata = await response.json();
      setCsvMetadata((current) => ({ ...current, [filePath]: metadata }));
    }
  }
  function updateClause(clauseIndex, patch) {
    const next = clauses.map((clause, currentIndex) => (currentIndex === clauseIndex ? { ...clause, ...patch } : clause));
    updateParams(index, { csv_match: { type: "column_equals_all", clauses: next } });
  }
  function addClause() {
    if (clauses.length >= 5) return;
    updateParams(index, { csv_match: { type: "column_equals_all", clauses: [...clauses, { column: "", from_context: "", number: false }] } });
  }
  function removeClause(clauseIndex) {
    updateParams(index, { csv_match: { type: "column_equals_all", clauses: clauses.filter((_, currentIndex) => currentIndex !== clauseIndex) } });
  }

  return (
    <div className="space-y-3">
      <FileControl label="Reference CSV" value={params.reference_file || ""} extensions=".csv" onChange={selectReference} startPath="reference_file" />
      <InlineFindings findings={findings} path={`tasks.${step.key}.params.reference_file`} />
      {columns.length ? <div className="text-xs text-base-content/60">{columns.length} CSV columns loaded.</div> : null}
      <SelectControl label="Update field" value={params.update_field || ""} onChange={(value) => updateParams(index, { update_field: value })} options={["", ...columns]} />
      <InlineFindings findings={findings} path={`tasks.${step.key}.params.update_field`} />
      <TextControl label="Write value" value={params.write_value || ""} onChange={(value) => updateParams(index, { write_value: value })} />
      <TextControl label="Task status key (optional)" hint="Overrides the task slug written to status metadata." value={params.task_slug || ""} onChange={(value) => updateParams(index, { task_slug: value || undefined })} mono />
      <div className="rounded-lg border border-primary/20 bg-primary/5 p-3" aria-live="polite">
        <div className="text-xs font-semibold uppercase tracking-wide text-primary">Rule outcome</div>
        <p className="mt-1 text-sm">
          If all {clauses.length || "configured"} {clauses.length === 1 ? "condition matches" : "conditions match"}, set <code className="font-semibold">{params.update_field || "the selected field"}</code> to <code className="font-semibold">{params.write_value || "the configured value"}</code>.
        </p>
      </div>
      <label className="flex items-center gap-3 rounded-lg border border-base-300 bg-base-100 px-3 py-2">
        <input type="checkbox" className="toggle toggle-sm" checked={Boolean(params.backup)} onChange={(event) => updateParams(index, { backup: event.target.checked })} />
        <span className="text-sm">Backup reference CSV before write</span>
      </label>
      <div className="rounded-lg border border-base-300 bg-base-100 p-3">
        <div className="mb-2 flex items-center justify-between">
          <div>
            <div className="text-sm font-semibold">Match conditions</div>
            <div className="text-xs text-base-content/55">Every condition must match (AND).</div>
          </div>
          <button className="btn btn-outline btn-xs" disabled={clauses.length >= 5} onClick={addClause}>
            <Plus size={13} /> Add clause
          </button>
        </div>
        <div className="space-y-2">
          {clauses.map((clause, clauseIndex) => (
            <div className="rounded-md border border-base-300 p-2" key={clauseIndex}>
              <div className="mb-2 text-xs font-semibold text-base-content/60">Condition {clauseIndex + 1}</div>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-[1fr_1fr_auto]">
                <SelectControl label="CSV column" value={clause.column || ""} onChange={(value) => updateClause(clauseIndex, { column: value })} options={["", ...columns]} />
                <SelectControl label="From context" value={clause.from_context || ""} onChange={(value) => updateClause(clauseIndex, { from_context: value })} options={["", ...fieldOptions]} />
                <button className="btn btn-ghost btn-square btn-sm self-end text-error" aria-label={`Remove condition ${clauseIndex + 1}`} title={clauses.length <= 1 ? "At least one condition is required" : `Remove condition ${clauseIndex + 1}`} disabled={clauses.length <= 1} onClick={() => removeClause(clauseIndex)}>
                  <Trash2 size={14} />
                </button>
              </div>
              <div className="mt-2 max-w-xs">
                <SelectControl label="Comparison type" value={clause.number === true ? "number" : clause.number === false ? "text" : "auto"} onChange={(value) => updateClause(clauseIndex, { number: value === "auto" ? undefined : value === "number" })} options={[
                  { value: "auto", label: "Auto-detect" },
                  { value: "text", label: "Text comparison" },
                  { value: "number", label: "Numeric comparison" },
                ]} />
              </div>
              <InlineFindings findings={findings} pathPrefix={`tasks.${step.key}.params.csv_match.clauses[${clauseIndex}]`} />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function ThresholdMapEditor({ label, hint, value, onChange, keyOptions = [] }) {
  const entries = Object.entries(isPlainObject(value) ? value : {});
  function updateEntry(entryIndex, nextKey, nextThreshold) {
    const nextEntries = entries.map(([key, threshold], index) => index === entryIndex ? [nextKey, nextThreshold] : [key, threshold]);
    onChange(Object.fromEntries(nextEntries.filter(([key]) => key.trim())));
  }
  function removeEntry(entryIndex) {
    onChange(Object.fromEntries(entries.filter((_, index) => index !== entryIndex)));
  }
  function addEntry() {
    const base = keyOptions.find((option) => !Object.prototype.hasOwnProperty.call(value || {}, option)) || "new_key";
    let key = base;
    let suffix = 2;
    while (Object.prototype.hasOwnProperty.call(value || {}, key)) {
      key = `${base}_${suffix}`;
      suffix += 1;
    }
    onChange({ ...(isPlainObject(value) ? value : {}), [key]: 0.8 });
  }
  return (
    <div className="rounded-lg border border-base-300 bg-base-100 p-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-sm font-semibold">{label}</div>
          <p className="mt-1 text-xs text-base-content/55">{hint}</p>
        </div>
        <button className="btn btn-outline btn-xs" type="button" onClick={addEntry}><Plus size={13} /> Add</button>
      </div>
      <div className="mt-3 space-y-2">
        {entries.map(([key, threshold], entryIndex) => (
          <div className="grid grid-cols-[minmax(0,1fr)_7rem_auto] gap-2" key={entryIndex}>
            {keyOptions.length ? (
              <SelectControl label="Field" value={key} onChange={(nextKey) => updateEntry(entryIndex, nextKey, threshold)} options={[...new Set([key, ...keyOptions])]} />
            ) : (
              <TextControl label="Document type" value={key} onChange={(nextKey) => updateEntry(entryIndex, nextKey, threshold)} mono />
            )}
            <NumberControl label="Threshold" value={threshold} min={0} max={1} step={0.01} onChange={(nextThreshold) => updateEntry(entryIndex, key, nextThreshold)} />
            <button className="btn btn-ghost btn-square btn-sm self-end text-error" type="button" title={`Remove ${key}`} onClick={() => removeEntry(entryIndex)}><Trash2 size={14} /></button>
          </div>
        ))}
        {!entries.length ? <div className="empty-panel py-3">No overrides. The default threshold applies.</div> : null}
      </div>
    </div>
  );
}

function BooleanSetting({ checked, label, hint, onChange }) {
  return (
    <label className="flex items-start gap-3 rounded-lg border border-base-300 bg-base-100 px-3 py-3">
      <input type="checkbox" className="toggle toggle-sm" checked={checked} onChange={(event) => onChange(event.target.checked)} />
      <span>
        <span className="block text-sm font-medium">{label}</span>
        {hint ? <span className="mt-1 block text-xs text-base-content/55">{hint}</span> : null}
      </span>
    </label>
  );
}

function ReviewControls({ step, index, updateParams, findings, steps }) {
  const params = step.params || {};
  const levels = Array.isArray(params.split_confidence_levels_requiring_review) ? params.split_confidence_levels_requiring_review : [];
  const fieldKeys = Object.keys(extractionFields(steps));
  function toggleSplitLevel(level) {
    updateParams(index, { split_confidence_levels_requiring_review: levels.includes(level) ? levels.filter((item) => item !== level) : [...levels, level] });
  }
  return (
    <div className="space-y-3">
      <div className="rounded-lg border border-info/20 bg-info/10 p-3 text-sm">
        Threshold priority is field override, then document type, then the default threshold.
      </div>
      <ConfidenceControl value={params.confidence_threshold ?? 0.8} onChange={(value) => updateParams(index, { confidence_threshold: value })} />
      <ThresholdMapEditor label="Field threshold overrides" hint="Set a stricter or more permissive score for individual extraction fields." value={params.field_threshold_overrides} keyOptions={fieldKeys} onChange={(value) => updateParams(index, { field_threshold_overrides: value })} />
      <ThresholdMapEditor label="Document-type thresholds" hint="Applied when a field has no field-specific override." value={params.per_document_type_thresholds} onChange={(value) => updateParams(index, { per_document_type_thresholds: value })} />
      <div className="rounded-lg border border-base-300 bg-base-100 p-3">
        <div className="text-sm font-semibold">Review split confidence levels</div>
        <p className="mt-1 text-xs text-base-content/55">Pause when the upstream split result reports a selected level.</p>
        <div className="mt-3 grid grid-cols-3 gap-2">
          {["high", "medium", "low"].map((level) => (
            <label className={`flex cursor-pointer items-center gap-2 rounded-md border px-2 py-2 text-sm ${levels.includes(level) ? "border-primary bg-primary/5" : "border-base-300"}`} key={level}>
              <input className="checkbox checkbox-sm" type="checkbox" checked={levels.includes(level)} onChange={() => toggleSplitLevel(level)} />
              <span className="capitalize">{level}</span>
            </label>
          ))}
        </div>
      </div>
      <FileControl label="Schema file (optional)" value={params.schema_file || ""} extensions=".yaml,.yml" onChange={(value) => updateParams(index, { schema_file: value || undefined })} startPath="schemas" />
      <InlineFindings findings={findings} path={`tasks.${step.key}.params.schema_file`} />
      <TextControl label="Queue" value={params.queue_name || "default_review"} onChange={(value) => updateParams(index, { queue_name: value })} />
      <SelectControl label="Review scope" hint="Choose which results are sent to a reviewer." value={params.review_scope || "low_confidence_fields"} onChange={(value) => updateParams(index, { review_scope: value })} options={[
        { value: "document", label: "Entire document" },
        { value: "low_confidence_fields", label: "Low-confidence fields only" },
        { value: "schema_errors", label: "Schema errors only" },
        { value: "split_result", label: "Document split result" },
      ]} />
      <SelectControl label="After review" hint="Production resumes at the next task after approval." value="next_task" onChange={() => {}} options={[{ value: "next_task", label: "Continue to next task" }]} />
      <BooleanSetting checked={params.require_review_when_missing_confidence ?? true} label="Review when confidence is missing" onChange={(value) => updateParams(index, { require_review_when_missing_confidence: value })} />
      <BooleanSetting checked={params.require_review_for_missing_required_fields ?? true} label="Review missing required fields" hint="Schema-required fields trigger review when absent." onChange={(value) => updateParams(index, { require_review_for_missing_required_fields: value })} />
      <BooleanSetting checked={params.always_review ?? false} label="Always require review" hint="Pause every document regardless of confidence and schema results." onChange={(value) => updateParams(index, { always_review: value })} />
      <BooleanSetting checked={params.allow_operator_to_edit_high_confidence_fields ?? true} label="Allow editing high-confidence fields" hint="Reviewers may correct fields that did not trigger the gate." onChange={(value) => updateParams(index, { allow_operator_to_edit_high_confidence_fields: value })} />
    </div>
  );
}

function ArchiveControls({ step, index, updateParams, findings }) {
  return (
    <div className="space-y-3">
      <div className="flex gap-2 rounded-lg border border-info/20 bg-info/10 p-3 text-sm">
        <Info className="mt-0.5 shrink-0 text-info" size={16} />
        <p>The original source PDF is copied here with a safe, unique filename. The source file remains in place.</p>
      </div>
      <DirectoryControl label="Archive directory" value={step.params.archive_dir || ""} onChange={(value) => updateParams(index, { archive_dir: value })} />
      <InlineFindings findings={findings} path={`tasks.${step.key}.params.archive_dir`} />
    </div>
  );
}

function ContextControls({ step, index, updateParams, findings }) {
  return (
    <>
      <NumberControl label="Nanoid length" value={step.params.length ?? 12} min={5} max={21} step={1} onChange={(value) => updateParams(index, { length: value })} />
      <InlineFindings findings={findings} path={`tasks.${step.key}.params.length`} />
    </>
  );
}

function HousekeepingControls({ step, index, updateParams, findings }) {
  return (
    <div className="space-y-3">
      <div className="flex gap-2 rounded-lg border border-warning/25 bg-warning/10 p-3 text-sm">
        <AlertTriangle className="mt-0.5 shrink-0 text-warning" size={16} />
        <p>This task removes the processed working file after downstream work is complete.</p>
      </div>
      <DirectoryControl label="Processing directory" value={step.params.processing_dir || "processing"} onChange={(value) => updateParams(index, { processing_dir: value })} startPath="processing" />
      <InlineFindings findings={findings} path={`tasks.${step.key}.params.processing_dir`} />
    </div>
  );
}

function DirectoryControl({ label, value, onChange, startPath = ".", hint }) {
  return <PathBrowser label={label} value={value} onChange={onChange} mode="directory" hint={hint} startPath={isAbsoluteLikePath(value) ? startPath : value || startPath} />;
}

function FileControl({ label, value, onChange, extensions, startPath = "." }) {
  return <PathBrowser label={label} value={value} onChange={onChange} mode="file" extensions={extensions} startPath={value ? value.split("/").slice(0, -1).join("/") || "." : startPath} />;
}

function isAbsoluteLikePath(value) {
  return /^[A-Za-z]:[\\/]/.test(String(value || "")) || String(value || "").startsWith("\\\\") || String(value || "").startsWith("/");
}

function PathBrowser({ label, value, onChange, mode, extensions = "", startPath, hint }) {
  const [open, setOpen] = useState(false);
  const [current, setCurrent] = useState(startPath || ".");
  const [listing, setListing] = useState(null);
  const [newDir, setNewDir] = useState("");
  const [errorText, setErrorText] = useState("");
  const [pickerStatus, setPickerStatus] = useState("");
  const pathType = value ? (isAbsoluteLikePath(value) ? "Absolute path" : "Project-relative") : "No path selected";

  useEffect(() => {
    if (!open) return;
    const endpoint = mode === "directory"
      ? `/api/prototype/fs/directories?path=${encodeURIComponent(current || ".")}`
      : `/api/prototype/fs/files?path=${encodeURIComponent(current || ".")}&extensions=${encodeURIComponent(extensions)}`;
    fetch(endpoint)
      .then((response) => {
        if (!response.ok) throw new Error("Unable to browse project path.");
        return response.json();
      })
      .then((payload) => {
        setListing(payload);
        setErrorText("");
      })
      .catch((error) => setErrorText(error.message || "Unable to browse project path."));
  }, [open, current, mode, extensions]);

  async function createDirectory() {
    if (!newDir.trim()) return;
    const path = `${current === "." ? "" : `${current}/`}${slugKey(newDir.trim()) || newDir.trim()}`;
    const response = await fetch("/api/prototype/fs/directories", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
    });
    if (response.ok) {
      const payload = await response.json();
      onChange(payload.path);
      setCurrent(payload.path);
      setNewDir("");
    }
  }

  async function chooseNativeDirectory() {
    setPickerStatus("Opening Windows folder picker...");
    setErrorText("");
    try {
      const response = await fetch("/api/prototype/fs/pick-directory", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: value || startPath || "." }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "Unable to open Windows folder picker.");
      if (payload.cancelled) {
        setPickerStatus("Folder selection cancelled.");
        return;
      }
      onChange(payload.path);
      setPickerStatus(payload.pathType === "absolute" ? "Selected absolute Windows path." : "Selected project-relative path.");
      if (payload.pathType === "project-relative") setCurrent(payload.path);
    } catch (error) {
      setPickerStatus("");
      setErrorText(error.message || "Unable to open Windows folder picker.");
    }
  }

  return (
    <div className="rounded-lg border border-base-300 bg-base-100 p-3">
      <label className="form-control">
        <span className="mb-1 flex items-center justify-between gap-2">
          <span className="label-text text-xs">{label}</span>
          <span className="badge badge-ghost badge-xs shrink-0">{pathType}</span>
        </span>
        <div className="flex flex-col gap-2 sm:flex-row">
          <input className="input input-bordered input-sm font-mono" value={value ?? ""} onChange={(event) => onChange(event.target.value)} />
          {mode === "directory" ? (
            <button className="btn btn-primary btn-sm shrink-0" onClick={chooseNativeDirectory}>
              <FolderOpen size={14} /> Choose folder
            </button>
          ) : null}
        </div>
      </label>
      {hint ? <div className="mt-2 text-xs text-base-content/55">{hint}</div> : null}
      {pickerStatus ? <div className="mt-2 text-xs text-base-content/55">{pickerStatus}</div> : null}
      <details className="mt-2" open={open} onToggle={(event) => setOpen(event.currentTarget.open)}>
        <summary className="cursor-pointer text-sm font-semibold text-primary">
          <FolderOpen className="mr-1 inline" size={14} /> {mode === "directory" ? "Browse project folders instead" : "Browse project files"}
        </summary>
        <div className="mt-2 rounded-md border border-base-300 bg-base-200/50 p-2">
          {errorText ? <div className="alert alert-error py-2 text-xs">{errorText}</div> : null}
          <div className="mb-2 flex flex-wrap items-center gap-2 text-xs">
            <span className="font-mono">{listing?.current || current}</span>
            {listing?.current && listing.current !== "." ? (
              <button className="btn btn-ghost btn-xs" onClick={() => setCurrent(listing.parent || ".")}>Up</button>
            ) : null}
            {mode === "directory" ? <button className="btn btn-outline btn-xs" onClick={() => onChange(listing?.current || current)}>Use current</button> : null}
          </div>
          <div className="max-h-48 space-y-1 overflow-auto">
            {(listing?.entries || listing?.directories || []).map((entry) => (
              <button className="path-row" key={entry.path} onClick={() => setCurrent(entry.path)}>
                <FolderOpen size={14} /> {entry.name}
              </button>
            ))}
            {mode === "file" ? (listing?.files || []).map((file) => (
              <button className="path-row" key={file.path} onClick={() => onChange(file.path)}>
                <FileText size={14} /> {file.name}
              </button>
            )) : null}
          </div>
          {mode === "directory" ? (
            <div className="mt-2 flex gap-2">
              <input className="input input-bordered input-xs" value={newDir} onChange={(event) => setNewDir(event.target.value)} placeholder="New folder" />
              <button className="btn btn-outline btn-xs" onClick={createDirectory}>Create</button>
            </div>
          ) : null}
        </div>
      </details>
    </div>
  );
}

function AdvancedParamsEditor({ step, index, replaceParams }) {
  const [text, setText] = useState(JSON.stringify(step.params || {}, null, 2));
  const [errorText, setErrorText] = useState("");
  useEffect(() => {
    setText(JSON.stringify(step.params || {}, null, 2));
    setErrorText("");
  }, [step.key, step.params]);
  function applyJson() {
    try {
      const parsed = JSON.parse(text || "{}");
      if (!isPlainObject(parsed)) throw new Error("Params JSON must be an object.");
      replaceParams(index, parsed);
      setErrorText("");
    } catch (error) {
      setErrorText(error.message || "Invalid JSON.");
    }
  }
  return (
    <details className="rounded-lg border border-base-300 bg-base-100">
      <summary className="cursor-pointer px-3 py-2 text-sm font-semibold">Advanced params JSON</summary>
      <div className="space-y-2 border-t border-base-300 p-3">
        <textarea className="textarea textarea-bordered min-h-56 w-full font-mono text-xs" value={text} onChange={(event) => setText(event.target.value)} />
        {errorText ? <div className="alert alert-error py-2 text-xs">{errorText}</div> : null}
        <button className="btn btn-outline btn-sm" onClick={applyJson}>Apply JSON params</button>
      </div>
    </details>
  );
}

function InlineFindings({ findings, path, pathPrefix }) {
  const matches = findings.filter((item) => item.severity === "error" && (path ? item.path === path : item.path.startsWith(pathPrefix)));
  if (!matches.length) return null;
  return (
    <div className="mt-2 space-y-1">
      {matches.map((item) => (
        <div className="rounded-md border border-error/30 bg-error/10 px-2 py-1 text-xs text-error" key={`${item.code}-${item.path}`}>
          {item.message}
        </div>
      ))}
    </div>
  );
}

function TaskIssuesPanel({ findings, step }) {
  if (!findings.length) {
    return (
      <div className="task-issues-empty">
        <span className="task-issues-icon"><CheckCircle2 size={20} /></span>
        <div>
          <div className="font-semibold">No issues in this task</div>
          <p className="mt-1 text-xs text-base-content/55">{step.label} passes its task-specific checks. Validate the pipeline for whole-file readiness.</p>
        </div>
      </div>
    );
  }
  return <ValidationPanel findings={findings} />;
}

function PipelineValidationPanel({ findings }) {
  const errors = findings.filter((item) => item.severity === "error");
  if (errors.length) return <ValidationPanel findings={findings} />;
  return (
    <div className="pipeline-empty-state">
      <span className="pipeline-empty-icon"><CheckCircle2 size={27} /></span>
      <div className="mt-4 text-lg font-semibold">Pipeline ready to publish</div>
      <p className="mt-2 max-w-md text-sm text-base-content/55">All tasks and whole-file checks passed. The current draft can be written to the prototype YAML file.</p>
    </div>
  );
}

function ValidationPanel({ findings }) {
  return (
    <div className="space-y-3">
      {findings.map((item) => (
        <div key={`${item.code}-${item.message}-${item.path}`} className={`alert text-sm ${item.severity === "error" ? "alert-error" : item.severity === "warning" ? "alert-warning" : "alert-success"}`}>
          {item.severity === "error" ? <AlertTriangle size={17} /> : <CheckCircle2 size={17} />}
          <div>
            <div className="font-semibold">{item.code}</div>
            <div className="text-xs">{item.path}: {item.message}</div>
          </div>
        </div>
      ))}
    </div>
  );
}

function YamlPanel({ draftYaml, currentYaml }) {
  return (
    <div className="space-y-4">
      <div>
        <div className="mb-2 flex items-center justify-between">
          <span className="text-sm font-semibold">Draft YAML</span>
          <span className="badge badge-sm">will publish</span>
        </div>
        <pre className="yaml-box">{draftYaml}</pre>
      </div>
      <details className="rounded-lg border border-base-300 bg-base-100">
        <summary className="cursor-pointer px-3 py-2 text-sm font-semibold">Current file YAML</summary>
        <pre className="yaml-box max-h-80 rounded-t-none">{currentYaml}</pre>
      </details>
    </div>
  );
}

function DiffPanel({ diffText, hasChanges = true }) {
  if (!hasChanges) {
    return (
      <div className="pipeline-empty-state">
        <span className="pipeline-empty-icon"><CheckCircle2 size={27} /></span>
        <div className="mt-4 text-lg font-semibold">No changes to review</div>
        <p className="mt-2 max-w-md text-sm text-base-content/55">The pipeline draft matches the published YAML file.</p>
      </div>
    );
  }
  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <span className="text-sm font-semibold">Current file vs draft</span>
        <span className="badge badge-sm">line diff</span>
      </div>
      <pre className="yaml-box diff-box">{diffText || "No differences"}</pre>
    </div>
  );
}

function RunSimulation({ steps, close }) {
  const enabled = steps.filter((step) => step.enabled !== false);
  return (
    <div className="rounded-lg border border-base-300 bg-base-100 p-3 shadow-sm">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold">Run simulation</h3>
          <p className="text-xs text-base-content/55">Source PDF follows the enabled YAML pipeline order.</p>
        </div>
        <button className="btn btn-ghost btn-square btn-sm" onClick={close}><X size={15} /></button>
      </div>
      <div className="grid gap-2 md:grid-cols-3">
        {enabled.map((step, index) => (
          <div className="rounded-lg border border-base-300 bg-base-200 p-3" key={`${step.key}-${index}`}>
            <div className="mb-2 flex items-center justify-between">
              <span className="font-semibold">{index + 1}. {step.label}</span>
              <span className={`badge badge-sm ${kindBadgeClass(taskKind(step))}`}>{taskKind(step)}</span>
            </div>
            <div className="truncate font-mono text-xs text-base-content/60">{step.key}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function TextControl({ label, value, onChange, mono, hint }) {
  return (
    <label className="form-control">
      <span className="label-text mb-1 text-xs">{label}</span>
      <input className={`input input-bordered input-sm ${mono ? "font-mono" : ""}`} value={value ?? ""} onChange={(event) => onChange(event.target.value)} />
      {hint ? <span className="mt-1 block text-xs text-base-content/55">{hint}</span> : null}
    </label>
  );
}

function SecretControl({ label, value, onChange }) {
  const [visible, setVisible] = useState(false);
  return (
    <div className="form-control min-w-0">
      <span className="label-text mb-1 text-xs">{label}</span>
      <div className="relative min-w-0">
        <input className="input input-bordered input-sm w-full min-w-0 pr-10 font-mono" aria-label={label} type={visible ? "text" : "password"} autoComplete="off" value={value ?? ""} onChange={(event) => onChange(event.target.value)} />
        <button className="btn btn-ghost btn-xs btn-circle absolute right-1 top-1" type="button" aria-label={visible ? `Hide ${label}` : `Show ${label}`} onClick={() => setVisible((current) => !current)}>
          {visible ? <EyeOff size={15} /> : <Eye size={15} />}
        </button>
      </div>
      <span className="mt-1 block text-xs text-base-content/55">Hidden by default to prevent accidental exposure.</span>
    </div>
  );
}

function TextAreaControl({ label, value, onChange, mono }) {
  return (
    <label className="form-control block">
      <span className="label-text mb-1 text-xs">{label}</span>
      <textarea className={`textarea textarea-bordered min-h-24 text-sm ${mono ? "font-mono" : ""}`} value={value ?? ""} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

function SelectControl({ label, value, onChange, options, disabled, hint }) {
  return (
    <label className="form-control block">
      <span className="label-text mb-1 text-xs">{label}</span>
      <select className="select select-bordered select-sm" value={value ?? ""} disabled={disabled} onChange={(event) => onChange(event.target.value)}>
        {options.map((option) => {
          const optionValue = typeof option === "string" ? option : option.value;
          const optionLabel = typeof option === "string" ? option || "Select..." : option.label;
          return <option key={optionValue} value={optionValue} disabled={typeof option === "object" && option.disabled}>{optionLabel}</option>;
        })}
      </select>
      {hint ? <span className="mt-1 block text-xs text-base-content/55">{hint}</span> : null}
    </label>
  );
}

function FieldTypeControl({ value, onChange, disableTableOption = false }) {
  const currentType = value || "str";
  const required = !isOptionalType(currentType);
  const baseType = unwrapOptionalType(currentType);
  const options = FIELD_TYPE_OPTIONS.map((option) => ({ ...option, disabled: option.value === TABLE_FIELD_TYPE && disableTableOption }));
  return (
    <div className="field-type-control">
      <SelectControl
        label="Type"
        value={baseType}
        onChange={(nextType) => onChange(withRequiredState(nextType, required))}
        options={options}
        hint={baseType === TABLE_FIELD_TYPE ? `Python type: ${withRequiredState(baseType, required)} · flat row objects` : `Python type: ${withRequiredState(baseType, required)}`}
      />
      <label className="field-required-control">
        <input
          type="checkbox"
          className="checkbox checkbox-sm"
          checked={required}
          onChange={(event) => onChange(withRequiredState(baseType, event.target.checked))}
        />
        <span>
          <span className="block text-xs font-medium">Required field</span>
          <span className="block text-xs text-base-content/55">{required ? "Must be returned" : "May be omitted"}</span>
        </span>
      </label>
    </div>
  );
}

function ConfidenceControl({ value, onChange }) {
  const percent = Math.round(Number(value) * 100);
  function updatePercent(nextPercent) {
    onChange(Math.min(100, Math.max(0, Number(nextPercent))) / 100);
  }
  return (
    <fieldset className="rounded-lg border border-base-300 bg-base-100 p-3">
      <div className="flex items-center justify-between gap-3">
        <legend className="text-xs">Confidence threshold</legend>
        <label className="flex items-center gap-1 text-sm font-semibold">
          <input className="input input-bordered input-xs w-20 text-right" type="number" min="0" max="100" step="1" value={percent} aria-label="Confidence threshold percentage" onChange={(event) => updatePercent(event.target.value)} />
          <span>%</span>
        </label>
      </div>
      <input className="range range-primary range-sm mt-3" type="range" min="0" max="100" step="1" value={percent} aria-label="Confidence threshold slider" onChange={(event) => updatePercent(event.target.value)} />
      <p className="mt-2 text-xs text-base-content/55">Send results below {percent}% confidence for review.</p>
    </fieldset>
  );
}

function NumberControl({ label, value, onChange, ...props }) {
  return (
    <label className="form-control">
      <span className="label-text mb-1 text-xs">{label}</span>
      <input className="input input-bordered input-sm" type="number" value={value} onChange={(event) => onChange(Number(event.target.value))} {...props} />
    </label>
  );
}

const rootElement = document.getElementById("root");
const appRoot = window.__pipelinePrototypeRoot || createRoot(rootElement);
window.__pipelinePrototypeRoot = appRoot;
appRoot.render(<App />);
