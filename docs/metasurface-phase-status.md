# Metasurface phase status (2026-09-27)

Scope: **Python `cst-rf` controls CST exclusively**. MATLAB, ordinary antenna
recipes and OpenCode agent permissions are outside the current acceptance
target. This is a status review of the original implementation plan, not a
claim that a registered tool has passed a live CST acceptance.

| Plan item | Evidence / remaining work |
|---|---|
| Infinite unit cell, periodic x/y boundaries, Zmax Floquet modes | Live readback and mode-count write/readback accepted on a controlled scratch; see `acceptance-cst-2026.2.md`. |
| Incidence theta/phi | Confirmed atomic write, rebuild, readback and save/reopen accepted. |
| Linear/circular polarization | TE/TM mode names read live. Two circular write/readback attempts failed and were rolled back; circular switching is **not accepted**. The independent-of-scan-phi flag has no verified getter. |
| Saved R/T/A and PCR | Successful frequency-domain result, complex S channels, PCR peak and report/Touchstone verified on a complete simulated backplane. `T=0` remains an explicit user-supplied *assumption*, not inferred from S data, and now emits a warning that independent backplane evidence is required. Saved-result extractors now label model/boundary/excitation `unknown`; independent live classification remains a separate step. Frequency axis, sample lengths and (when supplied) axis label and run ID are checked before combining channels. |
| Finite open-boundary array | Planning and Transform/PlaneWave templates only pass offline tests. No independent finite-array scratch has been built, read back or solved in CST. The existing build tool must **not** be taken as proof of an independent finite array: it has no post-apply geometry, boundary and excitation readback or verified result classification. |
| Solver / sweep | One unit-cell solve succeeded, with CST reusing result run IDs `0/1`. Successful stop and automatic abort-dialog completion remain unproved; bounded sweep template is offline only. Never assign a reused run ID to a specific job without independent evidence. |

**Active blocker:** the most recent job on the tested scratch is `unknown`.
The service refuses subsequent writes, solves and sweeps on that operation. Do not mark it solved
or stopped from CST's later `SUCCESS`. Resolving it requires explicit
authorization, two live idle checks, identity/fingerprint and a verified
complete backup; `abandoned` would not mean successful termination. Do not
start another job merely to bypass this guard.

**Remaining metasurface acceptance:** (1) in an independently controlled and
backed-up scratch, prove finite-array geometry counts and positions, open
boundary and plane-wave excitation by CST readback before labeling results;
(2) separately investigate circular-basis API/readback without asserting the
failed recipe works; (3) only if solver stop has safe evidence, run a bounded
parameter sweep with job/run/result provenance. None of these is claimed
complete. Normal CST write/solve calls still require `confirm=true`, a
controlled scratch, the cross-process lock and audit.

An earlier local implementation plan (not distributed with this repository)
contained outdated test counts and pre-acceptance assumptions about solver
results and automation. Consult the README and the public acceptance summary
for implemented behavior; do not infer release acceptance from an unchecked
phase list. The published environment recipe is manual-only; a local profile
used during selected historical acceptance runs was explicitly higher risk.
