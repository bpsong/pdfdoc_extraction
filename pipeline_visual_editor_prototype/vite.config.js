import react from "@vitejs/plugin-react";
import fs from "node:fs/promises";
import path from "node:path";
import yaml from "js-yaml";
import { defineConfig } from "vite";

const configPath = path.resolve(process.cwd(), "public", "config_sample_invoice.yaml");

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

function validateConfig(config) {
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
  }
  return findings;
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
      server.middlewares.use("/api/prototype/config", async (req, res) => {
        try {
          if (req.method === "GET") {
            jsonResponse(res, 200, await loadConfigPayload());
            return;
          }
          if (req.method === "PUT") {
            const body = await readJsonBody(req);
            const nextConfig = body.config;
            const findings = validateConfig(nextConfig);
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
