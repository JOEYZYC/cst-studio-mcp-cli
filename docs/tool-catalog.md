# Tool catalog

| Tool | Risk | Live CST | Write lock | Status |
|---|---|---:|---:|---|
| `inspect_status` | read | no | no | implemented |
| `inspect_list_results` | read | no | no | implemented |
| `inspect_read_saved_result` | read | no | no | implemented |
| `inspect_search_help` | read | no | no | implemented |
| `inspect_list_instances` | read | optional | no | implemented |
| `inspect_connect` | read | yes | no | implemented |
| `inspect_disconnect` | read | yes | no | implemented |
| `inspect_project_info` | read | yes | no | implemented |
| `inspect_model_tree` | read | yes | no | implemented |
| `inspect_list_parameters` | read | yes | no | implemented |
| `inspect_floquet_info` | read | yes | no | TE/TM mode names and linear basis read live; phi-independent flag has no getter |
| `inspect_list_boundaries` | read | yes | no | x/y/z and periodic scan theta/phi/direction live accepted |
| `common_prepare_scratch` | write | no | no | implemented |
| `common_create_primitive` | write | yes | yes | fixed template; live syntax not accepted |
| `common_set_frequency_range` | write | yes | yes | fixed template; live syntax not accepted |
| `common_set_boundary` | write | yes | yes | fixed template; live syntax not accepted |
| `common_add_monitor` | write | yes | yes | fixed template; live syntax not accepted |
| `common_define_material` | write | yes | yes | fixed template; live syntax not accepted |
| `common_assign_material` | write | yes | yes | fixed template; live syntax not accepted |
| `common_boolean` | write | yes | yes | fixed template; live syntax not accepted |
| `common_add_port` | write | yes | yes | fixed template; live syntax not accepted |
| `common_set_parameter` | write | yes | yes | optional full rebuild + theta/phi live readback accepted |
| `common_save_project` | write | yes | yes | confirmed save/reopen of the controlled unit-cell scan accepted |
| `metasurface_extract_rta` | read | no | no | implemented |
| `metasurface_extract_pcr` | read | no | no | implemented; explicit channels |
| `metasurface_set_floquet_modes` | write | yes | yes | History write/readback 2→3→2 live accepted |
| `metasurface_set_incidence_angle` | write | yes | yes | atomic theta/phi rebuild + scan getter (0,0)→(5,10)→(0,0) live accepted |
| `metasurface_set_polarization_basis` | write | yes | yes | fixed History + rollback; two circular live attempts failed readback, not accepted |
| `antenna_plan_patch` | read | no | no | offline plan |
| `antenna_create_patch` | write | yes | yes | fixed recipe; live syntax not accepted |
| `metasurface_plan_finite_array` | read | no | no | offline plan |
| `metasurface_build_finite_array` | write | yes | yes | documented Transform/PlaneWave recipe; live syntax not accepted |
| `solve_start` | solve | yes | job-held | one controlled unit-cell success accepted; confirm required |
| `solve_status` | read | yes | no | live RUNNING→SUCCESS accepted for first job; cross-process/unknown jobs are not inferred complete |
| `solve_stop` | solve | yes | job-held | exact Yes handler packaged; age/modal/current FD log gates offline-tested; final live call was refused at age 2 s (no abort sent), successful-stop acceptance pending |
| `solve_abandon_unknown` | write | yes | custom | live idle + full-backup/hash check; unknown job audited as abandoned, never success |
| `export_csv` | export | no | no | scratch result CSVs saved in operation artifacts |
| `export_report` | export | no | no | implemented; one saved result |
| `export_touchstone` | export | no | no | 1002-point post-solve `.s2p` with saved 376.7303-ohm ZRef; THz→GHz |
| `export_metasurface_report` | export | no | no | post-solve explicit R/T/A/PCR HTML in operation artifacts |

OpenCode MCP integration is intentionally deferred until live CST acceptance. The table's
"implemented" status means registered and offline-tested unless a live limitation is stated;
it does not mean every CST History template has passed against 2026.2.
