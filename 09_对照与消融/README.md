# 阶段 09：对照与消融

**状态：RandomSelection 已完成 VCS 1000-submit；其余四个消融尚未运行。** 本文件把论文方法、现场结果和未公开参数分开记录。

## 目标

在完全相同的初始语料、manifest、预算、worker 和 seed 下运行论文 AON Timer 的对照矩阵。

## 执行内容

- RandomSelection：使用 `algorithm_source/run_vcs_random_selection.py`，从阶段 04/06 冻结的四条 AON Timer 核心序列中均匀有放回随机选择；不启用 UCB、target steering 或 Bayesian training。
- NoIncrementalRefill：批次同步补位，其他组件不变。
- NoRuntimePenalty：去掉 runtime-aware penalty。
- SequenceUCBOnly：固定/取消 cluster-level UCB，只保留 sequence UCB。
- ClusterUCBOnly：固定/取消 sequence-level UCB，只保留 cluster UCB。
- 每个方法先 smoke，再完整 1000 submissions；失败和重试不改预算口径。

## 已完成结果

RandomSelection 的 VCS 1000-submit 结果保存在服务器结果目录 `runs/stage09_random_selection_full1000_20261106`，公开脱敏证据导出到本目录 `evidence/stage09_random_selection_full1000_20261106/`。它使用 39 条初始语料、4507 个冻结 bin、seed 42、10 workers、10×100 logical batches。论文未公开完整 AON Timer sequence pool，因此四条本地冻结序列是可复核的本地设定，不宣称等同作者隐藏 pool。coverage、runtime、walltime 和独立审计详见 `summary.json`、`audit.json` 与 `sequence_selection_audit.json`。

## 验收产物

六种方法的原始 manifest、逐次 coverage、runtime/walltime、最终表和曲线；不使用 Bayes 训练结果。

## 局限

如果工具、许可证、作者输入或 AON Timer sequence 不可用，必须记录为阻碍并停止推进，不用旧项目或 UART 结果填补。
