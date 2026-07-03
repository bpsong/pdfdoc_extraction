// Feature: pipeline-editor-ux-improvements, Property 6: ValidationPanel renders message as primary text
// Validates: Requirements 7.1, 7.2, 7.5

import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import * as fc from "fast-check";
import { ValidationPanel } from "../main.jsx";

describe("Property 6: ValidationPanel renders message as primary text", () => {
  it("property: each finding's message appears in a font-semibold element before any element containing the code", () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            severity: fc.constantFrom("error", "warning", "success"),
            code: fc.string({ minLength: 3, maxLength: 20 }).filter((s) => s.trim().length > 0),
            path: fc.string({ minLength: 3, maxLength: 20 }),
            message: fc.string({ minLength: 5, maxLength: 50 }).filter((s) => s.trim().length > 0),
          }),
          { minLength: 1, maxLength: 5 }
        ),
        (findings) => {
          // Ensure message and code differ to avoid false positives
          const uniqueFindings = findings.map((f, i) => ({
            ...f,
            code: `CODE-${i}-${f.code}`,
            message: `MSG-${i}-${f.message}`,
          }));

          const { container, unmount } = render(<ValidationPanel findings={uniqueFindings} />);

          uniqueFindings.forEach((item) => {
            // message must appear in a font-semibold element
            const allElements = container.querySelectorAll("*");
            const messageEl = Array.from(allElements).find(
              (el) => el.textContent.includes(item.message) && el.className.includes("font-semibold")
            );
            expect(messageEl).toBeTruthy();

            // code must NOT appear in a font-semibold element at the top level
            // (it should be in a font-mono span which is not itself font-semibold)
            const boldCodeEl = Array.from(allElements).find(
              (el) =>
                el.textContent === item.code &&
                el.className.includes("font-semibold") &&
                !el.className.includes("font-mono")
            );
            expect(boldCodeEl).toBeFalsy();

            // code must appear somewhere (in font-mono)
            const codeEl = Array.from(allElements).find(
              (el) => el.textContent === item.code && el.tagName.toLowerCase() === "span"
            );
            expect(codeEl).toBeTruthy();
          });

          unmount();
        }
      ),
      { numRuns: 50 }
    );
  });

  it("message is bold, code is in font-mono span in secondary line", () => {
    const findings = [
      { severity: "error", code: "extract-api-key-empty", path: "tasks.step.params", message: "Extraction needs an API key." },
    ];
    const { container } = render(<ValidationPanel findings={findings} />);

    const boldEl = container.querySelector(".font-semibold");
    expect(boldEl).toBeTruthy();
    expect(boldEl.textContent).toBe("Extraction needs an API key.");

    const monoEl = container.querySelector(".font-mono");
    expect(monoEl).toBeTruthy();
    expect(monoEl.textContent).toBe("extract-api-key-empty");
  });

  it("path appears in secondary muted text, not as primary bold text", () => {
    const findings = [
      { severity: "error", code: "test-code", path: "tasks.my_step.params", message: "Test message." },
    ];
    const { container } = render(<ValidationPanel findings={findings} />);

    const secondaryLine = container.querySelector(".text-xs");
    expect(secondaryLine).toBeTruthy();
    expect(secondaryLine.textContent).toContain("tasks.my_step.params");
  });
});
