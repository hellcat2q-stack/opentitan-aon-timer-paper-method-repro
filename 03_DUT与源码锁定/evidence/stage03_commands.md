# 阶段 03 服务器命令（脱敏）

服务器根目录用 `$ROOT` 表示；实际根目录只保留在服务器。兼容依赖在服务器 `runtime/stage03_compat`，不改动目标源码。

```bash
export PATH="$ROOT/runtime/stage03_compat/bin:$ROOT/../opentitan_aon_timer_vcs_repro/.venv/bin:$PATH"
export PYTHONPATH="$ROOT/runtime/stage03_compat/py:$ROOT/runtime/stage03_compat/src/fusesoc-ot-0.5.dev0:$ROOT/runtime/stage03_compat/src/edalize-0.4.0"

dvsim "$ROOT/src/opentitan/hw/ip/aon_timer/dv/aon_timer_sim_cfg.hjson" \
  --proj-root "$ROOT/src/opentitan" \
  --scratch-root "$ROOT/scratch/03_target_build_clean_<UTC>" \
  --branch stage03-clean-build --local --max-parallel 1 \
  --build-only --build-timeout-mins 30 --fixed-seed 42 -i aon_timer_smoke

dvsim "$ROOT/src/opentitan/hw/ip/aon_timer/dv/aon_timer_sim_cfg.hjson" \
  --proj-root "$ROOT/src/opentitan" \
  --scratch-root "$ROOT/scratch/03_coverage_smoke_<UTC>" \
  --branch stage03-coverage-smoke --local --max-parallel 1 \
  --run-timeout-mins 10 --cov --fixed-seed 42 -i aon_timer_smoke

urg -lca -full64 +urg+lic+wait -metric group -show tests \
  -group ratio -group lrm_bin_name -group instcov_for_score \
  -group maxmissing 100000 -dir <single-run>/coverage/default.vdb \
  -format text -report <run>/urg_direct_no_exclusions
```

The four untracked `dv/cov/*.el` files were deliberately omitted from the final URG command because they are not part of the locked revision.
