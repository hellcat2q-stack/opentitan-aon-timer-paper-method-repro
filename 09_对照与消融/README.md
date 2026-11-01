# 阶段 09：对照与消融

**状态：待开始。** 本文件是新项目的执行边界，不代表该阶段已经运行。

## 目标

在完全相同的初始语料、manifest、预算、worker 和 seed 下运行论文 AON Timer 的对照矩阵。

## 执行内容

- RandomSelection：使用 `generic_parallel_test.py`。
- NoIncrementalRefill：批次同步补位，其他组件不变。
- NoRuntimePenalty：去掉 runtime-aware penalty。
- SequenceUCBOnly：固定/取消 cluster-level UCB，只保留 sequence UCB。
- ClusterUCBOnly：固定/取消 sequence-level UCB，只保留 cluster UCB。
- 每个方法先 smoke，再完整 1000 submissions；失败和重试不改预算口径。

## 验收产物

六种方法的原始 manifest、逐次 coverage、runtime/walltime、最终表和曲线；不使用 Bayes 训练结果。

## 局限

如果工具、许可证、作者输入或 AON Timer sequence 不可用，必须记录为阻碍并停止推进，不用旧项目或 UART 结果填补。
