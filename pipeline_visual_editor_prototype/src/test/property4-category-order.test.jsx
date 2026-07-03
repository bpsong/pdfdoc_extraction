// Feature: pipeline-editor-ux-improvements, Property 4: Category headings appear in canonical order
// Validates: Requirements 5.2

import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import * as fc from "fast-check";
import { TaskPalette, CATEGORY_ORDER } from "../main.jsx";

const baseProps = {
  collapsed: false,
  setCollapsed: () => {},
  search: "",
  setSearch: () => {},
  steps: [],
  addTask: () => {},
};

describe("Property 4: Category headings appear in canonical order", () => {
  it("property: visible headings always appear in the canonical CATEGORY_ORDER sequence", () => {
    const searchStrings = ["", "a", "e", "s", "store", "arch", "split", "extract", "review", "context", "rule"];
    fc.assert(
      fc.property(
        fc.constantFrom(...searchStrings),
        (searchStr) => {
          const { container, unmount } = render(
            <TaskPalette {...baseProps} search={searchStr} />
          );
          const headings = container.querySelectorAll(".palette-category-heading");
          const headingTexts = Array.from(headings).map((h) => h.textContent);

          // Get indices in CATEGORY_ORDER for each visible heading
          const indices = headingTexts.map((text) => CATEGORY_ORDER.indexOf(text));

          // Every index should be valid (heading must be in CATEGORY_ORDER)
          indices.forEach((idx) => expect(idx).toBeGreaterThanOrEqual(0));

          // Indices must be strictly increasing (canonical order)
          for (let i = 1; i < indices.length; i++) {
            expect(indices[i]).toBeGreaterThan(indices[i - 1]);
          }
          unmount();
        }
      ),
      { numRuns: 100 }
    );
  });

  it("with no search filter, all category headings appear in canonical order", () => {
    const { container } = render(<TaskPalette {...baseProps} search="" />);
    const headings = container.querySelectorAll(".palette-category-heading");
    const headingTexts = Array.from(headings).map((h) => h.textContent);

    const indices = headingTexts.map((text) => CATEGORY_ORDER.indexOf(text));
    for (let i = 1; i < indices.length; i++) {
      expect(indices[i]).toBeGreaterThan(indices[i - 1]);
    }
  });
});
