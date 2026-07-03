// Feature: pipeline-editor-ux-improvements, Property 7: Copy button writes the panel's full text to the clipboard
// Validates: Requirements 8.3

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, fireEvent, waitFor } from "@testing-library/react";
import * as fc from "fast-check";
import { YamlPanel, DiffPanel } from "../main.jsx";

describe("Property 7: Copy button writes the panel's full text to the clipboard", () => {
  let writeTextMock;

  beforeEach(() => {
    writeTextMock = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText: writeTextMock },
      writable: true,
      configurable: true,
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("property: YamlPanel copy button writes exact draftYaml text", async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.string({ minLength: 1, maxLength: 200 }),
        async (draftYaml) => {
          writeTextMock.mockClear();
          const { container, unmount } = render(
            <YamlPanel draftYaml={draftYaml} currentYaml="" />
          );

          const copyBtn = container.querySelector(".pipeline-action");
          expect(copyBtn).toBeTruthy();
          fireEvent.click(copyBtn);

          await waitFor(() => expect(writeTextMock).toHaveBeenCalledWith(draftYaml));
          unmount();
        }
      ),
      { numRuns: 20 }
    );
  });

  it("property: DiffPanel copy button writes exact diffText", async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.string({ minLength: 1, maxLength: 200 }),
        async (diffText) => {
          writeTextMock.mockClear();
          const { container, unmount } = render(
            <DiffPanel diffText={diffText} hasChanges={true} />
          );

          const copyBtn = container.querySelector(".pipeline-action");
          expect(copyBtn).toBeTruthy();
          fireEvent.click(copyBtn);

          await waitFor(() => expect(writeTextMock).toHaveBeenCalledWith(diffText));
          unmount();
        }
      ),
      { numRuns: 20 }
    );
  });

  it("copy writes the full text without truncation", async () => {
    const longYaml = "tasks:\n  step1:\n    module: test\n".repeat(100);
    render(<YamlPanel draftYaml={longYaml} currentYaml="" />);
    const copyBtn = document.querySelector(".pipeline-action");
    fireEvent.click(copyBtn);
    await waitFor(() => expect(writeTextMock).toHaveBeenCalledWith(longYaml));
  });
});
