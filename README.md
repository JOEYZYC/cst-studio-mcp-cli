# CST Studio MCP/CLI

**A local Python automation core for CST Studio Suite 2026.2**, with a CLI
(`cst-rf`) and a stdio MCP server (`cst-rf-mcp`) sharing the same service,
schemas, result envelopes and audit trail.

[简体中文](README.zh-CN.md) · [Architecture](docs/architecture.md) ·
[Tool catalog](docs/tool-catalog.md) · [Acceptance status](docs/acceptance-cst-2026.2.md)

> **Development preview (`0.1.0.dev0`), not a fully validated unattended
> simulation product.** Registering a tool does not mean that its CST History
> commands or solver behavior passed live acceptance.

## Capabilities and status

- **Inspect:** discover/connect to a CST Design Environment, check the expected
  project identity, inspect the model tree, parameters, boundaries and Floquet
  modes. Saved results and the locally installed CST help can be read offline.
- **Model safely:** copy a source `.cst` project to an operation-specific scratch,
  then use structured parameters and fixed History templates; source projects
  are never live write targets. No arbitrary VBA or shell execution is exposed.
- **Metasurfaces:** set Floquet mode counts and incidence angles; calculate
  R/T/A and PCR from explicit saved complex channels and their real frequency
  axes. Export CSV, HTML and Touchstone with the recorded reference impedance.
  A claimed `T=0` is an assumption requiring independent complete-backplane
  evidence, not an inference from missing transmission data.
- **Jobs and safety:** require `confirm=true` for mutation and solver actions,
  confine writes to `CST_WORK_DIR`, use a cross-process project lock and
  append-only audit. Ambiguous solver outcomes stay `unknown` and block later
  writes rather than being reported as successful stops.

One periodic unit-cell solve, its S-parameter/R/T/A/PCR analysis, Floquet mode
and incidence-angle readback, and selected exports passed **local CST 2026.2
acceptance**. Finite-array replication, circular-polarization switching,
successful solver stopping, parameter sweeps and the patch-antenna recipe have
**not** passed complete live acceptance. The last local stop experiment has an
unresolved `unknown` job; do not treat its later CST `SUCCESS` as proof of a
successful stop. See [the public acceptance summary](docs/acceptance-cst-2026.2.md)
and [metasurface status](docs/metasurface-phase-status.md).

## Architecture

```text
CLI / MCP stdio -> shared ToolSpec registry -> Service (schemas, audit, lock)
                                      -> core/session (single CST worker thread)
                                      -> fixed History / official CST Python API
                                      -> saved-results and workflow adapters
```

`cst.interface` is used from its **original CST installation location**;
`cst.results.ProjectFile(..., allow_interactive=False)` reads saved data
without starting CST. The CLI exposes a **subset** of the MCP tool catalog.
See [architecture](docs/architecture.md) for trust boundaries and lifecycle.

## Install and run (Windows)

Requires Python 3.12, a licensed CST Studio Suite installation for live tools,
and a compatible CST-provided Python library. The repository does **not** ship
CST binaries, help files, or results. A conventional installation path is
`C:\Program Files\CST Studio Suite 2026`; set `CST_PATH` for another location.

```powershell
conda env create -f environment.yml
$env:CST_PATH = 'C:\Program Files\CST Studio Suite 2026'
$env:PYTHONPATH = "$env:CST_PATH\AMD64\python_cst_libraries"
$env:CST_WORK_DIR = Join-Path $HOME 'Documents\cst-rf-work'
conda run -n cst-rf-mcp cst-rf inspect status --json
conda run -n cst-rf-mcp cst-rf tools list --json
```

The public environment recipe defaults to **manual connection** and does not
auto-launch CST. Set `CST_WORK_DIR` to a private writable folder before any
mutation or solve. An existing conda environment may retain older environment
variables: inspect it with `conda env config vars list -n cst-rf-mcp` before
running; editing `environment.yml` does not reset an already activated process.
Automatic launch/open/switch/popup handling is an explicit high-risk opt-in,
not a safe installation default. Unknown dialogs are not clicked blindly.
`CST_TOOLSET` currently **does not filter tools** and is not an authorization
boundary; configure MCP client permissions separately. The MCP executable is
`cst-rf-mcp`; do not expose all mutation and solver tools to untrusted agents.

## Verify without CST

```powershell
conda run -n cst-rf-mcp ruff check .
conda run -n cst-rf-mcp ruff format --check .
conda run -n cst-rf-mcp mypy src tests
conda run -n cst-rf-mcp pytest -m "not live and not solver"
```

GitHub Actions runs the same offline checks on Windows. Real CST acceptance
requires separate opt-in and is **never** part of the default test suite.
Reference code was not incorporated; see [provenance](docs/provenance.md) and
[reference audit](docs/reference-audit.md).

## License

Apache-2.0; see [LICENSE](LICENSE). This is an independent project and is not
affiliated with or endorsed by Dassault Systèmes.
