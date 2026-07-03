// Feature: pipeline-editor-ux-improvements, Property 10: AdvancedParamsEditor live error round-trip
// Validates: Requirements 11.2, 11.3, 11.4

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, fireEvent, act } from "@testing-library/react";
import * as fc from "fast-check";
import { AdvancedParamsEditor } from "../main.jsx";

const baseStep = {
  key: "test_step",
  params: { api_key: "test" },
};

describe("Property 10: AdvancedParamsEditor live error round-trip", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("property: liveError is shown iff text is non-empty and invalid JSON (after 300ms)", () => {
    fc.assert(
      fc.property(
        fc.oneof(
          fc.constant(""),                                          // empty
          fc.constant("   "),                                      // whitespace
          fc.jsonValue().map((v) => JSON.stringify(v)),            // valid JSON
          fc.string({ minLength: 1 }).filter((s) => {              // invalid JSON
            try { JSON.parse(s); return false; } catch { return true; }
          })
        ),
        (text) => {
          const { container, unmount } = render(
            <AdvancedParamsEditor step={baseStep} index={0} replaceParams={() => {}} />
          );

          // Find the textarea (the advanced params section)
          const details = container.querySelector("details");
          // Open the details
          details.open = true;
          const textarea = container.querySelector("textarea");

          fireEvent.change(textarea, { target: { value: text } });

          act(() => {
            vi.advanceTimersByTime(300);
          });

          const errorEl = container.querySelector(".text-error:not(.alert-error)");

          const isValidJson = (() => {
            try {
              if (!text.trim()) return null; // empty
              JSON.parse(text);
              return true;
            } catch {
              return false;
            }
          })();

          if (isValidJson === null) {
            // empty — no error
            expect(errorEl).toBeNull();
          } else if (isValidJson) {
            // valid JSON — no live error
            expect(errorEl).toBeNull();
          } else {
            // invalid JSON — error shown
            expect(errorEl).not.toBeNull();
          }

          unmount();
        }
      ),
      { numRuns: 50 }
    );
  });

  it("shows live error after 300ms for invalid JSON", () => {
    const { container } = render(
      <AdvancedParamsEditor step={baseStep} index={0} replaceParams={() => {}} />
    );
    const details = container.querySelector("details");
    details.open = true;
    const textarea = container.querySelector("textarea");

    fireEvent.change(textarea, { target: { value: "{ invalid json" } });
    act(() => vi.advanceTimersByTime(300));

    const errorEl = container.querySelector(".text-error:not(.alert-error)");
    expect(errorEl).not.toBeNull();
    expect(errorEl.textContent).toContain("JSON");
  });

  it("clears live error for valid JSON", () => {
    const { container } = render(
      <AdvancedParamsEditor step={baseStep} index={0} replaceParams={() => {}} />
    );
    const details = container.querySelector("details");
    details.open = true;
    const textarea = container.querySelector("textarea");

    // First make it invalid
    fireEvent.change(textarea, { target: { value: "{ bad" } });
    act(() => vi.advanceTimersByTime(300));

    // Now make it valid
    fireEvent.change(textarea, { target: { value: '{"key": "value"}' } });
    act(() => vi.advanceTimersByTime(300));

    const errorEl = container.querySelector(".text-error:not(.alert-error)");
    expect(errorEl).toBeNull();
  });

  it("no live error for empty text", () => {
    const { container } = render(
      <AdvancedParamsEditor step={baseStep} index={0} replaceParams={() => {}} />
    );
    const details = container.querySelector("details");
    details.open = true;
    const textarea = container.querySelector("textarea");

    fireEvent.change(textarea, { target: { value: "" } });
    act(() => vi.advanceTimersByTime(300));

    const errorEl = container.querySelector(".text-error:not(.alert-error)");
    expect(errorEl).toBeNull();
  });
});
