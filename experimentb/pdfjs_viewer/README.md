# PDF.js citation viewer experiment

This is a standalone experiment for checking whether LlamaCloud citation
bounding boxes can be used to guide review beside a PDF.js-rendered document.
It defaults to these local input paths (the files are not included in GitHub):

- `sample_invoice.pdf`
- `experimentb/llama-extract-sample_invoice.json`

Provide your own PDF and extraction JSON, then run it from the repository root
with the project virtual environment:

```powershell
.\.venv\Scripts\python.exe experimentb\pdfjs_viewer\server.py --pdf path\to\document.pdf --json path\to\llama-result.json
```

Then open <http://127.0.0.1:8765/>. The left side renders the PDF with PDF.js;
the right side contains editable extracted values. Clicking or focusing a field
draws all of its cited bounding boxes over the PDF. The viewer automatically
centers the selected citation after a field change or zoom, and the **Center
citation** button repeats that action on demand. The `serial_numbers` sample
field has no citation in the source response, so it reports that location as
unavailable.

To try different inputs:

```powershell
.\.venv\Scripts\python.exe experimentb\pdfjs_viewer\server.py `
  --pdf path\to\document.pdf `
  --json path\to\llama-result.json `
  --port 8766
```
