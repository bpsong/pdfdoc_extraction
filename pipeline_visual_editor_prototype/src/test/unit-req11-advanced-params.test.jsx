// Unit tests — Req 11: AdvancedParamsEditor timer cleanup and Apply independence
// Validates: Requirements 11.5, 11.7

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, fireEvent, screen, act } from "@testing-library/react";
import { AdvancedParamsEditor } from "../main.jsx";

const baseStep = {
  key: "test_step",
  params: { api_key: "test", tier: "agentic" },
};

describe("Unit — Req 11: AdvancedParamsEditor timer cleanup and Apply independence", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("clearTimeout is called on unmount (timer cleanup)", () => {
    const clearTimeoutSpy = vi.spyOn(window, "clearTimeout");

    const { container, unmount } = render(
      <AdvancedParamsEditor step={baseStep} index={0} replaceParams={() => {}} />
    );
    const details = container.querySelector("details");
    details.open = true;
    const textarea = container.querySelector("textarea");

    // Trigger a debounce timer
    fireEvent.change(textarea, { target: { value: "{ invalid" } });

    // Unmount should clear the timer
    unmount();

    expect(clearTimeoutSpy).toHaveBeenCalled();
  });

  it("Apply JSON params button writes parsed params to state even when liveError is non-empty", () => {
    const replaceParams = vi.fn();
    const { container, getByText } = render(
      <AdvancedParamsEditor step={baseStep} index={0} replaceParams={replaceParams} />
    );
    const details = container.querySelector("details");
    details.open = true;
    const textarea = container.querySelector("textarea");

    // First introduce a live error
    fireEvent.change(textarea, { target: { value: "{ bad json" } });
    act(() => vi.advanceTimersByTime(300));

    // Verify live error is shown
    const liveErrorEl = container.querySelector(".text-error:not(.alert-error)");
    expect(liveErrorEl).not.toBeNull();

    // Now type valid JSON
    fireEvent.change(textarea, { target: { value: '{"api_key": "new-key"}' } });
    act(() => vi.advanceTimersByTime(300));

    // Click Apply JSON params
    fireEvent.click(getByText("Apply JSON params"));

    // replaceParams should be called with the parsed object
    expect(replaceParams).toHaveBeenCalledWith(0, { api_key: "new-key" });
  });

  it("Apply JSON params button is NOT disabled when liveError is non-empty", () => {
    const { container, getByText } = render(
      <AdvancedParamsEditor step={baseStep} index={0} replaceParams={() => {}} />
    );
    const details = container.querySelector("details");
    details.open = true;
    const textarea = container.querySelector("textarea");

    // Introduce live error
    fireEvent.change(textarea, { target: { value: "{ invalid json" } });
    act(() => vi.advanceTimersByTime(300));

    const applyBtn = getByText("Apply JSON params");
    expect(applyBtn).not.toBeDisabled();
  });
});
