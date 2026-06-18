import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import yaml from "js-yaml";
import {
  AlertTriangle,
  Archive,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Copy,
  Database,
  FileJson,
  FileText,
  GitBranch,
  HardDrive,
  Info,
  KeyRound,
  ListChecks,
  Lock,
  PanelRight,
  Play,
  Plus,
  RefreshCw,
  RotateCcw,
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
import { NodeEditor, ClassicPreset } from "rete";
import { AreaExtensions, AreaPlugin } from "rete-area-plugin";
import { ConnectionPlugin, Presets as ConnectionPresets } from "rete-connection-plugin";
import { ReactPlugin, Presets as ReactPresets } from "rete-react-plugin";
import { createRoot as createReactRoot } from "react-dom/client";
import "./styles.css";

const socket = new ClassicPreset.Socket("pipeline");

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
      poll_interval_seconds: 2,
      timeout_seconds: 7200,
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
      schema_file: "schemas/invoice.yaml",
      queue_name: "default_review",
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
  const match = taskTemplates.find((task) => task.class === step?.class);
  return match?.icon || Settings;
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

function configToSteps(config) {
  const tasks = config?.tasks && typeof config.tasks === "object" ? config.tasks : {};
  const pipeline = Array.isArray(config?.pipeline) ? config.pipeline : [];
  const ordered = [];
  const used = new Set();

  pipeline.forEach((key) => {
    const task = tasks[key];
    if (!task || typeof task !== "object") return;
    ordered.push(taskConfigToStep(key, task, true));
    used.add(key);
  });

  Object.entries(tasks).forEach(([key, task]) => {
    if (used.has(key) || !task || typeof task !== "object") return;
    ordered.push(taskConfigToStep(key, task, false));
  });

  return ordered;
}

function taskConfigToStep(key, task, enabled) {
  const template = taskTemplates.find((item) => item.class === task.class);
  return {
    key,
    label: labelForStep(key, task),
    category: template?.category || taskKind(task),
    module: String(task.module || ""),
    class: String(task.class || ""),
    enabled,
    on_error: task.on_error || "stop",
    params: clone(task.params || {}),
  };
}

function buildConfig(baseConfig, steps) {
  const config = clone(baseConfig || {});
  const tasks = {};
  const pipeline = [];

  steps.forEach((step) => {
    if (!step.key) return;
    const task = {
      module: step.module,
      class: step.class,
      params: clone(step.params || {}),
    };
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

function validateSteps(steps) {
  const findings = [];
  const keys = new Set();
  const enabled = steps.filter((step) => step.enabled !== false);
  const splitIndex = enabled.findIndex((step) => taskKind(step) === "split");
  const extractIndex = enabled.findIndex((step) => taskKind(step) === "extract");

  steps.forEach((step, index) => {
    if (!step.key?.trim()) {
      findings.push(error("task-key-empty", `Step ${index + 1} needs a task key.`));
    } else if (keys.has(step.key)) {
      findings.push(error("task-key-duplicate", `Task key '${step.key}' is duplicated.`));
    }
    keys.add(step.key);
    if (!step.module?.trim()) findings.push(error("task-module-empty", `${step.key} needs a module.`));
    if (!step.class?.trim()) findings.push(error("task-class-empty", `${step.key} needs a class.`));
    if (!isPlainObject(step.params)) findings.push(error("task-params-invalid", `${step.key} params must be an object.`));
  });

  if (extractIndex === -1) {
    findings.push(error("pipeline-missing-extract", "Add an extraction task before storage."));
  }
  if (splitIndex > -1 && extractIndex > -1 && splitIndex > extractIndex) {
    findings.push(error("split-after-extract", "Split needs to run before extraction."));
  }
  if (splitIndex === enabled.length - 1) {
    findings.push(warning("split-final-step", "Split is the final enabled step, so children have no downstream work."));
  }

  enabled.forEach((step) => {
    const kind = taskKind(step);
    if (kind === "split" && !step.params.configuration_id && !step.params.categories?.length) {
      findings.push(error("split-missing-category", "Split needs categories or a saved split configuration."));
    }
    if (kind === "storage") {
      const dir = step.params.files_dir || step.params.data_dir;
      if (!dir) findings.push(error("storage-missing-dir", `${step.label} needs an output directory.`));
      if (!step.params.filename) findings.push(error("storage-missing-filename", `${step.label} needs a filename template.`));
    }
    if (kind === "extract") {
      const fields = step.params.fields;
      if (!isPlainObject(fields)) findings.push(error("extract-fields-invalid", `${step.label} fields must be a mapping.`));
      Object.entries(fields || {}).forEach(([fieldKey, field]) => {
        if (!fieldKey.trim()) findings.push(error("extract-field-key-empty", "Extraction field keys cannot be empty."));
        if (!isPlainObject(field)) {
          findings.push(error("extract-field-invalid", `Field '${fieldKey}' must be a mapping.`));
          return;
        }
        if (!field.alias) findings.push(warning("extract-field-alias-empty", `Field '${fieldKey}' has no alias.`));
        if (!field.type) findings.push(error("extract-field-type-empty", `Field '${fieldKey}' needs a type.`));
        if (field.is_table && !isPlainObject(field.item_fields)) {
          findings.push(error("extract-table-fields-invalid", `Table field '${fieldKey}' needs item_fields.`));
        }
      });
    }
  });

  if (!findings.some((finding) => finding.severity === "error")) {
    findings.push({ severity: "success", code: "ready-to-publish", message: "Draft can be written to the prototype YAML file." });
  }
  return findings;
}

function error(code, message) {
  return { severity: "error", code, message };
}

function warning(code, message) {
  return { severity: "warning", code, message };
}

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function uniqueKey(base, steps, ignoreIndex = -1) {
  const normalized = String(base || "task").replace(/[^A-Za-z0-9_]/g, "_").replace(/^_+|_+$/g, "") || "task";
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
  const normalized = String(base || "field").replace(/[^A-Za-z0-9_]/g, "_").replace(/^_+|_+$/g, "") || "field";
  const used = new Set(Object.keys(object || {}).filter((key) => key !== oldKey));
  let candidate = normalized;
  let count = 2;
  while (used.has(candidate)) {
    candidate = `${normalized}_${count}`;
    count += 1;
  }
  return candidate;
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

class PipelineNode extends ClassicPreset.Node {
  constructor(step, index) {
    super(step.label);
    this.step = step;
    this.index = index;
    this.width = 218;
    this.height = taskKind(step) === "split" ? 168 : 138;
    if (index > 0) this.addInput("in", new ClassicPreset.Input(socket, "In"));
    this.addOutput("out", new ClassicPreset.Output(socket, "Next"));
    this.addControl("key", new ClassicPreset.InputControl("text", { initial: step.key, readonly: true }));
    this.addControl("meta", new ClassicPreset.InputControl("text", { initial: `${taskKind(step)} - ${step.on_error || "default"}`, readonly: true }));
    if (taskKind(step) === "extract") {
      this.addControl("fields", new ClassicPreset.InputControl("text", { initial: `${Object.keys(step.params.fields || {}).length} fields`, readonly: true }));
    }
    if (taskKind(step) === "storage") {
      this.addControl("output", new ClassicPreset.InputControl("text", { initial: step.params.files_dir || step.params.data_dir || "output", readonly: true }));
    }
  }
}

async function createRetePipeline(container, steps, onSelect) {
  const editor = new NodeEditor();
  const area = new AreaPlugin(container);
  const connection = new ConnectionPlugin();
  const render = new ReactPlugin({ createRoot: createReactRoot });

  connection.addPreset(ConnectionPresets.classic.setup());
  render.addPreset(ReactPresets.classic.setup());
  editor.use(area);
  area.use(connection);
  area.use(render);
  AreaExtensions.simpleNodesOrder(area);
  AreaExtensions.selectableNodes(area, AreaExtensions.selector(), {
    accumulating: AreaExtensions.accumulateOnCtrl(),
  });

  const nodes = [];
  for (let index = 0; index < steps.length; index += 1) {
    const node = new PipelineNode(steps[index], index);
    await editor.addNode(node);
    await area.translate(node.id, nodePosition(index));
    nodes.push(node);
  }
  for (let index = 0; index < nodes.length - 1; index += 1) {
    await editor.addConnection(new ClassicPreset.Connection(nodes[index], "out", nodes[index + 1], "in"));
  }
  area.addPipe((context) => {
    if (context.type === "nodepicked") {
      const node = editor.getNode(context.data.id);
      if (node?.index !== undefined) onSelect(node.index);
    }
    return context;
  });
  setTimeout(() => AreaExtensions.zoomAt(area, nodes), 80);
  return { destroy: () => area.destroy() };
}

function nodePosition(index) {
  const column = index % 3;
  const row = Math.floor(index / 3);
  return { x: 70 + column * 270, y: 120 + row * 230 };
}

function ReteCanvas({ steps, selectedIndex, onSelect }) {
  const ref = useRef(null);
  const instanceRef = useRef(null);

  useEffect(() => {
    let cancelled = false;
    if (!ref.current) return undefined;
    instanceRef.current?.destroy();
    ref.current.innerHTML = "";
    createRetePipeline(ref.current, steps, onSelect).then((instance) => {
      if (cancelled) instance.destroy();
      else instanceRef.current = instance;
    });
    return () => {
      cancelled = true;
      instanceRef.current?.destroy();
      instanceRef.current = null;
    };
  }, [steps, onSelect]);

  return (
    <div className="relative h-full min-h-[560px] overflow-hidden rounded-lg border border-base-300 bg-canvas">
      <div ref={ref} className="h-full min-h-[560px]" />
      <div className="pointer-events-none absolute left-4 top-4 flex flex-wrap gap-2">
        <span className="badge badge-neutral">Rete.js canvas</span>
        <span className="badge badge-outline">Selected node {selectedIndex + 1}</span>
      </div>
      <div className="pointer-events-none absolute bottom-4 left-4 max-w-[calc(100%-2rem)] rounded-lg border border-base-300 bg-base-100/90 px-3 py-2 text-xs shadow-sm">
        Drag nodes for inspection. Use Move controls to change saved pipeline order.
      </div>
    </div>
  );
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

  const selected = steps[selectedIndex] || steps[0] || null;
  const draftConfig = useMemo(() => buildConfig(baseConfig, steps), [baseConfig, steps]);
  const draftYaml = useMemo(() => dumpYaml(draftConfig), [draftConfig]);
  const diffText = useMemo(() => lineDiff(currentYaml, draftYaml), [currentYaml, draftYaml]);
  const findings = useMemo(() => validateSteps(steps), [steps]);
  const enabledCount = steps.filter((step) => step.enabled !== false).length;
  const hasErrors = findings.some((finding) => finding.severity === "error");

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
      setBaseConfig(payload.config || {});
      setCurrentYaml(payload.rawYaml || "");
      setSource(payload);
      const loadedSteps = configToSteps(payload.config || {});
      setSteps(loadedSteps);
      setSelectedIndex(0);
      setActiveTab("properties");
      setDirty(false);
      setPublishMessage("");
    } catch (error) {
      setLoadError(error.message || "Unable to load prototype config.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadConfig();
  }, [loadConfig]);

  const selectNode = useCallback((index) => {
    setSelectedIndex(index);
    setActiveTab("properties");
  }, []);

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

  function addTask(task) {
    const nextTask = {
      ...clone(task),
      key: uniqueKey(task.key, steps),
      enabled: true,
      params: clone(task.params),
    };
    setSteps((current) => [...current, nextTask]);
    setSelectedIndex(steps.length);
    markDirty();
  }

  function duplicateSelected() {
    if (!selected) return;
    const duplicate = clone(selected);
    duplicate.key = uniqueKey(`${selected.key}_copy`, steps);
    duplicate.label = `${selected.label} copy`;
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
      setBaseConfig(payload.config || {});
      setCurrentYaml(payload.rawYaml || "");
      setSource(payload);
      setSteps(configToSteps(payload.config || {}));
      setDirty(false);
      setPublishMessage("Published to public/config_sample_invoice.yaml. Backup updated.");
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
          {[
            [Upload, "Upload"],
            [ListChecks, "Pipeline"],
            [ShieldCheck, "Review"],
            [Database, "Reports"],
            [Settings, "Settings"],
          ].map(([Icon, label], index) => (
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
              <TaskPalette
                collapsed={collapsedPalette}
                setCollapsed={setCollapsedPalette}
                search={search}
                setSearch={setSearch}
                steps={steps}
                addTask={addTask}
              />

              <section className="flex min-h-[640px] min-w-0 flex-col gap-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <h2 className="text-sm font-semibold">Serial canvas with split-aware visualization</h2>
                    <p className="text-xs text-base-content/55">Enabled nodes compile into the YAML pipeline list. Disabled nodes remain in tasks only.</p>
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
                <ReteCanvas steps={steps} selectedIndex={selectedIndex} onSelect={selectNode} />
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
              />
            </div>
          )}
        </main>
      </div>
    </div>
  );
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

function PropertiesPanel(props) {
  const { step, activeTab, setActiveTab, findings, draftYaml, currentYaml, diffText } = props;
  if (!step) {
    return <section className="rounded-lg border border-base-300 bg-base-100 p-4">No step selected</section>;
  }
  const KindIcon = iconFor(step);
  const tabs = [
    ["properties", "Properties"],
    ["validate", "Validate"],
    ["yaml", "YAML"],
    ["diff", "Diff"],
  ];
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

function StepProperties({ step, index, steps, updateStep, updateParams, replaceParams, duplicateSelected, deleteStep }) {
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
        {kind === "split" ? <SplitControls step={step} index={index} updateParams={updateParams} /> : null}
        {kind === "extract" ? <ExtractControls step={step} index={index} updateParams={updateParams} /> : null}
        {kind === "storage" ? <StorageControls step={step} index={index} updateParams={updateParams} /> : null}
        {kind === "review" ? <ReviewControls step={step} index={index} updateParams={updateParams} /> : null}
        {kind === "archive" ? <ArchiveControls step={step} index={index} updateParams={updateParams} /> : null}
        {kind === "rules" ? <RulesControls step={step} index={index} updateParams={updateParams} /> : null}
        {kind === "context" ? <ContextControls step={step} index={index} updateParams={updateParams} /> : null}
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

function SplitControls({ step, index, updateParams }) {
  const category = step.params.categories?.[0] || { name: "", description: "" };
  return (
    <div className="space-y-3">
      <TextControl label="API key" value={step.params.api_key || ""} onChange={(value) => updateParams(index, { api_key: value })} mono />
      <SelectControl label="Uncategorized pages" value={step.params.allow_uncategorized || "include"} onChange={(value) => updateParams(index, { allow_uncategorized: value })} options={["include", "forbid", "omit"]} />
      <TextControl label="Split output directory" value={step.params.split_dir || ""} onChange={(value) => updateParams(index, { split_dir: value })} mono />
      <TextControl label="Category name" value={category.name} onChange={(value) => updateParams(index, { categories: [{ ...category, name: value }] })} />
      <TextAreaControl label="Category description" value={category.description} onChange={(value) => updateParams(index, { categories: [{ ...category, description: value }] })} />
      <div className="alert border-info/25 bg-info/10 text-xs">
        <Info size={15} />
        <span>Advanced params can edit multiple categories, timeouts, and confidence policy.</span>
      </div>
    </div>
  );
}

function ExtractControls({ step, index, updateParams }) {
  const fields = isPlainObject(step.params.fields) ? step.params.fields : {};
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
        <TextControl label="Tier" value={step.params.tier || ""} onChange={(value) => updateParams(index, { tier: value })} />
        <TextControl label="Target" value={step.params.extraction_target || ""} onChange={(value) => updateParams(index, { extraction_target: value })} />
      </div>
      <label className="flex items-center gap-3 rounded-lg border border-base-300 bg-base-100 px-3 py-2">
        <input type="checkbox" className="toggle toggle-sm" checked={Boolean(step.params.confidence_scores)} onChange={(event) => updateParams(index, { confidence_scores: event.target.checked })} />
        <span className="text-sm">Request confidence scores</span>
      </label>
      <div className="rounded-lg border border-base-300 bg-base-100">
        <div className="flex items-center justify-between border-b border-base-300 px-3 py-2">
          <span className="text-sm font-semibold">Fields</span>
          <button className="btn btn-outline btn-xs" onClick={addField}>
            <Plus size={13} /> Add field
          </button>
        </div>
        <div className="space-y-3 p-3">
          {Object.entries(fields).map(([key, config]) => (
            <FieldEditor
              key={key}
              fieldKey={key}
              config={isPlainObject(config) ? config : {}}
              fields={fields}
              renameField={renameField}
              updateField={updateField}
              removeField={removeField}
            />
          ))}
          {!Object.keys(fields).length ? <div className="empty-panel">No extraction fields configured</div> : null}
        </div>
      </div>
    </div>
  );
}

function FieldEditor({ fieldKey, config, fields, renameField, updateField, removeField }) {
  const [keyDraft, setKeyDraft] = useState(fieldKey);
  useEffect(() => setKeyDraft(fieldKey), [fieldKey]);

  function toggleTable(checked) {
    if (checked) {
      updateField(fieldKey, {
        is_table: true,
        type: config.type || "List[Any]",
        item_fields: isPlainObject(config.item_fields) ? config.item_fields : {},
      });
    } else {
      const next = { ...config };
      delete next.is_table;
      delete next.item_fields;
      updateField(fieldKey, next);
    }
  }

  function updateItem(itemKey, patch) {
    updateField(fieldKey, {
      item_fields: {
        ...(config.item_fields || {}),
        [itemKey]: { ...((config.item_fields || {})[itemKey] || {}), ...patch },
      },
    });
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
    <div className="field-editor">
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-[1fr_1fr_1fr_auto]">
        <label className="form-control">
          <span className="label-text mb-1 text-xs">Field key</span>
          <input
            className="input input-bordered input-sm font-mono"
            value={keyDraft}
            onChange={(event) => setKeyDraft(event.target.value)}
            onBlur={() => renameField(fieldKey, keyDraft)}
          />
        </label>
        <TextControl label="Alias" value={config.alias || ""} onChange={(value) => updateField(fieldKey, { alias: value })} />
        <TextControl label="Type" value={config.type || ""} onChange={(value) => updateField(fieldKey, { type: value })} mono />
        <button className="btn btn-ghost btn-square btn-sm self-end text-error" onClick={() => removeField(fieldKey)} title="Remove field">
          <Trash2 size={14} />
        </button>
      </div>
      <label className="mt-2 flex items-center gap-3 text-sm">
        <input type="checkbox" className="checkbox checkbox-sm" checked={Boolean(config.is_table)} onChange={(event) => toggleTable(event.target.checked)} />
        Table field with item columns
      </label>
      {config.is_table ? (
        <div className="mt-3 rounded-md border border-base-300 bg-base-200/60 p-3">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wide text-base-content/50">Item fields</span>
            <button className="btn btn-outline btn-xs" onClick={addItem}>
              <Plus size={13} /> Add column
            </button>
          </div>
          <div className="space-y-2">
            {Object.entries(config.item_fields || {}).map(([itemKey, itemConfig]) => (
              <ItemFieldEditor
                key={itemKey}
                itemKey={itemKey}
                itemConfig={isPlainObject(itemConfig) ? itemConfig : {}}
                renameItem={renameItem}
                updateItem={updateItem}
                removeItem={removeItem}
              />
            ))}
            {!Object.keys(config.item_fields || {}).length ? <div className="empty-panel">No item columns configured</div> : null}
          </div>
        </div>
      ) : null}
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
        <input className="input input-bordered input-sm font-mono" value={keyDraft} onChange={(event) => setKeyDraft(event.target.value)} onBlur={() => renameItem(itemKey, keyDraft)} />
      </label>
      <TextControl label="Alias" value={itemConfig.alias || ""} onChange={(value) => updateItem(itemKey, { alias: value })} />
      <TextControl label="Type" value={itemConfig.type || ""} onChange={(value) => updateItem(itemKey, { type: value })} mono />
      <button className="btn btn-ghost btn-square btn-sm self-end text-error" onClick={() => removeItem(itemKey)} title="Remove column">
        <Trash2 size={14} />
      </button>
    </div>
  );
}

function StorageControls({ step, index, updateParams }) {
  const isPdf = step.class === "StoreFileToLocaldrive";
  return (
    <div className="space-y-3">
      <TextControl label={isPdf ? "PDF output directory" : "Data output directory"} value={isPdf ? step.params.files_dir || "" : step.params.data_dir || ""} onChange={(value) => updateParams(index, isPdf ? { files_dir: value } : { data_dir: value })} mono />
      <TextControl label="Filename template" value={step.params.filename || ""} onChange={(value) => updateParams(index, { filename: value })} mono />
      <TokenList fields={["nanoid", "purchase_order_number", "supplier_name", "invoice_amount", "policy_number", "id", "original_filename"]} />
    </div>
  );
}

function ReviewControls({ step, index, updateParams }) {
  return (
    <div className="space-y-3">
      <NumberControl label="Confidence threshold" value={step.params.confidence_threshold ?? 0.8} min={0} max={1} step={0.01} onChange={(value) => updateParams(index, { confidence_threshold: value })} />
      <TextControl label="Schema file" value={step.params.schema_file || ""} onChange={(value) => updateParams(index, { schema_file: value })} mono />
      <TextControl label="Queue" value={step.params.queue_name || ""} onChange={(value) => updateParams(index, { queue_name: value })} />
      <SelectControl label="Resume policy" value={step.params.resume_policy || "next_task"} onChange={(value) => updateParams(index, { resume_policy: value })} options={["next_task", "restart_pipeline"]} />
    </div>
  );
}

function ArchiveControls({ step, index, updateParams }) {
  return <TextControl label="Archive directory" value={step.params.archive_dir || ""} onChange={(value) => updateParams(index, { archive_dir: value })} mono />;
}

function RulesControls({ step, index, updateParams }) {
  return (
    <div className="space-y-3">
      <TextControl label="Reference file" value={step.params.reference_file || ""} onChange={(value) => updateParams(index, { reference_file: value })} mono />
      <TextControl label="Update field" value={step.params.update_field || ""} onChange={(value) => updateParams(index, { update_field: value })} />
      <TextControl label="Write value" value={step.params.write_value || ""} onChange={(value) => updateParams(index, { write_value: value })} />
      <label className="flex items-center gap-3 rounded-lg border border-base-300 bg-base-100 px-3 py-2">
        <input type="checkbox" className="toggle toggle-sm" checked={Boolean(step.params.backup)} onChange={(event) => updateParams(index, { backup: event.target.checked })} />
        <span className="text-sm">Backup reference CSV before write</span>
      </label>
    </div>
  );
}

function ContextControls({ step, index, updateParams }) {
  return <NumberControl label="Nanoid length" value={step.params.length ?? 12} min={4} max={64} step={1} onChange={(value) => updateParams(index, { length: value })} />;
}

function TokenList({ fields }) {
  return (
    <div className="rounded-lg border border-base-300 bg-base-100 p-3 text-xs">
      <div className="mb-2 font-semibold">Available tokens</div>
      <div className="flex flex-wrap gap-1">
        {fields.map((token) => (
          <span className="badge badge-outline badge-sm font-mono" key={token}>{`{${token}}`}</span>
        ))}
      </div>
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
        <button className="btn btn-outline btn-sm" onClick={applyJson}>
          Apply JSON params
        </button>
      </div>
    </details>
  );
}

function ValidationPanel({ findings }) {
  return (
    <div className="space-y-3">
      {findings.map((finding) => (
        <div key={`${finding.code}-${finding.message}`} className={`alert text-sm ${finding.severity === "error" ? "alert-error" : finding.severity === "warning" ? "alert-warning" : "alert-success"}`}>
          {finding.severity === "error" ? <AlertTriangle size={17} /> : <CheckCircle2 size={17} />}
          <div>
            <div className="font-semibold">{finding.code}</div>
            <div className="text-xs">{finding.message}</div>
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
  const splitIndex = enabled.findIndex((step) => taskKind(step) === "split");
  return (
    <div className="rounded-lg border border-base-300 bg-base-100 p-3 shadow-sm">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold">Run simulation</h3>
          <p className="text-xs text-base-content/55">Source PDF follows the enabled YAML pipeline order.</p>
        </div>
        <button className="btn btn-ghost btn-square btn-sm" onClick={close}>
          <X size={15} />
        </button>
      </div>
      <div className="grid gap-2 md:grid-cols-4">
        {[1, 2, 3, 4].map((page) => (
          <div className="rounded-lg border border-base-300 bg-base-200 p-3" key={page}>
            <div className="mb-2 flex items-center justify-between">
              <span className="font-semibold">Document {page}</span>
              <span className="badge badge-info badge-sm">sample</span>
            </div>
            <div className="space-y-1 text-xs text-base-content/60">
              {enabled.slice(Math.max(0, splitIndex + 1)).map((step) => (
                <div className="flex items-center gap-2" key={`${page}-${step.key}`}>
                  <CheckCircle2 size={13} className="text-success" />
                  <span className="truncate">{step.label}</span>
                </div>
              ))}
            </div>
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

function SelectControl({ label, value, onChange, options }) {
  return (
    <label className="form-control">
      <span className="label-text mb-1 text-xs">{label}</span>
      <select className="select select-bordered select-sm" value={value ?? ""} onChange={(event) => onChange(event.target.value)}>
        {options.map((option) => (
          <option key={option} value={option}>{option}</option>
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

createRoot(document.getElementById("root")).render(<App />);
