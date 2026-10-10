# Performance measurement: 2026-09-29

| Item | Value |
| --- | --- |
| Audience | Readers investigating historical evidence |
| Owner | Application maintainers |
| Status | Historical record |
| Last verified | 2026-10-10 — repository/source review; no live deployment check |
| Applies to | Original checkpoint or snapshot documented below |

This is a historical local measurement, not a newly executed benchmark or a
production capacity estimate. Use the [benchmark procedure](../../developer/performance.md)
to reproduce it. The [original report](../archive/2026-10-10/docs/performance_benchmark.md)
is preserved unchanged.

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
