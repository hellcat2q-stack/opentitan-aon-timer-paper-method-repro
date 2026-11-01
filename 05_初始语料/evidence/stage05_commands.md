# 阶段 05 脱敏执行命令

服务器项目根目录写作 `$ROOT`；完整绝对路径、许可证信息、simv、VDB、URG 原始目录和完整日志仅留在服务器。

## 预注册参数

```text
sequences = [
  (aon_timer_smoke, aon_timer_smoke_vseq),
  (aon_timer_prescaler, aon_timer_prescaler_vseq),
  (aon_timer_jump, aon_timer_jump_vseq),
  (aon_timer_stress_all, aon_timer_stress_all_vseq),
]
runs_per_sequence = 10
base_seed = 505
seed_rule = random.Random(505).randint(1, 2**31-1), sequence-major job order
parallel_workers = 4
host_timeout_per_sim_or_urg = 20 minutes
adaptive_selection = false
```

## 执行

```bash
export PATH="$ROOT/runtime/stage03_compat/bin:$ROOT/../opentitan_aon_timer_vcs_repro/.venv/bin:$PATH"
export PYTHONPATH="$ROOT/runtime/stage03_compat/py:$ROOT/runtime/stage03_compat/src/fusesoc-ot-0.5.dev0:$ROOT/runtime/stage03_compat/src/edalize-0.4.0"
"$ROOT/.venv/bin/python" "$ROOT/runtime/stage05/run_aon_timer_initial_corpus.py" \
  --simv "$ROOT/scratch/04_entry_smoke_20261101T095206Z/stage04-entry-smoke/aon_timer-sim-vcs/default/simv" \
  --dv-root "$ROOT/src/opentitan/hw/dv" \
  --result-dir "<ROOT>/runs/stage05_initial_corpus_<NEW_RUN_TAG>" \
  --runs-per-sequence 10 --base-seed 505 --parallel 4 --timeout-mins 20
```

单次命令明确传入：

```text
+cdc_instrumentation_enabled=1
+ntb_random_seed=<seed>
+UVM_TESTNAME=aon_timer_base_test
+UVM_TEST_SEQ=<sequence>
+en_cov=1
-cm line+cond+fsm+tgl+branch+assert
```

每次 run 之后单独执行 URG，写入 `urg_report/`；失败不自动重试。

## 判定

- 40/40 VCS 返回 0。
- 40/40 URG 返回 0 并生成 dashboard。
- 35/40 UVM `TEST PASSED CHECKS`；runner 总返回码为 1，因为仍有 5 条 UVM 失败。
- 5/40 stress-all 在 UVM `200000000000 ps` 触发 `[PH_TIMEOUT]`；宿主侧 timeout 为 0。
- 成功语料必须同时满足 VCS=0、URG=0、`TEST PASSED CHECKS`、`UVM_ERROR=0` 和 `UVM_FATAL=0`。失败运行的部分 VDB 只能用于诊断。

具体失败 seed、run index、runtime 和相对目录见 `stage05_failures.json`；每个服务器 run 的命令、日志、返回码、VDB 成员、URG 文件和 result JSON 都有 SHA-256 索引。
