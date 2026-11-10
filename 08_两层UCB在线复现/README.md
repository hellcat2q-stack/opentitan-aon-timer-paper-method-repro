# 阶段 08：两层 UCB 在线复现

> 2026-11-11 WKUP 失败修复：V30 已通过 5 个真实失败 seed、故障注入、preflight 和 30/30 smoke（0 失败，937/4507），69-VDB 独立 URG 合并身份核对通过。新的 1000 次 Full 已于 05:37 启动，尚未完成。修复涉及复位子进程作用域、配置 CDC 同步、分频首周期上界及启动/收尾流程。真实回放还揭示 V23/V24 原脚本把 0 ps 退出误判为通过，原通过声明撤回；V22 原结果及各版本诊断均保留。见 [V30 修复与重跑记录](v30_WKUP复位与CDC写入修复_20261111.md)。

> 2026-11-10 v22：修正配置 bin 区间目标映射、扩大未定向 jump 的安全参数范围，并修复零阈值约束与目标池更新。1000 次 UCB Full 配对完成：v20 为 1739/4507（38.5844%），v22 为 4105/4507（91.0805%），增加 2366 个 bin（52.4961 个百分点）。两组事件/向量/奖励审计及独立 URG bin 身份复核均通过；v22 有 4 次 scoreboard 失败按预算计入，v20 零失败。完整数据见 [最终配对报告](evidence/stage08_v20_v22_ucb_pair_full1000_20261110/README.md) 和 [v22 改进记录](v22参数范围与目标映射_UCB对照_20261110.md)。

> 2026-11-09 独立复核更正：URG 直接合并 V19 的初始 39 条语料与 1000 次在线运行，详细 bin 覆盖为 **1191/4507（26.4256%）**；此前 Python 记录的 832/4507（18.4602%）存在映射漏计。还查出实际编译 scoreboard 读取 wakeup count 高位时使用了低位寄存器。详见 [低覆盖原因与改进优先级](低覆盖原因与独立URG复核_20261109.md)。现有历史摘要和审计原样保留，算法收益比较需在统一解析后重做。

> 2026-11-10 v20 修复验证：改用 VCS cumulative XML bin ordinal/cross tuple 重建 39 条初始矩阵，修正 illegal cross tuple 展开，并在独立源码/build 副本修复 scoreboard 的 wakeup 高 32 位读取。30 次 VCS smoke 全部通过，审计通过，最终 561/4507（12.4473%），目标 steering 11/11 命中；这是新 bin identity 下的 smoke 数据，不是 1000 次 Full。由于 smoke 中 10 次选中 stress-all、实际耗时约 40 分钟且服务器负载较高，本轮未启动 Full。详见 [v20 修复与 smoke 报告](v20解析与scoreboard修复_20261110.md) 和 [v20 摘要](evidence/stage08_v20_smoke30_20261110/summary.json)。

> 最新补充实验：2026-11-09 V19 混合序列两层 UCB Full 已完成，1000/1000 成功、0 失败、审计通过，覆盖 832/4507（18.4602%），比初始并集新增 599 个 bin。序列使用量为 jump 470、prescaler 179、smoke 181、stress-all 170；同时修正了 VCS/URG bin 映射并对兼容序列施加定向约束。详见 [V19 分析与最终结果](改进版分析与进度.md#v19-full-1000-最终结果2026-11-09) 和 [Full 摘要](evidence/stage08_vcs_paper_ucb_full1000_20261109_v19/summary.json)。该结果保留作者衍生的惩罚/互信息与两层调度结构，不代表已经严格复现论文或对齐学长的 70% 指标。

> 此前补充实验：2026-11-05 VCS 定向 Jump V15 smoke（30 次）和 V16 Full（1000 次）均完成并通过独立审计。V16 为独立 Full，1000/1000 成功、0 失败，覆盖并集 1134/4507（25.16%）。详见 [VCS 定向覆盖修正记录](VCS定向覆盖修正与当前进度_20261105.md) 和 `evidence/stage08_vcs_steered_full1000_v16_20261105/`。它不覆盖本页记录的 1000 次原始在线 UCB 实验，也不等同于论文的 Verisim Bayesian 闭环。

**最终状态（2026-11-10）：v20 与 v22 均完成 1000 次并通过独立事件/向量/奖励审计和原始 VDB URG 合并身份复核。** v20 为 1739/4507（38.5844%），v22 为 4105/4507（91.0805%），差值 +2366 bins（+52.4961 个百分点）。详见[配对结果和审计](evidence/stage08_v20_v22_ucb_pair_full1000_20261110/README.md)。这是单 seed 的项目结果，不代表论文原始数据，也不提供统计显著性结论。

## 方法与执行

使用师兄提供的 `generic_adaptive_runner_ucb_continuous_refill_norepeat_poolmi.py`，保留其两层 target-cluster/sequence UCB、MI、dynamic residual、runtime penalty、防重复和 continuous-refill 策略。`tools/run_vcs_ucb.py` 只适配 VCS/URG worker、阶段 06 coverage 解析、初始 CSV 字段及哈希审计，不修改原算法源码。

Full 使用同一阶段 06 初始语料（39 个接受的历史向量、4507-bin 分母、初始并集 233）、预注册本地 seed 42、1000 次提交、10 workers、logical batch size 10。每次 worker 完成后立即反馈并补位；每个提交最多尝试一次，失败尝试计入总预算且不获得覆盖奖励。22 次提交出现 UVM_ERROR，被保留并计入预算；其余 978 次通过严格 VCS/UVM/URG 检查。完整数据库、可执行文件、许可证信息及原始日志保留在学校服务器。

## 现场结果

Full 最终覆盖并集为 **296/4507（6.5676%）**，相对初始并集增加 63 bins。完成 1000/1000 次提交，22 次失败、978 次接受，无重试；最大并发 10。累计仿真 CPU 时间为 114,186.95 秒（包含失败尝试），在线 wall time 为 16,454.29 秒。seed 42 是项目本地预注册值，不是论文公开的 seed。

独立审计通过：1000 个 seed 与预注册列表一致；覆盖向量与逐次 URG 计数一致；每次奖励等于累计并集的增量；事件哈希链完整；990 次补位发生在反馈之后；被接受运行均有 UVM PASS 且无 UVM_ERROR/UVM_FATAL。审计沿用阶段 06 冻结的 URG prefix/行序 bin 身份口径，因此不构成对物理 bin 身份的额外证明。

## 证据

- Full 脱敏结果：`evidence/stage08_full_20261102_v1/`，包括 `summary.json`、`audit.json`、逐次事件、逐次覆盖向量、覆盖曲线和 SHA-256 清单。
- Smoke 脱敏结果：`evidence/stage08_smoke_20261102_v1/`，独立于 Full。
- `evidence/checkpoint_20261102_v1/` 是 03:16 UTC 的历史现场快照，记录当时 smoke 仍在运行的状态；Full 最终结果以以上脱敏证据为准。

`coverage_curve.png` 展示本地实测的 Full 覆盖变化，不含论文结果。论文表 II 的参考结果和本次现场结果分开保存；阶段 09 的对照/消融实验尚未开始。
