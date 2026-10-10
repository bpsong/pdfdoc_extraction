# Performance benchmark

Run from the repository root on Windows with the repository environment:

```powershell
.\.venv\Scripts\python.exe tools\benchmark_performance.py --output qa_artifacts\performance_benchmark_baseline.json
```

The benchmark uses temporary SQLite databases and synthetic data. It does not
read the configured application database, start web or worker processes, or
contact an OCR provider. It uses the locally generated 30-page PDF under
`test/performance_fixtures/` when present. Because PDFs are Git-ignored, a
fresh checkout regenerates an equivalent fixture in the temporary directory.
To create a persistent local copy explicitly:

```powershell
.\.venv\Scripts\python.exe tools\generate_performance_pdf.py test\performance_fixtures\synthetic_30_page_49_mib.pdf
```

The synthetic PDF contains 30 raster pages and a random embedded attachment.
The attachment brings the file close to the configured 50 MiB upload limit;
it does not affect page rendering. This separates upload byte volume from the
30-page OCR rendering workload while keeping both in one valid PDF.

## Workloads and interpretation

| Probe | Workload | What it measures |
| --- | --- | --- |
| Processing overview | Batches of 50, 250, and 1,000 documents; three task runs and one audit event per document | `ProcessingStateService.get_batch_state` duration and SELECT count |
| Failure detail | 25, 100, and 500 failed sibling documents | `FailureService.get_failure` duration and SELECT count |
| Config version counts | 1,000 versions with 64 KiB content each | Full repository list versus the summary's status-count query |
| Parent document lookup | 50,000 documents, one matching child | Query plan and lookup duration before and after a temporary index |
| Password verification | Synthetic bcrypt hash with 12 rounds | Synchronous `checkpw` duration |
| Upload | One 49 MiB synthetic PDF through the multipart receiver | Receiver time, bytes, and sampled process RSS |
| PDF rendering | The same 30-page PDF through `GlmOcrAdapter.render_pdf` | Rendering time, returned PNG bytes, and process RSS increase |

Times are medians of seven warmed calls, except bcrypt uses five calls and
upload/render each run once. Maxima show the highest observed repeat, not a
statistical p95. The upload RSS is sampled while chunks arrive; render RSS is
measured before and after `render_pdf`, so a short transient peak may be
higher. The database probes use a local temporary SQLite file except the
failure scenarios, which use in-memory SQLite.

These numbers show scaling and local costs, not production latency. They do
not include browser rendering, network transfer, OCR model inference, or
simultaneous access by the parent, web, and worker processes. Use the same
machine, fixture, dataset sizes, and command when comparing a code change.

## Measured result after the first optimizations

On 2026-09-29, the 1,000-document overview used six SELECTs and took 47.11 ms
median. A per-document read strategy, run against the same data in the same
benchmark process, used 2,002 SELECTs and took 269.49 ms median. The admin
summary's status count took 0.23 ms median for 1,000 versions; loading all
64 KiB version bodies as a reference took 441.48 ms median. The saved results
are `qa_artifacts/performance_benchmark_after.json`; the prior run is in
`qa_artifacts/performance_benchmark_baseline.json`.

The remaining probes did not change. In particular, the failure detail still
loads task runs per sibling, and the parent-document lookup still scans without
an index. These measurements support the two completed optimizations without
claiming a production-wide latency improvement.
