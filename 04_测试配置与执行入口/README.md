# 阶段 04：测试配置与执行入口

**状态：已完成（2026-11-01）。** 本阶段在锁定的 OpenTitan revision 上盘点了 AON Timer DV 测试入口，建立 VCS/DVSIM 参数配置，并运行四条核心 sequence 和单次完整 DVSIM smoke。

## 固定输入与目标

- OpenTitan revision：`9f20940d494a223cc950a5b98f748fb28109d458`。
- DVSIM 配置：`hw/ip/aon_timer/dv/aon_timer_sim_cfg.hjson`。
- UVM test：`aon_timer_base_test`；默认 reseed 为 50；配置默认运行参数包含 `+cdc_instrumentation_enabled=1`。
- 仿真工具：VCS P-2019.06-SP1；覆盖报告工具：URG P-2019.06-SP1。

## 测试入口盘点

`dvsim --list tests regressions` 实际返回 17 个 test 和 9 个 regression。四条阶段 04 核心 sequence 为：

- `aon_timer_smoke_vseq`
- `aon_timer_prescaler_vseq`
- `aon_timer_jump_vseq`
- `aon_timer_stress_all_vseq`

完整 test/regression 名单、默认参数和来源记录在 [sequence inventory](evidence/stage04_sequence_inventory.json)。盘点清单不是“全部测试都已运行”的声明。

## 执行结果

独立 DVSIM build+run+coverage smoke 使用 seed 411，返回码 0；`aon_timer_smoke` 为 1/1。该运行的 DVSIM dashboard 为 total coverage 55.26%、functional coverage 1.13%。

四条核心 sequence 使用已经构建的 `simv` 单独运行；每条运行均配置 CDC instrumentation、覆盖采集、独立 seed 和 `UVM_TEST_SEQ`。VCS、URG 均返回 0，UVM 错误和 fatal 计数均为 0，并记录 `TEST PASSED CHECKS`。

| DVSIM test | UVM sequence | seed | group bins hit | URG group score |
| --- | --- | ---: | ---: | ---: |
| `aon_timer_smoke` | `aon_timer_smoke_vseq` | 431 | 45/4525 | 0.99% |
| `aon_timer_prescaler` | `aon_timer_prescaler_vseq` | 432 | 46/4525 | 1.02% |
| `aon_timer_jump` | `aon_timer_jump_vseq` | 433 | 56/4525 | 1.24% |
| `aon_timer_stress_all` | `aon_timer_stress_all_vseq` | 434 | 188/4525 | 4.15% |

这些是四次独立单测的 URG group 统计，只证明序列和覆盖输出链路可用。4525 不是阶段 06 冻结后的正式分母；这些分数不是论文表 II 结果，也不能与不同运行直接求和。

seed 401、402、403 的 DVSIM 参数传递测试在 UVM 端通过，并观察到 seed、sequence、CDC 和 coverage 参数。但复制 `simv` 后的 DVSIM 二次 `cov_report` 因缺少完整 design metadata 报 `URG-CR`，最终 DVSIM 返回码为 1。因此这三次只作为参数传递证据，不计入完整流程通过。完整摘要见 [参数和执行结果](evidence/stage04_parameter_runs.json)。

## 配置和证据

- [VCS/DVSIM 配置](../configs/aon_timer_config.yaml)：使用路径占位符，不包含服务器私有绝对路径。
- [可复现命令与判定](evidence/stage04_commands.md)。
- [服务器文件 SHA-256 索引](evidence/stage04_server_hash_index.txt)。
- [实施记录](实施记录.md)。

完整 simv、VDB、URG 目录、许可证信息和仿真原始日志仅留在学校服务器项目隔离目录；GitHub 只提交脱敏配置、摘要和哈希。

## 局限与下一步

当前只有四个单 seed sequence 入口检查和一个独立 smoke；没有运行完整回归，没有构建阶段 05 初始语料，也没有冻结 coverage bin 分母。下一阶段按已审核的 sequence 池和预算采集初始语料，记录每次运行与原始覆盖证据，再进入 coverage 转换步骤。
