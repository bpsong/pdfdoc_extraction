import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CopyButton, FieldTypeControl } from "../main.jsx";

const stylesPath = resolve(process.cwd(), "src/styles.css");
const styles = readFileSync(stylesPath, "utf8");

describe("visual regression contracts", () => {
  it("uses the high-contrast code-panel style for copy controls", () => {
    render(<CopyButton getText={() => "pipeline: []"} />);

    expect(screen.getByTitle("Copy to clipboard")).toHaveClass("code-copy-button");
    expect(styles).toMatch(/\.code-copy-button\s*\{[^}]*color:\s*#f8fafc;/s);
  });

  it("gives the field type and required control a dedicated grid row", () => {
    const { container } = render(<FieldTypeControl value="str" onChange={() => {}} />);

    expect(container.querySelector(".field-type-required-row")).toBeTruthy();
    expect(styles).toMatch(/\.property-field-grid\s*>\s*\.field-type-control\s*\{[^}]*grid-column:\s*1\s*\/\s*3;/s);
    expect(styles).toMatch(/\.field-type-required-row\s*\{[^}]*grid-template-columns:\s*minmax\(6rem,\s*1fr\)\s*max-content;/s);
  });

  it("switches the ordered pipeline to a vertical mobile layout", () => {
    const mobileRules = styles.slice(styles.indexOf("@media (max-width: 767px)"));

    expect(mobileRules).toMatch(/\.ordered-canvas\s*\{[^}]*flex-direction:\s*column;[^}]*overflow-x:\s*visible;/s);
    expect(mobileRules).toMatch(/\.pipeline-insert\s*\{[^}]*flex-direction:\s*column;[^}]*align-items:\s*center;/s);
  });
});
