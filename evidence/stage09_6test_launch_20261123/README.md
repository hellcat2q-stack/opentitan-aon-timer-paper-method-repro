# Six-test experiment: verified launch

Full completed an independent 30/30 smoke with zero failures. Event/vector/reward checks, original UVM-log checks, frozen-input comparison, and the independent URG union audit all passed. Full's formal 1000-attempt run was then observed running on the school server.

The exact observation and progress are in launch_snapshot.json. This is launch evidence, not a final six-method result. The initial URG audit correctly stopped because two original Stage05 VDB directories had not been linked into the new root. Their links were added and all 39 frozen XML hashes verified before resuming the audit. The same 30 smoke simulations were retained, with zero simulation reruns or budget/parameter changes. Details are in initial_vdb_path_recovery.json and resume_launch_record.json. The other five methods run sequentially, each after its own 30-attempt smoke and audits. All methods retain seed 42, 10 workers, the 39-run initial corpus and 4507-bin denominator, with steering disabled and no retries. Full smoke evidence is in ../stage09_6test_Full_smoke30_20261123/.

The separate six-test catalog retains smoke, prescaler, jump, stress_all, interrupts and CSR read/write. No old online coverage is fed into this run. Original logs, databases and paths remain on the server.
