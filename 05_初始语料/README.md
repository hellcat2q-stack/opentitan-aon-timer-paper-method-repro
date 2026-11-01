# 阶段 05：初始语料

**状态：待开始。** 本文件是新项目的执行边界，不代表该阶段已经运行。

## 目标

遵循师兄流程，为每个可用序列运行 10 次初始语料，保存每次 seed、runtime、退出码和原始覆盖报告。

## 执行内容

- 使用 `algorithm_source/sequence_based_parallel_test.py` 或等价保留逻辑。
- 预注册初始语料规模、并发、base seed 和每次 seed 派生规则。
- 初始语料阶段不使用自适应选择。
- 失败、超时、许可证等待单独计数，不静默重试。

## 验收产物

initial run manifest、原始报告索引、runtime 表和失败清单；初始语料是历史输入，不是正式 UCB 奖励。

## 局限

如果工具、许可证、作者输入或 AON Timer sequence 不可用，必须记录为阻碍并停止推进，不用旧项目或 UART 结果填补。
