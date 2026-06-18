import react from "@vitejs/plugin-react";
import { execFile } from "node:child_process";
import fs from "node:fs/promises";
import path from "node:path";
import { promisify } from "node:util";
import yaml from "js-yaml";
import { defineConfig } from "vite";

const configPath = path.resolve(process.cwd(), "public", "config_sample_invoice.yaml");
const projectRoot = path.resolve(process.cwd(), "..");
const execFileAsync = promisify(execFile);

function jsonResponse(res, statusCode, payload) {
  res.statusCode = statusCode;
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.end(JSON.stringify(payload));
}

function readJsonBody(req) {
  return new Promise((resolve, reject) => {
    let body = "";
    req.on("data", (chunk) => {
      body += chunk;
      if (body.length > 5_000_000) {
        reject(new Error("Request body is too large."));
        req.destroy();
      }
    });
    req.on("end", () => {
      try {
        resolve(body ? JSON.parse(body) : {});
      } catch (error) {
        reject(new Error(`Invalid JSON request body: ${error.message}`));
      }
    });
    req.on("error", reject);
  });
}

async function validateConfig(config) {
  const findings = [];
  if (!config || typeof config !== "object" || Array.isArray(config)) {
    findings.push("YAML root must be an object.");
    return findings;
  }
  if (!config.tasks || typeof config.tasks !== "object" || Array.isArray(config.tasks)) {
    findings.push("tasks must be a mapping.");
  }
  if (!Array.isArray(config.pipeline)) {
    findings.push("pipeline must be a list.");
  }
  if (findings.length) return findings;

  const seen = new Set();
  for (const [index, key] of config.pipeline.entries()) {
    if (typeof key !== "string" || !key.trim()) {
      findings.push(`pipeline[${index}] must be a non-empty string.`);
      continue;
    }
    if (seen.has(key)) findings.push(`pipeline contains duplicate key '${key}'.`);
    seen.add(key);
    if (!Object.prototype.hasOwnProperty.call(config.tasks, key)) {
      findings.push(`pipeline key '${key}' is missing from tasks.`);
    }
  }

  for (const [key, task] of Object.entries(config.tasks)) {
    if (!task || typeof task !== "object" || Array.isArray(task)) {
      findings.push(`tasks.${key} must be an object.`);
      continue;
    }
    if (typeof task.module !== "string" || !task.module.trim()) {
      findings.push(`tasks.${key}.module must be a non-empty string.`);
    }
    if (typeof task.class !== "string" || !task.class.trim()) {
      findings.push(`tasks.${key}.class must be a non-empty string.`);
    }
    if (task.params !== undefined && (!task.params || typeof task.params !== "object" || Array.isArray(task.params))) {
      findings.push(`tasks.${key}.params must be a mapping.`);
    }
    if (!task.params || typeof task.params !== "object" || Array.isArray(task.params)) continue;
    for (const paramName of ["data_dir", "files_dir", "archive_dir", "split_dir", "processing_dir"]) {
      if (!task.params[paramName]) continue;
      try {
        const stats = await fs.stat(resolveConfigPath(task.params[paramName]));
        if (!stats.isDirectory()) findings.push(`tasks.${key}.params.${paramName} must reference a directory.`);
      } catch {
        findings.push(`tasks.${key}.params.${paramName} references a directory that does not exist.`);
      }
    }
    for (const paramName of ["reference_file", "schema_file"]) {
      if (!task.params[paramName]) continue;
      try {
        const stats = await fs.stat(resolveConfigPath(task.params[paramName]));
        if (!stats.isFile()) findings.push(`tasks.${key}.params.${paramName} must reference a file.`);
      } catch {
        findings.push(`tasks.${key}.params.${paramName} references a file that does not exist.`);
      }
    }
    if (task.params.reference_file && task.params.csv_match?.clauses) {
      try {
        const { columns } = await loadCsvColumns(task.params.reference_file);
        if (task.params.update_field && !columns.includes(task.params.update_field)) {
          findings.push(`tasks.${key}.params.update_field is not a column in ${task.params.reference_file}.`);
        }
        for (const [index, clause] of task.params.csv_match.clauses.entries()) {
          if (clause?.column && !columns.includes(clause.column)) {
            findings.push(`tasks.${key}.params.csv_match.clauses[${index}].column is not a column in ${task.params.reference_file}.`);
          }
        }
      } catch {
        findings.push(`tasks.${key}.params.reference_file could not be read for CSV validation.`);
      }
    }
  }
  return findings;
}

function safeProjectPath(relativePath = "") {
  const cleanPath = String(relativePath || "").replace(/\\/g, "/").replace(/^\/+/, "");
  const resolved = path.resolve(projectRoot, cleanPath);
  const relative = path.relative(projectRoot, resolved);
  if (relative.startsWith("..") || path.isAbsolute(relative)) {
    throw new Error("Path is outside the project root.");
  }
  return resolved;
}

function resolveConfigPath(value = "") {
  const text = String(value || "").trim();
  if (!text) throw new Error("Path value is empty.");
  if (path.isAbsolute(text)) return path.resolve(text);
  return safeProjectPath(text);
}

function toProjectRelative(absolutePath) {
  const relative = path.relative(projectRoot, absolutePath).replace(/\\/g, "/");
  return relative === "" ? "." : relative;
}

function toStoredPath(absolutePath) {
  const relative = path.relative(projectRoot, absolutePath);
  if (!relative.startsWith("..") && !path.isAbsolute(relative)) return toProjectRelative(absolutePath);
  return path.resolve(absolutePath);
}

async function pickWindowsDirectory(startPath) {
  let initialDirectory = projectRoot;
  try {
    if (startPath) initialDirectory = resolveConfigPath(startPath);
  } catch {
    initialDirectory = projectRoot;
  }
  const safeInitialDirectory = String(initialDirectory).replace(/\r?\n/g, " ");
  const script = `
Add-Type -AssemblyName System.Windows.Forms
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
$dialog.Description = "Select directory for prototype config"
$dialog.ShowNewFolderButton = $true
$dialog.SelectedPath = @'
${safeInitialDirectory}
'@
$result = $dialog.ShowDialog()
if ($result -eq [System.Windows.Forms.DialogResult]::OK) {
  Write-Output $dialog.SelectedPath
} else {
  Write-Output "__CANCELLED__"
}
`;
  const { stdout } = await execFileAsync(
    "powershell.exe",
    ["-NoProfile", "-STA", "-ExecutionPolicy", "Bypass", "-Command", script],
    { windowsHide: false, timeout: 300_000 },
  );
  const selectedPath = stdout.trim();
  if (!selectedPath || selectedPath === "__CANCELLED__") return { cancelled: true };
  const stats = await fs.stat(selectedPath);
  if (!stats.isDirectory()) throw new Error("Selected path is not a directory.");
  const storedPath = toStoredPath(selectedPath);
  return {
    cancelled: false,
    absolutePath: path.resolve(selectedPath),
    path: storedPath,
    pathType: path.isAbsolute(storedPath) ? "absolute" : "project-relative",
  };
}

async function listDirectories(relativePath) {
  const directory = safeProjectPath(relativePath);
  const entries = await fs.readdir(directory, { withFileTypes: true });
  return {
    current: toProjectRelative(directory),
    parent: toProjectRelative(path.dirname(directory)),
    entries: entries
      .filter((entry) => entry.isDirectory() && !entry.name.startsWith(".") && entry.name !== "node_modules")
      .map((entry) => {
        const absolute = path.join(directory, entry.name);
        return { name: entry.name, path: toProjectRelative(absolute) };
      })
      .sort((a, b) => a.name.localeCompare(b.name)),
  };
}

async function listFiles(relativePath, extensionsText) {
  const directory = safeProjectPath(relativePath);
  const extensions = String(extensionsText || "")
    .split(",")
    .map((extension) => extension.trim().toLowerCase())
    .filter(Boolean);
  const entries = await fs.readdir(directory, { withFileTypes: true });
  return {
    current: toProjectRelative(directory),
    parent: toProjectRelative(path.dirname(directory)),
    directories: entries
      .filter((entry) => entry.isDirectory() && !entry.name.startsWith(".") && entry.name !== "node_modules")
      .map((entry) => {
        const absolute = path.join(directory, entry.name);
        return { name: entry.name, path: toProjectRelative(absolute) };
      })
      .sort((a, b) => a.name.localeCompare(b.name)),
    files: entries
      .filter((entry) => {
        if (!entry.isFile()) return false;
        if (!extensions.length) return true;
        return extensions.includes(path.extname(entry.name).toLowerCase());
      })
      .map((entry) => {
        const absolute = path.join(directory, entry.name);
        return { name: entry.name, path: toProjectRelative(absolute), extension: path.extname(entry.name).toLowerCase() };
      })
      .sort((a, b) => a.name.localeCompare(b.name)),
  };
}

function parseCsvHeaderLine(line) {
  const columns = [];
  let current = "";
  let quoted = false;
  for (let index = 0; index < line.length; index += 1) {
    const char = line[index];
    if (char === '"' && line[index + 1] === '"') {
      current += '"';
      index += 1;
    } else if (char === '"') {
      quoted = !quoted;
    } else if (char === "," && !quoted) {
      columns.push(current.trim());
      current = "";
    } else {
      current += char;
    }
  }
  columns.push(current.trim());
  return columns.filter(Boolean);
}

async function loadCsvColumns(relativePath) {
  const filePath = safeProjectPath(relativePath);
  const text = await fs.readFile(filePath, "utf8");
  const header = text.split(/\r?\n/, 1)[0] || "";
  return { path: toProjectRelative(filePath), columns: parseCsvHeaderLine(header) };
}

async function loadConfigPayload() {
  const rawYaml = await fs.readFile(configPath, "utf8");
  const parsed = yaml.load(rawYaml) || {};
  const stats = await fs.stat(configPath);
  return {
    config: parsed,
    rawYaml,
    filePath: configPath,
    relativePath: "public/config_sample_invoice.yaml",
    modifiedTime: stats.mtime.toISOString(),
  };
}

function prototypeConfigApi() {
  return {
    name: "prototype-config-api",
    configureServer(server) {
      server.middlewares.use("/api/prototype/fs/directories", async (req, res) => {
        try {
          const url = new URL(req.url || "", "http://prototype.local");
          if (req.method === "GET") {
            jsonResponse(res, 200, await listDirectories(url.searchParams.get("path") || "."));
            return;
          }
          if (req.method === "POST") {
            const body = await readJsonBody(req);
            const target = safeProjectPath(body.path || "");
            await fs.mkdir(target, { recursive: true });
            jsonResponse(res, 200, { path: toProjectRelative(target), created: true });
            return;
          }
          res.statusCode = 405;
          res.setHeader("Allow", "GET, POST");
          res.end();
        } catch (error) {
          jsonResponse(res, 400, { error: error.message || "Directory request failed." });
        }
      });
      server.middlewares.use("/api/prototype/fs/files", async (req, res) => {
        try {
          const url = new URL(req.url || "", "http://prototype.local");
          jsonResponse(
            res,
            200,
            await listFiles(url.searchParams.get("path") || ".", url.searchParams.get("extensions") || ""),
          );
        } catch (error) {
          jsonResponse(res, 400, { error: error.message || "File request failed." });
        }
      });
      server.middlewares.use("/api/prototype/fs/pick-directory", async (req, res) => {
        try {
          if (req.method !== "POST") {
            res.statusCode = 405;
            res.setHeader("Allow", "POST");
            res.end();
            return;
          }
          const body = await readJsonBody(req);
          jsonResponse(res, 200, await pickWindowsDirectory(body.path || "."));
        } catch (error) {
          jsonResponse(res, 400, { error: error.message || "Directory picker failed." });
        }
      });
      server.middlewares.use("/api/prototype/fs/csv", async (req, res) => {
        try {
          const url = new URL(req.url || "", "http://prototype.local");
          jsonResponse(res, 200, await loadCsvColumns(url.searchParams.get("path") || ""));
        } catch (error) {
          jsonResponse(res, 400, { error: error.message || "CSV request failed." });
        }
      });
      server.middlewares.use("/api/prototype/config", async (req, res) => {
        try {
          if (req.method === "GET") {
            jsonResponse(res, 200, await loadConfigPayload());
            return;
          }
          if (req.method === "PUT") {
            const body = await readJsonBody(req);
            const nextConfig = body.config;
            const findings = await validateConfig(nextConfig);
            if (findings.length) {
              jsonResponse(res, 400, { error: "Config validation failed.", findings });
              return;
            }
            const nextYaml = yaml.dump(nextConfig, {
              lineWidth: 110,
              noRefs: true,
              sortKeys: false,
            });
            const backupPath = `${configPath}.bak`;
            const tempPath = `${configPath}.tmp`;
            try {
              await fs.copyFile(configPath, backupPath);
            } catch (error) {
              if (error.code !== "ENOENT") throw error;
            }
            await fs.writeFile(tempPath, nextYaml, "utf8");
            await fs.rename(tempPath, configPath);
            jsonResponse(res, 200, await loadConfigPayload());
            return;
          }
          res.statusCode = 405;
          res.setHeader("Allow", "GET, PUT");
          res.end();
        } catch (error) {
          jsonResponse(res, 500, { error: error.message || "Prototype config API failed." });
        }
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), prototypeConfigApi()],
});
