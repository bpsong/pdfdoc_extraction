# Architecture reading path

| Item | Value |
| --- | --- |
| Audience | Software architects and technical leads |
| Owner | Application maintainers |
| Status | Current |
| Last verified | 2026-10-10 — repository/source review; no live deployment check |
| Applies to | Production application; SQLite schema 9 |

Start with the [stable architecture overview](../design_architecture.md).
These pages explain implemented boundaries, invariants and tradeoffs. For
code-editing procedures, continue to the [Developer guide](../developer/README.md).


Read in this order, or choose the task you need:

1. [Runtime topology and component boundaries](runtime-and-boundaries.md)
2. [Workflow execution and state](workflow-and-state.md)
3. [Persistence and artifact ownership](persistence-and-artifacts.md)
4. [Configuration ownership and immutable versions](configuration-and-versioning.md)
5. [Security and trust boundaries](security-and-trust.md)
6. [Architectural decisions and constraints](decisions-and-constraints.md)

## Animated architecture walkthroughs

The linked sections embed one animation per topic alongside the detailed
contracts. Loops use synthetic examples and were checked against repository
code on 2026-10-11 at commit `6a67a26`; no live deployment check. Static diagrams
and prose remain available alongside the animations.

| Animation | Length | Key boundary |
| --- | --- | --- |
| [Document processing](workflow-and-state.md#animated-document-processing-flow) | 36 seconds | Durable acceptance, job leases and document outcomes |
| [Review pause and resume](workflow-and-state.md#animated-review-pause-and-resume) | 36 seconds | Persisted pause and one new downstream flow |
| [Immutable version pinning](configuration-and-versioning.md#animated-immutable-version-pinning) | 36 seconds | Publication changes future intake, not accepted work |
| [Split fan-out and fan-in](workflow-and-state.md#animated-split-fan-out-and-fan-in) | 36 seconds | Sequential children and leaf-derived aggregation |
| [Runtime startup and recovery](runtime-and-boundaries.md#animated-runtime-startup-and-recovery) | 42 seconds | Migration ownership, supervision and lease recovery |
| [Artifact storage lifecycle](persistence-and-artifacts.md#animated-artifact-storage-lifecycle) | 36 seconds | File contents, registration and task housekeeping |
| [Processing-history cleanup](persistence-and-artifacts.md#animated-processing-history-cleanup) | 36 seconds | Preview revalidation, atomic deletion and retained files |
| [Browser security](security-and-trust.md#animated-browser-security-flow) | 40 seconds | Cookies, CSRF, roles and shared authenticated PDF access |

### Maintain the animations

The seven processing/lifecycle GIFs are generated from
[editable storyboards](assets/architecture-storyboards.json) by the
[documentation renderer](../../tools/render_architecture_animations.py).
Update the storyboard, source symbols and verification revision after checking
changed behavior against the implementation. Render from the repository root
using the development environment (Pillow is pinned in `requirements-dev.txt`):

```powershell
.\.venv\Scripts\python.exe -m tools.render_architecture_animations
```

Use `--only document-processing-flow` to regenerate one animation. Optional
`--preview-dir <directory>` writes scene contact sheets for visual review.
The existing browser-security GIF is maintained separately from this renderer.

Check animation layout, export freshness, playback and documentation navigation:

```powershell
.\.venv\Scripts\python.exe -m pytest -v test\tools\test_architecture_animations.py test\tools\test_documentation_structure.py
```

[All documentation](../README.md)
