# 阶段 05：初始语料

**状态：执行完成，含已记录的 UVM 失败（2026-11-01）。** 按预注册协议运行 4 条核心 sequence、每条 10 次，共 40 次尝试；不做自适应选择、不自动重试。

## 预注册设置

- 序列：`aon_timer_smoke_vseq`、`aon_timer_prescaler_vseq`、`aon_timer_jump_vseq`、`aon_timer_stress_all_vseq`。
- 次数：每条 10 次，共 40 次。
- 本项目 base seed：505。此值是本地预注册输入，不是论文作者公开的 seed。
- 派生方式：`random.Random(505).randint(1, 2**31-1)`，按 sequence-major 顺序预先生成；manifest 保存每个实际 seed。
- 并发：4 个 worker；每次仿真和 URG 的宿主超时上限为 20 分钟。
- 运行入口：阶段 04 构建的 VCS `simv`，传入独立 `+ntb_random_seed`、`+UVM_TESTNAME=aon_timer_base_test`、对应 `+UVM_TEST_SEQ`、`+cdc_instrumentation_enabled=1`、`+en_cov=1` 和 line/cond/fsm/tgl/branch/assert coverage。
- 不进行自适应选择，不合并不同 run 的 VDB。每次 run 单独输出 VDB 和 URG 文本报告。

协议和 40 条运行 manifest 已分别保存为 [stage05_protocol.json](evidence/stage05_protocol.json) 和 [stage05_run_manifest.json](evidence/stage05_run_manifest.json)。执行入口为 [run_aon_timer_initial_corpus.py](tools/run_aon_timer_initial_corpus.py)，脱敏命令见 [stage05_commands.md](evidence/stage05_commands.md)。

## 结果

VCS 返回码为 0 的 40/40 次都生成了 URG 报告，URG 返回码也是 40/40 为 0。UVM 有 35/40 次通过；其余 5 次均来自 `aon_timer_stress_all_vseq`，触发 UVM `[PH_TIMEOUT]`，在仿真时间 `200000000000 ps`（200 ms）处结束。宿主 runner 的 20 分钟超时计数为 0；没有许可证失败，也没有静默重试。VCS 的 0 返回码不能覆盖日志里的 UVM fatal，故这 5 次被保留为失败记录。

| DVSIM test / sequence | 尝试 | UVM PASS | UVM 失败 | 累积 wall time | 每次 wall time 中位数 |
| --- | ---: | ---: | ---: | ---: | ---: |
| `aon_timer_smoke` / `aon_timer_smoke_vseq` | 10 | 10 | 0 | 38.053 s | 3.798 s |
| `aon_timer_prescaler` / `aon_timer_prescaler_vseq` | 10 | 10 | 0 | 912.116 s | 102.545 s |
| `aon_timer_jump` / `aon_timer_jump_vseq` | 10 | 10 | 0 | 43.022 s | 3.682 s |
| `aon_timer_stress_all` / `aon_timer_stress_all_vseq` | 10 | 5 | 5 | 3455.478 s | 204.132 s |

运行清单中的 4525 group bins 是各单次 URG 报告的现场分母，仍属阶段 06 冻结前的暂定口径。失败运行的 VDB/URG 仅作调查证据，其部分覆盖不得当作成功语料输入。详细失败和分类见 [stage05_failures.json](evidence/stage05_failures.json)；按 run、VDB 成员和 URG 文件生成的 SHA-256 清单见 [stage05_server_hash_index.txt](evidence/stage05_server_hash_index.txt)。总体摘要见 [stage05_summary.json](evidence/stage05_summary.json)。

## 文件与边界

- `tools/run_aon_timer_initial_corpus.py`：在 VCS/DVSIM 环境运行固定语料并记录 seed、wall time、simulator CPU time、退出码、UVM 结果、coverage 计数和逐文件 SHA-256。
- `algorithm_source/sequence_based_parallel_test.py`：师兄提供的原始 runner 仅作为方法来源保留。它把命令写死为旧 Verisim 入口，本阶段改用等价的 AON Timer VCS runner，没有执行 UART/Verisim 配置。
- `evidence/`：只包含不带服务器绝对路径的 protocol、manifest、失败摘要、runtime 和 hash 索引。
- 40 个 run 的完整日志、VDB、URG 报告和 VCS 仿真文件全部留在学校服务器 `$ROOT/runs/stage05_initial_corpus_20261101T/`。

这些初始运行是后续转换分析的历史输入，不是论文表 II 结果或 UCB 奖励。阶段 06 应保留每次运行的 PASS/FAIL 标记，将 5 个 PH_TIMEOUT run 从成功 coverage 语料中排除，并单独冻结正式 bin manifest。
