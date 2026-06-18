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

const FIELD_TYPES = [
  "str",
  "int",
  "float",
  "bool",
  "Decimal",
  "Any",
  "Optional[str]",
  "Optional[int]",
  "Optional[float]",
  "Optional[bool]",
  "Optional[List[str]]",
  "Optional[List[float]]",
  "List[Any]",
  "List[str]",
  "List[float]",
  "Dict[str, Any]",
];

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
      allow_uncategorized: "forbid",
      split_dir: "processing/split",
      fail_on_confidence_levels: ["low"],
      fail_on_unknown_category: true,
      categories: [{ name: "invoice", description: "A single invoice document." }],
    },
  },
  {
    key: "extract_document_data",
    label: "Extract document data",
    category: "Extraction",
    icon: Wand2,
    module: "standard_step.extraction.extract_pdf_v2",
    class: "ExtractPdfV2Task",
    on_error: "stop",
    params: {
      api_key: "",
      configuration_id: "",
      tier: "agentic",
      extraction_target: "per_doc",
      confidence_scores: true,
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
    module: "standard_step.storage.store_metadata_as_csv_v2",
    class: "StoreMetadataAsCsvV2",
    on_error: "continue",
    params: { data_dir: "data", filename: "{id}" },
  },
  {
    key: "store_metadata_json",
    label: "Store JSON metadata",
    category: "Storage",
    icon: FileJson,
    module: "standard_step.storage.store_metadata_as_json_v2",
    class: "StoreMetadataAsJsonV2",
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
      require_review_when_missing_confidence: true,
      require_review_for_missing_required_fields: true,
      schema_file: "schemas/invoice.yaml",
      queue_name: "default_review",
      review_scope: "low_confidence_fields",
      resume_policy: "next_task",
    },
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
  if (step?.class === "ExtractPdfV2Task" || moduleName.includes(".extraction.")) return "extract";
  if (step?.class === "ReviewGateTask" || moduleName.includes(".review.")) return "review";
  if (moduleName.includes(".storage.")) return "storage";
  if (moduleName.includes(".archiver.")) return "archive";
  if (moduleName.includes(".rules.")) return "rules";
  if (moduleName.includes(".context.")) return "context";
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
    if (kind === "split") validateSplit(step, findings);
    if (kind === "archive" && !params.archive_dir) {
      findings.push(finding("error", "archive-dir-empty", `tasks.${step.key}.params.archive_dir`, `${step.label} needs an archive directory.`));
    }
    if (kind === "review") {
      if (!params.schema_file) findings.push(finding("error", "review-schema-empty", `tasks.${step.key}.params.schema_file`, "Review gate needs a schema file."));
      if (Number(params.confidence_threshold) < 0 || Number(params.confidence_threshold) > 1) {
        findings.push(finding("error", "review-threshold-range", `tasks.${step.key}.params.confidence_threshold`, "Confidence threshold must be between 0 and 1."));
      }
    }
  });

  if (!findings.some((item) => item.severity === "error")) {
    findings.push(finding("success", "ready-to-publish", "config", "Draft can be written to the prototype YAML file."));
  }
  return findings;
}

function validateExtract(step, findings) {
  const fields = isPlainObject(step.params.fields) ? step.params.fields : {};
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
    if (!FIELD_TYPES.includes(field.type)) findings.push(finding("error", "extract-field-type-invalid", `${path}.type`, `Field '${fieldKey}' must use a supported type.`));
    if (field.is_table) {
      if (field.type !== "List[Any]") findings.push(finding("error", "extract-table-type", `${path}.type`, "Table fields must use List[Any]."));
      if (!isPlainObject(field.item_fields) || !Object.keys(field.item_fields).length) {
        findings.push(finding("error", "extract-table-items-empty", `${path}.item_fields`, `Table field '${fieldKey}' needs item fields.`));
      }
    }
  });
}

function validateStorage(step, scalarTokenSet, findings) {
  const params = step.params || {};
  const dirParam = step.class === "StoreFileToLocaldrive" ? "files_dir" : "data_dir";
  if (!params[dirParam]) findings.push(finding("error", "storage-dir-empty", `tasks.${step.key}.params.${dirParam}`, `${step.label} needs an output directory.`));
  if (!params.filename) {
    findings.push(finding("error", "storage-filename-empty", `tasks.${step.key}.params.filename`, `${step.label} needs a filename template.`));
  }
  extractTemplateTokens(params.filename).forEach((token) => {
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
  });
}

function validateContext(step, findings) {
  const length = step.params.length;
  if (!Number.isInteger(length) || length < 5 || length > 21) {
    findings.push(finding("error", "context-length-range", `tasks.${step.key}.params.length`, "Nanoid length must be an integer from 5 to 21."));
  }
}

function validateSplit(step, findings) {
  const params = step.params || {};
  if (!params.split_dir) findings.push(finding("error", "split-dir-empty", `tasks.${step.key}.params.split_dir`, "Split task needs an output directory."));
  const levels = params.fail_on_confidence_levels;
  if (levels !== undefined) {
    const allowed = new Set(["high", "medium", "low"]);
    if (!Array.isArray(levels) || levels.some((level) => !allowed.has(level))) {
      findings.push(finding("error", "split-confidence-level-invalid", `tasks.${step.key}.params.fail_on_confidence_levels`, "Split confidence levels must be high, medium, or low."));
    }
  }
}

function App() {
  const [baseConfig, setBaseConfig] = useState(null);
  const [steps, setSteps] = useState([]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [activeTab, setActiveTab] = useState("properties");
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
              <h1 className="mt-1 text-xl font-semibold">Visual Pipeline Builder</h1>
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

          <section className="grid gap-3 border-b border-base-300 bg-base-100/70 px-5 py-3 md:grid-cols-4">
            <StatusStat label="Enabled steps" value={`${enabledCount}/${steps.length}`} icon={ListChecks} />
            <StatusStat label="Dirty state" value={dirty ? "Unsaved draft" : "Matches file"} icon={dirty ? AlertTriangle : CheckCircle2} tone={dirty ? "warning" : "success"} />
            <StatusStat label="Validation" value={hasErrors ? "Needs fixes" : "Ready"} icon={hasErrors ? AlertTriangle : CheckCircle2} tone={hasErrors ? "warning" : "success"} />
            <StatusStat label="Runtime model" value="tasks + pipeline" icon={FileText} />
          </section>

          {loadError ? (
            <div className="m-4 alert alert-error">{loadError}</div>
          ) : (
            <div className="grid min-h-0 flex-1 grid-cols-1 items-start gap-4 p-4 xl:grid-cols-[minmax(13rem,16rem)_minmax(38rem,1fr)_minmax(24rem,31rem)]">
              <TaskPalette collapsed={collapsedPalette} setCollapsed={setCollapsedPalette} search={search} setSearch={setSearch} steps={steps} addTask={addTask} />

              <section className="flex min-h-[640px] min-w-0 flex-col gap-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <h2 className="text-sm font-semibold">Ordered pipeline</h2>
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
                draftYaml={draftYaml}
                currentYaml={currentYaml}
                diffText={diffText}
                availableTokens={availableTokens}
                csvMetadata={csvMetadata}
                setCsvMetadata={setCsvMetadata}
              />
            </div>
          )}
        </main>
      </div>
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
        <div className="text-[11px] uppercase tracking-wide text-base-content/45">Editable source</div>
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
        <div className="text-[11px] uppercase tracking-wide text-base-content/45">{label}</div>
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
            <h2 className="text-sm font-semibold">Task Palette</h2>
            <p className="text-xs text-base-content/50">Approved prototype steps</p>
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
                    <span className="block truncate text-xs text-base-content/50">{task.category} - {task.class}</span>
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
              <div className="truncate text-left font-mono text-[11px] text-base-content/55">{step.key}</div>
              <div className="mt-3 grid grid-cols-2 gap-2 text-[11px]">
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
                    <span className="block truncate text-[11px] text-base-content/50">{task.category}</span>
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
      <div className="text-base-content/45">{label}</div>
      <div className="truncate font-medium">{String(value || "-")}</div>
    </div>
  );
}

function PropertiesPanel(props) {
  const { step, activeTab, setActiveTab, findings, draftYaml, currentYaml, diffText } = props;
  if (!step) return <section className="rounded-lg border border-base-300 bg-base-100 p-4">No step selected</section>;
  const KindIcon = iconFor(step);
  const tabs = [["properties", "Properties"], ["validate", "Validate"], ["yaml", "YAML"], ["diff", "Diff"]];
  return (
    <section className="flex min-h-0 flex-col rounded-lg border border-base-300 bg-base-100">
      <div className="border-b border-base-300 p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <KindIcon size={19} />
            </span>
            <div className="min-w-0">
              <h2 className="truncate text-sm font-semibold">{step.label}</h2>
              <p className="truncate font-mono text-xs text-base-content/50">{step.key}</p>
            </div>
          </div>
          <span className={`badge badge-sm ${kindBadgeClass(taskKind(step))}`}>{taskKind(step)}</span>
        </div>
        <div className="mt-4 grid grid-cols-4 gap-1 rounded-lg bg-base-200 p-1 text-xs">
          {tabs.map(([tab, label]) => (
            <button key={tab} className={`rounded-md px-2 py-1.5 ${activeTab === tab ? "bg-base-100 font-semibold shadow-sm" : "text-base-content/60"}`} onClick={() => setActiveTab(tab)}>
              {label}
            </button>
          ))}
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-auto p-4">
        {activeTab === "properties" ? <StepProperties {...props} /> : null}
        {activeTab === "validate" ? <ValidationPanel findings={findings} /> : null}
        {activeTab === "yaml" ? <YamlPanel draftYaml={draftYaml} currentYaml={currentYaml} /> : null}
        {activeTab === "diff" ? <DiffPanel diffText={diffText} /> : null}
      </div>
    </section>
  );
}

function StepProperties({ step, index, steps, updateStep, updateParams, replaceParams, duplicateSelected, deleteStep, availableTokens, csvMetadata, setCsvMetadata, findings }) {
  const kind = taskKind(step);
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <TextControl label="Label" value={step.label} onChange={(value) => updateStep(index, { label: value })} />
        <TextControl label="Key" value={step.key} onChange={(value) => updateStep(index, { key: uniqueKey(value, steps, index) })} mono />
        <SelectControl label="On error" value={step.on_error} onChange={(value) => updateStep(index, { on_error: value })} options={["stop", "continue"]} />
        <label className="flex items-end gap-3 rounded-lg border border-base-300 px-3 py-2">
          <input type="checkbox" className="toggle toggle-sm" checked={step.enabled !== false} onChange={(event) => updateStep(index, { enabled: event.target.checked })} />
          <span className="pb-1 text-sm">Enabled in pipeline</span>
        </label>
      </div>
      <div className="rounded-lg border border-base-300 bg-base-200/50 p-3">
        <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-base-content/45">Task-specific controls</div>
        {kind === "split" ? <SplitControls step={step} index={index} updateParams={updateParams} findings={findings} /> : null}
        {kind === "extract" ? <ExtractControls step={step} index={index} updateParams={updateParams} findings={findings} /> : null}
        {kind === "storage" ? <StorageControls step={step} index={index} updateParams={updateParams} availableTokens={availableTokens} findings={findings} /> : null}
        {kind === "review" ? <ReviewControls step={step} index={index} updateParams={updateParams} findings={findings} /> : null}
        {kind === "archive" ? <ArchiveControls step={step} index={index} updateParams={updateParams} findings={findings} /> : null}
        {kind === "rules" ? <RulesControls step={step} index={index} updateParams={updateParams} steps={steps} csvMetadata={csvMetadata} setCsvMetadata={setCsvMetadata} findings={findings} /> : null}
        {kind === "context" ? <ContextControls step={step} index={index} updateParams={updateParams} findings={findings} /> : null}
        {kind === "task" ? <div className="text-sm text-base-content/60">Use advanced params for this task.</div> : null}
      </div>
      <AdvancedParamsEditor step={step} index={index} replaceParams={replaceParams} />
      <div className="grid grid-cols-2 gap-2">
        <button className="btn btn-outline btn-sm" onClick={duplicateSelected}>
          <Copy size={14} /> Duplicate
        </button>
        <button className="btn btn-outline btn-error btn-sm" onClick={() => deleteStep(index)}>
          <Trash2 size={14} /> Remove
        </button>
      </div>
    </div>
  );
}

function SplitControls({ step, index, updateParams, findings }) {
  const params = step.params || {};
  const category = params.categories?.[0] || { name: "", description: "" };
  const levels = Array.isArray(params.fail_on_confidence_levels) ? params.fail_on_confidence_levels : [];
  function toggleLevel(level) {
    const next = levels.includes(level) ? levels.filter((item) => item !== level) : [...levels, level];
    updateParams(index, { fail_on_confidence_levels: next });
  }
  return (
    <div className="space-y-3">
      <TextControl label="API key" value={params.api_key || ""} onChange={(value) => updateParams(index, { api_key: value })} mono />
      <SelectControl label="Uncategorized pages" value={params.allow_uncategorized || "include"} onChange={(value) => updateParams(index, { allow_uncategorized: value })} options={["include", "forbid", "omit"]} />
      <DirectoryControl label="Split output directory" value={params.split_dir || ""} onChange={(value) => updateParams(index, { split_dir: value })} />
      <InlineFindings findings={findings} path={`tasks.${step.key}.params.split_dir`} />
      <div className="rounded-lg border border-base-300 bg-base-100 p-3">
        <div className="mb-2 text-sm font-semibold">Fail on confidence</div>
        <div className="flex flex-wrap gap-3">
          {["high", "medium", "low"].map((level) => (
            <label className="flex items-center gap-2 text-sm" key={level}>
              <input className="checkbox checkbox-sm" type="checkbox" checked={levels.includes(level)} onChange={() => toggleLevel(level)} />
              {level}
            </label>
          ))}
        </div>
      </div>
      <label className="flex items-center gap-3 rounded-lg border border-base-300 bg-base-100 px-3 py-2">
        <input type="checkbox" className="toggle toggle-sm" checked={Boolean(params.fail_on_unknown_category)} onChange={(event) => updateParams(index, { fail_on_unknown_category: event.target.checked })} />
        <span className="text-sm">Fail on unknown category</span>
      </label>
      <TextControl label="Category name" value={category.name} onChange={(value) => updateParams(index, { categories: [{ ...category, name: value }] })} />
      <TextAreaControl label="Category description" value={category.description} onChange={(value) => updateParams(index, { categories: [{ ...category, description: value }] })} />
    </div>
  );
}

function ExtractControls({ step, index, updateParams, findings }) {
  const fields = isPlainObject(step.params.fields) ? step.params.fields : {};
  const tableFieldKeys = Object.entries(fields).filter(([, field]) => field?.is_table).map(([key]) => key);
  function setFields(nextFields) {
    updateParams(index, { fields: nextFields });
  }
  function updateField(key, patch) {
    setFields({ ...fields, [key]: { ...(fields[key] || {}), ...patch } });
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
  }
  function addField() {
    const key = uniqueObjectKey("new_field", fields);
    setFields({ ...fields, [key]: { alias: "New field", type: "str" } });
  }
  return (
    <div className="space-y-3">
      <TextControl label="API key" value={step.params.api_key || ""} onChange={(value) => updateParams(index, { api_key: value })} mono />
      <TextControl label="LlamaExtract configuration ID" value={step.params.configuration_id || ""} onChange={(value) => updateParams(index, { configuration_id: value })} mono />
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <SelectControl label="Tier" value={step.params.tier || "agentic"} onChange={(value) => updateParams(index, { tier: value })} options={["agentic", "premium", "balanced"]} />
        <SelectControl label="Target" value={step.params.extraction_target || "per_doc"} onChange={(value) => updateParams(index, { extraction_target: value })} options={["per_doc", "per_page", "per_table_row"]} />
      </div>
      <label className="flex items-center gap-3 rounded-lg border border-base-300 bg-base-100 px-3 py-2">
        <input type="checkbox" className="toggle toggle-sm" checked={Boolean(step.params.confidence_scores)} onChange={(event) => updateParams(index, { confidence_scores: event.target.checked })} />
        <span className="text-sm">Request confidence scores</span>
      </label>
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
            <FieldEditor key={key} fieldKey={key} config={isPlainObject(config) ? config : {}} fields={fields} tableFieldKeys={tableFieldKeys} renameField={renameField} updateField={updateField} removeField={removeField} findings={findings} stepKey={step.key} />
          ))}
          {!Object.keys(fields).length ? <div className="empty-panel">No extraction fields configured</div> : null}
        </div>
      </div>
    </div>
  );
}

function FieldEditor({ fieldKey, config, fields, tableFieldKeys, renameField, updateField, removeField, findings, stepKey }) {
  const [keyDraft, setKeyDraft] = useState(fieldKey);
  useEffect(() => setKeyDraft(fieldKey), [fieldKey]);
  const isTable = Boolean(config.is_table);
  const tableBlocked = !isTable && tableFieldKeys.length >= 1;
  function toggleTable(checked) {
    if (checked && tableBlocked) return;
    if (checked) {
      updateField(fieldKey, { is_table: true, type: "List[Any]", item_fields: isPlainObject(config.item_fields) ? config.item_fields : {} });
    } else {
      const next = { ...config };
      delete next.is_table;
      delete next.item_fields;
      updateField(fieldKey, next);
    }
  }
  return (
    <div className="field-editor">
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-[1fr_1fr_1fr_auto]">
        <label className="form-control">
          <span className="label-text mb-1 text-xs">Field key</span>
          <input className="input input-bordered input-sm font-mono" value={keyDraft} onChange={(event) => setKeyDraft(slugKey(event.target.value))} onBlur={() => renameField(fieldKey, keyDraft)} />
        </label>
        <TextControl label="Alias" value={config.alias || ""} onChange={(value) => updateField(fieldKey, { alias: value })} />
        <SelectControl label="Type" value={isTable ? "List[Any]" : config.type || "str"} onChange={(value) => updateField(fieldKey, { type: value })} options={FIELD_TYPES} disabled={isTable} />
        <button className="btn btn-ghost btn-square btn-sm self-end text-error" onClick={() => removeField(fieldKey)} title="Remove field">
          <Trash2 size={14} />
        </button>
      </div>
      <InlineFindings findings={findings} pathPrefix={`tasks.${stepKey}.params.fields.${fieldKey}`} />
      <label className={`mt-2 flex items-center gap-3 text-sm ${tableBlocked ? "opacity-50" : ""}`}>
        <input type="checkbox" className="checkbox checkbox-sm" checked={isTable} disabled={tableBlocked} onChange={(event) => toggleTable(event.target.checked)} />
        Table field with item columns
      </label>
      {tableBlocked ? <div className="mt-1 text-xs text-base-content/50">Only one table field can be enabled.</div> : null}
      {isTable ? <ItemFieldsEditor fieldKey={fieldKey} config={config} updateField={updateField} /> : null}
    </div>
  );
}

function ItemFieldsEditor({ fieldKey, config, updateField }) {
  function updateItem(itemKey, patch) {
    updateField(fieldKey, { item_fields: { ...(config.item_fields || {}), [itemKey]: { ...((config.item_fields || {})[itemKey] || {}), ...patch } } });
  }
  function renameItem(oldKey, nextKey) {
    const itemFields = config.item_fields || {};
    const key = uniqueObjectKey(nextKey, itemFields, oldKey);
    const next = {};
    Object.entries(itemFields).forEach(([itemKey, value]) => {
      next[itemKey === oldKey ? key : itemKey] = value;
    });
    updateField(fieldKey, { item_fields: next });
  }
  function removeItem(itemKey) {
    const next = { ...(config.item_fields || {}) };
    delete next[itemKey];
    updateField(fieldKey, { item_fields: next });
  }
  function addItem() {
    const itemFields = config.item_fields || {};
    const key = uniqueObjectKey("new_column", itemFields);
    updateField(fieldKey, { item_fields: { ...itemFields, [key]: { alias: "New column", type: "str" } } });
  }
  return (
    <div className="mt-3 rounded-md border border-base-300 bg-base-200/60 p-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wide text-base-content/50">Item fields</span>
        <button className="btn btn-outline btn-xs" onClick={addItem}>
          <Plus size={13} /> Add column
        </button>
      </div>
      <div className="space-y-2">
        {Object.entries(config.item_fields || {}).map(([itemKey, itemConfig]) => (
          <ItemFieldEditor key={itemKey} itemKey={itemKey} itemConfig={isPlainObject(itemConfig) ? itemConfig : {}} renameItem={renameItem} updateItem={updateItem} removeItem={removeItem} />
        ))}
        {!Object.keys(config.item_fields || {}).length ? <div className="empty-panel">No item columns configured</div> : null}
      </div>
    </div>
  );
}

function ItemFieldEditor({ itemKey, itemConfig, renameItem, updateItem, removeItem }) {
  const [keyDraft, setKeyDraft] = useState(itemKey);
  useEffect(() => setKeyDraft(itemKey), [itemKey]);
  return (
    <div className="grid grid-cols-1 gap-2 sm:grid-cols-[1fr_1fr_1fr_auto]">
      <label className="form-control">
        <span className="label-text mb-1 text-xs">Column key</span>
        <input className="input input-bordered input-sm font-mono" value={keyDraft} onChange={(event) => setKeyDraft(slugKey(event.target.value))} onBlur={() => renameItem(itemKey, keyDraft)} />
      </label>
      <TextControl label="Alias" value={itemConfig.alias || ""} onChange={(value) => updateItem(itemKey, { alias: value })} />
      <SelectControl label="Type" value={itemConfig.type || "str"} onChange={(value) => updateItem(itemKey, { type: value })} options={FIELD_TYPES.filter((type) => type !== "List[Any]")} />
      <button className="btn btn-ghost btn-square btn-sm self-end text-error" onClick={() => removeItem(itemKey)} title="Remove column">
        <Trash2 size={14} />
      </button>
    </div>
  );
}

function StorageControls({ step, index, updateParams, availableTokens, findings }) {
  const isPdf = step.class === "StoreFileToLocaldrive";
  const dirParam = isPdf ? "files_dir" : "data_dir";
  return (
    <div className="space-y-3">
      <DirectoryControl label={isPdf ? "PDF output directory" : "Data output directory"} value={step.params[dirParam] || ""} onChange={(value) => updateParams(index, { [dirParam]: value })} />
      <InlineFindings findings={findings} path={`tasks.${step.key}.params.${dirParam}`} />
      <FilenameBuilder value={step.params.filename || ""} onChange={(value) => updateParams(index, { filename: value })} tokens={availableTokens} />
      <InlineFindings findings={findings} path={`tasks.${step.key}.params.filename`} />
    </div>
  );
}

function FilenameBuilder({ value, onChange, tokens }) {
  return (
    <div className="rounded-lg border border-base-300 bg-base-100 p-3">
      <TextControl label="Filename template" value={value} onChange={onChange} mono />
      <div className="mt-3 text-xs font-semibold">Insert token</div>
      <div className="mt-2 flex flex-wrap gap-1">
        {tokens.map((token) => (
          <button className="badge badge-outline badge-sm font-mono" key={token} onClick={() => onChange(`${value || ""}{${token}}`)}>
            {`{${token}}`}
          </button>
        ))}
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
      <label className="flex items-center gap-3 rounded-lg border border-base-300 bg-base-100 px-3 py-2">
        <input type="checkbox" className="toggle toggle-sm" checked={Boolean(params.backup)} onChange={(event) => updateParams(index, { backup: event.target.checked })} />
        <span className="text-sm">Backup reference CSV before write</span>
      </label>
      <div className="rounded-lg border border-base-300 bg-base-100 p-3">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-sm font-semibold">Match clauses</span>
          <button className="btn btn-outline btn-xs" disabled={clauses.length >= 5} onClick={addClause}>
            <Plus size={13} /> Add clause
          </button>
        </div>
        <div className="space-y-2">
          {clauses.map((clause, clauseIndex) => (
            <div className="rounded-md border border-base-300 p-2" key={clauseIndex}>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-[1fr_1fr_auto]">
                <SelectControl label="CSV column" value={clause.column || ""} onChange={(value) => updateClause(clauseIndex, { column: value })} options={["", ...columns]} />
                <SelectControl label="From context" value={clause.from_context || ""} onChange={(value) => updateClause(clauseIndex, { from_context: value })} options={["", ...fieldOptions]} />
                <button className="btn btn-ghost btn-square btn-sm self-end text-error" disabled={clauses.length <= 1} onClick={() => removeClause(clauseIndex)}>
                  <Trash2 size={14} />
                </button>
              </div>
              <label className="mt-2 flex items-center gap-2 text-sm">
                <input className="checkbox checkbox-sm" type="checkbox" checked={Boolean(clause.number)} onChange={(event) => updateClause(clauseIndex, { number: event.target.checked })} />
                Numeric comparison
              </label>
              <InlineFindings findings={findings} pathPrefix={`tasks.${step.key}.params.csv_match.clauses[${clauseIndex}]`} />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function ReviewControls({ step, index, updateParams, findings }) {
  return (
    <div className="space-y-3">
      <NumberControl label="Confidence threshold" value={step.params.confidence_threshold ?? 0.8} min={0} max={1} step={0.01} onChange={(value) => updateParams(index, { confidence_threshold: value })} />
      <FileControl label="Schema file" value={step.params.schema_file || ""} extensions=".yaml,.yml" onChange={(value) => updateParams(index, { schema_file: value })} startPath="schemas" />
      <InlineFindings findings={findings} path={`tasks.${step.key}.params.schema_file`} />
      <TextControl label="Queue" value={step.params.queue_name || ""} onChange={(value) => updateParams(index, { queue_name: value })} />
      <SelectControl label="Review scope" value={step.params.review_scope || "low_confidence_fields"} onChange={(value) => updateParams(index, { review_scope: value })} options={["document", "low_confidence_fields", "schema_errors", "split_result"]} />
      <SelectControl label="Resume policy" value={step.params.resume_policy || "next_task"} onChange={(value) => updateParams(index, { resume_policy: value })} options={["next_task", "restart_pipeline"]} />
      <label className="flex items-center gap-3 rounded-lg border border-base-300 bg-base-100 px-3 py-2">
        <input type="checkbox" className="toggle toggle-sm" checked={Boolean(step.params.require_review_when_missing_confidence)} onChange={(event) => updateParams(index, { require_review_when_missing_confidence: event.target.checked })} />
        <span className="text-sm">Review when confidence is missing</span>
      </label>
    </div>
  );
}

function ArchiveControls({ step, index, updateParams, findings }) {
  return (
    <>
      <DirectoryControl label="Archive directory" value={step.params.archive_dir || ""} onChange={(value) => updateParams(index, { archive_dir: value })} />
      <InlineFindings findings={findings} path={`tasks.${step.key}.params.archive_dir`} />
    </>
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

function DirectoryControl({ label, value, onChange, startPath = "." }) {
  return <PathBrowser label={label} value={value} onChange={onChange} mode="directory" startPath={isAbsoluteLikePath(value) ? startPath : value || startPath} />;
}

function FileControl({ label, value, onChange, extensions, startPath = "." }) {
  return <PathBrowser label={label} value={value} onChange={onChange} mode="file" extensions={extensions} startPath={value ? value.split("/").slice(0, -1).join("/") || "." : startPath} />;
}

function isAbsoluteLikePath(value) {
  return /^[A-Za-z]:[\\/]/.test(String(value || "")) || String(value || "").startsWith("\\\\") || String(value || "").startsWith("/");
}

function PathBrowser({ label, value, onChange, mode, extensions = "", startPath }) {
  const [open, setOpen] = useState(false);
  const [current, setCurrent] = useState(startPath || ".");
  const [listing, setListing] = useState(null);
  const [newDir, setNewDir] = useState("");
  const [errorText, setErrorText] = useState("");
  const [pickerStatus, setPickerStatus] = useState("");

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
        <span className="label-text mb-1 text-xs">{label}</span>
        <div className="flex flex-col gap-2 sm:flex-row">
          <input className="input input-bordered input-sm font-mono" value={value ?? ""} onChange={(event) => onChange(event.target.value)} />
          {mode === "directory" ? (
            <button className="btn btn-primary btn-sm shrink-0" onClick={chooseNativeDirectory}>
              <FolderOpen size={14} /> Choose folder
            </button>
          ) : null}
        </div>
      </label>
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

function DiffPanel({ diffText }) {
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

function TextControl({ label, value, onChange, mono }) {
  return (
    <label className="form-control">
      <span className="label-text mb-1 text-xs">{label}</span>
      <input className={`input input-bordered input-sm ${mono ? "font-mono" : ""}`} value={value ?? ""} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

function TextAreaControl({ label, value, onChange }) {
  return (
    <label className="form-control">
      <span className="label-text mb-1 text-xs">{label}</span>
      <textarea className="textarea textarea-bordered min-h-24 text-sm" value={value ?? ""} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

function SelectControl({ label, value, onChange, options, disabled }) {
  return (
    <label className="form-control">
      <span className="label-text mb-1 text-xs">{label}</span>
      <select className="select select-bordered select-sm" value={value ?? ""} disabled={disabled} onChange={(event) => onChange(event.target.value)}>
        {options.map((option) => (
          <option key={option} value={option}>{option || "Select..."}</option>
        ))}
      </select>
    </label>
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
