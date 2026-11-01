# 阶段 05：初始语料

**状态：原始语料完成，timeout 参数缺陷已修复并有选择地重放（2026-11-01）。** 原始预注册语料是 4 条核心 sequence、每条 10 次，共 40 次尝试；该 manifest 和原失败记录保持不变。修正 runner 后只重放原来 5 个 timeout seed，其中 4 个 UVM PASS，另 1 个出现 UVM_ERROR。可接受的 coverage 输入是原始 35 个 PASS 加 4 个修复重放 PASS。

## 预注册设置

- 序列：`aon_timer_smoke_vseq`、`aon_timer_prescaler_vseq`、`aon_timer_jump_vseq`、`aon_timer_stress_all_vseq`。
- 次数：每条 10 次，共 40 次。
- 本项目 base seed：505。此值是本地预注册输入，不是论文作者公开的 seed。
- 派生方式：`random.Random(505).randint(1, 2**31-1)`，按 sequence-major 顺序预先生成；manifest 保存每个实际 seed。
- 原始执行并发：4 个 worker；仿真和 URG 的宿主超时上限为 20 分钟。修复重放并发为 2；stress-all 依据官方 test 配置传入 `+test_timeout_ns=10000000000`，宿主超时 180 分钟。
- 运行入口：阶段 04 构建的 VCS `simv`，传入独立 `+ntb_random_seed`、`+UVM_TESTNAME=aon_timer_base_test`、对应 `+UVM_TEST_SEQ`、`+cdc_instrumentation_enabled=1`、`+en_cov=1` 和 line/cond/fsm/tgl/branch/assert coverage。
- 不进行自适应选择，不合并不同 run 的 VDB。每次 run 单独输出 VDB 和 URG 文本报告。

协议和 40 条原始运行 manifest 已分别保存为 [stage05_protocol.json](evidence/stage05_protocol.json) 和 [stage05_run_manifest.json](evidence/stage05_run_manifest.json)。执行入口为 [run_aon_timer_initial_corpus.py](tools/run_aon_timer_initial_corpus.py)，修复重放记录见 [stage05_timeout_fix_replay.json](evidence/stage05_timeout_fix_replay.json)。

## 结果

原始运行 VCS/URG 均为 40/40 返回码 0，UVM 有 35/40 PASS；其余 5 次来自 `aon_timer_stress_all_vseq`，均在 `200000000000 ps`（200 ms）触发 `[PH_TIMEOUT]`。核对官方 `stress_all_test.hjson` 后确认 runner 漏传 `+test_timeout_ns=10000000000`，因此误用了 `dv_base_test.sv` 的 200 ms 默认值。修复后以原 seed 单独重放这 5 次，4 次通过，一次不再超时但报告了真实 UVM_ERROR（`intr_state` 检查期望 0、读回 2）；该错误仍按失败处理。原始 40 条结果没有被覆盖或删除，修复重放作为独立的补充数据记录。

| DVSIM test / sequence | 尝试 | UVM PASS | UVM 失败 | 累积 wall time | 每次 wall time 中位数 |
| --- | ---: | ---: | ---: | ---: | ---: |
| `aon_timer_smoke` / `aon_timer_smoke_vseq` | 10 | 10 | 0 | 38.053 s | 3.798 s |
| `aon_timer_prescaler` / `aon_timer_prescaler_vseq` | 10 | 10 | 0 | 912.116 s | 102.545 s |
| `aon_timer_jump` / `aon_timer_jump_vseq` | 10 | 10 | 0 | 43.022 s | 3.682 s |
| `aon_timer_stress_all` / `aon_timer_stress_all_vseq` | 10 | 5 | 5 | 3455.478 s | 204.132 s |

原始运行清单记录的 4525 是 dashboard 汇总数，仍需由阶段 06 的 bin 明细解析冻结口径。原始失败运行和修复后仍失败的重放 VDB/URG 都仅作调查证据，不纳入成功 coverage 输入。原始详细失败见 [stage05_failures.json](evidence/stage05_failures.json)；原始文件 SHA-256 索引见 [stage05_server_hash_index.txt](evidence/stage05_server_hash_index.txt)，重放独立索引为 [stage05_timeout_fix_hash_index.txt](evidence/stage05_timeout_fix_hash_index.txt)。原始摘要见 [stage05_summary.json](evidence/stage05_summary.json)。

## 文件与边界

- `tools/run_aon_timer_initial_corpus.py`：在 VCS/DVSIM 环境运行固定语料并记录 seed、wall time、simulator CPU time、退出码、UVM 结果、coverage 计数和逐文件 SHA-256。
- `algorithm_source/sequence_based_parallel_test.py`：师兄提供的原始 runner 仅作为方法来源保留。它把命令写死为旧 Verisim 入口，本阶段改用等价的 AON Timer VCS runner，没有执行 UART/Verisim 配置。
- `evidence/`：只包含不带服务器绝对路径的 protocol、manifest、失败摘要、runtime 和 hash 索引。
- 原始 40 个 run 与 5 个 timeout 修复重放的完整日志、VDB、URG 报告和 VCS 仿真文件全部留在学校服务器对应的 `runs/` 目录。

这些初始运行是后续转换分析的历史输入，不是论文表 II 结果或 UCB 奖励。阶段 06 按 UVM 状态纳入 39 个成功运行，保留 6 个失败尝试及其原始证据，并单独冻结正式 bin manifest。
