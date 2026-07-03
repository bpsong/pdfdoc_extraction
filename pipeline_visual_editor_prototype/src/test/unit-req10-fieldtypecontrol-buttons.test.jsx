// Unit tests — Req 10: FieldTypeControl button presence and checkbox removal
// Validates: Requirements 10.1, 10.2

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { FieldTypeControl } from "../main.jsx";

describe("Unit — Req 10: FieldTypeControl button presence and checkbox removal", () => {
  it("renders a 'Required' button", () => {
    render(<FieldTypeControl value="str" onChange={() => {}} />);
    expect(screen.getByText("Required")).toBeTruthy();
  });

  it("renders an 'Optional' button", () => {
    render(<FieldTypeControl value="str" onChange={() => {}} />);
    expect(screen.getByText("Optional")).toBeTruthy();
  });

  it("does NOT render an <input type='checkbox'> inside FieldTypeControl", () => {
    const { container } = render(<FieldTypeControl value="str" onChange={() => {}} />);
    const checkbox = container.querySelector("input[type='checkbox']");
    expect(checkbox).toBeNull();
  });

  it("Required button has active class when value is required (non-Optional)", () => {
    const { getByText } = render(<FieldTypeControl value="str" onChange={() => {}} />);
    const requiredBtn = getByText("Required");
    expect(requiredBtn.className).toContain("field-req-btn-active");
  });

  it("Optional button has active class when value is Optional[...]", () => {
    const { getByText } = render(<FieldTypeControl value="Optional[str]" onChange={() => {}} />);
    const optionalBtn = getByText("Optional");
    expect(optionalBtn.className).toContain("field-req-btn-active");
  });

  it("both Required and Optional buttons are rendered in a segmented control container", () => {
    const { container } = render(<FieldTypeControl value="str" onChange={() => {}} />);
    const control = container.querySelector(".field-required-control");
    expect(control).not.toBeNull();
    const buttons = control.querySelectorAll(".field-req-btn");
    expect(buttons.length).toBe(2);
  });
});
