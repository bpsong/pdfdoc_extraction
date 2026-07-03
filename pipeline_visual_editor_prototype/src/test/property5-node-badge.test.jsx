// Feature: pipeline-editor-ux-improvements, Property 5: Node error badge count equals findings error count
// Validates: Requirements 6.1, 6.2

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import * as fc from "fast-check";
import { OrderedPipeline } from "../main.jsx";
import { makeStep, makeFinding } from "./helpers.js";

describe("Property 5: Node error badge count equals findings error count for each step", () => {
  it("property: badge is absent when no findings match step.key with severity=error", () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 3, maxLength: 10 }),     // step key
        fc.array(
          fc.record({
            severity: fc.constantFrom("warning", "success"),
            code: fc.string({ minLength: 2, maxLength: 10 }),
            path: fc.string({ minLength: 2, maxLength: 30 }),
            message: fc.string({ minLength: 5, maxLength: 40 }),
          }),
          { maxLength: 5 }
        ),
        (stepKey, findings) => {
          const step = makeStep({ key: stepKey });
          const { container, unmount } = render(
            <OrderedPipeline
              steps={[step]}
              selectedIndex={0}
              onSelect={() => {}}
              onInsert={() => {}}
              findings={findings}
            />
          );
          const badge = container.querySelector(".badge-error");
          expect(badge).toBeNull();
          unmount();
        }
      ),
      { numRuns: 50 }
    );
  });

  it("property: badge shows exact count of error findings matching step.key", () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 3, maxLength: 10 }),    // step key
        fc.nat(4),                                      // matching error count
        fc.nat(3),                                      // non-matching findings count
        (stepKey, matchingErrors, otherCount) => {
          const matchingFindings = Array.from({ length: matchingErrors }, (_, i) =>
            makeFinding({ severity: "error", path: `tasks.${stepKey}.params.field${i}` })
          );
          const otherFindings = Array.from({ length: otherCount }, (_, i) =>
            makeFinding({ severity: "error", path: `tasks.other_step.params.field${i}` })
          );
          const allFindings = [...matchingFindings, ...otherFindings];

          const step = makeStep({ key: stepKey });
          const { container, unmount } = render(
            <OrderedPipeline
              steps={[step]}
              selectedIndex={0}
              onSelect={() => {}}
              onInsert={() => {}}
              findings={allFindings}
            />
          );

          const badge = container.querySelector(".badge-error");
          if (matchingErrors === 0) {
            expect(badge).toBeNull();
          } else {
            expect(badge).not.toBeNull();
            expect(badge.textContent).toBe(String(matchingErrors));
          }
          unmount();
        }
      ),
      { numRuns: 100 }
    );
  });

  it("badge is absent when there are no error findings", () => {
    const step = makeStep({ key: "my_step" });
    render(
      <OrderedPipeline
        steps={[step]}
        selectedIndex={0}
        onSelect={() => {}}
        onInsert={() => {}}
        findings={[]}
      />
    );
    const badge = document.querySelector(".badge-error");
    expect(badge).toBeNull();
  });

  it("badge shows count 2 when two errors match the step key", () => {
    const step = makeStep({ key: "my_step" });
    const findings = [
      makeFinding({ severity: "error", path: "tasks.my_step.params.api_key" }),
      makeFinding({ severity: "error", path: "tasks.my_step.params.fields" }),
      makeFinding({ severity: "warning", path: "tasks.my_step.params.tier" }),
    ];
    const { container } = render(
      <OrderedPipeline
        steps={[step]}
        selectedIndex={0}
        onSelect={() => {}}
        onInsert={() => {}}
        findings={findings}
      />
    );
    const badge = container.querySelector(".badge-error");
    expect(badge).not.toBeNull();
    expect(badge.textContent).toBe("2");
  });
});
