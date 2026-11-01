# 阶段 10：结果复核与论文对比

**状态：待开始。** 本文件是新项目的执行边界，不代表该阶段已经运行。

## 目标

独立检查所有结果是否真的满足论文协议，并形成可审计差异报告。

## 执行内容

- 重新计算 bin 分母、最终覆盖、累计 runtime、walltime 和 late-stage 增益。
- 检查所有方法是否同一 initial corpus、H、P、logical batch、seed 和 failure policy。
- 对照论文表 II，报告绝对差异和可归因偏差；不强行解释或伪造缺失数据。
- 生成最终图、CSV、manifest、hash index 和复现实验说明。

## 验收产物

final verification、论文差异表、结果归档和 GitHub 交付；结论只基于本项目真实证据。

## 局限

如果工具、许可证、作者输入或 AON Timer sequence 不可用，必须记录为阻碍并停止推进，不用旧项目或 UART 结果填补。
