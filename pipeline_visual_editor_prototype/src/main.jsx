import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import yaml from "js-yaml";
import {
  AlertTriangle,
  Archive,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Copy,
  Database,
  FileJson,
  FileText,
  GitBranch,
  GripVertical,
  HardDrive,
  Info,
  KeyRound,
  ListChecks,
  Lock,
  PanelRight,
  Play,
  Plus,
  RotateCcw,
  Save,
  Scissors,
  Search,
  Settings,
  ShieldCheck,
  Sparkles,
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

const taskCatalog = [
  {
    key: "split_document",
    label: "Split document",
    category: "Split",
    icon: Scissors,
    module: "standard_step.split.llamacloud_split",
    class: "LlamaCloudSplitTask",
    enabled: true,
    on_error: "stop",
    params: {
      enabled: true,
      api_key: "configured-secret",
      allow_uncategorized: "forbid",
      split_dir: "processing/split",
      poll_interval_seconds: 2,
      timeout_seconds: 7200,
      categories: [
        {
          name: "invoice",
          description:
            "A single invoice document. Split each separate invoice into its own segment even when adjacent invoices share the same category.",
        },
      ],
    },
  },
  {
    key: "extract_document_data",
    label: "Extract invoice fields",
    category: "Extraction",
    icon: Wand2,
    module: "standard_step.extraction.extract_pdf_v2",
    class: "ExtractPdfV2Task",
    enabled: true,
    on_error: "stop",
    params: {
      api_key: "configured-secret",
      configuration_id: "cfg-bfudokjvy11l6jnu4g1j2bg4t7q0",
      tier: "agentic",
      extraction_target: "per_doc",
      confidence_scores: true,
      fields: {
        invoiceNumber: { alias: "invoiceNumber", type: "str" },
        invoiceDate: { alias: "invoiceDate", type: "str" },
        billTo: { alias: "billTo", type: "str" },
        shipTo: { alias: "shipTo", type: "Optional[str]" },
        items: {
          alias: "items",
          type: "List[Any]",
          is_table: true,
          item_fields: {
            itemName: { alias: "itemName", type: "str" },
            quantity: { alias: "quantity", type: "float" },
            unitPrice: { alias: "unitPrice", type: "float" },
            lineItemTotal: { alias: "lineItemTotal", type: "float" },
          },
        },
        totalAmount: { alias: "totalAmount", type: "float" },
      },
    },
  },
  {
    key: "store_file_to_localdrive",
    label: "Save PDF",
    category: "Storage",
    icon: HardDrive,
    module: "standard_step.storage.store_file_to_localdrive",
    class: "StoreFileToLocaldrive",
    enabled: true,
    on_error: "continue",
    params: {
      files_dir: "files",
      filename: "{invoiceNumber}_{totalAmount}",
    },
  },
  {
    key: "store_metadata_json",
    label: "Store JSON metadata",
    category: "Storage",
    icon: FileJson,
    module: "standard_step.storage.store_metadata_as_json_v2",
    class: "StoreMetadataAsJsonV2",
    enabled: true,
    on_error: "continue",
    params: {
      data_dir: "data",
      filename: "{invoiceNumber}_{totalAmount}",
    },
  },
  {
    key: "review_gate",
    label: "Review gate",
    category: "Review",
    icon: ShieldCheck,
    module: "standard_step.review.review_gate",
    class: "ReviewGateTask",
    enabled: false,
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
    enabled: false,
    on_error: "continue",
    params: {
      archive_dir: "archive_folder",
    },
  },
];

const defaultSteps = taskCatalog.slice(0, 4).map((task) => cloneTask(task));

function cloneTask(task, suffix = "") {
  return {
    key: suffix ? `${task.key}_${suffix}` : task.key,
    label: task.label,
    category: task.category,
    module: task.module,
    class: task.class,
    enabled: task.enabled,
    on_error: task.on_error,
    params: structuredClone(task.params),
  };
}

function taskKind(step) {
  if (step.class === "LlamaCloudSplitTask") return "split";
  if (step.class === "ExtractPdfV2Task" || step.module.includes(".extraction.")) return "extract";
  if (step.class === "ReviewGateTask") return "review";
  if (step.module.includes(".storage.")) return "storage";
  if (step.module.includes(".archiver.")) return "archive";
  return "task";
}

function iconFor(step) {
  const match = taskCatalog.find((task) => task.class === step.class);
  return match?.icon || Settings;
}

function kindBadgeClass(kind) {
  return {
    split: "badge-info",
    extract: "badge-primary",
    review: "badge-warning",
    storage: "badge-success",
    archive: "badge-neutral",
    task: "badge-ghost",
  }[kind];
}

function validateSteps(steps) {
  const findings = [];
  const enabled = steps.filter((step) => step.enabled !== false);
  const splitIndex = enabled.findIndex((step) => taskKind(step) === "split");
  const extractIndex = enabled.findIndex((step) => taskKind(step) === "extract");
  const tableFields = enabled
    .filter((step) => taskKind(step) === "extract")
    .flatMap((step) =>
      Object.entries(step.params.fields || {})
        .filter(([, config]) => config?.is_table)
        .map(([key]) => key),
    );

  if (extractIndex === -1) {
    findings.push({ severity: "error", code: "pipeline-missing-extract", message: "Add an extraction task before storage." });
  }
  if (splitIndex > -1 && extractIndex > -1 && splitIndex > extractIndex) {
    findings.push({ severity: "error", code: "split-after-extract", message: "Split needs to run before extraction." });
  }
  if (splitIndex === enabled.length - 1) {
    findings.push({ severity: "warning", code: "split-final-step", message: "Split is the final enabled step, so children have no downstream work." });
  }
  if (tableFields.length > 1) {
    findings.push({ severity: "error", code: "multiple-table-fields", message: "Only one table field can be expanded by the current v2 storage tasks." });
  }
  enabled.forEach((step) => {
    if (taskKind(step) === "split" && !step.params.configuration_id && !step.params.categories?.length) {
      findings.push({ severity: "error", code: "split-missing-category", message: "Split needs categories or a saved split configuration." });
    }
    if (taskKind(step) === "storage") {
      const dir = step.params.files_dir || step.params.data_dir;
      if (!dir) findings.push({ severity: "error", code: "storage-missing-dir", message: `${step.label} needs an output directory.` });
      if (!step.params.filename) findings.push({ severity: "error", code: "storage-missing-filename", message: `${step.label} needs a filename template.` });
    }
  });
  if (!findings.some((finding) => finding.severity === "error")) {
    findings.push({ severity: "success", code: "ready-to-publish", message: "Draft compiles back to the current tasks + pipeline YAML model." });
  }
  return findings;
}

function buildConfig(steps) {
  const tasks = {};
  const pipeline = [];
  steps.forEach((step) => {
    tasks[step.key] = {
      module: step.module,
      class: step.class,
      params: redactedParams(step.params),
      on_error: step.on_error,
    };
    if (step.enabled !== false) pipeline.push(step.key);
  });
  return { tasks, pipeline };
}

function redactedParams(params) {
  const clone = structuredClone(params || {});
  if (clone.api_key) clone.api_key = "configured-secret";
  return clone;
}

class PipelineNode extends ClassicPreset.Node {
  constructor(step, index) {
    super(step.label);
    this.step = step;
    this.index = index;
    this.width = 210;
    this.height = taskKind(step) === "split" ? 176 : 142;
    if (index > 0) this.addInput("in", new ClassicPreset.Input(socket, "In"));
    this.addOutput("out", new ClassicPreset.Output(socket, "Next"));
    this.addControl("key", new ClassicPreset.InputControl("text", { initial: step.key, readonly: true }));
    this.addControl("meta", new ClassicPreset.InputControl("text", { initial: `${taskKind(step)} · ${step.on_error || "default"}`, readonly: true }));
    if (taskKind(step) === "split") {
      this.addControl("fanout", new ClassicPreset.InputControl("text", { initial: "fan-out boundary", readonly: true }));
    }
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
  return {
    destroy: () => area.destroy(),
  };
}

function nodePosition(index) {
  const positions = [
    { x: 60, y: 95 },
    { x: 305, y: 95 },
    { x: 550, y: 95 },
    { x: 305, y: 315 },
    { x: 60, y: 315 },
    { x: 550, y: 315 },
  ];
  if (index < positions.length) return positions[index];
  const column = index % 3;
  const row = Math.floor(index / 3);
  return { x: 60 + column * 245, y: 95 + row * 220 };
}

function PipelineNodeView({ data }) {
  const step = data.step;
  const kind = taskKind(step);
  const Icon = iconFor(step);
  const fieldCount = Object.keys(step.params.fields || {}).length;
  return (
    <div className={`rete-node-card ${kind} ${step.enabled === false ? "opacity-55" : ""}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <span className="node-icon">
            <Icon size={18} />
          </span>
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold">{step.label}</div>
            <div className="truncate font-mono text-[11px] text-base-content/55">{step.key}</div>
          </div>
        </div>
        <span className={`badge badge-sm ${kindBadgeClass(kind)}`}>{kind}</span>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2 text-[11px]">
        <Metric label="On error" value={step.on_error || "default"} />
        <Metric label="Status" value={step.enabled === false ? "Disabled" : "Enabled"} />
        {kind === "split" ? <Metric label="Fan-out" value={`${step.params.categories?.length || 0} category`} /> : null}
        {kind === "extract" ? <Metric label="Fields" value={`${fieldCount} fields`} /> : null}
        {kind === "storage" ? <Metric label="Output" value={step.params.files_dir || step.params.data_dir} /> : null}
      </div>
      {kind === "split" ? (
        <div className="mt-3 rounded-md border border-info/30 bg-info/10 px-2 py-1.5 text-[11px] leading-snug text-info-content">
          Child PDFs continue through downstream nodes. Fan-in remains implicit.
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
      <div className="pointer-events-none absolute left-4 top-4 flex gap-2">
        <span className="badge badge-neutral">Rete.js canvas</span>
        <span className="badge badge-outline">Selected node {selectedIndex + 1}</span>
      </div>
      <div className="pointer-events-none absolute bottom-4 left-4 rounded-lg border border-base-300 bg-base-100/90 px-3 py-2 text-xs shadow-sm">
        Drag nodes to rearrange visually. Use Move controls to change compiled serial order.
      </div>
    </div>
  );
}

function App() {
  const [steps, setSteps] = useState(defaultSteps);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [activeTab, setActiveTab] = useState("properties");
  const [search, setSearch] = useState("");
  const [sampleYaml, setSampleYaml] = useState("");
  const [simulated, setSimulated] = useState(false);
  const [collapsedPalette, setCollapsedPalette] = useState(false);

  const selected = steps[selectedIndex] || steps[0];
  const findings = useMemo(() => validateSteps(steps), [steps]);
  const compiledYaml = useMemo(() => yaml.dump(buildConfig(steps), { lineWidth: 110, noRefs: true }), [steps]);
  const enabledCount = steps.filter((step) => step.enabled !== false).length;
  const hasErrors = findings.some((finding) => finding.severity === "error");

  useEffect(() => {
    fetch("/config_sample_invoice.yaml")
      .then((response) => response.text())
      .then((text) => setSampleYaml(text))
      .catch(() => setSampleYaml("Unable to load copied sample config."));
  }, []);

  const selectNode = useCallback((index) => {
    setSelectedIndex(index);
    setActiveTab("properties");
  }, []);

  function updateStep(index, patch) {
    setSteps((current) =>
      current.map((step, stepIndex) => (stepIndex === index ? { ...step, ...patch } : step)),
    );
  }

  function updateParams(index, patch) {
    setSteps((current) =>
      current.map((step, stepIndex) =>
        stepIndex === index ? { ...step, params: { ...step.params, ...patch } } : step,
      ),
    );
  }

  function moveStep(index, direction) {
    const next = [...steps];
    const target = index + direction;
    if (target < 0 || target >= next.length) return;
    [next[index], next[target]] = [next[target], next[index]];
    setSteps(next);
    setSelectedIndex(target);
  }

  function deleteStep(index) {
    const next = steps.filter((_, stepIndex) => stepIndex !== index);
    setSteps(next);
    setSelectedIndex(Math.max(0, Math.min(index, next.length - 1)));
  }

  function addTask(task) {
    const existing = new Set(steps.map((step) => step.key));
    let suffix = 2;
    let key = task.key;
    while (existing.has(key)) {
      key = `${task.key}_${suffix}`;
      suffix += 1;
    }
    const nextTask = cloneTask(task);
    nextTask.key = key;
    nextTask.enabled = true;
    setSteps((current) => [...current, nextTask]);
    setSelectedIndex(steps.length);
  }

  function duplicateSelected() {
    if (!selected) return;
    const duplicate = cloneTask(selected, "copy");
    duplicate.key = uniqueKey(duplicate.key, steps);
    duplicate.label = `${selected.label} copy`;
    setSteps((current) => {
      const next = [...current];
      next.splice(selectedIndex + 1, 0, duplicate);
      return next;
    });
    setSelectedIndex(selectedIndex + 1);
  }

  function resetPrototype() {
    setSteps(defaultSteps);
    setSelectedIndex(0);
    setSimulated(false);
    setActiveTab("properties");
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
            <button
              className={`btn btn-ghost btn-square btn-sm mb-2 ${index === 1 ? "btn-active text-primary" : ""}`}
              title={label}
              key={label}
            >
              <Icon size={17} />
            </button>
          ))}
        </aside>
        <main className="flex min-w-0 flex-1 flex-col">
          <header className="flex min-h-20 flex-wrap items-center justify-between gap-3 border-b border-base-300 bg-base-100 px-5 py-4">
            <div>
              <div className="flex items-center gap-2">
                <span className="badge badge-primary badge-sm">Prototype</span>
                <span className="text-xs text-base-content/55">Admin / Pipeline Builder</span>
              </div>
              <h1 className="mt-1 text-xl font-semibold">Visual Pipeline Builder</h1>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <button className="btn btn-ghost btn-sm" onClick={resetPrototype}>
                <RotateCcw size={15} /> Reset
              </button>
              <button className="btn btn-outline btn-sm" onClick={() => setSimulated(true)}>
                <Play size={15} /> Simulate run
              </button>
              <button className={`btn btn-primary btn-sm ${hasErrors ? "btn-disabled" : ""}`}>
                <Save size={15} /> Publish draft
              </button>
            </div>
          </header>

          <section className="grid gap-3 border-b border-base-300 bg-base-100/70 px-5 py-3 md:grid-cols-4">
            <StatusStat label="Enabled steps" value={`${enabledCount}/${steps.length}`} icon={ListChecks} />
            <StatusStat label="Split behavior" value={steps.some((step) => taskKind(step) === "split") ? "Fan-out boundary" : "None"} icon={Split} />
            <StatusStat label="Validation" value={hasErrors ? "Needs fixes" : "Ready"} icon={hasErrors ? AlertTriangle : CheckCircle2} tone={hasErrors ? "warning" : "success"} />
            <StatusStat label="Runtime model" value="tasks + pipeline" icon={FileText} />
          </section>

          <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 p-4 xl:grid-cols-[minmax(13rem,16rem)_minmax(42rem,1fr)_minmax(21rem,25rem)]">
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
                  <p className="text-xs text-base-content/55">Normal nodes compile left to right. Split fans out at runtime, then children continue downstream.</p>
                </div>
                <div className="join">
                  <button className="btn join-item btn-sm" disabled={selectedIndex === 0} onClick={() => moveStep(selectedIndex, -1)}>
                    <ChevronLeft size={15} /> Move earlier
                  </button>
                  <button className="btn join-item btn-sm" disabled={selectedIndex >= steps.length - 1} onClick={() => moveStep(selectedIndex, 1)}>
                    Move later <ChevronRight size={15} />
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
              duplicateSelected={duplicateSelected}
              deleteStep={deleteStep}
              findings={findings}
              compiledYaml={compiledYaml}
              sampleYaml={sampleYaml}
            />
          </div>
        </main>
      </div>
    </div>
  );
}

function uniqueKey(base, steps) {
  const used = new Set(steps.map((step) => step.key));
  let candidate = base;
  let count = 2;
  while (used.has(candidate)) {
    candidate = `${base}_${count}`;
    count += 1;
  }
  return candidate;
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
  const filtered = taskCatalog.filter((task) => `${task.label} ${task.category} ${task.class}`.toLowerCase().includes(search.toLowerCase()));
  return (
    <section className={`min-w-0 rounded-lg border border-base-300 bg-base-100 ${collapsed ? "xl:w-14" : ""}`}>
      <div className="flex items-center justify-between border-b border-base-300 p-3">
        {!collapsed ? (
          <div>
            <h2 className="text-sm font-semibold">Task Palette</h2>
            <p className="text-xs text-base-content/50">Approved standard steps</p>
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
                    <span className="block truncate text-xs text-base-content/50">{task.category} · {task.class}</span>
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
  const { step, activeTab, setActiveTab, findings, compiledYaml, sampleYaml } = props;
  if (!step) {
    return <section className="rounded-lg border border-base-300 bg-base-100 p-4">No step selected</section>;
  }
  const KindIcon = iconFor(step);
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
        <div className="mt-4 grid grid-cols-3 gap-1 rounded-lg bg-base-200 p-1 text-xs">
          {["properties", "validate", "yaml"].map((tab) => (
            <button key={tab} className={`rounded-md px-2 py-1.5 capitalize ${activeTab === tab ? "bg-base-100 font-semibold shadow-sm" : "text-base-content/60"}`} onClick={() => setActiveTab(tab)}>
              {tab}
            </button>
          ))}
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-auto p-4">
        {activeTab === "properties" ? <StepProperties {...props} /> : null}
        {activeTab === "validate" ? <ValidationPanel findings={findings} /> : null}
        {activeTab === "yaml" ? <YamlPanel compiledYaml={compiledYaml} sampleYaml={sampleYaml} /> : null}
      </div>
    </section>
  );
}

function StepProperties({ step, index, updateStep, updateParams, duplicateSelected, deleteStep }) {
  const kind = taskKind(step);
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <TextControl label="Label" value={step.label} onChange={(value) => updateStep(index, { label: value })} />
        <TextControl label="Key" value={step.key} onChange={(value) => updateStep(index, { key: value.replace(/[^A-Za-z0-9_]/g, "_") })} mono />
        <SelectControl label="On error" value={step.on_error} onChange={(value) => updateStep(index, { on_error: value })} options={["stop", "continue"]} />
        <label className="flex items-end gap-3 rounded-lg border border-base-300 px-3 py-2">
          <input type="checkbox" className="toggle toggle-sm" checked={step.enabled !== false} onChange={(event) => updateStep(index, { enabled: event.target.checked })} />
          <span className="pb-1 text-sm">Enabled</span>
        </label>
      </div>
      <div className="rounded-lg border border-base-300 bg-base-200/50 p-3">
        <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-base-content/45">Task-specific controls</div>
        {kind === "split" ? <SplitControls step={step} index={index} updateParams={updateParams} /> : null}
        {kind === "extract" ? <ExtractControls step={step} index={index} updateParams={updateParams} /> : null}
        {kind === "storage" ? <StorageControls step={step} index={index} updateParams={updateParams} /> : null}
        {kind === "review" ? <ReviewControls step={step} index={index} updateParams={updateParams} /> : null}
        {kind === "archive" ? <TextControl label="Archive directory" value={step.params.archive_dir || ""} onChange={(value) => updateParams(index, { archive_dir: value })} /> : null}
      </div>
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
      <SecretStatus />
      <SelectControl label="Uncategorized pages" value={step.params.allow_uncategorized || "include"} onChange={(value) => updateParams(index, { allow_uncategorized: value })} options={["include", "forbid", "omit"]} />
      <TextControl label="Split output directory" value={step.params.split_dir || ""} onChange={(value) => updateParams(index, { split_dir: value })} mono />
      <TextControl
        label="Category name"
        value={category.name}
        onChange={(value) => updateParams(index, { categories: [{ ...category, name: value }] })}
      />
      <TextAreaControl
        label="Category description"
        value={category.description}
        onChange={(value) => updateParams(index, { categories: [{ ...category, description: value }] })}
      />
      <div className="alert border-info/25 bg-info/10 text-xs">
        <Info size={15} />
        <span>The visual fan-out is explanatory. The backend still compiles to the serial pipeline and lets `LlamaCloudSplitTask` create child workflows.</span>
      </div>
    </div>
  );
}

function ExtractControls({ step, index, updateParams }) {
  const fields = Object.entries(step.params.fields || {});
  return (
    <div className="space-y-3">
      <SecretStatus />
      <TextControl label="LlamaExtract configuration ID" value={step.params.configuration_id || ""} onChange={(value) => updateParams(index, { configuration_id: value })} mono />
      <div className="grid grid-cols-2 gap-3">
        <SelectControl label="Tier" value={step.params.tier || "agentic"} onChange={(value) => updateParams(index, { tier: value })} options={["agentic", "premium", "balanced"]} />
        <SelectControl label="Target" value={step.params.extraction_target || "per_doc"} onChange={(value) => updateParams(index, { extraction_target: value })} options={["per_doc", "per_page", "per_table_row"]} />
      </div>
      <div className="overflow-hidden rounded-lg border border-base-300 bg-base-100">
        <div className="flex items-center justify-between border-b border-base-300 px-3 py-2">
          <span className="text-sm font-semibold">Fields</span>
          <span className="badge badge-sm">{fields.length}</span>
        </div>
        <div className="max-h-64 overflow-auto">
          {fields.map(([key, config]) => (
            <div key={key} className="grid grid-cols-[1fr_max-content] gap-2 border-b border-base-200 px-3 py-2 last:border-b-0">
              <div className="min-w-0">
                <div className="truncate font-mono text-xs font-semibold">{key}</div>
                <div className="truncate text-xs text-base-content/50">{config.alias} · {config.type}</div>
              </div>
              {config.is_table ? <span className="badge badge-info badge-sm">table</span> : <span className="badge badge-ghost badge-sm">field</span>}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function StorageControls({ step, index, updateParams }) {
  const isPdf = step.class === "StoreFileToLocaldrive";
  return (
    <div className="space-y-3">
      <TextControl label={isPdf ? "PDF output directory" : "JSON output directory"} value={isPdf ? step.params.files_dir || "" : step.params.data_dir || ""} onChange={(value) => updateParams(index, isPdf ? { files_dir: value } : { data_dir: value })} mono />
      <TextControl label="Filename template" value={step.params.filename || ""} onChange={(value) => updateParams(index, { filename: value })} mono />
      <div className="rounded-lg border border-base-300 bg-base-100 p-3 text-xs">
        <div className="mb-2 font-semibold">Available tokens</div>
        <div className="flex flex-wrap gap-1">
          {["invoiceNumber", "totalAmount", "invoiceDate", "billTo", "id", "original_filename"].map((token) => (
            <span className="badge badge-outline badge-sm font-mono" key={token}>{`{${token}}`}</span>
          ))}
        </div>
      </div>
    </div>
  );
}

function ReviewControls({ step, index, updateParams }) {
  return (
    <div className="space-y-3">
      <NumberControl label="Confidence threshold" value={step.params.confidence_threshold || 0.8} min={0} max={1} step={0.01} onChange={(value) => updateParams(index, { confidence_threshold: value })} />
      <TextControl label="Schema file" value={step.params.schema_file || ""} onChange={(value) => updateParams(index, { schema_file: value })} mono />
      <TextControl label="Queue" value={step.params.queue_name || ""} onChange={(value) => updateParams(index, { queue_name: value })} />
    </div>
  );
}

function SecretStatus() {
  return (
    <div className="flex items-center gap-2 rounded-lg border border-base-300 bg-base-100 px-3 py-2 text-xs">
      <span className="flex h-7 w-7 items-center justify-center rounded-md bg-success/15 text-success">
        <KeyRound size={14} />
      </span>
      <span className="min-w-0 flex-1">API key is configured but redacted in the builder.</span>
      <Lock size={14} className="text-base-content/45" />
    </div>
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

function YamlPanel({ compiledYaml, sampleYaml }) {
  return (
    <div className="space-y-4">
      <div>
        <div className="mb-2 flex items-center justify-between">
          <span className="text-sm font-semibold">Compiled YAML preview</span>
          <span className="badge badge-sm">safe authoring layer</span>
        </div>
        <pre className="yaml-box">{compiledYaml}</pre>
      </div>
      <details className="rounded-lg border border-base-300 bg-base-100">
        <summary className="cursor-pointer px-3 py-2 text-sm font-semibold">Copied sample config source</summary>
        <pre className="yaml-box max-h-64 rounded-t-none">{sampleYaml}</pre>
      </details>
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
          <p className="text-xs text-base-content/55">Four-page merged invoice PDF becomes four child invoice documents.</p>
        </div>
        <button className="btn btn-ghost btn-square btn-sm" onClick={close}>
          <X size={15} />
        </button>
      </div>
      <div className="grid gap-2 md:grid-cols-4">
        {[1, 2, 3, 4].map((page) => (
          <div className="rounded-lg border border-base-300 bg-base-200 p-3" key={page}>
            <div className="mb-2 flex items-center justify-between">
              <span className="font-semibold">Child invoice {page}</span>
              <span className="badge badge-info badge-sm">page {page}</span>
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
      <input className={`input input-bordered input-sm ${mono ? "font-mono" : ""}`} value={value || ""} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

function TextAreaControl({ label, value, onChange }) {
  return (
    <label className="form-control">
      <span className="label-text mb-1 text-xs">{label}</span>
      <textarea className="textarea textarea-bordered min-h-24 text-sm" value={value || ""} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

function SelectControl({ label, value, onChange, options }) {
  return (
    <label className="form-control">
      <span className="label-text mb-1 text-xs">{label}</span>
      <select className="select select-bordered select-sm" value={value || ""} onChange={(event) => onChange(event.target.value)}>
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
