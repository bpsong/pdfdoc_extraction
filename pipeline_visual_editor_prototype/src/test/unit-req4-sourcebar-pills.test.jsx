// Unit tests — Req 4: SourceBar existing pills preserved
// Validates: Requirements 4.5

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { SourceBar } from "../main.jsx";

const baseProps = {
  source: null,
  loading: false,
  hasErrors: false,
  publishMessage: "",
  loadError: "",
  enabledCount: 3,
  totalCount: 5,
};

describe("Unit — Req 4: SourceBar existing pills preserved", () => {
  it("renders the dirty-state indicator with 'Draft changed' when dirty", () => {
    render(<SourceBar {...baseProps} dirty={true} />);
    expect(screen.getByText("Draft changed")).toBeTruthy();
  });

  it("renders the dirty-state indicator with 'Clean' when not dirty", () => {
    render(<SourceBar {...baseProps} dirty={false} />);
    expect(screen.getByText("Clean")).toBeTruthy();
  });

  it("renders 'Publish blocked' pill when hasErrors is true", () => {
    render(<SourceBar {...baseProps} dirty={false} hasErrors={true} />);
    const pill = screen.getByText("Publish blocked");
    expect(pill).toBeTruthy();
    expect(pill.className).toContain("source-pill-warning");
  });

  it("renders 'Publish ready' pill when hasErrors is false", () => {
    render(<SourceBar {...baseProps} dirty={false} hasErrors={false} />);
    const pill = screen.getByText("Publish ready");
    expect(pill).toBeTruthy();
    expect(pill.className).toContain("source-pill-success");
  });

  it("renders the enabled count pill alongside existing pills", () => {
    render(<SourceBar {...baseProps} dirty={false} hasErrors={false} enabledCount={3} totalCount={5} />);
    expect(screen.getByText("3/5 enabled")).toBeTruthy();
    expect(screen.getByText("Clean")).toBeTruthy();
    expect(screen.getByText("Publish ready")).toBeTruthy();
  });
});
