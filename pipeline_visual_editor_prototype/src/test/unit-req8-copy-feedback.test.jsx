// Unit tests — Req 8: copy button feedback states
// Validates: Requirements 8.4, 8.4a, 8.6

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, fireEvent, waitFor, screen, act } from "@testing-library/react";
import { CopyButton, YamlPanel } from "../main.jsx";

describe("Unit — Req 8: copy button feedback states", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("renders the Copy icon button by default (status: idle)", () => {
    render(<CopyButton getText={() => "test"} />);
    // The button should have title "Copy to clipboard" and no status text
    const btn = screen.getByTitle("Copy to clipboard");
    expect(btn).toBeTruthy();
    // Should not contain "Copied" or "Failed" text
    expect(btn.textContent).not.toContain("Copied");
    expect(btn.textContent).not.toContain("Failed");
  });

  it("displays 'Copied' label for ~1500ms after successful clipboard write, then reverts to idle", async () => {
    const writeTextMock = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText: writeTextMock },
      writable: true,
      configurable: true,
    });

    render(<CopyButton getText={() => "test yaml content"} />);
    const btn = screen.getByTitle("Copy to clipboard");

    fireEvent.click(btn);

    // After click, wait for promise to resolve
    await act(async () => {
      await Promise.resolve();
    });

    expect(btn.textContent).toContain("Copied");

    // After 1500ms, reverts to idle
    act(() => vi.advanceTimersByTime(1500));
    expect(btn.textContent).not.toContain("Copied");
  });

  it("displays 'Failed' label for ~1500ms after clipboard write rejection, then reverts", async () => {
    const writeTextMock = vi.fn().mockRejectedValue(new Error("Permission denied"));
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText: writeTextMock },
      writable: true,
      configurable: true,
    });

    render(<CopyButton getText={() => "test content"} />);
    const btn = screen.getByTitle("Copy to clipboard");

    fireEvent.click(btn);

    await act(async () => {
      await Promise.resolve();
    });

    expect(btn.textContent).toContain("Failed");

    act(() => vi.advanceTimersByTime(1500));
    expect(btn.textContent).not.toContain("Failed");
  });

  it("silently does nothing when navigator.clipboard is undefined", () => {
    Object.defineProperty(navigator, "clipboard", {
      value: undefined,
      writable: true,
      configurable: true,
    });

    render(<CopyButton getText={() => "test"} />);
    const btn = screen.getByTitle("Copy to clipboard");
    // Should not throw
    expect(() => fireEvent.click(btn)).not.toThrow();
  });
});
