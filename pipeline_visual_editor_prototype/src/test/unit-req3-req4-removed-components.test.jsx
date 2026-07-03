// Unit tests — Req 3, 4: removed components are absent
// Validates: Requirements 3.1, 3.2, 4.1

import { describe, it, expect, vi, beforeAll, afterAll } from "vitest";
import { render, screen } from "@testing-library/react";
import { App } from "../main.jsx";

// Mock fetch so App can load without a real server
beforeAll(() => {
  global.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({
      config: {
        tasks: {
          extract_doc: {
            module: "standard_step.extraction.extract_pdf",
            class: "ExtractPdfTask",
            params: { api_key: "test", fields: { invoice_number: { alias: "Invoice #", type: "str" } } },
          },
        },
        pipeline: ["extract_doc"],
      },
      rawYaml: "",
      relativePath: "test.yaml",
      modifiedTime: new Date().toISOString(),
    }),
  });
});

afterAll(() => {
  vi.restoreAllMocks();
});

describe("Unit — Req 3, 4: removed components are absent", () => {
  it("RunSimulation is not rendered anywhere in App output", async () => {
    const { container } = render(<App />);
    // Wait for loading to complete
    await screen.findByText("Visual Pipeline Builder");

    // The RunSimulation overlay showed a heading "Simulated run" - it should be gone
    const simText = container.querySelector("*");
    const allText = container.textContent;
    expect(allText).not.toContain("Simulated run");
    expect(allText).not.toContain("Simulate run");
  });

  it("StatusStat grid section is absent from App output", async () => {
    const { container } = render(<App />);
    await screen.findByText("Visual Pipeline Builder");

    // StatusStat showed labels like "Enabled steps", "Dirty state", "Validation", "Runtime model"
    const allText = container.textContent;
    expect(allText).not.toContain("Enabled steps");
    expect(allText).not.toContain("Dirty state");
    expect(allText).not.toContain("Runtime model");
  });

  it("Simulate run button is absent from App header", async () => {
    render(<App />);
    await screen.findByText("Visual Pipeline Builder");

    const buttons = screen.queryAllByRole("button");
    const simulateBtn = buttons.find((btn) => btn.textContent.includes("Simulate run"));
    expect(simulateBtn).toBeUndefined();
  });
});
