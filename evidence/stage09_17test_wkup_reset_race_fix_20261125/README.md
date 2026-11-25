# 17-test WKUP reset-race fix

Date: 2026-11-25

## Diagnosis

The original 17-test Full completed 1000 submissions: 997 accepted and 3 failed. All three failures were in `aon_timer_stress_all_with_rand_reset` (run IDs 307, 547, and 918) and reported a WKUP threshold readback mismatch. A randomized reset can interrupt configuration after the TL write returns but before the AON-domain threshold has settled. The reset clears the DUT register while the sequence still holds the pre-reset randomized threshold, so the strict readback check compares reset value zero against stale stimulus.

This is a UVM sequence/readback race around reset. It does not indicate a VCS or URG crash. The original Full result is preserved unchanged: 4137/4507 groups (91.7905%), 228817.91 simulator CPU seconds across all attempts, and 26807.94 seconds wall time.

## Repair

`08_两层UCB在线复现/tools/aon_timer_wkup_reset_race_v31.patch` adds a five-AON-clock settle fence after threshold writes and a reset-generation guard around strict WKUP readback. When reset changes the generation during configuration, the sequence exits that configuration path and leaves reset-value checks to the existing reset CSR audit. If no reset intervenes, both strict count and threshold readbacks remain enabled. Smoke, jump, and prescaler sequences also stop before enabling a partially configured timer.

Patch SHA-256: `92ba475b04ca930106dbc105972f6bd8ab729b8443939db54e654ed723e00ee8`

The patch passed `patch --dry-run` against the frozen V30 source. A separate VCS build compiled with the patch; its `simv` SHA-256 is `8b0fd96293a6f85dc1fd3984edf1cdd68f16e6482802c85d784b3722cb0b2760`.

## Verification

- Wait-only repair, seed 307: still failed with one UVM error. This showed that a fixed delay alone does not handle reset interrupting a readback.
- Wait-only repair, seed 547: passed; VCS/URG return codes 0, 0 UVM errors and fatals, 272/4525 groups; wall 707.232 seconds, simulator CPU 675.66 seconds.
- Wait-only repair, seed 918: passed; VCS/URG return codes 0, 0 UVM errors and fatals, 182/4525 groups; wall 72.727 seconds, simulator CPU 68.78 seconds.
- Final reset-generation repair, seed 307: passed; VCS/URG return codes 0, 0 UVM errors and fatals, 332/4525 groups; wall 477.099 seconds, simulator CPU 455.93 seconds. The log records reset generation `10 -> 11` and confirms the interrupted readback was skipped for the reset audit.

Final-patch seeds 547 and 918 were not completed. A seed 547 attempt was stopped after it began competing for CPU with the active formal NoIncrementalRefill Full, which would have distorted that method's wall-time measurement. The partial attempt is excluded. An earlier direct launch lacked the required `dv_root` environment variable and stopped at 0 ps; it is also excluded. The 17-test Full was not rerun, so its original 3 failures remain part of that historical result.

## Server evidence

Raw VCS logs, URG reports, VDBs, and the partial attempt remain on the school server under:

- `scratch/stage09_17test_repair_20261125/`
- `scratch/stage09_17test_repair_v2_20261125/`

The final passing seed 307 `run.log` SHA-256 is `91396ca205d72274394c3c062163e5711958c7b68c6b4be79305af0703cbe08b`; its `result.json` SHA-256 is `4f14326584971ad965dde77ed1b84439f2b71dc5fb5659d00e1d70a203ee2d28`.
