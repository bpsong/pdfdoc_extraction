// Feature: pipeline-editor-ux-improvements, Property 3: Category headings appear for and only for non-empty groups
// Validates: Requirements 5.1, 5.3, 5.4

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import * as fc from "fast-check";
import { TaskPalette, CATEGORY_ORDER } from "../main.jsx";

// Re-export taskTemplates from main.jsx by accessing the module
// Since taskTemplates is not exported, we test through the rendered component.

const baseProps = {
  collapsed: false,
  setCollapsed: () => {},
  search: "",
  setSearch: () => {},
  steps: [],
  addTask: () => {},
};

describe("Property 3: Category headings appear for and only for non-empty groups", () => {
  it("property: every rendered heading has at least one visible task in that category", () => {
    // Generate a search string from characters that could match task labels
    fc.assert(
      fc.property(
        fc.string({ maxLength: 20 }),
        (searchStr) => {
          const { container, unmount } = render(
            <TaskPalette {...baseProps} search={searchStr} />
          );
          const headings = container.querySelectorAll(".palette-category-heading");
          headings.forEach((heading) => {
            const category = heading.textContent;
            // Find task buttons in the same parent container after this heading
            const parentDiv = heading.parentElement;
            const buttons = parentDiv ? parentDiv.querySelectorAll(".task-palette-item") : [];
            // There should be at least one task button in the category
            expect(buttons.length).toBeGreaterThan(0);
            // All found buttons should belong to categories in CATEGORY_ORDER
            expect(CATEGORY_ORDER).toContain(category);
          });
          unmount();
        }
      ),
      { numRuns: 100 }
    );
  });

  it("shows no heading for a category with no matching tasks", () => {
    // Search for something that matches no tasks
    render(<TaskPalette {...baseProps} search="zzzzzzzzzzzzzzzzzzz_nomatch_xyz" />);
    const headings = document.querySelectorAll(".palette-category-heading");
    expect(headings.length).toBe(0);
  });

  it("shows empty-state message when all tasks are filtered out", () => {
    render(<TaskPalette {...baseProps} search="zzzzzzzzzzzzzzzzzzz_nomatch_xyz" />);
    expect(screen.getByText("No matching tasks")).toBeTruthy();
  });

  it("shows headings only for categories that have matching tasks when searching", () => {
    // "Split" matches "split_document" task
    render(<TaskPalette {...baseProps} search="split" />);
    const headings = document.querySelectorAll(".palette-category-heading");
    const headingTexts = Array.from(headings).map((h) => h.textContent);
    expect(headingTexts).toContain("Split");
    // No Archive heading since no archive tasks match "split"
    expect(headingTexts).not.toContain("Archive");
  });
});
