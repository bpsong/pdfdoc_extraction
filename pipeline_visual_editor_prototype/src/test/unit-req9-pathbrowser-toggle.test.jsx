// Unit tests — Req 9: PathBrowser initial state and explicit toggle
// Validates: Requirements 9.1, 9.3, 9.4

import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { PathBrowser } from "../main.jsx";

const baseProps = {
  label: "Archive directory",
  value: "",
  onChange: () => {},
  mode: "directory",
  startPath: ".",
};

describe("Unit — Req 9: PathBrowser initial state and explicit toggle", () => {
  it("browser content is NOT visible (closed) on fresh mount", () => {
    const { container } = render(<PathBrowser {...baseProps} />);
    // When closed, the bg-base-200/50 div is not rendered
    const content = container.querySelector(".bg-base-200\\/50");
    expect(content).toBeNull();
  });

  it("clicking the toggle button renders the browser content (open)", () => {
    const { container, getByText } = render(<PathBrowser {...baseProps} />);
    fireEvent.click(getByText(/Browse project folders instead/i));
    const content = container.querySelector(".bg-base-200\\/50");
    expect(content).not.toBeNull();
  });

  it("clicking the toggle button a second time hides the browser content (closed)", () => {
    const { container, getByText } = render(<PathBrowser {...baseProps} />);
    const toggleBtn = getByText(/Browse project folders instead/i);

    // Open
    fireEvent.click(toggleBtn);
    expect(container.querySelector(".bg-base-200\\/50")).not.toBeNull();

    // Close
    fireEvent.click(toggleBtn);
    expect(container.querySelector(".bg-base-200\\/50")).toBeNull();
  });

  it("renders a button (not <summary>) for the toggle", () => {
    const { container } = render(<PathBrowser {...baseProps} />);
    // Should NOT use <details>/<summary> for the toggle
    const summary = container.querySelector("summary");
    expect(summary).toBeNull();

    // Should use a button
    const toggleBtn = container.querySelector("button[type='button']");
    expect(toggleBtn).not.toBeNull();
    expect(toggleBtn.textContent).toContain("Browse");
  });
});
