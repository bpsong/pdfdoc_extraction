// Unit tests — Req 7: ValidationPanel path and code secondary display
// Validates: Requirements 7.3, 7.4

import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { ValidationPanel } from "../main.jsx";

describe("Unit — Req 7: ValidationPanel path and code secondary display", () => {
  const findings = [
    {
      severity: "error",
      code: "extract-api-key-empty",
      path: "tasks.extract_doc.params.api_key",
      message: "Extraction needs an API key.",
    },
    {
      severity: "warning",
      code: "storage-token-invalid",
      path: "tasks.store_csv.params.filename",
      message: "Filename token is not valid.",
    },
  ];

  it("each finding's path field is present in the secondary text line", () => {
    const { container } = render(<ValidationPanel findings={findings} />);
    const secondaryLines = container.querySelectorAll(".text-xs");
    findings.forEach((item) => {
      const match = Array.from(secondaryLines).some((el) => el.textContent.includes(item.path));
      expect(match).toBe(true);
    });
  });

  it("each finding's code appears inside a font-mono span in the secondary line", () => {
    const { container } = render(<ValidationPanel findings={findings} />);
    findings.forEach((item) => {
      const monoSpans = container.querySelectorAll("span.font-mono");
      const codeSpan = Array.from(monoSpans).find((el) => el.textContent === item.code);
      expect(codeSpan).not.toBeNull();
    });
  });

  it("code is NOT the primary bold heading text", () => {
    const { container } = render(<ValidationPanel findings={findings} />);
    const boldEls = container.querySelectorAll(".font-semibold");
    findings.forEach((item) => {
      const codeBold = Array.from(boldEls).find(
        (el) => el.textContent === item.code && !el.className.includes("font-mono")
      );
      expect(codeBold).toBeFalsy();
    });
  });

  it("message is the primary bold heading text", () => {
    const { container } = render(<ValidationPanel findings={findings} />);
    const boldEls = container.querySelectorAll(".font-semibold");
    findings.forEach((item) => {
      const messageBold = Array.from(boldEls).find((el) => el.textContent === item.message);
      expect(messageBold).not.toBeNull();
    });
  });

  it("secondary line contains path separator dot and code", () => {
    const { container } = render(<ValidationPanel findings={[findings[0]]} />);
    const secondaryLines = container.querySelectorAll(".text-xs");
    const secondaryText = Array.from(secondaryLines)
      .map((el) => el.textContent)
      .join(" ");
    expect(secondaryText).toContain(findings[0].path);
    expect(secondaryText).toContain(findings[0].code);
    expect(secondaryText).toContain("·");
  });
});
