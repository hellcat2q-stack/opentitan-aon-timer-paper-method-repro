# 阶段 04 服务器命令与判定

服务器项目根目录在下文统一写作 `$ROOT`；实际绝对路径、许可证值、simv、VDB 和完整日志不进入仓库。

## 1. 盘点入口

```bash
export PATH="$ROOT/runtime/stage03_compat/bin:$ROOT/../opentitan_aon_timer_vcs_repro/.venv/bin:$PATH"
export PYTHONPATH="$ROOT/runtime/stage03_compat/py:$ROOT/runtime/stage03_compat/src/fusesoc-ot-0.5.dev0:$ROOT/runtime/stage03_compat/src/edalize-0.4.0"
dvsim "$ROOT/src/opentitan/hw/ip/aon_timer/dv/aon_timer_sim_cfg.hjson" \
  --proj-root "$ROOT/src/opentitan" --list tests regressions
```

结果是 17 个 test 和 9 个 regression；清单见 `stage04_sequence_inventory.json`。

## 2. 正式 DVSIM smoke 入口

```bash
dvsim "$ROOT/src/opentitan/hw/ip/aon_timer/dv/aon_timer_sim_cfg.hjson" \
  --proj-root "$ROOT/src/opentitan" \
  --scratch-root "$ROOT/scratch/04_entry_smoke_<UTC>" \
  --branch stage04-entry-smoke --local --max-parallel 1 \
  --run-timeout-mins 10 --cov --fixed-seed 411 -i aon_timer_smoke
```

该独立 build+run+coverage 流程返回码为 0，DVSIM dashboard 为 `aon_timer_smoke` 1/1；只作为入口闭环证据。

## 3. 直接 simv 序列验证

先设置运行时变量；`dv_root` 必须是 OpenTitan 的 `hw/dv` 目录，不能只指向源码根目录：

```bash
export dv_root="$ROOT/src/opentitan/hw/dv"
export SIMULATOR=vcs
export WAVES=none
```

然后对四条序列分别执行配置中的 `direct_simv` 命令，并将标准输入重定向为 `/dev/null`。每条命令都使用 `+cdc_instrumentation_enabled=1`、`+en_cov=1`、`+ntb_random_seed=<seed>`、`+UVM_TESTNAME=aon_timer_base_test` 和对应的 `+UVM_TEST_SEQ`。每条命令之后执行配置中的 `urg` 命令。

| 运行 | seed | sequence | VCS | URG | covered/expected | group score |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
| `04_valid_smoke_20261101T431Z` | 431 | `aon_timer_smoke_vseq` | 0 | 0 | 45/4525 | 0.99% |
| `04_valid_prescaler_20261101T432Z` | 432 | `aon_timer_prescaler_vseq` | 0 | 0 | 46/4525 | 1.02% |
| `04_valid_jump_20261101T433Z` | 433 | `aon_timer_jump_vseq` | 0 | 0 | 56/4525 | 1.24% |
| `04_valid_stress_all_20261101T434Z` | 434 | `aon_timer_stress_all_vseq` | 0 | 0 | 188/4525 | 4.15% |

四条日志均包含 `UVM_ERROR : 0`、`UVM_FATAL : 0` 和 `TEST PASSED CHECKS`。这些分数是单次独立 URG group 统计，不是论文最终 coverage。

## 4. 参数传递的边界

seed 401、402、403 的 DVSIM 参数传递 run 均观察到 seed、sequence、CDC 和 coverage 参数，UVM 均通过；但复制已有 simv 后的 DVSIM 二次 `cov_report` 因缺少完整 design metadata 返回 `URG-CR`，所以在证据中标为 `parameter_transfer_only`，不标作 DVSIM 全流程通过。

## 5. 失败尝试的排除

`04_direct_*` 旧运行未设置正确的 `dv_root`，不能作为证据；它们不会写入阶段 04 的通过统计。阶段 04 只使用 `04_valid_*` 和独立的 `04_entry_smoke_*`。
