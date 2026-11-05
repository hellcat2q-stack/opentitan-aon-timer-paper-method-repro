# 阶段 08：两层 UCB 在线复现

> 最新补充实验：2026-11-05 完成 VCS 定向 Jump V15 smoke（30 次）与 Full（500 次）。该实验修正了 URG 自动 bin 行序变化造成的特征映射错位；500 次全部成功，覆盖并集 1062/4507（23.56%）。详细方法、限制和脱敏证据见 [VCS 定向覆盖修正记录](VCS定向覆盖修正与当前进度_20261105.md) 及下方 V15 证据目录。此补充结果不覆盖本页记录的 1000 次原始在线 UCB 实验，也不等同于论文的 Verisim Bayesian 闭环。

**状态：已完成并通过审计（2026-11-02）。** 在学校服务器上以 VCS/URG 真实执行 10 次 smoke 和 1000 次 Full 在线补位实验。结果为本项目的现场复现数据，不是论文原始结果。

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
