# Reference audit

Reference repositories are read-only research inputs, not runtime dependencies.
Links below pin the reviewed upstream commits, so this document remains useful
when `cst-rf` is published without the local reference corpus.

| Reference (reviewed commit) | Role | Code policy |
|---|---|---|
| [ismailakdag/cst-studio-mcp](https://github.com/ismailakdag/cst-studio-mcp/tree/e027735f0f61e666801fe18a6e0f93cfbfff9f69) | Manual startup, safe detach, worker thread, stdio, schemas, saved results | No root LICENSE at pinned commit; do not copy code |
| [bbl21/cst-runtime-cli](https://github.com/bbl21/cst-runtime-cli/tree/7eac82190845083396889a7ae96ed22c2118a892) | Core/CLI contracts, results, gateway rules, workspace and tests | MIT; adapt only reviewed units |
| [MuziIsabel/CST-Studio-Suite-Help](https://github.com/MuziIsabel/CST-Studio-Suite-Help/tree/1b1450a8040b4bf7fc81488fb3ba69ac6d2c158c) | Offline help parser, FTS5 index and citations | MIT; adapt only the help component |
| [AndersOnLin4/cst-mcp](https://github.com/AndersOnLin4/cst-mcp/tree/4367d5467e234e174c567bf88796046137f058f5) | CST 2026 Floquet probes and unit-cell behavior | MIT; do not reuse its session/process control |
| [K-13ROBOT/CST_MCP](https://github.com/K-13ROBOT/CST_MCP/tree/dce59df12fba358bb89d0f88bea514ac08d3916b) | Antenna ports, far-field metrics and live cases | MIT; behavior reference |
| [valenZW/cst-sim-agent](https://github.com/valenZW/cst-sim-agent/tree/d8ae8a4045661c31fd9b4b3c5919b06a46e6e60a) | Layering and patch-antenna acceptance fixture | Apache-2.0; behavior reference |
| [JustArri/py4cst](https://github.com/JustArri/py4cst/tree/585a8dfc3aae32d15679a77aa6dcd9b0feb3cec7) | Typed wrappers and VBA mapping inventory | MIT; API mapping reference |
| [MrM1ko/CST_MCP](https://github.com/MrM1ko/CST_MCP/tree/20267b2f899f25fbaae6a371b5f7ef945b1628c2) | Safety, audit and job acceptance scenarios | AGPL-3.0; do not copy code |

The installed CST 2026.2 help is authoritative for API names and semantics.

Verified local Help topics used by the current implementation:

- `mergedProjects/VBA_3D/special_vbaports/floquetport_object.htm`
  - `Port("Zmin"|"Zmax")` selects the port;
  - `GetNumberOfModes()` and `GetNumberOfModesConsidered()` are read methods;
  - `IsPortAtZmin()` and `IsPortAtZmax()` identify the selected port location;
  - direct Python calls require the official `Model3D.allow_history_commands()` gate
    in CST 2026.2, otherwise CST rejects the command as a History command.
- `mergedProjects/VBA_3D/special_vbasolver/special_vbasolver_boundary_object.htm`
  - `GetXmin`/`GetXmax`/`GetYmin`/`GetYmax`/`GetZmin`/`GetZmax` are documented reads;
  - boundary and periodic scan-angle getters have since passed live readback
    on the controlled unit-cell scratch.

## Abort/stop reference review (read-only, 2026-09-27)

The installed CST Python binding documents `Model3D.abort_solver()` as an abort
request, but does not document the subsequent UI confirmation. In the current
CST 2026.2 live probe, that call showed a Qt modal with the exact message
`Do you really want to abort this calculation?`; its Yes/No/Cancel buttons
were readable through Windows UI Automation, but had **no Win32 child HWNDs**.
`abort_solver(timeout=30)` timed out while the UI waited for a response.

- `ismailakdag__cst-studio-mcp/src/cst_mcp/session.py` (lines 951–975) calls
  the official `abort_solver` and reports `executed` if the call returns;
  it has no stop-specific dialog confirmation or post-stop proof. Its
  `dialog_handler.py` searches Win32 child buttons, then falls back to
  `WM_CLOSE` for unmatched dialogs (lines 83–128). The observed Qt abort
  modal has no Win32 child buttons, so this is not a safe donor for this case.
- `bbl21__cst-runtime-cli/skills/cst-runtime-cli/scripts/cst_runtime/core/simulation.py`
  (lines 90–108) calls `modeler.abort_solver()` and immediately returns a
  success response; it does not distinguish confirmation from actual stop.
- `valenZW__cst-sim-agent/src/controller.py` (lines 342–352) calls the
  official `abort_solver` and returns a boolean without confirming the UI.
  Its `popup_watchdog.py` matches broad title keywords and presses Enter;
  its default keywords do not match this dialog's generic
  `CST MICROWAVE STUDIO 2026` title, and widening them would be unsafe.
  Its `popup_utils.py` explicitly notes that the Qt modal is not exposed as
  Win32 child buttons. That broad default-button behavior cannot be used
  under this project's unknown-dialog rule.
- `MrM1ko__CST_MCP/src/cst_mcp_lite/client.py` (line 564) sends
  `Solver.Abort` as a VBA string. Its `execute_vba` defaults to
  `record_history=True` (lines 436–451), so this stop command would also be
  appended to model History; replay on rebuild is unsafe. The installed CST
  2026.2 Solver Object Help does not document `Solver.Abort` as a method.
  Despite a user-authorized raw-VBA fallback, an undocumented, history-stored
  abort is not adopted without a separate safe probe.

No reference clone was changed or copied. The narrow abort confirmation
handler in this repository instead verifies CST PID, project owner, exact
message and exact button set via UI Automation; it records Yes separately
from later solver status and does not infer that `SUCCESS` means an abort.
