// Feature: pipeline-editor-ux-improvements, Property 2: SourceBar enabled-step pill
// Validates: Requirements 4.2, 4.3, 4.4

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import * as fc from "fast-check";
import { SourceBar } from "../main.jsx";

describe("Property 2: SourceBar enabled-step pill reflects count and style", () => {
  const baseProps = {
    source: null,
    dirty: false,
    loading: false,
    hasErrors: false,
    publishMessage: "",
    loadError: "",
  };

  it("property: pill shows correct count text and class for any enabledCount/totalCount", () => {
    fc.assert(
      fc.property(
        fc.nat(20),        // extra (so totalCount = enabledCount + extra)
        fc.nat(20),        // enabledCount
        (extra, enabledCount) => {
          const totalCount = enabledCount + extra;
          const { unmount } = render(
            <SourceBar {...baseProps} enabledCount={enabledCount} totalCount={totalCount} />
          );

          const pill = screen.getByText(`${enabledCount}/${totalCount} enabled`);
          expect(pill).toBeTruthy();

          if (enabledCount === 0) {
            expect(pill.className).toContain("source-pill-warning");
            expect(pill.className).not.toContain("source-pill-success");
          } else {
            expect(pill.className).toContain("source-pill-success");
            expect(pill.className).not.toContain("source-pill-warning");
          }

          unmount();
        }
      ),
      { numRuns: 100 }
    );
  });

  it("shows warning pill when enabledCount is 0", () => {
    render(<SourceBar {...baseProps} enabledCount={0} totalCount={5} />);
    const pill = screen.getByText("0/5 enabled");
    expect(pill).toHaveClass("source-pill-warning");
  });

  it("shows success pill when enabledCount > 0", () => {
    render(<SourceBar {...baseProps} enabledCount={3} totalCount={5} />);
    const pill = screen.getByText("3/5 enabled");
    expect(pill).toHaveClass("source-pill-success");
  });
});
