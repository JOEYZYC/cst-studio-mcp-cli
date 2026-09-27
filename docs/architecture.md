# Architecture

`cst-rf` is one Python core with two entry points. The CLI exposes a subset of
the MCP tool catalog; both invoke the same `Service` and return the same result
envelope/error format. The MCP server speaks **stdio** and reserves stdout for
protocol messages; incidental output is redirected to stderr.

```text
                  CLI                       MCP stdio
                   |                            |
                   +-----> Service.call() <-----+
                              |  ToolSpec registry + JSON Schema
                              |  confirmation / identity / path checks
                              |  append-only audit / project write lock
                +-------------+-------------------+
                |                                 |
       live CST session                 offline saved results / help
       one worker thread                cst.results (no CST process)
       cst.interface + fixed VBA        FTS5 + R/T/A/PCR/export
                |
       operation-local working.cst
```

## Trust boundary and file layout

- `config.py` reads process environment. The public recipe is manual-only;
  automatic launch/open/switch/close/popup handling requires an explicit
  high-risk opt-in. `CST_TOOLSET` is currently informational, **not** a filter.
- `registry.py` / `service.py` define the tool contract once. Input/output
  schemas, stable errors and result envelopes are shared by both frontends.
  MCP permissions must be configured in the client; the service independently
  validates `confirm=true` for model changes and solver operations.
- `core/scratch.py` copies a saved source `.cst` and its companion directory
  to `CST_WORK_DIR/operations/<operation-id>/project/working.cst`. Source
  fingerprints are recorded. `core/safety.py` confines write targets and
  rejects overwrites; other operation directories cannot be live write targets.
- `core/locking.py` serializes writes to the same project across processes.
  `core/audit.py` records append-only, redacted JSONL events. Audit logs and
  results are local data, excluded from Git.

## CST interaction

- `core/session.py` serializes live API calls on one worker thread. It lazily
  imports the **original** installed `cst.interface` package and verifies the
  requested Design Environment/project identity. Detaching does not kill a
  user-started CST instance. Normal inspection and offline tests need not
  start CST.
- `core/backends/history_vba.py` generates **fixed templates** from validated
  structured fields. No raw VBA endpoint is available. A successful History
  call is not necessarily proof that a property persisted: Floquet modes and
  incidence angles use live readback where acceptance exists.
- `core/popups.py` handles only opt-in, specifically recognized dialogs.
  Unknown input dialogs fail closed; a button press is not evidence of a
  completed stop. Exact abort-dialog handling exists but still lacks an
  integrated successful-stop live acceptance.
- `core/jobs.py` persists solver job states. On restart, or after ambiguous
  timeouts, a job can be `unknown`; the service blocks further writes/solves
  for that operation. Explicit abandonment requires separate safeguards and
  never counts as a successful solve or stop.

## Offline and domain layers

`core/backends/results.py` reads saved complex results using
`cst.results.ProjectFile(..., allow_interactive=False)`, retaining real and
imaginary components. `core/workflows/metasurface.py` combines explicitly
selected co-/cross-polarized and reflection/transmission channels, validates
frequency axes, and computes **unclamped** R/T/A and PCR. Zero transmission
must be stated as an assumption with independent complete-backplane evidence.
Offline results default to `unknown` model/boundary/excitation classification
until separately identified from a live model. `core/help/indexer.py` indexes
the user's locally installed CST help without redistributing it. CSV, HTML and
Touchstone exporters write controlled artifacts; Touchstone conversion uses
saved reference impedance rather than an assumed 50 ohms.

No optimizer, MATLAB control backend, network service or general-purpose
arbitrary-code endpoint is part of this core. See the [tool catalog](tool-catalog.md)
and [acceptance summary](acceptance-cst-2026.2.md) for what is implemented
versus what has passed live CST 2026.2 verification.
