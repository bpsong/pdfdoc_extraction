// Feature: pipeline-editor-ux-improvements, Property 9: FieldTypeControl applies withRequiredState correctly
// Validates: Requirements 10.5

import { describe, it, expect, vi } from "vitest";
import { render, fireEvent } from "@testing-library/react";
import * as fc from "fast-check";
import { FieldTypeControl, FIELD_TYPE_VALUES, withRequiredState, unwrapOptionalType, isOptionalType } from "../main.jsx";

// Re-export withRequiredState for testing
function buildValue(baseType, required) {
  return required ? baseType : `Optional[${baseType}]`;
}

describe("Property 9: FieldTypeControl applies withRequiredState correctly", () => {
  it("property: clicking Required button calls onChange with withRequiredState(baseType, true)", () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...FIELD_TYPE_VALUES),
        fc.boolean(),
        (baseType, startAsRequired) => {
          const initialValue = buildValue(baseType, startAsRequired);
          const onChange = vi.fn();

          const { getByText, unmount } = render(
            <FieldTypeControl value={initialValue} onChange={onChange} />
          );

          fireEvent.click(getByText("Required"));

          expect(onChange).toHaveBeenCalledWith(buildValue(baseType, true));
          unmount();
        }
      ),
      { numRuns: 100 }
    );
  });

  it("property: clicking Optional button calls onChange with withRequiredState(baseType, false)", () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...FIELD_TYPE_VALUES),
        fc.boolean(),
        (baseType, startAsRequired) => {
          const initialValue = buildValue(baseType, startAsRequired);
          const onChange = vi.fn();

          const { getByText, unmount } = render(
            <FieldTypeControl value={initialValue} onChange={onChange} />
          );

          fireEvent.click(getByText("Optional"));

          expect(onChange).toHaveBeenCalledWith(buildValue(baseType, false));
          unmount();
        }
      ),
      { numRuns: 100 }
    );
  });

  it("changing the type select preserves required state", () => {
    const onChange = vi.fn();
    const { container } = render(
      <FieldTypeControl value="str" onChange={onChange} />
    );
    const select = container.querySelector("select");
    fireEvent.change(select, { target: { value: "int" } });
    // Should preserve required=true (original "str" is required by default)
    expect(onChange).toHaveBeenCalledWith("int");
  });

  it("changing type select from Optional[str] preserves optional state", () => {
    const onChange = vi.fn();
    const { container } = render(
      <FieldTypeControl value="Optional[str]" onChange={onChange} />
    );
    const select = container.querySelector("select");
    fireEvent.change(select, { target: { value: "int" } });
    expect(onChange).toHaveBeenCalledWith("Optional[int]");
  });
});
