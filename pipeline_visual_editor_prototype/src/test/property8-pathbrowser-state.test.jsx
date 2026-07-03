// Feature: pipeline-editor-ux-improvements, Property 8: PathBrowser open state persists across parent re-renders
// Validates: Requirements 9.2

import { describe, it, expect } from "vitest";
import { render, fireEvent } from "@testing-library/react";
import { useState } from "react";
import * as fc from "fast-check";
import { PathBrowser } from "../main.jsx";

/** Wrapper that lets us trigger parent re-renders without unmounting PathBrowser */
function PathBrowserWrapper({ initialCounter = 0 }) {
  const [counter, setCounter] = useState(initialCounter);
  return (
    <div>
      <button data-testid="trigger-rerender" onClick={() => setCounter((c) => c + 1)}>
        Rerender ({counter})
      </button>
      <PathBrowser
        label="Test directory"
        value=""
        onChange={() => {}}
        mode="directory"
        startPath="."
      />
    </div>
  );
}

describe("Property 8: PathBrowser open state persists across parent re-renders", () => {
  it("property: open state is retained after n parent re-renders", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 20 }),
        (rerenderCount) => {
          const { getByText, getByTestId, unmount } = render(<PathBrowserWrapper />);

          // Open the PathBrowser by clicking the toggle button
          const toggleBtn = getByText(/Browse project folders instead/i);
          fireEvent.click(toggleBtn);

          // Trigger n parent re-renders
          const triggerBtn = getByTestId("trigger-rerender");
          for (let i = 0; i < rerenderCount; i++) {
            fireEvent.click(triggerBtn);
          }

          // The browser content should still be visible (open state preserved)
          // The content div is rendered when open=true
          // We check that the "Use current" button is visible (it's inside the open content)
          const useCurrentBtn = document.querySelector(".btn-outline.btn-xs");
          expect(useCurrentBtn).not.toBeNull();

          unmount();
        }
      ),
      { numRuns: 20 }
    );
  });

  it("starts closed on fresh mount", () => {
    const { container } = render(
      <PathBrowser label="Dir" value="" onChange={() => {}} mode="directory" startPath="." />
    );
    // The content div with "Use current" button should NOT be present when closed
    // The browse content has class bg-base-200/50
    const content = container.querySelector(".bg-base-200\\/50");
    expect(content).toBeNull();
  });

  it("opens when toggle button is clicked", () => {
    const { getByText, container } = render(
      <PathBrowser label="Dir" value="" onChange={() => {}} mode="directory" startPath="." />
    );
    fireEvent.click(getByText(/Browse project folders instead/i));
    const content = container.querySelector(".bg-base-200\\/50");
    expect(content).not.toBeNull();
  });
});
