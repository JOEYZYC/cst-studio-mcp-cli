# CST 2026.2 acceptance summary (public)

This is a **sanitized summary of a local acceptance run**, not a redistributable
CST project or proof that all registered tools work on every installation.
Instance PIDs, job IDs, project SHA-256 fingerprints, exact local paths,
timestamps and artifact filenames are kept only in private acceptance records.
The original source, complete scratch backups, audit log and CST results are
not included in this repository.

## Environment and isolation

- Windows x64, Python 3.12.9 and licensed CST Studio Suite **2026.2**.
- Local install paths vary; documentation uses the conventional example
  `C:\Program Files\CST Studio Suite 2026`. The actual tested installation
  used a different path, supplied through `CST_PATH` and `PYTHONPATH`.
- Source `.cst` was never the live write target: one operation-local scratch
  and complete backups were used. Agent-selected projects were closed after
  idle checks; the user-started CST Design Environment was left running.
- A high-risk automatic lifecycle profile was explicitly opted into during
  selected tests. The **published `environment.yml` defaults to manual mode**.

## Live-accepted unit-cell behavior

| Capability | Observed evidence / boundary |
|---|---|
| Inspection and lifecycle | Attach with expected project identity; model tree, parameters, periodic x/y boundary and Zmax Floquet port readback; safe disconnect. Automatic open/activate/close of an agent-selected scratch was also observed, but does not cover unknown input dialogs. |
| History | One Brick creation and a known result-invalidation dialog passed an integrated smoke test. Remaining fixed History templates are **not** live-accepted. |
| Floquet | Considered mode count changed `2 -> 3 -> 2` with History and readback. A direct setter did not persist. Fundamental mode names read back `TE(0,0)` and `TM(0,0)` (linear basis). |
| Scan angles | Theta and phi were rebuilt, read back, saved, closed, reopened and restored. Atomic `(theta, phi)` write/readback was also observed. |
| Frequency-domain solve | One confirmed solve was observed `RUNNING -> idle/SUCCESS`. CST **reused** saved result run IDs `0/1` rather than allocating a new run ID; a run ID alone cannot prove which job produced data. |
| Saved results | 1–7 THz complex S channels (1002 samples) were read and exported. PCR peaked at **0.6880303025441555 at 3.61 THz**, agreeing with CST's saved PCR table to about `2.8e-17` absolute error. CSV, an explicit R/T/A/PCR HTML report and a two-port Touchstone file were produced. Touchstone frequency conversion used THz -> GHz and the **saved real reference impedance**, not an assumed 50 ohms. |
| Transmission assumption | The tested infinite periodic model had an explicitly identified complete x/y `Zmin=electric` ideal backplane and no `Zmin` Floquet port. Its simulated `T=0` assumption does **not** apply to a finite array or to other structures by default. Absorption was not silently clamped. Saved-result-only exports conservatively report model/boundary/excitation as `unknown` until separately classified live. |

## Stop and dialog limitations

`abort_solver()` displayed the CST modal **“Do you really want to abort this
calculation?”** with Yes/No/Cancel. A single user-authorized Yes was invoked
only after validating the owning CST process, project window, full message
and button set. CST later reported `SUCCESS`; that does **not** prove an
interruption rather than natural completion.

Other runs exposed an **Adaptive Mesh Refinement** modal. In one early stop
attempt, the API returned before this modal appeared and no abort prompt was
handled. In the final preflight attempt the request was refused as
`SOLVER_BUSY` because the job was only two seconds old: **no abort command was
sent**. A newly added startup-age, visible-modal and fresh-log guard passes
offline tests but has not passed an integrated live successful-stop test.

Several ambiguous historical jobs were explicitly audited as `abandoned`
after user authorization, two idle checks and complete-backup verification.
`abandoned` means **neither successful solve nor successful stop**. The latest
job on the tested scratch is still `unknown`; the service blocks further
writing/solving/sweeps on that operation pending separately authorized,
audited resolution. No new solve was started to bypass that guard.

## Not yet live-accepted

- Circular-basis switching: two attempts failed mode-name readback and were
  rolled back without saving. The independent-of-scan-phi flag has no verified
  live getter.
- Replication into an **independent finite-array scratch**, followed by live
  geometry, open-boundary and plane-wave readback and a finite-array solve.
- A confirmed successful stop and the integrated exact-abort-dialog handler.
- Multi-run parameter sweeps, optimizer behavior and job-to-result provenance.
- Ordinary patch-antenna recipe, ports and far-field results.
- OpenCode-specific MCP permission integration.

The default offline suite exercises schema/protocol, path confinement,
locking/audit, saved complex data, result provenance, bounded fixed templates,
CSV/HTML/Touchstone exporters, scratch planning and conservative job states.
Run it with `pytest -m "not live and not solver"`. These tests do **not** start
CST or establish acceptance of untested History templates.
